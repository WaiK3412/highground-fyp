"""Password reset by email.

Requirement covered: a person who forgot their password can set a new one
through a one-time emailed link, without the reset form revealing whether an
email address has an account.
"""

import re

from django.conf import settings
from django.core import mail
from django.test import Client, override_settings

from accounts.models import UserAccount
from .throttle_helpers import ThrottleTestCase

SENT = {"detail": "If an account uses that address, we've emailed a link."}


@override_settings(EMAIL_SKIP_DOMAINS={"hg.my"})
class PasswordResetTests(ThrottleTestCase):
    def setUp(self):
        super().setUp()
        self.user = UserAccount.objects.create_user(
            email="siti@example.my", full_name="Siti", password="OldPassword2026"
        )

    def request_reset(self, email, **extra):
        return self.client.post(
            "/api/auth/password-reset/", {"email": email}, content_type="application/json", **extra
        )

    def link_parts(self):
        match = re.search(r"/reset-password/([^/\s]+)/([^/\s]+)", mail.outbox[-1].body)
        return match.group(1), match.group(2)

    def confirm(self, uid, token, password="NewPassword2026", again=None):
        return self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password1": password, "new_password2": again or password},
            content_type="application/json",
        )

    def test_known_email_gets_one_link(self):
        response = self.request_reset("Siti@Example.my")
        self.assertEqual(response.json(), SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f"{settings.APP_ORIGIN}/reset-password/", mail.outbox[0].body)

    def test_unknown_email_gets_the_same_answer_and_no_mail(self):
        response = self.request_reset("nobody@example.my")
        self.assertEqual((response.status_code, response.json()), (200, SENT))
        self.assertEqual(mail.outbox, [])

    def test_inactive_and_placeholder_accounts_get_no_mail(self):
        UserAccount.objects.create_user(email="gone@example.my", full_name="Gone", is_active=False, password="x")
        UserAccount.objects.create_user(email="demo@hg.my", full_name="Demo", password="x")
        for email in ("gone@example.my", "demo@hg.my"):
            with self.subTest(email=email):
                self.assertEqual(self.request_reset(email).json(), SENT)
        self.assertEqual(mail.outbox, [])

    @override_settings(ALLOWED_HOSTS=["*"])  # let the forged host reach the view
    def test_link_ignores_the_request_host(self):
        self.request_reset(self.user.email, HTTP_HOST="evil.example")
        self.assertNotIn("evil.example", mail.outbox[0].body)

    def test_valid_link_sets_the_password(self):
        self.request_reset(self.user.email)
        response = self.confirm(*self.link_parts())
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword2026"))
        self.assertFalse(self.user.check_password("OldPassword2026"))

    def test_reset_link_also_confirms_the_email(self):
        # Opening a link sent to the inbox proves the address, just as the confirmation link does.
        self.user.email_confirmed = False
        self.user.save(update_fields=["email_confirmed"])
        self.request_reset(self.user.email)
        self.confirm(*self.link_parts())
        response = self.client.post(
            "/api/auth/login/", {"email": self.user.email, "password": "NewPassword2026"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_reused_or_tampered_link_is_refused(self):
        self.request_reset(self.user.email)
        uid, token = self.link_parts()
        self.confirm(uid, token)
        for attempt in ((uid, token), (uid, token[:-1] + "x"), ("bad", token)):
            with self.subTest(attempt=attempt):
                response = self.confirm(*attempt, password="Another2026pass")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_link")

    def test_weak_or_mismatched_password_is_refused(self):
        self.request_reset(self.user.email)
        uid, token = self.link_parts()
        for password, again in (("12345678", None), ("NewPassword2026", "Different2026x")):
            with self.subTest(password=password):
                response = self.confirm(uid, token, password, again)
                self.assertEqual(response.status_code, 400)
                self.assertIn("new_password2", response.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPassword2026"))

    def test_reset_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/api/auth/password-reset/", {"email": self.user.email})
        self.assertEqual(response.status_code, 403)

    def test_reset_is_throttled(self):
        statuses = [self.request_reset("nobody@example.my").status_code for _ in range(6)]
        self.assertEqual(statuses[-1], 429)
