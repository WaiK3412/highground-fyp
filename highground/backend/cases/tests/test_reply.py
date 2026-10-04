"""FR5: the household answers the district office's request for more information.

Also: a case sent back for information or rejected loses its priority class,
so a class is only ever shown for a case on the verified path.
"""

from accounts.models import UserAccount
from cases.models import CaseEventLog, CaseRecord
from cases.tests.test_lifecycle import LifecycleTestCase


class ReplyTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        CaseRecord.objects.filter(pk=self.case.pk).update(status=CaseRecord.Status.NEEDS_INFO)
        self.case.refresh_from_db()

    def reply(self, user, data):
        self.login(user)
        return self.client.post(
            f"/api/cases/{self.case.pk}/reply/", data, content_type="application/json"
        )

    def test_reply_returns_the_case_to_the_verification_list(self):
        response = self.reply(self.resident, {"note": "Yes, my mother uses a wheelchair."})
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.SUBMITTED)
        event = CaseEventLog.objects.get(
            event_type=CaseEventLog.EventType.INFO_PROVIDED, notification_copy_of__isnull=True
        )
        self.assertIn("wheelchair", event.detail)
        self.assertEqual(event.actor_user, self.resident)

    def test_reply_may_correct_the_answers_the_class_reads(self):
        self.reply(self.resident, {
            "note": "Corrected.",
            "urgency": "medical_disrupted",
            "access_level": "foot",
            "vulnerability_flags": ["disability"],
        })
        self.case.refresh_from_db()
        self.assertEqual(self.case.urgency, "medical_disrupted")
        self.assertEqual(self.case.access_level, "foot")
        self.assertEqual(self.case.vulnerability_flags, ["disability"])
        event = CaseEventLog.objects.get(
            event_type=CaseEventLog.EventType.INFO_PROVIDED, notification_copy_of__isnull=True
        )
        self.assertIn("Updated:", event.detail)

    def test_address_and_status_cannot_be_changed_through_a_reply(self):
        self.reply(self.resident, {"note": "x", "address": "Lot 999", "status": "verified"})
        self.case.refresh_from_db()
        self.assertEqual(self.case.address, "Lot 1")
        self.assertEqual(self.case.status, CaseRecord.Status.SUBMITTED)

    def test_officers_are_notified(self):
        self.reply(self.resident, {"note": "Answer."})
        self.assertTrue(CaseEventLog.objects.filter(
            event_type=CaseEventLog.EventType.INFO_PROVIDED, recipient_user=self.officer
        ).exists())

    def test_invalid_reply_fields_are_refused(self):
        cases = (
            ("blank note", {"note": "   "}, 400),
            ("unknown vulnerability", {"note": "x", "vulnerability_flags": ["vip"]}, 400),
        )
        for value, payload, expected_status in cases:
            with self.subTest(value=value):
                self.assertEqual(self.reply(self.resident, payload).status_code, expected_status)

    def test_only_a_case_waiting_for_information_can_be_answered(self):
        self.reply(self.resident, {"note": "First answer."})
        self.assertEqual(self.reply(self.resident, {"note": "Second."}).status_code, 409)

    def test_another_household_cannot_reply(self):
        other = UserAccount.objects.create_user(
            email="other@example.my", full_name="Other", password="Recovery2026"
        )
        self.assertEqual(self.reply(other, {"note": "x"}).status_code, 404)

    def test_responders_cannot_reply(self):
        cases = (
            ("officer", self.officer, 403),
            ("ngo", self.mercy_lead, 403),
        )
        for actor, user, expected_status in cases:
            with self.subTest(actor=actor):
                self.assertEqual(self.reply(user, {"note": "x"}).status_code, expected_status)

    def test_anonymous_and_administrators_cannot_reply(self):
        self.assertEqual(self.client.post(f"/api/cases/{self.case.pk}/reply/", {"note": "x"}).status_code, 403)
        admin = UserAccount.objects.create_user(
            email="admin@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN
        )
        self.assertEqual(self.reply(admin, {"note": "x"}).status_code, 403)

    def test_reverification_classifies_the_corrected_reply(self):
        from cases.duplicate_services import detect_duplicates_for_case
        from cases.models import LocationArea

        self.case.location_area = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.case.save(update_fields=["location_area"])
        detect_duplicates_for_case(self.case.pk)
        self.assertEqual(self.reply(self.resident, {"note": "We can only be reached on foot.", "access_level": "foot"}).status_code, 200)
        self.login(self.officer)
        response = self.client.post(f"/api/cases/{self.case.pk}/verify/", {"decision": "verified"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.priority_class, 2)
        self.assertTrue(any("on foot" in reason for reason in self.case.priority_reasons))


class DecisionClearsClassTests(LifecycleTestCase):
    def decide(self, decision):
        self.login(self.officer)
        return self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": decision, "note": "Please confirm the address."},
            content_type="application/json",
        )

    def test_asking_for_information_clears_the_class(self):
        CaseRecord.objects.filter(pk=self.case.pk).update(
            priority_class=2, priority_reasons=["older person in the household"]
        )
        self.assertEqual(self.decide("needs_info").status_code, 200)
        self.case.refresh_from_db()
        self.assertIsNone(self.case.priority_class)
        self.assertEqual(self.case.priority_reasons, [])

    def test_rejecting_clears_the_class(self):
        CaseRecord.objects.filter(pk=self.case.pk).update(priority_class=1, priority_reasons=["x"])
        self.decide("rejected")
        self.case.refresh_from_db()
        self.assertIsNone(self.case.priority_class)
