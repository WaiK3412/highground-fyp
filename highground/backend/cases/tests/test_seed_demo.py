"""Tests that demo data follows the live submission and scoring contracts."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from cases.api import NEEDS_VOCAB
from cases.management.commands.seed_demo import NEEDS
from cases.models import CaseRecord


class SeedDemoTests(TestCase):
    def test_demo_needs_are_values_the_submission_api_accepts(self):
        self.assertLessEqual(set(NEEDS), NEEDS_VOCAB)

    def test_seeded_cases_match_the_live_submission_and_classification_rules(self):
        call_command("seed_demo", stdout=StringIO())

        canonical = CaseRecord.objects.get(reference="FRC-1042")
        self.assertEqual(canonical.priority_class, 1)  # medical_disrupted
        self.assertTrue(canonical.priority_reasons[0].startswith("Health-critical"))
        # The retired weighted score is no longer written for new cases.
        self.assertIsNone(canonical.score_total)
        self.assertLessEqual(set(canonical.needs_flags), NEEDS_VOCAB)

        unclassified = CaseRecord.objects.filter(
            status__in=[CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO]
        )
        self.assertTrue(unclassified.exists())
        for case in unclassified:
            self.assertIsNone(case.priority_class)
            self.assertIsNone(case.score_total)
        self.assertFalse(
            CaseRecord.objects.exclude(
                status__in=[CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO]
            ).filter(priority_class__isnull=True).exists()
        )

        event_types = list(
            canonical.events.order_by("created_at").values_list("event_type", flat=True)
        )
        self.assertLess(event_types.index("verified"), event_types.index("score_computed"))

    def test_seeded_cases_are_filed_under_controlled_villages(self):
        call_command("seed_demo", stdout=StringIO())

        for case in CaseRecord.objects.select_related("location_area"):
            self.assertIsNotNone(case.location_area, case.reference)
            self.assertEqual(case.location_area.level, "village")
            self.assertEqual(case.village, case.location_area.name)
        self.assertEqual(
            CaseRecord.objects.get(reference="FRC-1042").location_area.code, "MY0304-V001"
        )

    def test_demo_includes_a_cross_language_duplicate_for_review(self):
        """The relative's Malay report of the FRC-1042 household is flagged by
        the same lot number and address (Jln -> Jalan) under rules-1.0, and
        cannot be verified until an officer decides."""
        from cases import duplicate_services as svc
        from cases.models import DuplicateCaseMatch

        call_command("seed_demo", stdout=StringIO())

        match = DuplicateCaseMatch.objects.get(
            case_a__reference="FRC-1042", case_b__reference="FRC-1056"
        )
        self.assertEqual(match.status, DuplicateCaseMatch.Status.OPEN)
        self.assertEqual(match.matched_rules, ["same_house_and_address"])
        newer = CaseRecord.objects.get(reference="FRC-1056")
        self.assertEqual(svc.duplicate_verification_block(newer)[0], "duplicate_review_required")
        others = DuplicateCaseMatch.objects.exclude(pk=match.pk).count()
        self.assertEqual(others, 0, "only the deliberate pair should be flagged in the demo")
