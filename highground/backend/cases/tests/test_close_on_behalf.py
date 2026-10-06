"""FR6/FR16: officer closure is distinct from household confirmation, and disputable.

CHS 2024 Commitment 5: a household retains a route to report unfinished help.
No contact-attempt count or timeout is invented by this workflow (ADR-023).
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TransactionTestCase
from django.utils import timezone

from accounts.models import UserAccount
from accounts.permissions import holds_active_job
from cases.models import CaseEventLog, CaseJob, CasePhoto, CaseRecord, CaseTask
from cases.services import refresh_case_status
from cases.tests.job_helpers import give_job
from cases.tests.race_helpers import GazetteerReloadMixin, race
from cases.tests.test_lifecycle import LifecycleTestCase

CLOSED_UNCONFIRMED = "closed_unconfirmed"
LABEL = "Closed without household confirmation"
REASON = {"outcome": "household_unreachable", "note": "Called on 1 and 3 October; no answer."}


class CloseOnBehalfTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        self.job = give_job(self.case, self.mercy, CaseJob.Status.PENDING_CONFIRM)
        self.since = timezone.now() - timedelta(days=3)
        self.job.completed_at = self.since
        self.job.save(update_fields=["completed_at"])
        self.task = CaseTask.objects.create(
            case=self.case, job=self.job, title="Clear mud", task_type="cleanup",
            status=CaseTask.Status.DONE, lead_user=self.mercy_lead, completed_at=self.since,
        )
        self.url = f"/api/cases/{self.case.pk}/close/"
        self.login(self.officer)

    def close(self, payload=None):
        return self.client.post(self.url, REASON if payload is None else payload, content_type="application/json")

    def test_officer_closes_without_marking_household_confirmation_and_notifies_owner(self):
        """FR16: one officer decision, with reason, attribution and an accessible dispute notice."""
        with self.captureOnCommitCallbacks(execute=True):
            response = self.close()
        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.CLOSED)
        self.assertIsNotNone(self.case.closed_at)
        self.assertEqual(self.job.status, CLOSED_UNCONFIRMED)
        self.assertNotEqual(self.job.status, CaseJob.Status.DONE)
        self.assertEqual(self.job.completed_at, self.since)
        self.assertEqual(response.json()["jobs"][0]["status_display"], LABEL)
        event = CaseEventLog.objects.get(case=self.case, event_type=CaseEventLog.EventType.CLOSED)
        self.assertEqual(event.actor_user, self.officer)
        self.assertEqual(event.recipient_user, self.resident)
        for text in ("Officer", "without household confirmation", "Unable to contact the household", REASON["note"], "Report incomplete work"):
            self.assertIn(text, event.detail)
        self.login(self.resident)
        notification = self.client.get("/api/notifications/").json()["results"][0]
        self.assertIn("Report incomplete work", notification["detail"])
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/").json()["jobs"][0]["status_display"], LABEL)

    def test_outcome_and_a_nonblank_bounded_note_are_required(self):
        for payload in (
            {"note": "No answer"}, {"outcome": "household_unreachable"},
            {**REASON, "outcome": "invented"}, {**REASON, "note": "   "},
            {**REASON, "note": "x" * 501}, {**REASON, "note": ["wrong type"]},
        ):
            with self.subTest(payload=payload):
                response = self.close(payload)
                self.assertEqual(response.status_code, 400, response.content)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CaseJob.Status.PENDING_CONFIRM)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_each_outcome_is_an_officer_decision_even_when_confirmed_verbally(self):
        outcomes = {
            "household_unreachable": "Unable to contact the household",
            "confirmed_verbally": "Household confirmed by phone or in person",
            "other": "Other",
        }
        for outcome, label in outcomes.items():
            with self.subTest(outcome=outcome):
                CaseRecord.objects.filter(pk=self.case.pk).update(status="pending_confirm", closed_at=None)
                CaseJob.objects.filter(pk=self.job.pk).update(status="pending_confirm")
                response = self.close({**REASON, "outcome": outcome})
                self.assertEqual(response.status_code, 200, response.content)
                self.job.refresh_from_db()
                self.assertEqual(self.job.status, CLOSED_UNCONFIRMED)
                self.assertIn(label, CaseEventLog.objects.filter(case=self.case).latest("pk").detail)

    def test_another_organisations_unfinished_help_blocks_close(self):
        """FR16, Review Focus 4: pending confirmation cannot abandon other unfinished jobs."""
        other = CaseJob.objects.create(case=self.case, help_type="repair", claimed_by_org=self.belia)
        for status in (CaseJob.Status.OPEN, CaseJob.Status.CLAIMED, CaseJob.Status.IN_PROGRESS):
            with self.subTest(status=status):
                other.status = status
                other.save(update_fields=["status"])
                response = self.close()
                self.assertEqual(response.status_code, 409, response.content)
                self.job.refresh_from_db()
                self.assertEqual(self.job.status, CaseJob.Status.PENDING_CONFIRM)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_case_must_be_awaiting_confirmation(self):
        for status in ("verified", "in_progress", "submitted", "rejected", "closed"):
            with self.subTest(status=status):
                self.case.status = status
                self.case.save(update_fields=["status"])
                self.assertEqual(self.close().status_code, 409)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_at_least_one_job_must_be_pending_confirmation(self):
        self.job.status = CaseJob.Status.DONE
        self.job.save(update_fields=["status"])
        self.assertEqual(self.close().status_code, 409)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_only_officers_can_close(self):
        admin = UserAccount.objects.create_user(
            email="admin-close@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN,
        )
        for user in (self.resident, self.mercy_lead, self.belia_lead, admin):
            with self.subTest(role=user.role):
                self.login(user)
                self.assertEqual(self.close().status_code, 403)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_anonymous_cannot_close(self):
        self.client.logout()
        self.assertIn(self.close().status_code, (401, 403))

    def test_unknown_case_is_not_found(self):
        self.assertEqual(self.client.post("/api/cases/99999999/close/", REASON, content_type="application/json").status_code, 404)

    def test_second_close_is_a_conflict_without_another_audit_row(self):
        self.assertEqual(self.close().status_code, 200)
        self.case.refresh_from_db()
        closed_at = self.case.closed_at
        self.assertEqual(self.close().status_code, 409)
        self.case.refresh_from_db()
        self.assertEqual(self.case.closed_at, closed_at)
        self.assertEqual(CaseEventLog.objects.filter(case=self.case, event_type="closed").count(), 1)

    def test_mix_of_done_and_closed_unconfirmed_is_a_closed_case(self):
        self.job.status = CaseJob.Status.DONE
        self.job.save(update_fields=["status"])
        CaseJob.objects.create(case=self.case, help_type="repair", status=CLOSED_UNCONFIRMED)
        self.assertTrue(refresh_case_status(self.case))
        self.assertEqual(self.case.status, CaseRecord.Status.CLOSED)
        self.assertIsNotNone(self.case.closed_at)

    def test_close_changes_pending_jobs_and_preserves_both_existing_finished_outcomes(self):
        confirmed = CaseJob.objects.create(case=self.case, help_type="repair", status=CaseJob.Status.DONE, completed_at=self.since)
        administrative = CaseJob.objects.create(case=self.case, help_type="other", status=CLOSED_UNCONFIRMED, completed_at=self.since)
        self.assertEqual(self.close().status_code, 200)
        for job, expected in ((self.job, CLOSED_UNCONFIRMED), (confirmed, CaseJob.Status.DONE), (administrative, CLOSED_UNCONFIRMED)):
            job.refresh_from_db()
            self.assertEqual(job.status, expected)
            self.assertEqual(job.completed_at, self.since)
        self.assertEqual(CaseEventLog.objects.filter(case=self.case, event_type="closed").count(), 1)

    def test_close_ends_ngo_private_access_and_does_not_leave_unmet_help(self):
        """NFR3: administrative closure is finished for active access, never confirmation."""
        photo = CasePhoto.objects.create(
            case=self.case, task=self.task, uploaded_by_user=self.mercy_lead,
            stage="after", file_path="cases/synthetic.jpg",
        )
        self.assertEqual(self.close().status_code, 200)
        self.job.refresh_from_db()
        self.assertFalse(holds_active_job(self.mercy_lead, self.case))
        self.assertEqual(self.client.get("/api/jobs/unmet/").json(), [])
        self.login(self.mercy_lead)
        self.assertEqual(self.client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/").json()["detail_access"], "summary")

    def test_notification_is_deferred_until_commit(self):
        with patch("cases.notifications.notify") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.close()
                self.assertEqual(response.status_code, 200)
                notify.assert_not_called()
            notify.assert_called_once()

    def test_audit_failure_rolls_back_every_job_and_the_case(self):
        with patch("cases.views.verification.CaseEventLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesMessage(RuntimeError, "audit unavailable"):
                self.close()
        self.job.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.job.status, CaseJob.Status.PENDING_CONFIRM)
        self.assertEqual(self.case.status, CaseRecord.Status.PENDING_CONFIRM)
        self.assertIsNone(self.case.closed_at)


class OfficerClosureDisputeTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.CLOSED
        self.case.closed_at = timezone.now()
        self.case.save(update_fields=["status", "closed_at"])
        self.job = give_job(self.case, self.mercy, CLOSED_UNCONFIRMED)
        self.job.completed_at = timezone.now() - timedelta(days=3)
        self.job.save(update_fields=["completed_at"])
        self.login(self.resident)

    def decide(self, decision="incomplete", note="Kitchen is still muddy."):
        return self.client.post(f"/api/jobs/{self.job.pk}/confirm/", {"decision": decision, "note": note}, content_type="application/json")

    def test_owner_reopens_officer_closed_work_and_notifies_the_organisation(self):
        """FR6/FR16: reporting unfinished work reopens the job and clears closure time."""
        response = self.decide()
        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.job.status, CaseJob.Status.IN_PROGRESS)
        self.assertIsNone(self.job.completed_at)
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)
        self.assertIsNone(self.case.closed_at)
        event = CaseEventLog.objects.get(case=self.case, event_type="reopened")
        self.assertEqual(event.actor_user, self.resident)
        self.assertEqual(event.recipient_user, self.mercy_lead)
        self.assertIn("Kitchen is still muddy", event.detail)
        self.assertTrue(holds_active_job(self.mercy_lead, self.case))

    def test_household_confirmed_work_cannot_be_reopened(self):
        self.job.status = CaseJob.Status.DONE
        self.job.save(update_fields=["status"])
        self.assertEqual(self.decide().status_code, 409)
        self.assertEqual(self.decide("confirm").status_code, 409)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_confirmation_after_officer_closure_is_refused(self):
        self.assertEqual(self.decide("confirm").status_code, 409)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CLOSED_UNCONFIRMED)

    def test_dispute_requires_an_explanation(self):
        self.assertEqual(self.decide(note="   ").status_code, 400)
        self.assertFalse(CaseEventLog.objects.exists())

    def test_malformed_dispute_note_is_a_400(self):
        self.assertEqual(self.decide(note=["wrong type"]).status_code, 400)
        self.assertEqual(self.decide(note="x" * 1001).status_code, 400)

    def test_only_the_owning_household_may_dispute(self):
        other = UserAccount.objects.create_user(email="other-close-household@example.my", full_name="Other")
        self.login(other)
        self.assertEqual(self.decide().status_code, 404)
        for user in (self.mercy_lead, self.belia_lead, self.officer):
            self.login(user)
            self.assertEqual(self.decide().status_code, 403)
        self.client.logout()
        self.assertIn(self.decide().status_code, (401, 403))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CLOSED_UNCONFIRMED)


class ConfirmationWaitingTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        self.job = give_job(self.case, self.mercy, CaseJob.Status.PENDING_CONFIRM)
        self.since = timezone.now() - timedelta(days=5)
        self.job.completed_at = self.since
        self.job.save(update_fields=["completed_at"])

    def test_district_staff_get_the_earliest_pending_completion_date_only(self):
        later = CaseJob.objects.create(
            case=self.case, help_type="repair", status=CaseJob.Status.PENDING_CONFIRM,
            completed_at=self.since + timedelta(days=1), claimed_by_org=self.belia,
        )
        CaseJob.objects.create(case=self.case, help_type="other", status=CaseJob.Status.DONE, completed_at=self.since - timedelta(days=10))
        admin = UserAccount.objects.create_user(email="waiting-admin@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN)
        expected = self.since.isoformat().replace("+00:00", "Z")
        for user in (self.officer, admin):
            self.login(user)
            self.assertEqual(self.client.get("/api/cases/").json()["results"][0]["awaiting_confirmation_since"], expected)
            self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/").json()["awaiting_confirmation_since"], expected)
        CaseJob.objects.filter(pk__in=[self.job.pk, later.pk]).update(status=CLOSED_UNCONFIRMED)
        self.assertIsNone(self.client.get(f"/api/cases/{self.case.pk}/").json()["awaiting_confirmation_since"])

    def test_household_and_ngo_rows_never_include_the_waiting_key(self):
        for user in (self.resident, self.mercy_lead, self.belia_lead):
            self.login(user)
            self.assertNotIn("awaiting_confirmation_since", self.client.get("/api/cases/").json()["results"][0])
            self.assertNotIn("awaiting_confirmation_since", self.client.get(f"/api/cases/{self.case.pk}/").json())

    def test_unknown_historical_completion_date_is_null_without_backfill_or_timeout(self):
        self.job.completed_at = None
        self.job.save(update_fields=["completed_at"])
        self.login(self.officer)
        self.assertIsNone(self.client.get(f"/api/cases/{self.case.pk}/").json()["awaiting_confirmation_since"])
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CaseJob.Status.PENDING_CONFIRM)
        self.assertIsNone(self.job.completed_at)

    def test_officer_pending_confirmation_filter_excludes_other_cases(self):
        CaseRecord.objects.create(
            reference="FRC-9002", submitted_by_user=self.resident, status="verified",
            damage_category="cleanup", description="Mud.", village="Kg. Test", address="Lot 2", created_at=timezone.now(),
        )
        self.login(self.officer)
        rows = self.client.get("/api/cases/?status=pending_confirm").json()["results"]
        self.assertEqual([row["id"] for row in rows], [self.case.pk])
        self.assertIsNotNone(rows[0]["awaiting_confirmation_since"])

    def test_requesting_completion_records_waiting_start_without_needing_photos(self):
        """FR6: a real waiting date starts when the NGO requests confirmation."""
        self.job.status = CaseJob.Status.IN_PROGRESS
        self.job.completed_at = None
        self.job.save(update_fields=["status", "completed_at"])
        CaseTask.objects.create(case=self.case, job=self.job, title="Clear mud", task_type="cleanup", status="done")
        self.login(self.mercy_lead)
        before = timezone.now()
        response = self.client.post(f"/api/jobs/{self.job.pk}/complete/")
        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.assertIsNotNone(self.job.completed_at)
        self.assertGreaterEqual(self.job.completed_at, before)
        self.assertFalse(CasePhoto.objects.exists())


class OfficerCloseRaceTests(GazetteerReloadMixin, TransactionTestCase):
    def setUp(self):
        # TransactionTestCase empties every table between tests, and the
        # lifecycle fixture files its case under a gazetteer village (ADR-024).
        from importlib import import_module

        from django.apps import apps

        from cases.models import LocationArea

        if not LocationArea.objects.exists():
            import_module("cases.migrations.0008_load_kelantan_locations").load(apps, None)
        LifecycleTestCase.setUp(self)
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        self.job = give_job(self.case, self.mercy, CaseJob.Status.PENDING_CONFIRM)

    def poster(self, user, path, payload):
        def post():
            client = Client()
            client.force_login(user)
            return client.post(path, payload, content_type="application/json").status_code
        return post

    def test_two_officer_closes_have_one_winner_and_one_audit_event(self):
        """FR16: real PostgreSQL locks prevent two decisions on the same pending jobs."""
        path = f"/api/cases/{self.case.pk}/close/"
        results = race(self.poster(self.officer, path, REASON), self.poster(self.officer, path, REASON))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(CaseEventLog.objects.filter(case=self.case, event_type="closed", notification_copy_of=None).count(), 1)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, CLOSED_UNCONFIRMED)

    def test_household_dispute_racing_officer_close_always_preserves_unfinished_help(self):
        results = race(
            self.poster(self.officer, f"/api/cases/{self.case.pk}/close/", REASON),
            self.poster(self.resident, f"/api/jobs/{self.job.pk}/confirm/", {"decision": "incomplete", "note": "Mud remains."}),
        )
        self.assertIn(results[0], (200, 409))
        self.assertEqual(results[1], 200)
        self.job.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.job.status, CaseJob.Status.IN_PROGRESS)
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)
        self.assertIsNone(self.case.closed_at)
        self.assertEqual(CaseEventLog.objects.filter(case=self.case, event_type="reopened", notification_copy_of=None).count(), 1)
