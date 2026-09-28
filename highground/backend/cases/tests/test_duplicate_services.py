"""Duplicate detection and review services (report §3.7.8).

Traceability — requirements covered by this file:
  FR14 Possible duplicates are flagged for officer review, never auto-merged
  FR21 Every detection and decision is recorded in the append-only event log
"""

from unittest import mock

from django.test import TestCase
from django.utils import timezone

from cases import duplicate_services as svc
from cases.models import CaseEventLog, CaseRecord, CaseTask, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld, event_types, make_case

Event = CaseEventLog.EventType
MatchStatus = DuplicateCaseMatch.Status


class InputTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()

    def test_input_uses_account_details_and_the_case_pin_not_the_village_centroid(self):
        case = make_case(self.resident, self.area, reference="FRC-1")
        data = svc.duplicate_input_for_case(case)
        self.assertEqual(data.submitter_name, "Ahmad bin Ismail")
        self.assertEqual(data.phone, "012-555 0142")
        self.assertEqual(data.needs, ("food", "water"))
        # The village has a centroid; the case has no pin, so none is passed.
        self.assertIsNone(data.latitude)
        self.assertIsNone(data.longitude)

    def test_description_adapter_returns_the_original_text(self):
        case = make_case(self.resident, self.area, reference="FRC-1", description="Banjir teruk.")
        self.assertEqual(svc.description_for_matching(case), "Banjir teruk.")

    def test_canonical_pair_orders_by_time_then_id(self):
        older, newer = self.older_and_newer()
        self.assertEqual(svc.canonical_pair(newer, older), (older, newer))
        newer.created_at = older.created_at
        self.assertEqual(svc.canonical_pair(newer, older), (older, newer))  # lower pk first

    def test_blocking_excludes_other_villages_closed_rejected_and_linked(self):
        live = make_case(self.resident, self.area, reference="FRC-1")
        make_case(self.resident, self.other_area, reference="FRC-2")
        make_case(self.resident, self.area, reference="FRC-3", status=CaseRecord.Status.CLOSED)
        make_case(self.resident, self.area, reference="FRC-4", status=CaseRecord.Status.REJECTED)
        make_case(self.resident, self.area, reference="FRC-5", duplicate_of_case=live)
        self.assertEqual(list(svc.eligible_duplicate_cases(self.area.pk)), [live])


class DetectionTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()

    def test_same_household_is_flagged_older_as_a_and_check_completes(self):
        older, newer = self.older_and_newer()
        result = svc.detect_duplicates_for_case(newer.pk)

        match = DuplicateCaseMatch.objects.get()
        self.assertEqual((match.case_a, match.case_b), (older, newer))
        self.assertEqual(match.status, MatchStatus.OPEN)
        self.assertGreaterEqual(match.similarity_score, 35)
        self.assertEqual(result.created, 1)
        self.assertEqual(svc.duplicate_check_state(newer), "completed")
        self.assertIn(Event.DUPLICATE_FLAGGED, event_types(older))
        self.assertIn(Event.DUPLICATE_FLAGGED, event_types(newer))

    def test_next_door_neighbour_is_not_flagged(self):
        make_case(self.resident, self.area, reference="FRC-1", minutes_ago=90)
        neighbour = make_case(
            self.neighbour, self.area, reference="FRC-2",
            address="Lot 89, Jalan Masjid, Kampung Sireh",
        )
        svc.detect_duplicates_for_case(neighbour.pk)
        self.assertFalse(DuplicateCaseMatch.objects.exists())
        self.assertEqual(svc.duplicate_check_state(neighbour), "completed")

    def test_other_villages_are_never_compared(self):
        make_case(self.resident, self.other_area, reference="FRC-1", minutes_ago=90)
        case = make_case(self.relative, self.area, reference="FRC-2")
        result = svc.detect_duplicates_for_case(case.pk)
        self.assertEqual(result.examined, 0)

    def test_a_case_without_a_controlled_village_stays_pending(self):
        legacy = make_case(self.resident, None, reference="FRC-1")
        result = svc.detect_duplicates_for_case(legacy.pk)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(svc.duplicate_check_state(legacy), "pending")

    def test_no_events_means_pending(self):
        case = make_case(self.resident, self.area, reference="FRC-1")
        self.assertEqual(svc.duplicate_check_state(case), "pending")

    def test_a_pair_is_never_recorded_twice(self):
        older, newer = self.older_and_newer()
        svc.detect_duplicates_for_case(newer.pk)
        svc.detect_duplicates_for_case(older.pk)
        svc.detect_duplicates_for_case(newer.pk)
        self.assertEqual(DuplicateCaseMatch.objects.count(), 1)

    def test_detection_failure_rolls_back_its_writes_and_leaves_pending(self):
        older, newer = self.older_and_newer()
        with mock.patch.object(svc, "compare_cases", side_effect=RuntimeError("boom")):
            with self.assertLogs("cases.duplicate_services", level="WARNING") as logs:
                svc.run_detection_after_submission(newer)
        self.assertFalse(DuplicateCaseMatch.objects.exists())
        self.assertEqual(svc.duplicate_check_state(newer), "pending")
        # Ids and exception type only: no household text in operational logs.
        self.assertIn(f"id={newer.pk}", logs.output[0])
        self.assertIn("RuntimeError", logs.output[0])
        self.assertNotIn("boom", logs.output[0])
        self.assertNotIn("Masjid", logs.output[0])


class ScanTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()

    def test_scan_flags_and_completes_every_case(self):
        result = svc.scan_duplicate_area(self.area.pk)
        self.assertEqual((result.examined, result.created), (1, 1))
        self.assertEqual(svc.duplicate_check_state(self.older), "completed")
        self.assertEqual(svc.duplicate_check_state(self.newer), "completed")

    def test_dry_run_writes_nothing(self):
        before = CaseEventLog.objects.count()
        result = svc.scan_duplicate_area(self.area.pk, dry_run=True)
        self.assertEqual(result.created, 1)
        self.assertFalse(DuplicateCaseMatch.objects.exists())
        self.assertEqual(CaseEventLog.objects.count(), before)

    def test_rescan_preserves_decisions_and_scores(self):
        svc.scan_duplicate_area(self.area.pk)
        match = DuplicateCaseMatch.objects.get()
        svc.decide_duplicate_match(match.pk, self.officer, "dismiss")
        score = match.similarity_score

        result = svc.scan_duplicate_area(self.area.pk)
        match.refresh_from_db()
        self.assertEqual(result.existing, 1)
        self.assertEqual(result.created, 0)
        self.assertEqual(match.status, MatchStatus.REJECTED)
        self.assertEqual(match.similarity_score, score)
        self.assertEqual(
            CaseEventLog.objects.filter(event_type=Event.DUPLICATE_FLAGGED).count(), 2
        )

    def test_failed_scan_leaves_cases_pending_not_completed(self):
        svc.scan_duplicate_area(self.area.pk)
        with mock.patch.object(svc, "compare_cases", side_effect=RuntimeError):
            DuplicateCaseMatch.objects.all().delete()
            with self.assertRaises(RuntimeError):
                svc.scan_duplicate_area(self.area.pk)
        self.assertEqual(svc.duplicate_check_state(self.older), "pending")
        self.assertEqual(svc.duplicate_check_state(self.newer), "pending")
        self.assertFalse(DuplicateCaseMatch.objects.exists())


class VerificationBlockTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        svc.scan_duplicate_area(self.area.pk)
        self.match = DuplicateCaseMatch.objects.get()

    def test_open_flag_blocks_the_newer_case_only(self):
        self.assertEqual(svc.duplicate_verification_block(self.newer)[0], "duplicate_review_required")
        self.assertIsNone(svc.duplicate_verification_block(self.older))

    def test_dismissing_the_last_flag_unblocks(self):
        third = make_case(self.resident, self.area, reference="FRC-5003", minutes_ago=60)
        svc.scan_duplicate_area(self.area.pk)
        flags = DuplicateCaseMatch.objects.filter(case_b=self.newer, status=MatchStatus.OPEN)
        self.assertEqual(flags.count(), 2)  # FRC-5001 and FRC-5003 both precede it
        first, second = list(flags.order_by("pk"))

        svc.decide_duplicate_match(first.pk, self.officer, "dismiss")
        self.assertEqual(svc.duplicate_verification_block(self.newer)[0], "duplicate_review_required")
        svc.decide_duplicate_match(second.pk, self.officer, "dismiss")
        self.assertIsNone(svc.duplicate_verification_block(self.newer))
        self.assertIsNotNone(third)


class DecisionTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        svc.scan_duplicate_area(self.area.pk)
        self.match = DuplicateCaseMatch.objects.get()

    def decide(self, decision, match=None):
        return svc.decide_duplicate_match((match or self.match).pk, self.officer, decision)

    def test_confirm_links_and_closes_the_newer_case_and_keeps_its_history(self):
        CaseEventLog.objects.create(
            case=self.newer, event_type=Event.SUBMITTED, detail="x", created_at=timezone.now()
        )
        outcome = self.decide("confirm")
        self.newer.refresh_from_db()
        self.older.refresh_from_db()

        self.assertTrue(outcome.changed)
        self.assertEqual(outcome.match.status, MatchStatus.CONFIRMED)
        self.assertEqual(outcome.match.decided_by_user, self.officer)
        self.assertEqual(self.newer.duplicate_of_case, self.older)
        self.assertEqual(self.newer.status, CaseRecord.Status.CLOSED)
        self.assertIsNotNone(self.newer.closed_at)
        self.assertEqual(self.older.status, CaseRecord.Status.SUBMITTED)
        self.assertIn(Event.SUBMITTED, event_types(self.newer))
        self.assertIn(Event.DUPLICATE_CONFIRMED, event_types(self.older))
        self.assertIn(Event.DUPLICATE_CLOSED, event_types(self.newer))

    def test_safe_closure_event_names_only_the_households_own_reference(self):
        self.decide("confirm")
        closed = CaseEventLog.objects.get(case=self.newer, event_type=Event.DUPLICATE_CLOSED)
        self.assertIn(self.newer.reference, closed.detail)
        self.assertNotIn(self.older.reference, closed.detail)
        self.assertNotIn("Ahmad", closed.detail)

    def test_dismiss_leaves_both_cases_unchanged(self):
        self.decide("dismiss")
        self.newer.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.REJECTED)
        self.assertIsNone(self.newer.duplicate_of_case)
        self.assertEqual(self.newer.status, CaseRecord.Status.SUBMITTED)
        self.assertIn(Event.DUPLICATE_DISMISSED, event_types(self.newer))

    def test_repeating_a_decision_writes_nothing_more(self):
        self.decide("confirm")
        before = CaseEventLog.objects.count()
        outcome = self.decide("confirm")
        self.assertFalse(outcome.changed)
        self.assertEqual(CaseEventLog.objects.count(), before)

    def test_opposite_decision_is_a_conflict(self):
        self.decide("dismiss")
        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("confirm")
        self.assertEqual(caught.exception.code, "conflicting_decision")

    def test_unknown_match_returns_none(self):
        self.assertIsNone(svc.decide_duplicate_match(999999, self.officer, "confirm"))

    def test_confirm_supersedes_other_open_flags_on_the_closed_case(self):
        later = make_case(self.resident, self.area, reference="FRC-5003", minutes_ago=1)
        svc.scan_duplicate_area(self.area.pk)
        others = DuplicateCaseMatch.objects.exclude(pk=self.match.pk)
        involving_newer = others.filter(case_a=self.newer, case_b=later).get()

        outcome = self.decide("confirm")
        involving_newer.refresh_from_db()
        self.assertEqual(involving_newer.status, MatchStatus.SUPERSEDED)
        self.assertIsNone(involving_newer.decided_by_user)  # no officer judged it
        self.assertIn(involving_newer.pk, outcome.superseded_ids)
        # A flag between the older case and the later one is not the closed
        # case's question, so it stays open.
        self.assertEqual(others.get(case_a=self.older, case_b=later).status, MatchStatus.OPEN)
        self.assertIn(Event.DUPLICATE_SUPERSEDED, event_types(later))

        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("dismiss", involving_newer)
        self.assertEqual(caught.exception.code, "match_superseded")

    def test_newer_case_with_an_organisation_working_on_it_cannot_be_closed(self):
        self.newer.status = CaseRecord.Status.CLAIMED
        self.newer.claimed_by_org = self.org
        self.newer.save()
        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("confirm")
        self.assertEqual(caught.exception.code, "active_case")
        self.newer.refresh_from_db()
        self.assertIsNone(self.newer.duplicate_of_case)

    def test_unfinished_tasks_block_confirmation(self):
        CaseTask.objects.create(case=self.newer, title="Clear mud", task_type="cleanup")
        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("confirm")
        self.assertEqual(caught.exception.code, "active_case")

    def test_older_case_may_be_operationally_active(self):
        self.older.status = CaseRecord.Status.CLAIMED
        self.older.claimed_by_org = self.org
        self.older.save()
        self.assertTrue(self.decide("confirm").changed)

    def test_confirming_would_not_create_a_chain(self):
        make_case(
            self.resident, self.area, reference="FRC-4999", minutes_ago=500,
            status=CaseRecord.Status.CLOSED, duplicate_of_case=self.newer,
        )
        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("confirm")
        self.assertEqual(caught.exception.code, "duplicate_chain")

    def test_stale_pair_cannot_be_confirmed_but_can_be_dismissed(self):
        self.older.status = CaseRecord.Status.REJECTED
        self.older.save()
        with self.assertRaises(svc.DuplicateConflict) as caught:
            self.decide("confirm")
        self.assertEqual(caught.exception.code, "stale_pair")
        self.assertTrue(self.decide("dismiss").changed)
