"""Tests for in-app notifications and the email nudge.

Traceability — requirements covered by this file:
  FR11 Status notifications to residents and responders on key case events
  FR20 A user sees only their own notifications
  FR21 Notifications are the same append-only event-log rows (ADR-004)

The point of most of these is that adding notifications must not damage the
audit trail. A notification is an event row addressed to somebody — not a
second copy of the event.
"""

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseRecord, LocationArea


class NotificationTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Mercy Relief", type=Organization.Type.NGO,
            contact_no="03-1", service_area="Kelantan",
        )
        self.resident = UserAccount.objects.create_user(
            email="siti@example.my", full_name="Siti binti Rahman", password="Recovery2026",
        )
        # ADR-024: the case is filed in a gazetteer village of the officer's district.
        self.village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.officer = UserAccount.objects.create_user(
            email="officer@example.my", full_name="Encik Zulkifli", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER, district_id=self.village.parent_id,
        )
        self.ngo = UserAccount.objects.create_user(
            email="aisyah@example.my", full_name="Aisyah Tan", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.org,
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-8001", submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud through the ground floor.",
            village="Kg. Bechah Laut", address="No. 14", location_area=self.village,
            household_size=4, status=CaseRecord.Status.SUBMITTED,
            created_at=timezone.now(),
        )
        mail.outbox = []


class AddressingTests(NotificationTestCase):
    def test_verifying_notifies_the_household(self):
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)

        row = CaseEventLog.objects.get(recipient_user=self.resident)
        self.assertEqual(row.event_type, CaseEventLog.EventType.VERIFIED)

    def test_nobody_is_notified_of_their_own_action(self):
        """The resident submitted it; telling them they submitted it is noise."""
        from cases.notifications import notify

        rows = notify(self.case, CaseEventLog.EventType.CLAIMED, self.resident)
        self.assertEqual(rows, [])

    def test_a_new_case_notifies_every_officer_of_its_district_only(self):
        """ADR-024: another district's officer is not told about this household."""
        second = UserAccount.objects.create_user(
            email="officer2@example.my", full_name="Officer Two", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER, district_id=self.village.parent_id,
        )
        elsewhere = LocationArea.objects.filter(level=LocationArea.Level.DISTRICT).exclude(
            pk=self.village.parent_id
        ).first()
        UserAccount.objects.create_user(
            email="officer3@example.my", full_name="Officer Elsewhere", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER, district=elsewhere,
        )
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.SUBMITTED, self.resident)

        recipients = set(
            CaseEventLog.objects.filter(recipient_user__isnull=False)
            .values_list("recipient_user", flat=True)
        )
        self.assertEqual(recipients, {self.officer.pk, second.pk})

    def test_a_case_with_no_village_notifies_no_officer(self):
        from cases.notifications import notify

        CaseRecord.objects.filter(pk=self.case.pk).update(location_area=None)
        self.case.refresh_from_db()
        notify(self.case, CaseEventLog.EventType.SUBMITTED, self.resident)

        self.assertFalse(CaseEventLog.objects.filter(recipient_user__isnull=False).exists())

    def test_an_ngo_is_not_told_about_a_household_event(self):
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertFalse(
            CaseEventLog.objects.filter(recipient_user=self.ngo).exists()
        )


class AuditIntegrityTests(NotificationTestCase):
    """Notifying must not corrupt the audit trail.

    A claimed case has been claimed once, however many people were told.
    """

    def test_notifying_does_not_duplicate_the_audit_row(self):
        CaseEventLog.objects.create(
            case=self.case, actor_user=self.ngo,
            event_type=CaseEventLog.EventType.CLAIMED,
            detail="Case claimed by Mercy Relief.", created_at=timezone.now(),
        )
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.CLAIMED, self.ngo)

        self.assertEqual(
            CaseEventLog.objects.filter(
                case=self.case, event_type=CaseEventLog.EventType.CLAIMED
            ).count(),
            1,
            "the notification became a second 'claimed' row in the audit trail",
        )

    def test_the_original_detail_is_not_overwritten(self):
        CaseEventLog.objects.create(
            case=self.case, actor_user=self.officer,
            event_type=CaseEventLog.EventType.NEEDS_INFO,
            detail="Please send a photo of the back room.", created_at=timezone.now(),
        )
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.NEEDS_INFO, self.officer)

        row = CaseEventLog.objects.get(case=self.case)
        self.assertEqual(row.detail, "Please send a photo of the back room.")


class EndpointTests(NotificationTestCase):
    def setUp(self):
        super().setUp()
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.client.force_login(self.resident)

    def test_anonymous_cannot_read_notifications(self):
        self.client.logout()
        self.assertIn(self.client.get("/api/notifications/").status_code, {401, 403})

    def test_a_user_sees_only_their_own(self):
        self.client.force_login(self.ngo)
        body = self.client.get("/api/notifications/").json()

        self.assertEqual(body["results"], [])
        self.assertEqual(body["unread"], 0)

    def test_the_household_sees_theirs_with_an_unread_count(self):
        body = self.client.get("/api/notifications/").json()

        self.assertEqual(body["unread"], 1)
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["case_reference"], "FRC-8001")

    def test_marking_one_read_clears_it_from_the_count(self):
        row_id = self.client.get("/api/notifications/").json()["results"][0]["id"]

        self.client.post(f"/api/notifications/{row_id}/read/")

        self.assertEqual(self.client.get("/api/notifications/").json()["unread"], 0)

    def test_marking_someone_elses_read_is_refused(self):
        row_id = self.client.get("/api/notifications/").json()["results"][0]["id"]
        self.client.force_login(self.ngo)

        response = self.client.post(f"/api/notifications/{row_id}/read/")

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(CaseEventLog.objects.get(pk=row_id).read_at)

    def test_mark_all_read(self):
        self.client.post("/api/notifications/read-all/")
        self.assertEqual(self.client.get("/api/notifications/").json()["unread"], 0)

    def test_marking_read_leaves_the_audit_fields_alone(self):
        """The one write the event log permits touches delivery state only."""
        row_id = self.client.get("/api/notifications/").json()["results"][0]["id"]
        before = CaseEventLog.objects.get(pk=row_id)
        actor, event_type, detail, created = (
            before.actor_user, before.event_type, before.detail, before.created_at,
        )

        self.client.post(f"/api/notifications/{row_id}/read/")

        after = CaseEventLog.objects.get(pk=row_id)
        self.assertEqual(after.actor_user, actor)
        self.assertEqual(after.event_type, event_type)
        self.assertEqual(after.detail, detail)
        self.assertEqual(after.created_at, created)
        self.assertIsNotNone(after.read_at)


class EmailTests(NotificationTestCase):
    def test_an_email_goes_out_with_the_notification(self):
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["siti@example.my"])
        self.assertIn("FRC-8001", mail.outbox[0].subject)

    def test_the_email_says_to_call_999_for_emergencies(self):
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertIn("999", mail.outbox[0].body)

    def test_delivery_status_is_recorded(self):
        from cases.notifications import notify

        rows = notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertEqual(rows[0].delivery_status, "sent")

    def test_a_verified_notification_carries_the_priority_class(self):
        """One message, not two: the class is folded into the verification."""
        self.case.priority_class = 1
        self.case.save(update_fields=["priority_class"])
        from cases.notifications import notify

        notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)

        self.assertIn("priority class 1 (Health-critical)", mail.outbox[0].subject)

    def test_a_failed_email_does_not_lose_the_notification(self):
        """Email is the secondary channel. The in-app row must survive."""
        from unittest.mock import patch

        from cases.notifications import notify

        with patch("cases.notifications.send_mail", side_effect=OSError("no route")):
            rows = notify(self.case, CaseEventLog.EventType.VERIFIED, self.officer)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].delivery_status.startswith("failed:"))
        self.assertTrue(
            CaseEventLog.objects.filter(recipient_user=self.resident).exists()
        )
