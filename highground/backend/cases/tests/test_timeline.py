"""Read-side tests for the resident case timeline.

Traceability:
  FR20 Case reads enforce role boundaries
  FR21 Residents see one safe, chronological view of the event log
"""
from datetime import timedelta

from django.contrib import admin
from django.test import RequestFactory, TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.admin import CaseEventLogAdmin
from cases.models import CaseEventLog, CaseRecord


class TimelineTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Mercy Relief",
            type=Organization.Type.NGO,
            contact_no="03-1",
            service_area="Kelantan",
        )
        self.resident = UserAccount.objects.create_user(
            email="resident@example.my",
            full_name="Resident",
            password="Recovery2026",
        )
        self.other_resident = UserAccount.objects.create_user(
            email="other@example.my",
            full_name="Other Resident",
            password="Recovery2026",
        )
        self.responder = UserAccount.objects.create_user(
            email="responder@example.my",
            full_name="Responder",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.org,
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-7001",
            submitted_by_user=self.resident,
            claimed_by_org=self.org,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud through the ground floor.",
            village="Kg. Test",
            address="Lot 1",
            status=CaseRecord.Status.VERIFIED,
            created_at=timezone.now(),
        )

        start = self.case.created_at
        self.submitted = CaseEventLog.objects.create(
            case=self.case,
            actor_user=self.resident,
            event_type=CaseEventLog.EventType.SUBMITTED,
            detail="Request submitted by Resident.",
            created_at=start,
        )
        self.needs_info = CaseEventLog.objects.create(
            case=self.case,
            event_type=CaseEventLog.EventType.NEEDS_INFO,
            detail="Please add a kitchen photo.",
            created_at=start + timedelta(minutes=1),
        )
        self.internal_update = CaseEventLog.objects.create(
            case=self.case,
            actor_user=self.responder,
            event_type=CaseEventLog.EventType.TASK_UPDATED,
            detail="Internal responder note: access key is with a neighbour.",
            created_at=start + timedelta(minutes=2),
        )
        self.notification_copy = CaseEventLog.objects.create(
            case=self.case,
            recipient_user=self.other_resident,
            notification_copy_of=self.submitted,
            event_type=CaseEventLog.EventType.SUBMITTED,
            detail="Notification copy, not a second audit action.",
            created_at=start + timedelta(minutes=3),
        )

    def test_resident_sees_one_chronological_event_per_action(self):
        self.client.force_login(self.resident)
        response = self.client.get(f"/api/cases/{self.case.pk}/")

        self.assertEqual(response.status_code, 200)
        events = response.json()["events"]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["submitted", "needs_info", "task_updated"],
        )

    def test_resident_sees_household_note_but_not_internal_operational_detail(self):
        self.client.force_login(self.resident)
        events = self.client.get(f"/api/cases/{self.case.pk}/").json()["events"]
        details = {event["event_type"]: event["detail"] for event in events}

        self.assertEqual(details["needs_info"], "Please add a kitchen photo.")
        self.assertEqual(details["task_updated"], "")

    def test_responder_can_see_operational_detail(self):
        self.client.force_login(self.responder)
        events = self.client.get(f"/api/cases/{self.case.pk}/").json()["events"]
        task_update = next(event for event in events if event["event_type"] == "task_updated")
        self.assertIn("access key", task_update["detail"])

    def test_other_resident_cannot_read_the_case_or_timeline(self):
        self.client.force_login(self.other_resident)
        response = self.client.get(f"/api/cases/{self.case.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_admin_audit_view_uses_canonical_actions_only(self):
        request = RequestFactory().get("/admin/cases/caseeventlog/")
        request.user = self.responder
        model_admin = CaseEventLogAdmin(CaseEventLog, admin.site)

        rows = model_admin.get_queryset(request)

        self.assertIn(self.submitted, rows)
        self.assertNotIn(self.notification_copy, rows)
