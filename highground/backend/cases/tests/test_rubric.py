"""Tests for the coordinator-facing "how priority works" endpoint.

Traceability:
  FR10 Coordinators can inspect the priority rules (classes-1.0) and sources
  FR20 Rule reads enforce role boundaries
  FR22 The retired weighted rubric keeps its model validation (kept for the
       report's comparison, not used by the app)
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.management.commands.seed_demo import RUBRIC_V3
from scoring.models import PriorityRubricCriterion, PriorityRubricVersion


class PriorityRulesEndpointTests(TestCase):
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
        self.assertEqual(self.client.get("/api/priority-rules/").status_code, 403)
        for user in (self.resident, self.unattached_responder):
            with self.subTest(role=user.role, email=user.email):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/api/priority-rules/").status_code, 403)

    def test_authorised_coordinator_roles_can_read_the_rules(self):
        for user in (self.officer, self.responder, self.admin):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertEqual(self.client.get("/api/priority-rules/").status_code, 200)

    def test_response_lists_each_class_with_its_rule_and_sources(self):
        self.client.force_login(self.officer)
        data = self.client.get("/api/priority-rules/").json()

        self.assertEqual(data["version"], "classes-1.0")
        first = data["classes"][0]
        self.assertEqual(first["label"], "Health-critical")
        self.assertTrue(first["rule"])
        self.assertTrue(first["sources"])
        self.assertIn("earliest submitted", data["order"])

    def test_the_old_rubric_url_is_gone(self):
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get("/api/rubric/").status_code, 404)

    def test_invalid_threshold_order_is_refused_by_model_validation(self):
        self.version.medium_threshold = 70
        self.version.high_threshold = 70
        with self.assertRaises(ValidationError):
            self.version.full_clean()
