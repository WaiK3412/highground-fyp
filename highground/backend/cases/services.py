"""Bridge between the case records and the pure priority modules.

The modules take plain values and return a result; they never touch the
database. This is the only place that reads a case and writes its priority
back through classify_case_record (classes-1.0).
"""

from django.utils import timezone

from priority.classes import CLASS_RULES_VERSION, ClassInput, classify

from .models import CaseEventLog


def classify_case_record(case, actor, at=None):
    """Assign the literature-sourced priority class at verification (classes-1.0)."""
    result = classify(
        ClassInput(
            urgency=case.urgency,
            access_level=case.access_level,
            vulnerability_flags=tuple(case.vulnerability_flags or ()),
        )
    )
    case.priority_class = result.priority_class
    case.priority_reasons = list(result.reasons)
    case.save(update_fields=["priority_class", "priority_reasons"])

    CaseEventLog.objects.create(
        case=case,
        actor_user=actor,
        event_type=CaseEventLog.EventType.SCORE_COMPUTED,
        detail=(
            f"Priority class {result.priority_class} ({result.label}) under "
            f"{CLASS_RULES_VERSION}: {'; '.join(result.reasons)}."
        ),
        # `at` lets the demo seed place the event in its back-dated timeline.
        created_at=at or timezone.now(),
    )
    return result


def refresh_case_status(case):
    """Recompute a verified case's status from its jobs (ADR-020).

    The request closes when every job is household-confirmed or explicitly
    closed by an officer without confirmation (ADR-023). Otherwise it
    shows its most advanced live job: awaiting confirmation, then in progress,
    then claimed; with nothing taken yet it is simply verified (back in the
    NGO queue). The caller must hold the case row lock, so two jobs finishing
    at once cannot both close it. Returns True if the status changed.
    """
    from .models import CaseJob, CaseRecord

    if case.status not in OPERATIONAL_CASE_STATUSES:
        return False  # submitted, needs_info, rejected: not driven by jobs
    statuses = set(case.jobs.values_list("status", flat=True))
    if statuses and statuses.issubset(CaseJob.FINISHED):
        new_status = CaseRecord.Status.CLOSED
    elif CaseJob.Status.PENDING_CONFIRM in statuses:
        new_status = CaseRecord.Status.PENDING_CONFIRM
    elif CaseJob.Status.IN_PROGRESS in statuses:
        new_status = CaseRecord.Status.IN_PROGRESS
    elif CaseJob.Status.CLAIMED in statuses:
        new_status = CaseRecord.Status.CLAIMED
    else:
        new_status = CaseRecord.Status.VERIFIED
    if new_status == case.status:
        return False
    case.status = new_status
    case.closed_at = timezone.now() if new_status == CaseRecord.Status.CLOSED else None
    case.save(update_fields=["status", "closed_at"])
    return True


OPERATIONAL_CASE_STATUSES = {
    "verified", "claimed", "in_progress", "pending_confirm", "closed",
}
