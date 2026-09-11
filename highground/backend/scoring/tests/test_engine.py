"""Tests for the priority scoring engine.

Traceability — requirements covered by this file:
  FR9  Compute an explainable priority score from the submitted case data
  FR10 Show the per-criterion breakdown that justifies the score
  FR22 Scores are attributable to a published rubric version

The engine is pure, so these tests need no database and no fixtures loaded.
`now` is supplied explicitly, which is why the waiting-time assertions stay
true regardless of when the suite is run.
"""

from datetime import datetime, timedelta
from unittest import TestCase

from scoring.engine import (
    CaseScoreInput,
    Criterion,
    Rubric,
    band_for,
    score_case,
)

# Rubric v3.0 as published — weights 25/20/20/15/10/10, totalling 100.
RUBRIC_V3 = Rubric(
    label="v3.0",
    criteria=(
        Criterion("safety", "Safety & medical urgency", 25, 25),
        Criterion("damage", "Damage severity & loss of shelter", 20, 20),
        Criterion("vulnerability", "Household vulnerability", 20, 20),
        Criterion("needs", "Essential needs shortage", 15, 15),
        Criterion("access", "Location accessibility", 10, 10),
        Criterion("waiting", "Waiting time", 10, 10),
    ),
)

NOW = datetime(2026, 8, 19, 12, 0, 0)


def make_case(**overrides) -> CaseScoreInput:
    """A deliberately low-scoring baseline; each test overrides one axis."""
    defaults = dict(
        urgency="none",
        liveability="liveable",
        flood_depth="ankle",
        access_level="normal",
        needs_flags=(),
        vulnerability_flags=(),
        created_at=NOW,
    )
    defaults.update(overrides)
    return CaseScoreInput(**defaults)


class CanonicalCaseTests(TestCase):
    """#FRC-1042 is the worked example carried through the report."""

    def test_frc_1042_scores_87(self):
        case = make_case(
            urgency="medical_disrupted",                      # 18
            liveability="partial",
            flood_depth="waist",                              # 16
            vulnerability_flags=("elderly", "child_under_5", "disability"),  # 20 (capped)
            needs_flags=("water", "food", "bedding", "hygiene", "medicine"),  # 15
            access_level="cut_off",                           # 10
            created_at=NOW - timedelta(days=4),               # 8
        )

        result = score_case(case, RUBRIC_V3, now=NOW)

        self.assertEqual(result.total, 87)
        self.assertEqual(result.band, "High")

    def test_frc_1042_component_breakdown(self):
        case = make_case(
            urgency="medical_disrupted",
            liveability="partial",
            flood_depth="waist",
            vulnerability_flags=("elderly", "child_under_5", "disability"),
            needs_flags=("water", "food", "bedding", "hygiene", "medicine"),
            access_level="cut_off",
            created_at=NOW - timedelta(days=4),
        )

        result = score_case(case, RUBRIC_V3, now=NOW)
        points = {c.key: c.points for c in result.components}

        self.assertEqual(points["safety"], 18)
        self.assertEqual(points["damage"], 16)
        self.assertEqual(points["vulnerability"], 20)
        self.assertEqual(points["needs"], 15)
        self.assertEqual(points["access"], 10)
        self.assertEqual(points["waiting"], 8)

    def test_every_component_explains_itself(self):
        """FR10: the score is explainable, not a bare number."""
        result = score_case(make_case(urgency="urgent"), RUBRIC_V3, now=NOW)

        self.assertEqual(len(result.components), 6)
        for component in result.components:
            self.assertTrue(component.reason, f"{component.key} has no reason string")


class BandTests(TestCase):
    def test_thresholds(self):
        self.assertEqual(band_for(39), "Low")
        self.assertEqual(band_for(40), "Medium")
        self.assertEqual(band_for(69), "Medium")
        self.assertEqual(band_for(70), "High")

    def test_empty_case_scores_low(self):
        result = score_case(make_case(), RUBRIC_V3, now=NOW)
        self.assertEqual(result.total, 4)  # cosmetic damage only
        self.assertEqual(result.band, "Low")

    def test_score_uses_the_rubric_versions_thresholds(self):
        rubric = Rubric(
            label="low thresholds",
            criteria=RUBRIC_V3.criteria,
            medium_threshold=2,
            high_threshold=4,
        )
        self.assertEqual(score_case(make_case(), rubric, now=NOW).band, "High")

    def test_invalid_threshold_order_is_refused(self):
        with self.assertRaises(ValueError):
            band_for(50, high_threshold=40, medium_threshold=40)


class CriterionBandTests(TestCase):
    def test_urgency_bands(self):
        for urgency, expected in [
            ("none", 0),
            ("health_risk", 10),
            ("medical_disrupted", 18),
            ("urgent", 25),
        ]:
            result = score_case(make_case(urgency=urgency), RUBRIC_V3, now=NOW)
            points = {c.key: c.points for c in result.components}
            self.assertEqual(points["safety"], expected, urgency)

    def test_damage_scales_with_flood_depth(self):
        for depth, expected in [
            ("ankle", 10),
            ("knee", 13),
            ("waist", 16),
            ("above_head", 18),
        ]:
            case = make_case(liveability="partial", flood_depth=depth)
            points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
            self.assertEqual(points["damage"], expected, depth)

    def test_fully_unliveable_takes_the_full_weight(self):
        case = make_case(liveability="unliveable")
        points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
        self.assertEqual(points["damage"], 20)

    def test_access_bands(self):
        for access, expected in [
            ("normal", 0),
            ("four_wd", 5),
            ("foot", 8),
            ("cut_off", 10),
        ]:
            case = make_case(access_level=access)
            points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
            self.assertEqual(points["access"], expected, access)


class CapTests(TestCase):
    """Caps matter: without them a single criterion could outweigh the rubric."""

    def test_vulnerability_caps_at_20(self):
        case = make_case(
            vulnerability_flags=("elderly", "child_under_5", "disability", "single_parent")
        )  # 6 + 6 + 8 + 4 = 24 raw
        points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
        self.assertEqual(points["vulnerability"], 20)

    def test_needs_caps_at_15(self):
        case = make_case(needs_flags=tuple(f"need{i}" for i in range(9)))  # 27 raw
        points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
        self.assertEqual(points["needs"], 15)

    def test_waiting_caps_at_10_after_five_days(self):
        case = make_case(created_at=NOW - timedelta(days=30))
        points = {c.key: c.points for c in score_case(case, RUBRIC_V3, now=NOW).components}
        self.assertEqual(points["waiting"], 10)

    def test_cap_is_recorded_in_the_reason(self):
        case = make_case(
            vulnerability_flags=("elderly", "child_under_5", "disability", "single_parent")
        )
        result = score_case(case, RUBRIC_V3, now=NOW)
        reason = next(c.reason for c in result.components if c.key == "vulnerability")
        self.assertIn("capped", reason)


class WeightTests(TestCase):
    def test_changing_a_weight_changes_that_contribution(self):
        criteria = tuple(
            Criterion(c.key, c.name, 50 if c.key == "safety" else c.weight, c.max_points)
            for c in RUBRIC_V3.criteria
        )
        rubric = Rubric("safety doubled", criteria)

        result = score_case(
            make_case(urgency="medical_disrupted"), rubric, now=NOW
        )
        safety = next(c for c in result.components if c.key == "safety")

        self.assertEqual(safety.points, 36)  # 18/25 severity × weight 50
        self.assertIn("weight 50", safety.reason)

    def test_no_component_exceeds_its_weight(self):
        weights = {"safety": 7, "damage": 6, "vulnerability": 5, "needs": 4, "access": 3, "waiting": 2}
        criteria = tuple(
            Criterion(c.key, c.name, weights[c.key], c.max_points)
            for c in RUBRIC_V3.criteria
        )
        result = score_case(
            make_case(
                urgency="urgent",
                liveability="unliveable",
                vulnerability_flags=("elderly", "child_under_5", "disability", "single_parent"),
                needs_flags=tuple(str(i) for i in range(10)),
                access_level="cut_off",
                created_at=NOW - timedelta(days=30),
            ),
            Rubric("small weights", criteria),
            now=NOW,
        )

        for component in result.components:
            self.assertLessEqual(component.points, weights[component.key])

    def test_invalid_severity_scale_is_refused(self):
        broken = tuple(
            Criterion(c.key, c.name, c.weight, 0 if c.key == "safety" else c.max_points)
            for c in RUBRIC_V3.criteria
        )
        with self.assertRaises(ValueError):
            score_case(make_case(), Rubric("broken", broken), now=NOW)


class PurityTests(TestCase):
    def test_same_inputs_give_same_result(self):
        case = make_case(urgency="urgent", created_at=NOW - timedelta(days=2))
        first = score_case(case, RUBRIC_V3, now=NOW)
        second = score_case(case, RUBRIC_V3, now=NOW)
        self.assertEqual(first.total, second.total)

    def test_maximum_possible_score_is_100(self):
        case = make_case(
            urgency="urgent",
            liveability="unliveable",
            vulnerability_flags=("elderly", "child_under_5", "disability"),
            needs_flags=("a", "b", "c", "d", "e"),
            access_level="cut_off",
            created_at=NOW - timedelta(days=5),
        )
        self.assertEqual(score_case(case, RUBRIC_V3, now=NOW).total, 100)
