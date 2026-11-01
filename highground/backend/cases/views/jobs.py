"""Atomic job lifecycle (ADR-020): claim, release, complete and confirm."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from accounts.permissions import (
    IsCommunityMember,
    IsDisasterOfficer,
    IsNgoVolunteer,
    may_see_private_case_details,
    officer_district_q,
)
from ..models import CaseEventLog, CaseJob, CaseRecord, CaseTask
from ..serializers.cases import CaseDetailSerializer, CaseSummaryDetailSerializer
from ..serializers.decisions import CompletionDecisionSerializer


def _locked_job(pk):
    """Lock the job's case row, then the job row (the one lock order)."""
    case_id = CaseJob.objects.filter(pk=pk).values_list("case_id", flat=True).first()
    if case_id is None:
        return None, None
    case = CaseRecord.objects.select_for_update().get(pk=case_id)
    job = CaseJob.objects.select_for_update().get(pk=pk)
    return case, job


def _job_response(request, case):
    """The case as this user may now see it, with every job's state."""
    case = CaseRecord.objects.prefetch_related("jobs__claimed_by_org").get(pk=case.pk)
    serializer_class = (
        CaseDetailSerializer
        if may_see_private_case_details(request.user, case)
        else CaseSummaryDetailSerializer
    )
    return Response(serializer_class(case, context={"request": request}).data)


class AlreadyClaimed(APIException):
    status_code = 409
    default_detail = "This job has already been claimed by another organisation."


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def claim_job(request, pk):
    """Claim one type of help on a verified case for the caller's organisation.

    Two NGOs can press this in the same millisecond. Unlocked, both read
    claimed_by_org IS NULL, both believe the job is free, and the later write
    silently wins — a lost update. The row locks make the second caller wait,
    then see the truth. Different jobs on one case can go to different
    organisations (ADR-020); one job only ever has one.

    Adapted from the user-written claim_case: the same steps — lock, retry
    check before status check, save, audit row — now on the job.
    """
    from ..services import refresh_case_status

    with transaction.atomic():
        case, job = _locked_job(pk)
        if job is None:
            return Response({"detail": "Not found."}, status=404)

        if job.claimed_by_org_id is not None:
            if job.claimed_by_org_id == request.user.organization_id:
                # A retry of a claim that already succeeded: write nothing.
                return _job_response(request, case)
            raise AlreadyClaimed(f"Already claimed by {job.claimed_by_org.name}.")

        if case.status not in CaseRecord.CLAIMABLE or job.status != CaseJob.Status.OPEN:
            return Response({"detail": "Only open jobs on verified cases can be claimed."}, status=409)

        job.claimed_by_org = request.user.organization
        job.status = CaseJob.Status.CLAIMED
        job.claimed_at = timezone.now()
        job.save(update_fields=["claimed_by_org", "status", "claimed_at"])
        refresh_case_status(case)
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.CLAIMED,
            detail=f"{job.get_help_type_display()} claimed by {request.user.organization.name}.",
            created_at=timezone.now(),
        )

    from ..notifications import notify

    notify(
        case,
        CaseEventLog.EventType.CLAIMED,
        request.user,
        f"{request.user.organization.name} will be in touch about the "
        f"{job.get_help_type_display().lower()} help.",
        job=job,
    )
    return _job_response(request, case)


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def release_job(request, pk):
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response({"reason": ["Give a reason for releasing the job."]}, status=400)
    from ..services import refresh_case_status

    with transaction.atomic():
        case, job = _locked_job(pk)
        if job is None or job.claimed_by_org_id != request.user.organization_id:
            return Response({"detail": "Not found."}, status=404)
        if job.status != CaseJob.Status.CLAIMED:
            return Response(
                {"detail": "Only a claimed job whose work has not started can be released."},
                status=409,
            )
        if job.tasks.exists():
            return Response(
                {"detail": "A job with tasks needs an explicit operational handover; it cannot be returned to the public queue."},
                status=409,
            )
        organisation_name = request.user.organization.name
        job.claimed_by_org = None
        job.claimed_at = None
        job.status = CaseJob.Status.OPEN
        job.save(update_fields=["claimed_by_org", "claimed_at", "status"])
        refresh_case_status(case)
        detail = (
            f"{organisation_name} released the {job.get_help_type_display().lower()} job "
            f"back to the queue: {reason}"
        )
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.RELEASED,
            detail=detail,
            created_at=timezone.now(),
        )

    from ..notifications import notify

    notify(case, CaseEventLog.EventType.RELEASED, request.user, detail, job=job)
    return _job_response(request, case)


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def complete_job(request, pk):
    from ..services import refresh_case_status

    with transaction.atomic():
        case, job = _locked_job(pk)
        if job is None or job.claimed_by_org_id != request.user.organization_id:
            return Response({"detail": "Not found."}, status=404)
        if job.status not in {CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS}:
            return Response({"detail": "This job is not ready for completion."}, status=409)
        tasks = job.tasks.all()
        if not tasks.exists():
            return Response({"detail": "Create and complete at least one task first."}, status=409)
        if tasks.exclude(status=CaseTask.Status.DONE).exists():
            return Response(
                {"detail": "Every task must be done before requesting confirmation."},
                status=409,
            )
        job.status = CaseJob.Status.PENDING_CONFIRM
        # Waiting starts at this explicit request, not at submission or a guessed date.
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        refresh_case_status(case)
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.COMPLETION_REQUESTED,
            detail=(
                f"{request.user.organization.name} marked the {job.get_help_type_display().lower()} "
                "work complete. Please confirm the result."
            ),
            created_at=timezone.now(),
        )

    from ..notifications import notify

    notify(case, CaseEventLog.EventType.COMPLETION_REQUESTED, request.user, job=job)
    return _job_response(request, case)


@api_view(["POST"])
@permission_classes([IsCommunityMember])
def confirm_job(request, pk):
    """The household confirms one job's work, or reports it unfinished.

    The case closes only after all help is finished (refresh_case_status).
    Officer-closed work remains disputable; household-confirmed work does not.
    """
    serializer = CompletionDecisionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    decision = serializer.validated_data["decision"]
    note = serializer.validated_data["note"]
    from ..services import refresh_case_status

    with transaction.atomic():
        case, job = _locked_job(pk)
        if job is None or case.submitted_by_user_id != request.user.id:
            return Response({"detail": "Not found."}, status=404)
        may_dispute_closure = decision == "incomplete" and job.status == CaseJob.Status.CLOSED_UNCONFIRMED
        if job.status != CaseJob.Status.PENDING_CONFIRM and not may_dispute_closure:
            return Response(
                {"detail": "This job is not awaiting confirmation or available for an incomplete-work report."}, status=409
            )
        help_name = job.get_help_type_display().lower()
        if decision == "confirm":
            job.status = CaseJob.Status.DONE
            job.completed_at = timezone.now()
            event_type = CaseEventLog.EventType.CLOSED
            detail = f"The resident confirmed that the {help_name} work is complete."
        else:
            job.status = CaseJob.Status.IN_PROGRESS
            job.completed_at = None
            event_type = CaseEventLog.EventType.REOPENED
            detail = f"The resident reported incomplete {help_name} work: {note}"
        job.save(update_fields=["status", "completed_at"])
        refresh_case_status(case)
        if decision == "confirm" and case.status == CaseRecord.Status.CLOSED:
            detail += " Every type of help on this request is now finished; the request is closed."
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=event_type,
            detail=detail,
            created_at=timezone.now(),
        )

    from ..notifications import notify

    notify(case, event_type, request.user, detail, job=job)
    return _job_response(request, case)


@api_view(["GET"])
@permission_classes([IsDisasterOfficer])
def unmet_help(request):
    """Officers: types of help no organisation has taken yet.

    Open jobs on verified cases, by type of help: how many, how many
    households are Health-critical, and how long the oldest has waited. A
    priority class cannot help a household if no NGO offers the work it
    needs; this shows the district where to find more help.
    """
    from django.db.models import Count, Min, Q

    rows = (
        CaseJob.objects.filter(
            # Only this officer's district (ADR-024).
            officer_district_q(request.user, "case__"),
            status=CaseJob.Status.OPEN,
            case__status__in=CaseRecord.CLAIMABLE,
        )
        .values("help_type")
        .annotate(
            open_jobs=Count("id"),
            health_critical=Count("id", filter=Q(case__priority_class=1)),
            oldest=Min("case__created_at"),
        )
        .order_by("help_type")
    )
    labels = dict(CaseRecord.DamageCategory.choices)
    now = timezone.now()
    return Response(
        [
            {
                "help_type": row["help_type"],
                "help_type_display": labels.get(row["help_type"], row["help_type"]),
                "open_jobs": row["open_jobs"],
                "health_critical": row["health_critical"],
                "oldest_waiting_days": (now - row["oldest"]).days,
            }
            for row in rows
        ]
    )
