"""Phase 6 session and public endpoint permission checks."""

from django.test import Client, TestCase

from accounts.models import Organization, UserAccount


class AuthSecurityTests(TestCase):
    def setUp(self):
        self.resident = UserAccount.objects.create_user(
            email="resident@example.test", full_name="Resident",
            password="ValidTestPass2026",
        )

    def test_login_requires_csrf_even_before_authentication(self):
        client = Client(enforce_csrf_checks=True)
        body = {"email": self.resident.email, "password": "ValidTestPass2026"}
        self.assertEqual(client.post("/api/auth/login/", body).status_code, 403)
        client.get("/api/auth/csrf/")
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post("/api/auth/login/", body, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code, 204)
        self.assertIn(client.get("/api/auth/me/").status_code, (401, 403))

    def test_register_requires_csrf_and_bad_login_shape_is_validation_error(self):
        client = Client(enforce_csrf_checks=True)
        form = {
            "full_name": "Second Resident", "email": "second@example.test",
            "phone": "012-000 0000", "password": "ValidTestPass2026",
            "password_confirm": "ValidTestPass2026",
        }
        self.assertEqual(client.post("/api/auth/register/", form).status_code, 403)
        self.assertFalse(UserAccount.objects.filter(email=form["email"]).exists())
        self.assertEqual(self.client.post("/api/auth/login/", {"email": ["bad"], "password": []}, content_type="application/json").status_code, 400)

    def test_public_directory_is_thin_and_other_roles_cannot_submit_cases(self):
        Organization.objects.create(name="Relief", type=Organization.Type.NGO, contact_no="PRIVATE")
        directory = self.client.get("/api/organizations/")
        self.assertEqual(directory.status_code, 200)
        self.assertNotIn("PRIVATE", str(directory.json()))
        for role in (UserAccount.Role.DISASTER_OFFICER, UserAccount.Role.NGO_VOLUNTEER, UserAccount.Role.SYSTEM_ADMIN):
            user = UserAccount.objects.create_user(
                email=f"{role}@example.test", full_name=role, password="ValidTestPass2026", role=role
            )
            self.client.force_login(user)
            self.assertEqual(self.client.post("/api/cases/", {}, content_type="application/json").status_code, 403)
