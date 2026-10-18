"""Donations in the data model and the event log (ADR-025).

Requirement covered: residents record donations to supply appeals and the
appeal's organisation confirms receipt; the event log, which also holds case
history, stays append-only when its rows concern a donation instead.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from cases.models import CaseEventLog, Donation
from cases.tests.test_appeals import AppealTestCase


class DonationModelTests(AppealTestCase):
    def setUp(self):
        super().setUp()
        self.appeal = self.make()
        self.donation = Donation.objects.create(
            appeal=self.appeal, donor_user=self.resident, items="10 kg rice"
        )

    def event(self, **subject):
        return CaseEventLog.objects.create(
            actor_user=self.resident,
            event_type=CaseEventLog.EventType.DONATION_RECORDED,
            created_at=timezone.now(),
            **subject,
        )

    def test_event_row_needs_exactly_one_subject(self):
        for subject in ({}, {"case": self.case, "donation": self.donation}):
            with self.subTest(subject=sorted(subject)):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.event(**subject)

    def test_donation_with_audit_rows_cannot_be_deleted(self):
        self.event(donation=self.donation)
        with self.assertRaises(ProtectedError):
            self.donation.delete()

    def test_event_str_names_the_appeal_for_donation_rows(self):
        self.assertIn(self.appeal.title, str(self.event(donation=self.donation)))

    def test_new_donation_waits_for_drop_off(self):
        self.assertEqual(self.donation.status, Donation.Status.WAITING)
        self.assertEqual(self.donation.get_status_display(), "Waiting for drop-off")
