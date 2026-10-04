"""Traceability: FR10 (case prioritisation) under classes-1.0 (ADR-018)."""

from django.test import SimpleTestCase

from priority.classes import ClassInput, classify


def case(urgency="none", access="normal", flags=()):
    return ClassInput(urgency=urgency, access_level=access, vulnerability_flags=tuple(flags))


class ClassifyTests(SimpleTestCase):
    def test_medical_disruption_is_class_1(self):
        result = classify(case(urgency="medical_disrupted"))
        self.assertEqual(result.priority_class, 1)
        self.assertEqual(result.label, "Health-critical")
        self.assertIn("medical care disrupted", result.reasons[0])

    def test_urgent_is_class_1(self):
        self.assertEqual(classify(case(urgency="urgent")).priority_class, 1)

    def test_class_1_wins_over_vulnerability_and_lists_it_first(self):
        result = classify(case(urgency="medical_disrupted", flags=["elderly"], access="cut_off"))
        self.assertEqual(result.priority_class, 1)
        self.assertIn("medical care disrupted", result.reasons[0])

    def test_each_vulnerability_flag_is_class_2(self):
        for flag in ("elderly", "child_under_5", "disability", "single_parent"):
            with self.subTest(flag=flag):
                self.assertEqual(classify(case(flags=[flag])).priority_class, 2)

    def test_any_non_normal_access_is_class_2(self):
        for access in ("four_wd", "foot", "cut_off"):
            with self.subTest(access=access):
                self.assertEqual(classify(case(access=access)).priority_class, 2)

    def test_health_risk_alone_is_class_3(self):
        result = classify(case(urgency="health_risk"))
        self.assertEqual(result.priority_class, 3)
        self.assertEqual(result.label, "Standard")

    def test_unknown_and_missing_values_do_not_crash(self):
        self.assertEqual(
            classify(case(urgency="legacy_value", access=None, flags=["unknown_flag"])).priority_class,
            3,
        )

    def test_class_2_reasons_name_every_trigger(self):
        result = classify(case(flags=["elderly", "disability"], access="foot"))
        self.assertEqual(len(result.reasons), 3)
