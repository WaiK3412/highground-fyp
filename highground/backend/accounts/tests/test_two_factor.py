"""Two-factor sign-in for staff with an authenticator app (ADR-026).

Requirement covered: officers, NGO responders and administrators enter a code
from an authenticator app after their password, in the app and in the Django
admin; a password alone gives a staff account no access. Residents sign in with
their password only.
"""

import re
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import UserAccount
from accounts.two_factor import PENDING_KEY
from .throttle_helpers import ThrottleTestCase

PASSWORD = "Recovery2026"


def code_for(device):
    return f"{totp(device.bin_key):06d}"


@override_settings(TWO_FACTOR_REQUIRED=True, EMAIL_SKIP_DOMAINS=set())
class TwoFactorTests(ThrottleTestCase):
    def setUp(self):
        super().setUp()
        self.resident = UserAccount.objects.create_user(
            email="resident@example.my", full_name="Resident", password=PASSWORD
        )
        self.officer = UserAccount.objects.create_user(
            email="officer@example.my", full_name="Officer", password=PASSWORD,
            role=UserAccount.Role.DISASTER_OFFICER,
        )

    def login(self, user):
        return self.client.post(
            "/api/auth/login/", {"email": user.email, "password": PASSWORD}, content_type="application/json"
        )

    def verify(self, code):
        return self.client.post("/api/auth/two-factor/verify/", {"code": code}, content_type="application/json")

    def setup(self):
        return self.client.post("/api/auth/two-factor/setup/", content_type="application/json")

    def enrolled(self, user):
        return TOTPDevice.objects.create(user=user, name="Authenticator app", confirmed=True)

    def test_resident_signs_in_with_password_only(self):
        response = self.login(self.resident)
        self.assertEqual(response.json()["email"], self.resident.email)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_staff_password_alone_gives_no_access(self):
        response = self.login(self.officer)
        self.assertEqual(response.json(), {"two_factor": "setup"})
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
        self.assertEqual(self.client.get("/api/cases/").status_code, 403)

    def test_setup_then_valid_code_signs_in(self):
        self.login(self.officer)
        setup = self.setup().json()
        self.assertTrue(setup["qr_data_uri"].startswith("data:image/svg+xml;base64,"))
        self.assertRegex(setup["setup_key"], r"^[A-Z2-7]+$")
        device = TOTPDevice.objects.get(user=self.officer)
        self.assertFalse(device.confirmed)

        response = self.verify(code_for(device))
        self.assertEqual(response.json()["email"], self.officer.email)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertNotIn(PENDING_KEY, self.client.session)

    def test_opening_setup_with_get_creates_nothing(self):
        # Creating the device is a change, so it needs a POST (and the CSRF token).
        self.login(self.officer)
        self.assertEqual(self.client.get("/api/auth/two-factor/setup/").status_code, 405)
        self.assertFalse(TOTPDevice.objects.filter(user=self.officer).exists())

    def test_confirmed_device_goes_straight_to_verify(self):
        device = self.enrolled(self.officer)
        self.assertEqual(self.login(self.officer).json(), {"two_factor": "verify"})
        self.assertEqual(self.setup().status_code, 409)
        self.assertEqual(self.verify(code_for(device)).status_code, 200)

    def test_wrong_or_reused_code_is_refused(self):
        # Valid first: after a failure django-otp makes the device wait before the next try.
        device = self.enrolled(self.officer)
        self.login(self.officer)
        code = code_for(device)
        self.assertEqual(self.verify(code).status_code, 200)
        self.client.logout()
        self.login(self.officer)
        reused = self.verify(code)  # each code works once
        self.assertEqual((reused.status_code, reused.json()["code"]), (400, "invalid_code"))
        wrong = self.verify("000000" if code != "000000" else "111111")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_pending_marker_expires_after_five_minutes(self):
        device = self.enrolled(self.officer)
        self.login(self.officer)
        session = self.client.session
        session[PENDING_KEY]["at"] -= 5 * 60 + 1
        session.save()
        response = self.verify(code_for(device))
        self.assertEqual((response.status_code, response.json()["code"]), (403, "pending_expired"))

    def test_setup_and_verify_require_a_pending_login(self):
        self.assertEqual(self.setup().status_code, 403)
        self.assertEqual(self.verify("123456").status_code, 403)

    def test_unverified_staff_session_counts_as_signed_out(self):
        self.client.force_login(self.officer)  # e.g. a session from before this change
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_admin_site_requires_the_code(self):
        admin = UserAccount.objects.create_superuser(email="admin@example.my", full_name="Admin", password=PASSWORD)
        self.client.force_login(admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_verified_admin_reaches_the_admin_site(self):
        admin = UserAccount.objects.create_superuser(email="admin@example.my", full_name="Admin", password=PASSWORD)
        device = self.enrolled(admin)
        self.login(admin)
        self.verify(code_for(device))
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_password_reset_does_not_bypass_two_factor(self):
        self.enrolled(self.officer)
        self.client.post("/api/auth/password-reset/", {"email": self.officer.email}, content_type="application/json")
        uid, token = re.search(r"/reset-password/([^/\s]+)/([^/\s]+)", mail.outbox[-1].body).groups()
        self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password1": "Another2026pass", "new_password2": "Another2026pass"},
            content_type="application/json",
        )
        response = self.client.post(
            "/api/auth/login/", {"email": self.officer.email, "password": "Another2026pass"},
            content_type="application/json",
        )
        self.assertEqual(response.json(), {"two_factor": "verify"})
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_reset_two_factor_command_removes_devices(self):
        self.enrolled(self.officer)
        call_command("reset_two_factor", self.officer.email, stdout=StringIO())
        self.assertFalse(TOTPDevice.objects.filter(user=self.officer).exists())
        self.assertEqual(self.login(self.officer).json(), {"two_factor": "setup"})

    def test_verify_is_throttled(self):
        self.enrolled(self.officer)
        self.login(self.officer)
        statuses = [self.verify("000000").status_code for _ in range(6)]
        self.assertEqual(statuses[-1], 429)


@override_settings(TWO_FACTOR_REQUIRED=True)
class ResidentOptInTests(ThrottleTestCase):
    """Residents may switch two-step sign-in on for themselves; staff cannot switch it off."""

    def setUp(self):
        super().setUp()
        self.resident = UserAccount.objects.create_user(
            email="resident@example.my", full_name="Resident", password=PASSWORD
        )
        self.client.force_login(self.resident)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, content_type="application/json")

    def enable(self):
        setup = self.post("/api/auth/two-factor/enable/").json()
        device = TOTPDevice.objects.get(user=self.resident)
        response = self.post("/api/auth/two-factor/enable/confirm/", {"code": code_for(device)})
        return setup, device, response

    def test_status_starts_off_and_optional(self):
        self.assertEqual(self.client.get("/api/auth/two-factor/").json(), {"enabled": False, "required": False})

    def test_turning_it_on_keeps_this_session_signed_in(self):
        setup, device, response = self.enable()
        self.assertTrue(setup["qr_data_uri"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual(response.json(), {"enabled": True, "required": False})
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_once_on_the_next_sign_in_needs_a_code(self):
        self.enable()
        self.client.logout()
        response = self.client.post(
            "/api/auth/login/", {"email": self.resident.email, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.json(), {"two_factor": "verify"})
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_wrong_code_does_not_turn_it_on(self):
        self.post("/api/auth/two-factor/enable/")
        response = self.post("/api/auth/two-factor/enable/confirm/", {"code": "000000"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TOTPDevice.objects.filter(user=self.resident, confirmed=True).exists())

    def test_turning_it_off_needs_a_current_code(self):
        _, device, _ = self.enable()
        refused = self.post("/api/auth/two-factor/disable/", {"code": "000000"})
        self.assertEqual(refused.status_code, 400)
        self.assertTrue(TOTPDevice.objects.filter(user=self.resident).exists())

    def test_turning_it_off_with_a_new_code(self):
        _, device, _ = self.enable()
        device.refresh_from_db()
        device.last_t -= 1  # let the next code in this 30-second window count as new
        device.save()
        response = self.post("/api/auth/two-factor/disable/", {"code": code_for(device)})
        self.assertEqual(response.json(), {"enabled": False, "required": False})
        self.assertFalse(TOTPDevice.objects.filter(user=self.resident).exists())

    def test_staff_cannot_turn_it_off(self):
        officer = UserAccount.objects.create_user(
            email="officer@example.my", full_name="Officer", password=PASSWORD,
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        device = TOTPDevice.objects.create(user=officer, name="Authenticator app", confirmed=True)
        self.client.logout()
        self.client.post("/api/auth/login/", {"email": officer.email, "password": PASSWORD}, content_type="application/json")
        self.post("/api/auth/two-factor/verify/", {"code": code_for(device)})
        self.assertEqual(self.client.get("/api/auth/two-factor/").json(), {"enabled": True, "required": True})
        response = self.post("/api/auth/two-factor/disable/", {"code": code_for(device)})
        self.assertEqual(response.status_code, 403)

    def test_settings_need_a_signed_in_account(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/auth/two-factor/").status_code, 403)
        self.assertEqual(self.post("/api/auth/two-factor/enable/").status_code, 403)
