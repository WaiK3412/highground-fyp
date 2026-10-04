"""Officer verification and priority decisions; resident information replies."""

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from accounts.permissions import IsCommunityMember, IsDisasterOfficer
from ..models import CaseEventLog, CaseJob, CaseRecord
from ..serializers.cases import CaseDetailSerializer
from ..serializers.decisions import (
    CLOSE_OUTCOMES, CaseReplySerializer, CloseOnBehalfSerializer, PriorityOverrideSerializer,
)


@api_view(["POST"])
@permission_classes([IsDisasterOfficer])
def close_on_behalf(request, pk):
    """FR16: record an officer closure, preserving the household's dispute route."""
    serializer = CloseOnBehalfSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    from ..notifications import notify
    from ..services import refresh_case_status

    with transaction.atomic():
        # Same lock order as job confirmation; never close around unfinished help.
        case = CaseRecord.objects.select_for_update().filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        jobs = list(CaseJob.objects.select_for_update().filter(case=case).order_by("pk"))
        pending = [job for job in jobs if job.status == CaseJob.Status.PENDING_CONFIRM]
        if case.status != CaseRecord.Status.PENDING_CONFIRM or not pending:
            return Response({"detail": "This request is not awaiting household confirmation."}, status=409)
        if any(job.status not in (*CaseJob.FINISHED, CaseJob.Status.PENDING_CONFIRM) for job in jobs):
            return Response(
                {"detail": "Every job must be awaiting confirmation or finished before this request can close."},
                status=409,
            )
        for job in pending:
            job.status = CaseJob.Status.CLOSED_UNCONFIRMED
            job.save(update_fields=["status"])
        refresh_case_status(case)
        detail = (
            f"Closed by {request.user.full_name} without household confirmation "
            f"({CLOSE_OUTCOMES[data['outcome']]}): {data['note']}"
            ' You can still choose "Report incomplete work" to reopen unfinished work.'
        )
        CaseEventLog.objects.create(
            case=case, actor_user=request.user, event_type=CaseEventLog.EventType.CLOSED,
            detail=detail, created_at=timezone.now(),
        )
        # The canonical audit row also carries the household's notification text.
        transaction.on_commit(lambda: notify(case, CaseEventLog.EventType.CLOSED, request.user, detail))

    return Response(CaseDetailSerializer(case, context={"request": request}).data)


DECISIONS = {
    "verified": (CaseRecord.Status.VERIFIED, CaseEventLog.EventType.VERIFIED),
    "needs_info": (CaseRecord.Status.NEEDS_INFO, CaseEventLog.EventType.NEEDS_INFO),
    "rejected": (CaseRecord.Status.REJECTED, CaseEventLog.EventType.REJECTED),
}


@api_view(["POST"])
@permission_classes([IsDisasterOfficer])
def verify_case(request, pk):
    """Verify, request more information, or reject.

    Attributed to the officer, so no status change in the audit trail is
    anonymous.
    """
    decision = request.data.get("decision")
    if decision not in DECISIONS:
        return Response(
            {"detail": f"decision must be one of {', '.join(DECISIONS)}."}, status=400
        )

    note = (request.data.get("note") or "").strip()
    if decision in {"needs_info", "rejected"} and not note:
        return Response(
            {"detail": "A note is required when asking for more information or rejecting."},
            status=400,
        )

    with transaction.atomic():
        case = CaseRecord.objects.select_for_update().filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=404)

        if case.jobs.exclude(claimed_by_org=None).exists():
            return Response(
                {"detail": "A claimed case cannot be re-verified."}, status=409
            )

        # Duplicate review comes before verification (report §3.7.8): a
        # possible duplicate is resolved by an officer before it is classified and
        # released to NGOs. Asking for information or rejecting stays open.
        from ..duplicate_services import duplicate_verification_block

        block = duplicate_verification_block(case)
        if block and (decision == "verified" or block[0] == "case_linked_duplicate"):
            code, detail = block
            from ..models import DuplicateCaseMatch

            match_ids = []
            if code == "duplicate_review_required":
                match_ids = list(DuplicateCaseMatch.objects.filter(
                    case_b=case, status=DuplicateCaseMatch.Status.OPEN
                ).order_by("pk").values_list("pk", flat=True))
            elif code == "case_linked_duplicate":
                match_ids = list(DuplicateCaseMatch.objects.filter(
                    case_b=case, status=DuplicateCaseMatch.Status.CONFIRMED
                ).order_by("-pk").values_list("pk", flat=True)[:1])
            return Response({"code": code, "detail": detail, "duplicate_match_ids": match_ids}, status=409)

        new_status, event_type = DECISIONS[decision]
        case.status = new_status
        case.verified_by_user = request.user
        update_fields = ["status", "verified_by_user"]
        if decision != "verified" and case.priority_class is not None:
            # A class describes a verified case. Sent back or rejected, it no
            # longer has one; the event log keeps the history.
            case.priority_class = None
            case.priority_reasons = []
            update_fields += ["priority_class", "priority_reasons"]
        case.save(update_fields=update_fields)

        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=event_type,
            detail=note or f"Marked {case.get_status_display().lower()} by {request.user.full_name}.",
            created_at=timezone.now(),
        )

        # Classification happens at verification, not submission: screen 17
        # has an officer check a request before it is prioritised and released
        # to the NGO queue. Inside the transaction, so a failure undoes the
        # verification rather than leaving a verified case with no class.
        # Re-verifying (after needs_info) recomputes from the current answers.
        if decision == "verified":
            # Imported here, not at module level: services imports the models
            # this module also imports, and at import time that loop cannot
            # resolve. Inside the function it runs after both are loaded.
            from ..services import classify_case_record

            classify_case_record(case, request.user)

    from ..notifications import notify

    case.refresh_from_db()  # so a verification notification carries the class
    notify(case, event_type, request.user, note)

    return Response(CaseDetailSerializer(case, context={"request": request}).data)


REPLY_FIELDS = ("urgency", "access_level", "vulnerability_flags")


@api_view(["POST"])
@permission_classes([IsCommunityMember])
def reply_to_case(request, pk):
    """FR5: answer a "needs more information" request.

    The case goes back to `submitted`, so it reappears in the officer's
    verification list; re-verifying classifies it from the corrected answers.
    """
    serializer = CaseReplySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    with transaction.atomic():
        case = (
            CaseRecord.objects.select_for_update()
            .filter(pk=pk, submitted_by_user=request.user)
            .first()
        )
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        if case.status != CaseRecord.Status.NEEDS_INFO:
            return Response(
                {"detail": "Only a request the district office has asked about can be answered."},
                status=409,
            )

        changed = [
            field for field in REPLY_FIELDS
            if field in data and getattr(case, field) != data[field]
        ]
        for field in changed:
            setattr(case, field, data[field])
        case.status = CaseRecord.Status.SUBMITTED
        case.save(update_fields=["status", *changed])

        detail = data["note"]
        if changed:
            detail += f" (Updated: {', '.join(f.replace('_', ' ') for f in changed)}.)"
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.INFO_PROVIDED,
            detail=detail,
            created_at=timezone.now(),
        )

    from ..notifications import notify

    notify(case, CaseEventLog.EventType.INFO_PROVIDED, request.user)
    return Response(CaseDetailSerializer(case, context={"request": request}).data)


OVERRIDE_PREFIX = "Officer decision: "

OVERRIDABLE_STATUSES = {
    CaseRecord.Status.VERIFIED, CaseRecord.Status.CLAIMED,
    CaseRecord.Status.IN_PROGRESS, CaseRecord.Status.PENDING_CONFIRM,
}


@api_view(["POST"])
@permission_classes([IsDisasterOfficer])
def override_priority(request, pk):
    """FR23: change a verified case's class, with a reason.

    The classes-1.0 rules give the default. When an officer knows something
    the rules cannot see, their decision and reason go first in the reasons
    list, the rule reasons stay underneath, and the audit row records both
    classes. The household reads the officer's reason as part of "Why this
    priority", so it must be written for them.
    """
    serializer = PriorityOverrideSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    new_class = serializer.validated_data["priority_class"]
    reason = serializer.validated_data["reason"]

    with transaction.atomic():
        case = CaseRecord.objects.select_for_update().filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        if case.status not in OVERRIDABLE_STATUSES or case.priority_class is None:
            return Response(
                {"detail": "Only a verified case's priority class can be changed."}, status=409
            )
        if case.priority_class == new_class:
            return Response(
                {"priority_class": ["The case is already in that class."]}, status=400
            )

        old_class, old_label = case.priority_class, case.get_priority_class_display()
        rule_reasons = [r for r in case.priority_reasons if not r.startswith(OVERRIDE_PREFIX)]
        case.priority_class = new_class
        case.priority_reasons = [f"{OVERRIDE_PREFIX}{reason}", *rule_reasons]
        case.save(update_fields=["priority_class", "priority_reasons"])

        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.SCORE_OVERRIDDEN,
            detail=(
                f"Priority class changed from {old_class} ({old_label}) to {new_class} "
                f"({case.get_priority_class_display()}) by {request.user.full_name}: {reason}"
            ),
            created_at=timezone.now(),
        )

    return Response(CaseDetailSerializer(case, context={"request": request}).data)
