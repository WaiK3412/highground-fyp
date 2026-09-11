"""Bridge between the case records and the pure scoring engine.

The engine takes plain values and returns a result; it never touches the
database. This is the only place that reads a case, fetches the published
rubric, and writes the score back.
"""

from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from scoring.engine import CaseScoreInput, Criterion, Rubric, score_case
from scoring.models import CaseScoreComponent, PriorityRubricVersion

from .models import CaseEventLog


def score_case_record(case, actor):
      """Score a verified case and store the result with its reasoning."""

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
