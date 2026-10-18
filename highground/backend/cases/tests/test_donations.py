"""Donations to supply appeals (ADR-025).

Requirement covered: a resident records what they will bring to an open appeal,
and only the appeal's own organisation sees the donor's contact details and
confirms receipt. Every endpoint is checked for each role it must refuse.
"""

from accounts.models import UserAccount
from cases.models import CaseEventLog, Donation, SupplyAppeal
from cases.tests.test_appeals import AppealTestCase


class DonationTestCase(AppealTestCase):
    def setUp(self):
        super().setUp()
        self.appeal = self.make()

    def donate(self, user, appeal=None, items="10 kg rice"):
        self.login(user)
        return self.client.post(
            f"/api/appeals/{(appeal or self.appeal).pk}/donations/",
            {"items": items},
            content_type="application/json",
        )

    def action(self, user, donation, name):
        self.login(user)
        return self.client.post(f"/api/donations/{donation.pk}/{name}/")

    def waiting(self, donor=None):
        return Donation.objects.create(
            appeal=self.appeal, donor_user=donor or self.resident, items="Bottled water"
        )

    def other_resident(self):
        return UserAccount.objects.create_user(
            email="other@example.my", full_name="Another resident", password="Recovery2026"
        )

    def audit_rows(self, donation, event_type):
        return CaseEventLog.objects.filter(
            donation=donation, event_type=event_type, notification_copy_of__isnull=True
        )


class RecordingTests(DonationTestCase):
    def test_resident_records_donation_on_open_appeal(self):
        response = self.donate(self.resident)
        self.assertEqual(response.status_code, 201)
        donation = Donation.objects.get()
        self.assertEqual(donation.donor_user, self.resident)
        self.assertEqual(response.json()["status"], "waiting")
        row = self.audit_rows(donation, CaseEventLog.EventType.DONATION_RECORDED).get()
        self.assertIsNone(row.case_id)

    def test_only_residents_can_donate(self):
        for actor, user in (
            ("officer", self.officer), ("owning NGO", self.mercy_lead), ("other NGO", self.belia_lead),
        ):
            with self.subTest(actor=actor):
                self.assertEqual(self.donate(user).status_code, 403)
        self.client.logout()
        anonymous = self.client.post(
            f"/api/appeals/{self.appeal.pk}/donations/", {"items": "Rice"},
            content_type="application/json",
        )
        self.assertEqual(anonymous.status_code, 403)
        self.assertFalse(Donation.objects.exists())

    def test_cannot_donate_to_closed_appeal(self):
        closed = self.make(status=SupplyAppeal.Status.CLOSED)
        response = self.donate(self.resident, closed)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "This appeal is no longer accepting donations."})

    def test_cannot_donate_after_appeal_expires(self):
        response = self.donate(self.resident, self.make(days=-1))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "This appeal is no longer accepting donations."})

    def test_items_required_and_limited(self):
        for items in ("   ", "x" * 501):
            with self.subTest(length=len(items)):
                response = self.donate(self.resident, items=items)
                self.assertEqual(response.status_code, 400)
                self.assertIn("items", response.json())
        self.assertFalse(Donation.objects.exists())

    def test_missing_appeal_is_404(self):
        self.login(self.resident)
        response = self.client.post(
            "/api/appeals/999999/donations/", {"items": "Rice"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)


class ListingTests(DonationTestCase):
    def test_resident_lists_only_own_donations(self):
        mine = self.waiting()
        other = self.other_resident()
        self.waiting(donor=other)
        self.login(self.resident)
        rows = self.client.get("/api/donations/").json()["results"]
        self.assertEqual([row["id"] for row in rows], [mine.pk])
        self.assertEqual(rows[0]["appeal"]["title"], self.appeal.title)
        self.assertNotIn("donor_phone", rows[0])

    def test_owning_ngo_lists_donations_with_donor_contact(self):
        self.resident.phone = "012-111 2222"
        self.resident.save()
        self.waiting()
        self.login(self.mercy_lead)
        rows = self.client.get(f"/api/appeals/{self.appeal.pk}/donations/").json()["results"]
        self.assertEqual(rows[0]["donor_name"], self.resident.full_name)
        self.assertEqual(rows[0]["donor_phone"], "012-111 2222")

    def test_other_organisation_gets_404(self):
        donation = self.waiting()
        self.login(self.belia_lead)
        self.assertEqual(self.client.get(f"/api/appeals/{self.appeal.pk}/donations/").status_code, 404)
        self.assertEqual(self.action(self.belia_lead, donation, "receive").status_code, 404)

    def test_resident_and_officer_cannot_list_appeal_donations(self):
        for user in (self.resident, self.officer):
            with self.subTest(role=user.role):
                self.login(user)
                self.assertEqual(
                    self.client.get(f"/api/appeals/{self.appeal.pk}/donations/").status_code, 403
                )

    def test_officer_and_ngo_have_no_own_donation_list(self):
        for user in (self.officer, self.mercy_lead):
            with self.subTest(role=user.role):
                self.login(user)
                self.assertEqual(self.client.get("/api/donations/").status_code, 403)


class CancelTests(DonationTestCase):
    def test_donor_cancels_waiting_donation(self):
        donation = self.waiting()
        response = self.action(self.resident, donation, "cancel")
        self.assertEqual(response.status_code, 200)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.CANCELLED)
        self.assertIsNotNone(donation.cancelled_at)
        self.assertTrue(self.audit_rows(donation, CaseEventLog.EventType.DONATION_CANCELLED).exists())

    def test_another_resident_cannot_cancel(self):
        donation = self.waiting()
        other = self.other_resident()
        self.assertEqual(self.action(other, donation, "cancel").status_code, 404)

    def test_received_donation_cannot_be_cancelled(self):
        donation = self.waiting()
        self.action(self.mercy_lead, donation, "receive")
        self.assertEqual(self.action(self.resident, donation, "cancel").status_code, 409)


class ReceiveTests(DonationTestCase):
    def test_ngo_marks_received_even_after_appeal_closes(self):
        donation = self.waiting()
        self.appeal.status = SupplyAppeal.Status.CLOSED
        self.appeal.save()
        response = self.action(self.mercy_lead, donation, "receive")
        self.assertEqual(response.status_code, 200)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.RECEIVED)
        self.assertEqual(donation.received_by_user, self.mercy_lead)
        self.assertIsNotNone(donation.received_at)
        self.assertEqual(response.json()["received_by"], self.mercy_lead.full_name)
        self.assertTrue(self.audit_rows(donation, CaseEventLog.EventType.DONATION_RECEIVED).exists())

    def test_second_receive_conflicts(self):
        donation = self.waiting()
        self.action(self.mercy_lead, donation, "receive")
        donation.refresh_from_db()
        first_received_at = donation.received_at
        self.assertEqual(self.action(self.mercy_lead, donation, "receive").status_code, 409)
        donation.refresh_from_db()
        self.assertEqual(donation.received_at, first_received_at)

    def test_cancelled_donation_cannot_be_received(self):
        donation = self.waiting()
        self.action(self.resident, donation, "cancel")
        self.assertEqual(self.action(self.mercy_lead, donation, "receive").status_code, 409)

    def test_resident_and_officer_cannot_receive(self):
        donation = self.waiting()
        for user in (self.resident, self.officer):
            with self.subTest(role=user.role):
                self.assertEqual(self.action(user, donation, "receive").status_code, 403)

