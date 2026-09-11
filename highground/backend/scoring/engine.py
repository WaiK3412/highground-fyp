"""Pure, explainable priority scoring for rubric v3.0.

No Django imports on purpose: the clock, case data and rubric all arrive as
arguments. The point tables are value functions describing severity on each
criterion's own scale; a versioned weight controls that criterion's maximum
contribution to the final score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


URGENCY_POINTS = {
    "none": 0,
    "health_risk": 10,
    "medical_disrupted": 18,
    "urgent": 25,
}

# The report gives criterion 2 a 10-18 range for "partially unliveable" but no
# per-depth values; this split is the project's explicit implementation rule.
PARTIAL_DEPTH_POINTS = {
    "ankle": 10,
    "knee": 13,
    "waist": 16,
    "above_head": 18,
}

VULNERABILITY_POINTS = {
    "elderly": 6,
    "child_under_5": 6,
    "disability": 8,
    "single_parent": 4,
}

ACCESS_POINTS = {
    "normal": 0,
    "four_wd": 5,
    "foot": 8,
    "cut_off": 10,
}

NEEDS_POINTS_EACH = 3
WAITING_POINTS_PER_DAY = 2

HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40


@dataclass(frozen=True)
class Criterion:
    """One weighted rubric factor, as loaded from the database."""

    key: str
    name: str
    weight: int
    max_points: int


@dataclass(frozen=True)
class Rubric:
    label: str
    criteria: tuple[Criterion, ...]
    high_threshold: int = HIGH_THRESHOLD
    medium_threshold: int = MEDIUM_THRESHOLD

    def by_key(self, key: str) -> Criterion:
        for criterion in self.criteria:
            if criterion.key == key:
                return criterion
        raise KeyError(f"Rubric {self.label} has no criterion {key!r}")


@dataclass(frozen=True)
class CaseScoreInput:
    """The non-identifying subset of a case that scoring depends on."""

    urgency: str
    liveability: str
    flood_depth: str
    access_level: str
    needs_flags: tuple[str, ...]
    vulnerability_flags: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    name: str
    points: int
    reason: str


@dataclass
class ScoreResult:
    total: int
    band: str
    components: list[ScoreComponent] = field(default_factory=list)


def weighted_points(raw_points: int, criterion: Criterion) -> int:
    """Convert a severity value into a criterion's weighted contribution.

    ``max_points`` is the top of the criterion's severity scale; ``weight`` is
    its maximum contribution. Integer half-up rounding keeps persisted score
    components deterministic when a future rubric changes a weight.
    """
    if criterion.max_points <= 0:
        raise ValueError(f"Criterion {criterion.key!r} must have max_points above zero.")
    if criterion.weight < 0:
        raise ValueError(f"Criterion {criterion.key!r} cannot have a negative weight.")

    bounded = min(max(raw_points, 0), criterion.max_points)
    return (bounded * criterion.weight + criterion.max_points // 2) // criterion.max_points


def _weighted_result(
    raw_points: int, criterion: Criterion, reason: str
) -> tuple[int, str]:
    """Return weighted points and explain any cap or non-default scaling."""
    bounded = min(max(raw_points, 0), criterion.max_points)
    points = weighted_points(raw_points, criterion)

    if raw_points > bounded:
        reason += f", capped at {bounded} severity points"
    if criterion.weight != criterion.max_points:
        reason += (
            f"; {bounded}/{criterion.max_points} severity"
            f" × weight {criterion.weight} = {points}"
        )
    return points, reason


def _safety_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    raw = URGENCY_POINTS.get(case.urgency, 0)
    return _weighted_result(raw, criterion, f"Urgency: {case.urgency} = {raw}")


def _damage_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    if case.liveability == "unliveable":
        raw = criterion.max_points
        reason = f"Home fully unliveable = {raw}"
    elif case.liveability == "partial":
        raw = PARTIAL_DEPTH_POINTS.get(case.flood_depth, 10)
        reason = f"Partially unliveable, {case.flood_depth} = {raw}"
    else:
        raw = 4
        reason = f"Cosmetic damage only = {raw}"
    return _weighted_result(raw, criterion, reason)


def _vulnerability_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    if not case.vulnerability_flags:
        return _weighted_result(0, criterion, "No vulnerability factors recorded = 0")

    raw = sum(VULNERABILITY_POINTS.get(flag, 0) for flag in case.vulnerability_flags)
    return _weighted_result(raw, criterion, f"Total vulnerability points = {raw}")


def _needs_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    count = len(case.needs_flags)
    raw = count * NEEDS_POINTS_EACH
    reason = f"{count} shortage categories × {NEEDS_POINTS_EACH} = {raw}"
    return _weighted_result(raw, criterion, reason)


def _access_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    raw = ACCESS_POINTS.get(case.access_level, 0)
    return _weighted_result(raw, criterion, f"Access: {case.access_level} = {raw}")


def _waiting_points(
    case: CaseScoreInput, criterion: Criterion, now: datetime
) -> tuple[int, str]:
    # The clock is supplied so a test does not change meaning as real time passes.
    days = max((now - case.created_at).days, 0)
    raw = days * WAITING_POINTS_PER_DAY
    reason = f"{days} days waiting × {WAITING_POINTS_PER_DAY} = {raw}"
    return _weighted_result(raw, criterion, reason)


def band_for(
    total: int,
    high_threshold: int = HIGH_THRESHOLD,
    medium_threshold: int = MEDIUM_THRESHOLD,
) -> str:
    """Return the band using the rubric version's two thresholds."""
    if medium_threshold >= high_threshold:
        raise ValueError("The medium threshold must be below the high threshold.")
    if total >= high_threshold:
        return "High"
    if total >= medium_threshold:
        return "Medium"
    return "Low"


def score_case(case: CaseScoreInput, rubric: Rubric, now: datetime) -> ScoreResult:
    """Score a case and return six ordered, explained contributions."""
    components = []

    def add(key, rule):
        criterion = rubric.by_key(key)
        points, reason = rule(case, criterion)
        components.append(
            ScoreComponent(key=key, name=criterion.name, points=points, reason=reason)
        )

    add("safety", _safety_points)
    add("damage", _damage_points)
    add("vulnerability", _vulnerability_points)
    add("needs", _needs_points)
    add("access", _access_points)

    criterion = rubric.by_key("waiting")
    points, reason = _waiting_points(case, criterion, now)
    components.append(
        ScoreComponent(key="waiting", name=criterion.name, points=points, reason=reason)
    )

    total = sum(component.points for component in components)
    return ScoreResult(
        total=total,
        band=band_for(total, rubric.high_threshold, rubric.medium_threshold),
        components=components,
    )
