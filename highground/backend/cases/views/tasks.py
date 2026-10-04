"""Organisation task board, creation, assignment and task transitions."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import IsNgoVolunteer
from accounts.models import UserAccount
from ..images import UnreadableImage, clean_photo
from ..models import CaseEventLog, CaseJob, CasePhoto, CaseRecord, CaseTask
from ..serializers.cases import CasePhotoSerializer, CaseTaskSummarySerializer
from ..serializers.tasks import (
    BoardJobSerializer,
    CaseTaskBoardSerializer,
    CaseTaskCreateSerializer,
    CaseTaskUpdateSerializer,
    TaskPhotoUploadSerializer,
)


def _lead_for_organisation(lead_id, organisation):
    if lead_id is None:
        return None
    return UserAccount.objects.filter(
        pk=lead_id,
        role=UserAccount.Role.NGO_VOLUNTEER,
        organization=organisation,
        is_active=True,
    ).first()


def _may_read_tasks(user, case):
    if user.role in {UserAccount.Role.DISASTER_OFFICER, UserAccount.Role.SYSTEM_ADMIN}:
        return True
    if user.role == UserAccount.Role.COMMUNITY_MEMBER:
        return case.submitted_by_user_id == user.id
    # Read cases this organisation worked on; update_task restricts changes to its own jobs.
    return (
        user.role == UserAccount.Role.NGO_VOLUNTEER
        and user.organization_id is not None
        and case.jobs.filter(claimed_by_org_id=user.organization_id).exists()
    )


def _task_queryset():
    return CaseTask.objects.select_related("case", "job", "lead_user").prefetch_related(
        "events__actor_user", "case__jobs", "photos__task", "photos__uploaded_by_user__organization",
    )


def _locked_task(pk, organisation):
    """Use the lifecycle's case → job → task lock order, including note updates."""
    reference = CaseTask.objects.filter(pk=pk, job__claimed_by_org=organisation).values(
        "case_id", "job_id",
    ).first()
    if reference is None:
        return None
    case = CaseRecord.objects.select_for_update().get(pk=reference["case_id"])
    job = CaseJob.objects.select_for_update().get(pk=reference["job_id"])
    task = CaseTask.objects.select_for_update().filter(pk=pk, case=case, job=job).first()
    if task is None or job.claimed_by_org_id != organisation.pk:
        return None
    task.case = case
    task.job = job
    return task


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
@parser_classes([MultiPartParser])
def task_photos(request, pk):
    """FR19: optional Before/After evidence, under the progress-note boundary."""
    if not CaseTask.objects.filter(pk=pk, job__claimed_by_org=request.user.organization).exists():
        return Response({"detail": "Not found."}, status=404)
    serializer = TaskPhotoUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        cleaned = [clean_photo(upload) for upload in data["photos"]]
    except UnreadableImage as exc:
        return Response({"photos": [str(exc)]}, status=400)

    with transaction.atomic():
        task = _locked_task(pk, request.user.organization)
        if task is None:
            return Response({"detail": "Not found."}, status=404)
        if task.job.status not in {CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS}:
            return Response(
                {"detail": "Photos cannot be added while this job awaits confirmation or is finished."},
                status=409,
            )
        photos = [
            CasePhoto.objects.create(
                case=task.case, task=task, stage=data["stage"],
                uploaded_by_user=request.user, file_path=upload, caption=data.get("caption", ""),
            )
            for upload in cleaned
        ]
        CaseEventLog.objects.create(
            case=task.case, task=task, actor_user=request.user,
            event_type=CaseEventLog.EventType.TASK_UPDATED,
            detail=f'{request.user.organization.name} added {len(photos)} {data["stage"]} photo(s) to "{task.title}".',
            created_at=timezone.now(),
        )
    return Response({"photos": CasePhotoSerializer(photos, many=True, context={"request": request}).data}, status=201)


@api_view(["GET"])
@permission_classes([IsNgoVolunteer])
def task_board(request):
    """The organisation's own jobs, their tasks, and assignable responders."""
    from datetime import timedelta
    from django.db.models import Q

    recent = timezone.now() - timedelta(days=7)
    tasks = (
        _task_queryset()
        .filter(job__claimed_by_org=request.user.organization)
        .filter(
            Q(job__status__in=CaseJob.ACTIVE)
            | Q(status=CaseTask.Status.DONE, completed_at__gte=recent)
        )
        .order_by("case__reference", "id")
    )
    jobs = (
        CaseJob.objects.filter(claimed_by_org=request.user.organization, status__in=CaseJob.ACTIVE)
        .select_related("case", "claimed_by_org")
        .prefetch_related("tasks")
        .order_by("case__reference", "id")
    )
    responders = UserAccount.objects.filter(
        role=UserAccount.Role.NGO_VOLUNTEER,
        organization=request.user.organization,
        is_active=True,
    ).order_by("full_name")
    return Response(
        {
            "tasks": CaseTaskBoardSerializer(tasks, many=True, context={"request": request}).data,
            "jobs": BoardJobSerializer(jobs, many=True, context={"request": request}).data,
            "responders": [
                {"id": responder.id, "full_name": responder.full_name}
                for responder in responders
            ],
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def case_tasks(request, pk):
    case = CaseRecord.objects.filter(pk=pk).first()
    if case is None or not _may_read_tasks(request.user, case):
        return Response({"detail": "Not found."}, status=404)

    if request.method == "GET":
        tasks = _task_queryset().filter(case=case).order_by("id")
        # Expose task status/lead to residents, keeping operational access and safety notes private.
        serializer_class = (
            CaseTaskSummarySerializer
            if request.user.role == UserAccount.Role.COMMUNITY_MEMBER
            else CaseTaskBoardSerializer
        )
        return Response(serializer_class(tasks, many=True, context={"request": request}).data)

    if request.user.role != UserAccount.Role.NGO_VOLUNTEER or request.user.organization_id is None:
        return Response({"detail": "Only the organisation holding the job may create tasks."}, status=403)

    serializer = CaseTaskCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    job = case.jobs.filter(pk=serializer.validated_data["job_id"]).first()
    if job is None or job.claimed_by_org_id != request.user.organization_id:
        return Response({"detail": "Only the organisation holding the job may create tasks."}, status=403)
    if job.status not in {CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS}:
        return Response(
            {"detail": "Tasks can only be added while the job is claimed or in progress."},
            status=409,
        )
    lead_id = serializer.validated_data.get("lead_user_id")
    lead = _lead_for_organisation(lead_id, request.user.organization)
    if lead_id is not None and lead is None:
        return Response(
            {"lead_user_id": ["Choose an active responder from your organisation."]},
            status=400,
        )

    with transaction.atomic():
        # Lock order everywhere: the case row, then the job row.
        locked_case = CaseRecord.objects.select_for_update().get(pk=case.pk)
        locked_job = CaseJob.objects.select_for_update().get(pk=job.pk)
        if (
            locked_job.claimed_by_org_id != request.user.organization_id
            or locked_job.status not in {CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS}
        ):
            return Response(
                {"detail": "This job is no longer available for task changes."},
                status=409,
            )
        task = CaseTask.objects.create(
            case=locked_case,
            job=locked_job,
            lead_user=lead,
            title=serializer.validated_data["title"],
            task_type=serializer.validated_data["task_type"],
            safety_note=serializer.validated_data.get("safety_note", ""),
            status=CaseTask.Status.ASSIGNED if lead else CaseTask.Status.OPEN,
            assigned_at=timezone.now() if lead else None,
        )
        event_type = (
            CaseEventLog.EventType.TASK_ASSIGNED
            if lead
            else CaseEventLog.EventType.TASK_UPDATED
        )
        detail = (
            f"{request.user.organization.name} assigned a responder to {task.title}."
            if lead
            else f"Task created: {task.title}."
        )
        CaseEventLog.objects.create(
            case=locked_case,
            task=task,
            actor_user=request.user,
            event_type=event_type,
            detail=detail,
            created_at=timezone.now(),
        )

    return Response(CaseTaskBoardSerializer(task, context={"request": request}).data, status=201)


TASK_TRANSITIONS = {
    CaseTask.Status.OPEN: {CaseTask.Status.ASSIGNED},
    CaseTask.Status.ASSIGNED: {CaseTask.Status.IN_PROGRESS},
    CaseTask.Status.IN_PROGRESS: {CaseTask.Status.DONE},
    # A resident may report incomplete work after every task was marked done.
    CaseTask.Status.DONE: {CaseTask.Status.IN_PROGRESS},
}


def _apply_lead_change(task, lead_id, organisation):
    lead = _lead_for_organisation(lead_id, organisation)
    if lead_id is not None and lead is None:
        return Response(
            {"lead_user_id": ["Choose an active responder from your organisation."]},
            status=400,
        )
    if lead is None and task.status == CaseTask.Status.IN_PROGRESS:
        return Response(
            {"lead_user_id": ["A task in progress must keep its accountable lead."]},
            status=409,
        )
    if task.status == CaseTask.Status.DONE and lead_id != task.lead_user_id:
        return Response(
            {"lead_user_id": ["Reopen the task before reassigning it."]},
            status=409,
        )
    task.lead_user = lead


def _target_status(task, requested_status, lead_changed):
    target_status = requested_status
    if lead_changed:
        if task.status == CaseTask.Status.OPEN:
            target_status = CaseTask.Status.ASSIGNED
        elif task.status == CaseTask.Status.ASSIGNED and task.lead_user_id is None:
            target_status = CaseTask.Status.OPEN
        elif task.status == CaseTask.Status.IN_PROGRESS:
            target_status = CaseTask.Status.ASSIGNED

    if target_status != task.status:
        if not lead_changed and target_status not in TASK_TRANSITIONS.get(task.status, set()):
            return Response(
                {"status": [f"Cannot move a task from {task.status} to {target_status}."]},
                status=409,
            )
    if target_status != CaseTask.Status.OPEN and task.lead_user_id is None:
        return Response(
            {"lead_user_id": ["Assign an accountable responder before moving this task."]},
            status=400,
        )
    return target_status


def _check_start(task, user, validated, starting):
    acknowledgement_supplied = "safety_acknowledged" in validated
    if acknowledgement_supplied and (not starting or not task.safety_note):
        return Response(
            {"safety_acknowledged": ["Acknowledge a safety note only when starting its task."]},
            status=400,
        )
    if starting and task.lead_user_id != user.id:
        return Response(
            {"detail": "Only the task's accountable lead can start it. Reassign the task first if someone else will do the work."},
            status=403,
        )
    if starting and task.safety_note and validated.get("safety_acknowledged") is not True:
        return Response(
            {"safety_acknowledged": ["Read and acknowledge the safety note before starting."]},
            status=400,
        )


def _save_task_progress(task, target_status, lead_changed, status_changed):
    task.status = target_status
    if task.lead_user_id and (task.assigned_at is None or lead_changed):
        task.assigned_at = timezone.now()
    if target_status == CaseTask.Status.OPEN:
        task.assigned_at = None
    if target_status == CaseTask.Status.DONE:
        task.completed_at = timezone.now()
    elif status_changed:
        task.completed_at = None
    task.save(
        update_fields=["lead_user", "status", "assigned_at", "completed_at"]
    )


def _record_safety_acknowledgement(task, user, starting):
    if starting and task.safety_note:
        CaseEventLog.objects.create(
            case=task.case,
            task=task,
            actor_user=user,
            event_type=CaseEventLog.EventType.SAFETY_ACKNOWLEDGED,
            detail=(
                f'The task lead acknowledged the safety note shown before starting "{task.title}". '
                f'This confirms the warning was presented, not that the site is safe. '
                f'Note: {task.safety_note}'
            ),
            created_at=timezone.now(),
        )


def _advance_job(task, target_status):
    if target_status == CaseTask.Status.IN_PROGRESS and task.job.status == CaseJob.Status.CLAIMED:
        # The first task started moves its job, and so the case, along.
        from ..services import refresh_case_status

        task.job.status = CaseJob.Status.IN_PROGRESS
        task.job.save(update_fields=["status"])
        refresh_case_status(CaseRecord.objects.select_for_update().get(pk=task.case_id))


def _record_task_update(task, user, lead_changed, old_status, note):
    event_type = (
        CaseEventLog.EventType.TASK_ASSIGNED
        if lead_changed and task.lead_user_id
        else CaseEventLog.EventType.TASK_UPDATED
    )
    if event_type == CaseEventLog.EventType.TASK_ASSIGNED:
        # Only a started task is reset; a first assignment is not a handover.
        if old_status == CaseTask.Status.IN_PROGRESS:
            detail = (
                f'{user.organization.name} reassigned "{task.title}"; '
                'it returns to Assigned until the new lead starts it.'
            )
        else:
            detail = f"{user.organization.name} assigned a responder to {task.title}."
    elif note:
        detail = note
    else:
        detail = f"{task.title} moved to {task.get_status_display().lower()}."
    CaseEventLog.objects.create(
        case=task.case,
        task=task,
        actor_user=user,
        event_type=event_type,
        detail=detail,
        created_at=timezone.now(),
    )


@api_view(["PATCH"])
@permission_classes([IsNgoVolunteer])
def update_task(request, pk):
    serializer = CaseTaskUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    if not validated:
        return Response({"detail": "Provide a lead, status or progress note."}, status=400)

    with transaction.atomic():
        task = _locked_task(pk, request.user.organization)
        if task is None:
            return Response({"detail": "Not found."}, status=404)
        if task.job.status not in {CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS}:
            return Response(
                {"detail": "This task cannot change while its job awaits confirmation or is done."},
                status=409,
            )

        if "lead_user_id" in validated and "status" in validated:
            return Response(
                {"detail": "Change the lead and the status in separate steps."}, status=400
            )
        old_lead_id = task.lead_user_id
        old_status = task.status
        if "lead_user_id" in validated:
            error = _apply_lead_change(task, validated["lead_user_id"], request.user.organization)
            if error is not None:
                return error

        lead_changed = old_lead_id != task.lead_user_id
        target_status = _target_status(task, validated.get("status", task.status), lead_changed)
        if isinstance(target_status, Response):
            return target_status
        status_changed = target_status != task.status
        starting = task.status == CaseTask.Status.ASSIGNED and target_status == CaseTask.Status.IN_PROGRESS
        error = _check_start(task, request.user, validated, starting)
        if error is not None:
            return error
        note = validated.get("note", "").strip()
        if not lead_changed and not status_changed and not note:
            return Response({"detail": "Nothing changed."}, status=400)

        _save_task_progress(task, target_status, lead_changed, status_changed)
        _record_safety_acknowledgement(task, request.user, starting)
        _advance_job(task, target_status)
        _record_task_update(task, request.user, lead_changed, old_status, note)

    return Response(CaseTaskBoardSerializer(task, context={"request": request}).data)
