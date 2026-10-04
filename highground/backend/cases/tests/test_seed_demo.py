"""Tests that demo data follows the live submission and priority-class contracts."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from cases.serializers.submission import NEEDS_VOCAB
from cases.management.commands.seed_demo import NEEDS
from cases.models import CaseRecord


@override_settings(DEBUG=True)
class SeedDemoTests(TestCase):
    def test_demo_reset_removes_photo_evidence_before_its_protected_task(self):
        """Photo evidence is protected normally; an explicit demo reset clears it first."""
        from cases.models import CasePhoto, CaseTask

        call_command("seed_demo", stdout=StringIO())
        task = CaseTask.objects.exclude(lead_user=None).first()
        CasePhoto.objects.create(
            case=task.case, task=task, uploaded_by_user=task.lead_user,
            stage="after", file_path="cases/synthetic.jpg",
        )
        call_command("seed_demo", "--flush", stdout=StringIO())
        self.assertFalse(CasePhoto.objects.exists())
        self.assertTrue(CaseTask.objects.exists())

    def test_demo_needs_are_values_the_submission_api_accepts(self):
        self.assertLessEqual(set(NEEDS), NEEDS_VOCAB)

    def test_seeded_cases_match_the_live_submission_and_classification_rules(self):
        call_command("seed_demo", stdout=StringIO())

        canonical = CaseRecord.objects.get(reference="FRC-1042")
        self.assertEqual(canonical.priority_class, 1)  # medical_disrupted
        self.assertTrue(canonical.priority_reasons[0].startswith("Health-critical"))
        self.assertLessEqual(set(canonical.needs_flags), NEEDS_VOCAB)

        # Rejected cases have no class either: verify_case clears it (3 Oct).
        no_class = [
            CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO, CaseRecord.Status.REJECTED,
        ]
        unclassified = CaseRecord.objects.filter(status__in=no_class)
        self.assertTrue(unclassified.exists())
        for case in unclassified:
            self.assertIsNone(case.priority_class)
        self.assertFalse(
            CaseRecord.objects.exclude(status__in=no_class)
            .filter(priority_class__isnull=True)
            .exists()
        )

        event_types = list(
            canonical.events.order_by("created_at").values_list("event_type", flat=True)
        )
        self.assertLess(event_types.index("verified"), event_types.index("score_computed"))

    def test_seeded_work_belongs_to_organisations_that_can_do_it(self):
        # Government agencies have no responder accounts in the demo, so a job
        # they "claimed" could never be worked; and an officer's queue would
        # label it "your organisation".
        from accounts.models import Organization
        from cases.models import CaseJob

        call_command("seed_demo", stdout=StringIO())
        self.assertFalse(
            CaseJob.objects.filter(claimed_by_org__type=Organization.Type.AGENCY).exists()
        )

    def test_seeded_jobs_awaiting_confirmation_say_when_work_finished(self):
        # The officer's "waiting for household" count reads this time.
        from cases.models import CaseJob

        call_command("seed_demo", stdout=StringIO())
        waiting = CaseJob.objects.filter(status=CaseJob.Status.PENDING_CONFIRM)
        self.assertTrue(waiting.exists())
        self.assertFalse(waiting.filter(completed_at__isnull=True).exists())

    def test_each_seeded_officer_decision_matches_the_case_status(self):
        # The resident's reply form quotes the officer's question, so a
        # needs-info case must carry that question, not a "verified" event.
        from cases.models import CaseEventLog

        call_command("seed_demo", stdout=StringIO())
        expected = {
            CaseRecord.Status.NEEDS_INFO: CaseEventLog.EventType.NEEDS_INFO,
            CaseRecord.Status.REJECTED: CaseEventLog.EventType.REJECTED,
        }
        for status, event_type in expected.items():
            cases = CaseRecord.objects.filter(status=status)
            self.assertTrue(cases.exists(), status)
            for case in cases:
                decision = case.events.get(event_type=event_type)
                self.assertTrue(decision.detail.strip())
                self.assertFalse(
                    case.events.filter(event_type=CaseEventLog.EventType.VERIFIED).exists()
                )

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

    def test_seed_posts_one_open_appeal_and_reflushes_cleanly(self):
        from django.core.management import call_command
        from django.test import override_settings

        from cases.models import SupplyAppeal

        with override_settings(DEBUG=True):
            call_command("seed_demo", "--flush", verbosity=0, stdout=StringIO())
            call_command("seed_demo", "--flush", verbosity=0, stdout=StringIO())  # PROTECT must not block a reflush
        self.assertEqual(SupplyAppeal.objects.filter(status=SupplyAppeal.Status.OPEN).count(), 1)


    @override_settings(DEBUG=False)
    def test_seed_refuses_to_run_outside_development(self):
        from django.core.management import CommandError
        from accounts.models import UserAccount

        with self.assertRaisesMessage(CommandError, "only runs in development"):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(UserAccount.objects.exists())
