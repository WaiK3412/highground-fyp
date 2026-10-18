"""Notifications about donations (ADR-025, extending ADR-004).

Requirement covered: the appeal's organisation hears when a donation is
recorded or cancelled, and the donor hears when it is received. The rows are
the same append-only event-log rows as case notifications.
"""

from django.core import mail
from django.test import override_settings

from accounts.models import UserAccount
from cases.models import CaseEventLog, Donation
from cases.tests.test_donations import DonationTestCase


@override_settings(EMAIL_SKIP_DOMAINS=set())
class DonationNotificationTests(DonationTestCase):
    def setUp(self):
        super().setUp()
        self.mercy_second = UserAccount.objects.create_user(
            email="m2@example.my", full_name="Mercy Second", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.mercy,
        )
        self.mercy_inactive = UserAccount.objects.create_user(
            email="m3@example.my", full_name="Mercy Former", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.mercy, is_active=False,
        )

    def recipients(self, event_type):
        return set(
            CaseEventLog.objects.filter(event_type=event_type, recipient_user__isnull=False)
            .values_list("recipient_user__email", flat=True)
        )

    def recorded(self):
        self.donate(self.resident)
        return Donation.objects.get()

    def test_recorded_notifies_active_members_of_the_owning_org_only(self):
        self.recorded()
        self.assertEqual(
            self.recipients(CaseEventLog.EventType.DONATION_RECORDED),
            {self.mercy_lead.email, self.mercy_second.email},
        )

    def test_one_audit_row_per_action(self):
        donation = self.recorded()
        canonical = CaseEventLog.objects.filter(donation=donation, notification_copy_of__isnull=True)
        self.assertEqual(canonical.count(), 1)
        self.assertEqual(CaseEventLog.objects.filter(donation=donation).count(), 2)

    def test_cancelled_notifies_owning_org(self):
        self.action(self.resident, self.recorded(), "cancel")
        self.assertEqual(
            self.recipients(CaseEventLog.EventType.DONATION_CANCELLED),
            {self.mercy_lead.email, self.mercy_second.email},
        )

    def test_received_notifies_donor_not_the_ngo_actor(self):
        self.action(self.mercy_lead, self.recorded(), "receive")
        self.assertEqual(
            self.recipients(CaseEventLog.EventType.DONATION_RECEIVED), {self.resident.email}
        )

    def test_email_subject_names_the_appeal(self):
        self.action(self.mercy_lead, self.recorded(), "receive")
        subject = mail.outbox[-1].subject
        self.assertIn(self.appeal.title, subject)
        self.assertNotIn("FRC-", subject)

    def test_placeholder_address_is_not_emailed(self):
        self.resident.email = "resident@hg.my"
        self.resident.save()
        with override_settings(EMAIL_SKIP_DOMAINS={"hg.my"}):
            self.action(self.mercy_lead, self.recorded(), "receive")
        row = CaseEventLog.objects.get(
            event_type=CaseEventLog.EventType.DONATION_RECEIVED, recipient_user=self.resident
        )
        self.assertEqual(row.delivery_status, "skipped_placeholder_address")

    def test_notification_list_includes_donation_rows(self):
        self.action(self.mercy_lead, self.recorded(), "receive")
        self.login(self.resident)
        body = self.client.get("/api/notifications/").json()
        row = next(r for r in body["results"] if r["event_type"] == "donation_received")
        self.assertIsNone(row["case_id"])
        self.assertIsNone(row["case_reference"])
        self.assertEqual(row["appeal_id"], self.appeal.pk)
        self.assertIn(self.appeal.title, row["detail"])
        self.assertGreaterEqual(body["unread"], 1)

    def test_member_who_left_sees_generic_text(self):
        self.recorded()
        self.mercy_second.organization = self.belia
        self.mercy_second.save()
        self.login(self.mercy_second)
        row = self.client.get("/api/notifications/").json()["results"][0]
        self.assertEqual(row["detail"], "Donation updated. Sign in to view it.")

    def test_mark_read_works_for_donation_rows(self):
        self.recorded()
        row = CaseEventLog.objects.get(recipient_user=self.mercy_lead)
        self.login(self.mercy_lead)
        response = self.client.post(f"/api/notifications/{row.pk}/read/")
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertIsNotNone(row.read_at)
