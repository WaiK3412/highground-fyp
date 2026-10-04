"""FR23: an officer may change a verified case's class, with a reason.

The rules give the default; an officer who disagrees records why. The rule
reasons are kept so a reader can see both.
"""

from django.test import Client

from cases.models import CaseEventLog, CaseRecord
from cases.tests.test_lifecycle import LifecycleTestCase
from accounts.models import UserAccount


class OverrideTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        CaseRecord.objects.filter(pk=self.case.pk).update(
            priority_class=3, priority_reasons=["no rule for Class 1 or 2 applied"]
        )

    def override(self, user, data):
        self.login(user)
        return self.client.post(
            f"/api/cases/{self.case.pk}/priority-override/", data, content_type="application/json"
        )

    def test_officer_changes_the_class_and_the_reason_is_kept(self):
        response = self.override(self.officer, {"priority_class": 2, "reason": "Roof collapsed; family sleeping outside."})
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.priority_class, 2)
        self.assertEqual(self.case.priority_reasons[0], "Officer decision: Roof collapsed; family sleeping outside.")
        self.assertIn("no rule for Class 1 or 2 applied", self.case.priority_reasons)

    def test_the_change_is_audited_with_old_and_new_class(self):
        self.override(self.officer, {"priority_class": 1, "reason": "Dialysis patient."})
        event = CaseEventLog.objects.get(event_type=CaseEventLog.EventType.SCORE_OVERRIDDEN)
        self.assertIn("from 3 (Standard) to 1 (Health-critical)", event.detail)
        self.assertEqual(event.actor_user, self.officer)

    def test_a_second_override_replaces_the_first_officer_reason(self):
        self.override(self.officer, {"priority_class": 2, "reason": "First."})
        self.override(self.officer, {"priority_class": 1, "reason": "Second."})
        self.case.refresh_from_db()
        officer_lines = [r for r in self.case.priority_reasons if r.startswith("Officer decision: ")]
        self.assertEqual(officer_lines, ["Officer decision: Second."])

    def test_invalid_priority_overrides_are_refused(self):
        cases = (
            ("blank reason", {"priority_class": 2, "reason": " "}, 400),
            ("unknown class", {"priority_class": 4, "reason": "x"}, 400),
            ("unchanged class", {"priority_class": 3, "reason": "x"}, 400),
        )
        for value, payload, expected_status in cases:
            with self.subTest(value=value):
                self.assertEqual(self.override(self.officer, payload).status_code, expected_status)

    def test_unverified_cases_cannot_be_overridden(self):
        CaseRecord.objects.filter(pk=self.case.pk).update(
            status=CaseRecord.Status.SUBMITTED, priority_class=None
        )
        self.assertEqual(self.override(self.officer, {"priority_class": 1, "reason": "x"}).status_code, 409)

    def test_rejected_cases_cannot_be_overridden(self):
        CaseRecord.objects.filter(pk=self.case.pk).update(status=CaseRecord.Status.REJECTED)
        self.assertEqual(self.override(self.officer, {"priority_class": 1, "reason": "x"}).status_code, 409)

    def test_non_officers_cannot_override_priority(self):
        ngo_client = Client()
        ngo_client.force_login(self.mercy_lead)
        resident_client = Client()
        resident_client.force_login(self.resident)
        admin = UserAccount.objects.create_user(
            email="admin@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN
        )
        admin_client = Client()
        admin_client.force_login(admin)
        cases = (
            ("ngo", ngo_client, {"content_type": "application/json"}, 403),
            ("resident", resident_client, {"content_type": "application/json"}, 403),
            ("anonymous", self.client, {}, 403),
            ("administrator", admin_client, {"content_type": "application/json"}, 403),
        )
        for actor, client, request_options, expected_status in cases:
            with self.subTest(actor=actor):
                response = client.post(
                    f"/api/cases/{self.case.pk}/priority-override/",
                    {"priority_class": 1, "reason": "x"}, **request_options,
                )
                self.assertEqual(response.status_code, expected_status)

    def test_active_verified_path_allows_override_but_needs_info_and_closed_do_not(self):
        for status in (CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS, CaseRecord.Status.PENDING_CONFIRM):
            with self.subTest(status=status):
                CaseRecord.objects.filter(pk=self.case.pk).update(status=status, priority_class=3)
                self.assertEqual(self.override(self.officer, {"priority_class": 2, "reason": "x"}).status_code, 200)
        for status in (CaseRecord.Status.NEEDS_INFO, CaseRecord.Status.CLOSED):
            with self.subTest(status=status):
                CaseRecord.objects.filter(pk=self.case.pk).update(status=status)
                self.assertEqual(self.override(self.officer, {"priority_class": 1, "reason": "x"}).status_code, 409)

    def test_household_can_read_the_officer_reason_in_its_own_detail(self):
        self.override(self.officer, {"priority_class": 2, "reason": "Roof collapsed."})
        self.login(self.resident)
        detail = self.client.get(f"/api/cases/{self.case.pk}/").json()
        self.assertEqual(detail["priority_reasons"][0], "Officer decision: Roof collapsed.")
