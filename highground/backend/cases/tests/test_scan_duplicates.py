"""The scan_duplicates backfill command.

Traceability: FR14 — existing cases are checked with the same engine and
rules as new submissions; output carries counts, never household details.
"""

from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from cases import duplicate_services as svc
from cases.models import CaseEventLog, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld, make_case


class ScanCommandTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        self.legacy = make_case(self.resident, None, reference="FRC-LEGACY")

    def run_command(self, *args):
        out, err = StringIO(), StringIO()
        call_command("scan_duplicates", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_scan_reports_aggregate_counts_only(self):
        out, _ = self.run_command()
        self.assertIn("1 pairs compared, flagged 1", out)
        self.assertIn("1 cases skipped", out)
        self.assertNotIn("FRC-", out)
        self.assertNotIn("Ahmad", out)
        self.assertEqual(DuplicateCaseMatch.objects.count(), 1)

    def test_dry_run_changes_nothing(self):
        events = CaseEventLog.objects.count()
        out, _ = self.run_command("--dry-run")
        self.assertIn("[dry run]", out)
        self.assertIn("would flag 1", out)
        self.assertFalse(DuplicateCaseMatch.objects.exists())
        self.assertEqual(CaseEventLog.objects.count(), events)

    def test_repeat_run_adds_no_flags_or_flag_events(self):
        self.run_command()
        out, _ = self.run_command()
        self.assertIn("flagged 0, 1 already recorded", out)
        self.assertEqual(
            CaseEventLog.objects.filter(event_type=CaseEventLog.EventType.DUPLICATE_FLAGGED).count(), 2
        )

    def test_location_code_limits_the_scan_and_unknown_codes_are_refused(self):
        out, _ = self.run_command("--location-code", self.other_area.code)
        self.assertIn("0 pairs compared", out)
        with self.assertRaises(CommandError):
            self.run_command("--location-code", "NOPE")
        with self.assertRaises(CommandError):
            self.run_command("--location-code", "TST-D01")  # a district, not a village

    def test_one_failing_village_keeps_the_others_and_exits_non_zero(self):
        make_case(self.resident, self.other_area, reference="FRC-6001")
        real = svc.scan_duplicate_area

        def fail_first_village(area_id, dry_run=False):
            if area_id == self.area.pk:
                raise RuntimeError("private detail")
            return real(area_id, dry_run=dry_run)

        with mock.patch("cases.management.commands.scan_duplicates.scan_duplicate_area", fail_first_village):
            with self.assertRaises(CommandError):
                out, err = StringIO(), StringIO()
                try:
                    call_command("scan_duplicates", stdout=out, stderr=err)
                finally:
                    self.assertIn("failed (RuntimeError)", err.getvalue())
                    self.assertNotIn("private detail", err.getvalue())
        self.assertEqual(svc.duplicate_check_state(self.older), "pending")

    def test_a_case_without_a_village_is_released_once_an_officer_sets_one(self):
        """Legacy cases have no controlled village, so no scan can check them.

        The way out is administrative: an officer sets the village (the field is
        on the case admin form), then the rescan completes the check. Until then
        the case is never silently treated as checked.
        """
        self.assertEqual(svc.duplicate_check_state(self.legacy), "pending")
        self.assertEqual(svc.duplicate_verification_block(self.legacy)[0], "duplicate_check_pending")

        self.run_command()
        self.assertEqual(svc.duplicate_check_state(self.legacy), "pending")

        self.legacy.location_area = self.other_area
        self.legacy.village = self.other_area.name
        self.legacy.save(update_fields=["location_area", "village"])
        self.run_command("--location-code", self.other_area.code)

        self.assertEqual(svc.duplicate_check_state(self.legacy), "completed")
        self.assertIsNone(svc.duplicate_verification_block(self.legacy))
