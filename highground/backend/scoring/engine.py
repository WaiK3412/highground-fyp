"""Priority scoring — report §2.4.1, rubric v3.0.

No Django imports on purpose: the clock, the case and the rubric all arrive as
arguments, so scoring is testable without a database and "4 days = 8 points"
stays true whenever the suite runs.

High >= 70 - Medium 40-69 - Low <= 39.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# ===========================================================================
# GIVEN — the rubric's numbers. Data from the report, not logic.
# ===========================================================================

URGENCY_POINTS = {
    "none": 0,
    "health_risk": 10,
    "medical_disrupted": 18,
    "urgent": 25,
}

# The report gives criterion 2 a 10-18 range for "partially unliveable" but no
# per-depth values; this split is our decision (ADR-012).
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


# ===========================================================================
# GIVEN — the shapes passed in and out. Containers, no logic.
# ===========================================================================


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

    def by_key(self, key: str) -> Criterion:
        for criterion in self.criteria:
            if criterion.key == key:
                return criterion
        raise KeyError(f"Rubric {self.label} has no criterion {key!r}")


@dataclass(frozen=True)
class CaseScoreInput:
    """The subset of a case that scoring actually depends on."""

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


# ===========================================================================
# YOURS — the logic. Eight functions to fill in.
#
# Run `python manage.py test scoring` after each one. Read only the FIRST
# failure. Ugly-but-passing beats elegant-but-broken.
# ===========================================================================


def _safety_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    """Criterion 1 — safety & medical urgency (weight 25).

    none 0 - health_risk 10 - medical_disrupted 18 - urgent 25

    Return (points, reason). URGENCY_POINTS already holds the bands, so this
    is a dictionary lookup plus a sentence.
    """
    points =  URGENCY_POINTS.get(case.urgency,0)
    reason = f'urgency: {case.urgency} = {points}'

    return points,reason


def _damage_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    """Criterion 2 — damage severity & loss of shelter (weight 20).

    Three branches on case.liveability:
        "unliveable" -> criterion.max_points
        "partial"    -> look case.flood_depth up in PARTIAL_DEPTH_POINTS
        otherwise    -> 4 (cosmetic)
    """
    if case.liveability == 'unliveable':
        points = criterion.max_points
        reason = f'Home fully unliveable = {points}'

    elif case.liveability == 'partial':
        points = PARTIAL_DEPTH_POINTS.get(case.flood_depth,10)
        reason = f'Partially unliveable, {case.flood_depth} = {points}'

    else:
        points= 4
        reason=f'Cosmetic damage only = {points}'

    return points, reason



def _vulnerability_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    """Criterion 3 — household vulnerability (weight 20, CAP 20).

    Add VULNERABILITY_POINTS for every flag in case.vulnerability_flags, then
    cap at criterion.max_points.

    Two things the tests check:
        no flags at all -> 0
        when the cap bites, the word "capped" appears in the reason
    """
    if not case.vulnerability_flags :
        return 0,f'no vulnerability factors recorded = 0'

    raw = 0

    for flag in case.vulnerability_flags:
        raw += VULNERABILITY_POINTS.get(flag,0)

    points = min(raw,criterion.max_points)
    reason = f'Total Flags points = {raw}'
    if raw>points:
        reason += f', capped at {points}'

    return points,reason


def _needs_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    """Criterion 4 — essential needs shortage (weight 15, CAP 15).

    NEEDS_POINTS_EACH per flag in case.needs_flags, capped at
    criterion.max_points. The flag names do not matter, only how many.
    """
    count = len(case.needs_flags)
    raw = count * NEEDS_POINTS_EACH
    points = min(raw,criterion.max_points)

    reason = f'{count} shortage categories x 3 = {raw}'
    if raw > points:
        reason += f', capped at {points}'

    return points, reason

def _access_points(case: CaseScoreInput, criterion: Criterion) -> tuple[int, str]:
    """Criterion 5 — location accessibility (weight 10).

    normal 0 - four_wd 5 - foot 8 - cut_off 10. Same shape as _safety_points.
    """
    points =  ACCESS_POINTS.get(case.access_level,0)
    reason = f'access: {case.access_level} = {points}'

    return points,reason


def _waiting_points(
    case: CaseScoreInput, criterion: Criterion, now: datetime
) -> tuple[int, str]:
    """Criterion 6 — waiting time (weight 10, CAP 10).

    WAITING_POINTS_PER_DAY for each whole day between case.created_at and
    `now`, capped at criterion.max_points. Never negative.

    This is the one that must NOT read the clock itself.
    """
    days = max((now - case.created_at).days,0)
    raw = days * 2
    points = min(raw, criterion.max_points)

    reason = f'{days} days waiting x 2 = {raw}'
    if raw > points:
        reason += f', capped at {points}'

    return points,reason
    


def band_for(total: int) -> str:
    """High >= 70, Medium >= 40, otherwise Low. Returns the word."""
    if total >= HIGH_THRESHOLD:
        return 'High'

    elif total >=MEDIUM_THRESHOLD:
        return 'Medium'   

    else:
        return 'Low' 


def score_case(case: CaseScoreInput, rubric: Rubric, now: datetime) -> ScoreResult:
    """Score one case against one rubric version at a given moment.

    Build six ScoreComponents in this order, one per rule above:
        safety, damage, vulnerability, needs, access, waiting

    For each: fetch the Criterion with rubric.by_key(key), call the rule, and
    append ScoreComponent(key=..., name=criterion.name, points=..., reason=...).

    Then sum the points and return ScoreResult(total, band_for(total),
    components). Note that `waiting` takes a third argument the others do not.
    """
    components = []

    def add(key,rule):
        criterion = rubric.by_key(key)
        points, reason = rule(case,criterion)
        components.append(ScoreComponent(key=key ,name = criterion.name, points= points,reason=reason))

    add("safety", _safety_points)
    add("damage", _damage_points)
    add("vulnerability", _vulnerability_points)
    add("needs", _needs_points)
    add("access", _access_points)

    criterion = rubric.by_key('waiting')
    points, reason = _waiting_points(case, criterion,now)
    components.append(ScoreComponent(key='waiting', name=criterion.name,points=points,reason=reason))

    total = sum(component.points for component in components)
    return ScoreResult(total=total,band=band_for(total),components=components)


