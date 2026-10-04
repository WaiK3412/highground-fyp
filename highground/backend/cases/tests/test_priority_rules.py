"""Tests for the coordinator-facing "how priority works" endpoint.

Traceability:
  FR10 Coordinators can inspect the priority rules (classes-1.0) and sources
  FR20 Rule reads enforce role boundaries
"""
from django.test import Client, TestCase

from accounts.models import Organization, UserAccount


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
