"""Tests for the case lifecycle actions.

Traceability — requirements covered by this file:
  FR4  Disaster officer verifies, requests more information, or rejects a case
  FR20 Role-based permissions on every endpoint
  FR21 Every status change is recorded in the append-only event log
"""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseRecord
from cases.tests.job_helpers import give_job


class LifecycleTestCase(TestCase):
    def setUp(self):
        self.mercy = Organization.objects.create(
            name="Mercy Relief", type=Organization.Type.NGO,
            contact_no="03-1", service_area="Kelantan",
        )
        self.belia = Organization.objects.create(
            name="Persatuan Belia", type=Organization.Type.VOLUNTEER_GROUP,
            contact_no="03-2", service_area="Pasir Mas",
        )
        self.resident = UserAccount.objects.create_user(
            email="r@example.my", full_name="Resident", password="Recovery2026",
        )
        # ADR-024: an officer acts for one district, so the case is filed under
        # a gazetteer village and the officer is that village's district officer.
        from cases.models import LocationArea

        self.village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.officer = UserAccount.objects.create_user(
            email="o@example.my", full_name="Officer", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER, district_id=self.village.parent_id,
        )
        self.mercy_lead = UserAccount.objects.create_user(
            email="m@example.my", full_name="Mercy Lead", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.mercy,
        )
        self.belia_lead = UserAccount.objects.create_user(
            email="b@example.my", full_name="Belia Lead", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.belia,
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-9001", submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud through the ground floor.",
            village="Kg. Test", address="Lot 1", location_area=self.village,
            status=CaseRecord.Status.VERIFIED,
            created_at=timezone.now(),
        )

    def login(self, user):
        self.client.force_login(user)


class VerifyTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.SUBMITTED
        # Verification now waits for a finished duplicate check, which needs a
        # controlled village; give the case both, as a real submission would.
        from cases.duplicate_services import detect_duplicates_for_case
        from cases.models import LocationArea

        self.case.location_area = LocationArea.objects.filter(
            level=LocationArea.Level.VILLAGE
        ).first()
        self.case.save()
        detect_duplicates_for_case(self.case.pk)

    def test_officer_can_verify(self):
        self.login(self.officer)
        response = self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "verified"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.VERIFIED)
        self.assertEqual(self.case.verified_by_user, self.officer)

    def test_rejection_requires_a_note(self):
        """A household is owed a reason; a bare rejection is refused."""
        self.login(self.officer)
        response = self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "rejected"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.SUBMITTED)

    def test_needs_info_records_the_note(self):
        self.login(self.officer)
        self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "needs_info", "note": "Please add a photo of the kitchen."},
            content_type="application/json",
        )

        event = CaseEventLog.objects.get(
            case=self.case, event_type=CaseEventLog.EventType.NEEDS_INFO
        )
        self.assertIn("photo of the kitchen", event.detail)

    def test_unknown_decision_is_rejected(self):
        self.login(self.officer)
        response = self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "approved"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_claimed_case_cannot_be_re_verified(self):
        self.case.status = CaseRecord.Status.CLAIMED
        self.case.save()
        give_job(self.case, self.mercy)
        self.login(self.officer)

        response = self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "rejected", "note": "changed my mind"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_only_officers_may_verify(self):
        cases = (
            ("resident", self.resident, 403),
            ("ngo", self.mercy_lead, 403),
        )
        for actor, user, expected_status in cases:
            with self.subTest(actor=actor):
                self.login(user)
                response = self.client.post(
                    f"/api/cases/{self.case.pk}/verify/",
                    {"decision": "verified"},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, expected_status)
