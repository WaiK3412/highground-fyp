"""Phase 6 session and public endpoint permission checks."""

from django.test import Client, TestCase

from accounts.models import Organization, UserAccount
from .throttle_helpers import ThrottleTestCase


class AuthSecurityTests(ThrottleTestCase):
    def setUp(self):
        super().setUp()
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
            "password_confirm": "ValidTestPass2026", "consent": True,
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


class LoginThrottleTests(TestCase):
    """NFR3: repeated wrong passwords from one client are slowed down."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)

    def attempt(self, **headers):
        return self.client.post(
            "/api/auth/login/", {"email": "nobody@example.my", "password": "wrong"},
            content_type="application/json", **headers,
        )

    def test_eleventh_attempt_in_a_minute_is_refused(self):
        from unittest.mock import patch
        from rest_framework.throttling import SimpleRateThrottle

        with patch.object(SimpleRateThrottle, "timer", return_value=1000):
            responses = [self.attempt() for _ in range(11)]
            self.assertEqual([r.status_code for r in responses[:10]], [401] * 10)
            self.assertEqual(responses[10].status_code, 429)
            self.assertTrue(responses[10].json()["detail"].startswith("Request was throttled."))
            self.assertEqual(responses[10]["Retry-After"], "60")
            changed_email = self.client.post(
                "/api/auth/login/", {"email": "another@example.my", "password": "wrong"},
                content_type="application/json",
            )
            self.assertEqual(changed_email.status_code, 429)
            # IPs have separate counters; changing email does not reset one.
            self.assertEqual(self.attempt(REMOTE_ADDR="192.0.2.2").status_code, 401)
        with patch.object(SimpleRateThrottle, "timer", return_value=1061):
            self.assertEqual(self.attempt().status_code, 401)


class RegisterThrottleTests(TestCase):
    """NFR3: public account creation has its own per-client request limit."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)

    def test_sixth_registration_attempt_is_refused(self):
        from unittest.mock import patch
        from rest_framework.throttling import SimpleRateThrottle

        with patch.object(SimpleRateThrottle, "timer", return_value=1000):
            responses = [self.client.post("/api/auth/register/", {}, content_type="application/json")
                         for _ in range(6)]
            self.assertEqual([r.status_code for r in responses[:5]], [400] * 5)
            self.assertEqual(responses[5].status_code, 429)
            self.assertTrue(responses[5].json()["detail"].startswith("Request was throttled."))
            self.assertEqual(responses[5]["Retry-After"], "60")
            # Registration requests cannot consume the login allowance.
            login = self.client.post(
                "/api/auth/login/", {"email": "nobody@example.my", "password": "wrong"},
                content_type="application/json",
            )
            self.assertEqual(login.status_code, 401)


class SettingsDefaultTests(TestCase):
    """NFR3: deployments must explicitly opt into development debug mode."""

    def test_debug_is_off_when_the_variable_is_missing(self):
        import os
        import subprocess
        import sys

        env = {key: value for key, value in os.environ.items() if key != "DJANGO_DEBUG"}
        env["DJANGO_SETTINGS_MODULE"] = "config.settings"
        # Mock dotenv before settings import: local development values must
        # not hide the real default, and the subprocess must not read .env.
        code = (
            "from unittest.mock import patch\n"
            "with patch('dotenv.load_dotenv'):\n"
            "    import django\n"
            "    django.setup()\n"
            "    from django.conf import settings\n"
            "    print(settings.DEBUG)\n"
        )
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                             text=True, check=True)
        self.assertEqual(out.stdout.strip(), "False")
