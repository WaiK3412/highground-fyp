"""Bridge between the case records and the pure priority modules.

The modules take plain values and return a result; they never touch the
database. This is the only place that reads a case and writes its priority
back. classify_case_record (classes-1.0) is what the app calls;
score_case_record (the weighted rubric) is retired and kept for comparison.
"""

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from scoring.classes import CLASS_RULES_VERSION, ClassInput, classify
from scoring.engine import CaseScoreInput, Criterion, Rubric, score_case
from scoring.models import CaseScoreComponent, PriorityRubricVersion

from .models import CaseEventLog


def score_case_record(case, actor):
      """Retired weighted score (rubric v3.0). Kept for the report's comparison; not called by the app."""

      version = PriorityRubricVersion.objects.filter(
          status=PriorityRubricVersion.Status.PUBLISHED
      ).order_by("-published_at").first()

      if version is None:
          raise ImproperlyConfigured("No published rubric version to score against.")

      rubric = Rubric(
        label=version.label,
        criteria=tuple(
            Criterion(c.key, c.name, c.weight, c.max_points)
            for c in version.criteria.all()
        ),
        high_threshold=version.high_threshold,
        medium_threshold=version.medium_threshold,
    )

      result = score_case(
          CaseScoreInput(
              urgency=case.urgency,
              liveability=case.liveability,
              flood_depth=case.flood_depth,
              access_level=case.access_level,
              needs_flags=tuple(case.needs_flags),
              vulnerability_flags=tuple(case.vulnerability_flags),
              created_at=case.created_at,
          ),
      rubric,
      now=timezone.now(),
      )

      case.score_total = result.total
      case.rubric_version = version
      case.save(update_fields=["score_total", "rubric_version"])

      criteria = {c.key: c for c in version.criteria.all()}
      for component in result.components:
          CaseScoreComponent.objects.create(
              case=case,
              criterion=criteria[component.key],
              points=component.points,
              reason=component.reason,
          )

      CaseEventLog.objects.create(

          case=case,
          actor_user=actor,
          event_type=CaseEventLog.EventType.SCORE_COMPUTED,
          detail=f"Priority {result.total} ({result.band}) under rubric {version.label}.",
          created_at=timezone.now(),
      )

      return result


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

    The household request is closed when every job is done. Otherwise it
    shows its most advanced live job: awaiting confirmation, then in progress,
    then claimed; with nothing taken yet it is simply verified (back in the
    NGO queue). The caller must hold the case row lock, so two jobs finishing
    at once cannot both close it. Returns True if the status changed.
    """
    from .models import CaseJob, CaseRecord

    if case.status not in OPERATIONAL_CASE_STATUSES:
        return False  # submitted, needs_info, rejected: not driven by jobs
    statuses = set(case.jobs.values_list("status", flat=True))
    if statuses and statuses == {CaseJob.Status.DONE}:
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
