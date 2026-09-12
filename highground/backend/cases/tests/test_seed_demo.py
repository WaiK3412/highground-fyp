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

    def test_seeded_cases_match_the_live_submission_and_scoring_rules(self):
        call_command("seed_demo", stdout=StringIO())

        canonical = CaseRecord.objects.get(reference="FRC-1042")
        self.assertEqual(canonical.score_total, 87)
        self.assertLessEqual(set(canonical.needs_flags), NEEDS_VOCAB)

        unscored = CaseRecord.objects.filter(
            status__in=[CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO]
        )
        self.assertTrue(unscored.exists())
        for case in unscored:
            self.assertIsNone(case.score_total)
            self.assertIsNone(case.rubric_version_id)

        event_types = list(
            canonical.events.order_by("created_at").values_list("event_type", flat=True)
        )
        self.assertLess(event_types.index("verified"), event_types.index("score_computed"))
