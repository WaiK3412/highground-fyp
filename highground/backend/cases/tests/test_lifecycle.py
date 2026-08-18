"""Tests for the case lifecycle actions.

Traceability — requirements covered by this file:
  FR4  Disaster officer verifies, requests more information, or rejects a case
  FR6  Responding organisation claims a verified case
  FR20 Role-based permissions on every endpoint
  FR21 Every status change is recorded in the append-only event log
"""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseRecord


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
        self.officer = UserAccount.objects.create_user(
            email="o@example.my", full_name="Officer", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER,
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
            village="Kg. Test", address="Lot 1",
            status=CaseRecord.Status.VERIFIED,
            created_at=timezone.now(),
        )

    def login(self, user):
        self.client.force_login(user)


class ClaimTests(LifecycleTestCase):
    def test_ngo_can_claim_a_verified_case(self):
        self.login(self.mercy_lead)
        response = self.client.post(f"/api/cases/{self.case.pk}/claim/")

        self.assertEqual(response.status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.claimed_by_org, self.mercy)
        self.assertEqual(self.case.status, CaseRecord.Status.CLAIMED)

    def test_second_organisation_is_refused(self):
        """The core requirement: exactly one organisation wins a case."""
        self.login(self.mercy_lead)
        self.client.post(f"/api/cases/{self.case.pk}/claim/")

        self.login(self.belia_lead)
        response = self.client.post(f"/api/cases/{self.case.pk}/claim/")

        self.assertEqual(response.status_code, 409)
        self.case.refresh_from_db()
        self.assertEqual(self.case.claimed_by_org, self.mercy)

    def test_reclaiming_by_the_same_org_is_idempotent(self):
        """A dropped response must not turn a successful claim into an error."""
        self.login(self.mercy_lead)
        first = self.client.post(f"/api/cases/{self.case.pk}/claim/")
        second = self.client.post(f"/api/cases/{self.case.pk}/claim/")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            CaseEventLog.objects.filter(
                case=self.case, event_type=CaseEventLog.EventType.CLAIMED
            ).count(),
            1,
            "the retry must not add a second 'claimed' row to the audit trail",
        )

    def test_unverified_cases_cannot_be_claimed(self):
        self.case.status = CaseRecord.Status.SUBMITTED
        self.case.save()
        self.login(self.mercy_lead)

        response = self.client.post(f"/api/cases/{self.case.pk}/claim/")

        self.assertEqual(response.status_code, 409)

    def test_claim_writes_an_audit_row(self):
        self.login(self.mercy_lead)
        self.client.post(f"/api/cases/{self.case.pk}/claim/")

        event = CaseEventLog.objects.get(
            case=self.case, event_type=CaseEventLog.EventType.CLAIMED
        )
        self.assertEqual(event.actor_user, self.mercy_lead)
        self.assertIn("Mercy Relief", event.detail)

    def test_residents_and_officers_cannot_claim(self):
        for user in (self.resident, self.officer):
            with self.subTest(role=user.role):
                self.login(user)
                response = self.client.post(f"/api/cases/{self.case.pk}/claim/")
                self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_claim(self):
        response = self.client.post(f"/api/cases/{self.case.pk}/claim/")
        self.assertEqual(response.status_code, 403)


class VerifyTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.SUBMITTED
        self.case.save()

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
        self.case.claimed_by_org = self.mercy
        self.case.save()
        self.login(self.officer)

        response = self.client.post(
            f"/api/cases/{self.case.pk}/verify/",
            {"decision": "rejected", "note": "changed my mind"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)

    def test_only_officers_may_verify(self):
        for user in (self.resident, self.mercy_lead):
            with self.subTest(role=user.role):
                self.login(user)
                response = self.client.post(
                    f"/api/cases/{self.case.pk}/verify/",
                    {"decision": "verified"},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)
