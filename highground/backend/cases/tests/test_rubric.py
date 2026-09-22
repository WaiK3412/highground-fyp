"""Tests for the coordinator-facing published rubric endpoint.

Traceability:
  FR10 Coordinators can inspect the explainable published rubric
  FR20 Rubric reads enforce role boundaries
  FR22 Scores and thresholds are attributable to a rubric version
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.management.commands.seed_demo import RUBRIC_V3
from scoring.models import PriorityRubricCriterion, PriorityRubricVersion


class RubricEndpointTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Mercy Relief",
            type=Organization.Type.NGO,
            contact_no="03-1",
            service_area="Kelantan",
        )
        self.resident = UserAccount.objects.create_user(
            email="resident@example.my", full_name="Resident", password="Recovery2026"
        )
        self.officer = UserAccount.objects.create_user(
            email="officer@example.my",
            full_name="Officer",
            password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        self.responder = UserAccount.objects.create_user(
            email="responder@example.my",
            full_name="Responder",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.org,
        )
        self.unattached_responder = UserAccount.objects.create_user(
            email="unattached@example.my",
            full_name="Unattached",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
        )
        self.admin = UserAccount.objects.create_user(
            email="admin@example.my",
            full_name="Admin",
            password="Recovery2026",
            role=UserAccount.Role.SYSTEM_ADMIN,
        )

        self.version = PriorityRubricVersion.objects.create(
            label="v3.1",
            status=PriorityRubricVersion.Status.PUBLISHED,
            medium_threshold=35,
            high_threshold=65,
            published_at=timezone.now(),
        )
        for key, name, weight, max_points, rule in RUBRIC_V3:
            PriorityRubricCriterion.objects.create(
                version=self.version,
                key=key,
                name=name,
                weight=50 if key == "safety" else weight,
                max_points=max_points,
                rule_text=rule,
            )

    def test_anonymous_resident_and_unattached_responder_are_refused(self):
        self.assertEqual(self.client.get("/api/rubric/").status_code, 403)
        for user in (self.resident, self.unattached_responder):
            with self.subTest(role=user.role, email=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/api/rubric/").status_code, 403)

    def test_authorised_coordinator_roles_can_read_the_rubric(self):
        for user in (self.officer, self.responder, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/api/rubric/").status_code, 200)

    def test_response_uses_versioned_thresholds_weights_and_value_bands(self):
        self.client.force_login(self.officer)
        data = self.client.get("/api/rubric/").json()

        self.assertEqual(data["thresholds"], {"high": 65, "medium": 35})
        safety = next(c for c in data["criteria"] if c["key"] == "safety")
        urgent = next(b for b in safety["bands"] if b["when"] == "urgent")
        self.assertEqual(safety["weight"], 50)
        self.assertEqual(safety["max_points"], 25)
        self.assertEqual(urgent["points"], 25)

    def test_case_detail_names_the_rubric_version_that_scored_it(self):
        """FR22: the breakdown a coordinator reads says which rubric produced it."""
        from cases.models import CaseRecord

        scored = CaseRecord.objects.create(
            reference="FRC-9301", submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP, description="Scored case.",
            village="Kg. Rubric", address="Lot 1", status=CaseRecord.Status.VERIFIED,
            score_total=70, rubric_version=self.version, created_at=timezone.now(),
        )
        unscored = CaseRecord.objects.create(
            reference="FRC-9302", submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP, description="New case.",
            village="Kg. Rubric", address="Lot 2", status=CaseRecord.Status.SUBMITTED,
            created_at=timezone.now(),
        )
        self.client.force_login(self.officer)

        self.assertEqual(self.client.get(f"/api/cases/{scored.pk}/").json()["rubric_label"], "v3.1")
        self.assertIsNone(self.client.get(f"/api/cases/{unscored.pk}/").json()["rubric_label"])

        # An NGO's village-level summary carries the label too; it is not private.
        self.client.force_login(self.responder)
        self.assertEqual(self.client.get(f"/api/cases/{scored.pk}/").json()["rubric_label"], "v3.1")

    def test_no_published_rubric_returns_404(self):
        self.version.status = PriorityRubricVersion.Status.RETIRED
        self.version.save(update_fields=["status"])
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get("/api/rubric/").status_code, 404)

    def test_invalid_threshold_order_is_refused_by_model_validation(self):
        self.version.medium_threshold = 70
        self.version.high_threshold = 70
        with self.assertRaises(ValidationError):
            self.version.full_clean()
