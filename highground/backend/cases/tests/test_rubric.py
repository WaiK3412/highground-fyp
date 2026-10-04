"""Tests for the coordinator-facing "how priority works" endpoint.

Traceability:
  FR10 Coordinators can inspect the priority rules (classes-1.0) and sources
  FR20 Rule reads enforce role boundaries
  FR22 The retired weighted rubric keeps its model validation (kept for the
       report's comparison, not used by the app)
"""
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from scoring.models import PriorityRubricCriterion, PriorityRubricVersion


# Reserved rubric model validation uses a local historical fixture.
RUBRIC_V3 = [
    ("safety", "Safety & medical urgency", 25, 25,
     "none 0 · health risk 10 · medical needs disrupted 18 · urgent 25"),
    ("damage", "Damage severity & loss of shelter", 20, 20,
     "cosmetic 4 · partially unliveable 10–18 by flood depth · fully unliveable 20"),
    ("vulnerability", "Household vulnerability", 20, 20,
     "elderly +6 · child <5 +6 · disability +8 · single parent +4 (cap 20)"),
    ("needs", "Essential needs shortage", 15, 15, "+3 per category ticked (cap 15)"),
    ("access", "Location accessibility", 10, 10,
     "normal 0 · 4x4 only 5 · foot only 8 · cut off 10"),
    ("waiting", "Waiting time", 10, 10, "+2 per day (cap 10)"),
]


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

    def test_only_authorised_coordinator_roles_can_read_priority_rules(self):
        resident_client = Client()
        resident_client.force_login(self.resident)
        unattached_client = Client()
        unattached_client.force_login(self.unattached_responder)
        officer_client = Client()
        officer_client.force_login(self.officer)
        responder_client = Client()
        responder_client.force_login(self.responder)
        admin_client = Client()
        admin_client.force_login(self.admin)
        cases = (
            ("anonymous", self.client, 403),
            ("resident", resident_client, 403),
            ("unattached responder", unattached_client, 403),
            ("officer", officer_client, 200),
            ("organisation responder", responder_client, 200),
            ("administrator", admin_client, 200),
        )
        for actor, client, expected_status in cases:
            with self.subTest(actor=actor):
                self.assertEqual(client.get("/api/priority-rules/").status_code, expected_status)

    def test_response_lists_each_class_with_its_rule_and_sources(self):
        self.client.force_login(self.officer)
        data = self.client.get("/api/priority-rules/").json()

        self.assertEqual(data["version"], "classes-1.0")
        self.assertEqual([c["priority_class"] for c in data["classes"]], [1, 2, 3])
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
