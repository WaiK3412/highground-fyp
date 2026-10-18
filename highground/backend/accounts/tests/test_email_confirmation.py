"""Email confirmation at sign-up (ADR-026).

Requirement covered: a new account confirms its email address before it can
sign in, and registration no longer reveals whether an address is taken.
"""

import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import override_settings

from accounts.models import UserAccount
from accounts.tokens import make_confirmation_token
from .throttle_helpers import ThrottleTestCase

CHECK_EMAIL = {"detail": "Check your email to confirm your account."}
RESENT = {"detail": "If that address needs confirming, we've emailed a new link."}


def form(email="new@example.my", **overrides):
    data = {
        "full_name": "New Resident", "email": email, "phone": "012-000 0000",
        "password": "Recovery2026", "password_confirm": "Recovery2026",
    }
    data.update(overrides)
    return data


@override_settings(EMAIL_SKIP_DOMAINS=set())
class EmailConfirmationTests(ThrottleTestCase):
    def register(self, **overrides):
        return self.client.post("/api/auth/register/", form(**overrides), content_type="application/json")

    def login(self, email="new@example.my", password="Recovery2026"):
        return self.client.post(
            "/api/auth/login/", {"email": email, "password": password}, content_type="application/json"
        )

    def confirm(self, token):
        return self.client.post("/api/auth/confirm-email/", {"token": token}, content_type="application/json")

    def token_from_email(self):
        return re.search(r"/confirm-email/(\S+)", mail.outbox[-1].body).group(1)

    def test_new_and_taken_addresses_get_the_same_answer(self):
        UserAccount.objects.create_user(email="taken@example.my", full_name="Owner", password="x")
        new = self.register()
        taken = self.register(email="Taken@example.my")
        self.assertEqual((new.status_code, new.json()), (202, CHECK_EMAIL))
        self.assertEqual((taken.status_code, taken.json()), (202, CHECK_EMAIL))
        self.assertEqual(UserAccount.objects.filter(email__iexact="taken@example.my").count(), 1)
        to_owner = [m for m in mail.outbox if m.to == ["taken@example.my"]]
        self.assertEqual(len(to_owner), 1)
        self.assertIn("tried to create", to_owner[0].body)
        self.assertNotIn("/confirm-email/", to_owner[0].body)

    def test_new_account_gets_a_confirmation_link(self):
        self.register()
        self.assertIn(f"{settings.APP_ORIGIN}/confirm-email/", mail.outbox[-1].body)

    def test_unconfirmed_sign_in_is_refused_with_code(self):
        self.register()
        response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "email_unconfirmed")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_wrong_password_still_says_nothing_about_confirmation(self):
        self.register()
        response = self.login(password="WrongPassword1")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("code", response.json())

    def test_valid_link_confirms_the_account(self):
        self.register()
        response = self.confirm(self.token_from_email())
        self.assertEqual(response.json(), {"detail": "Email confirmed. You can now log in."})
        self.assertTrue(UserAccount.objects.get(email="new@example.my").email_confirmed)
        self.assertEqual(self.login().status_code, 200)

    def test_expired_tampered_or_reset_token_is_refused(self):
        self.register()
        user = UserAccount.objects.get(email="new@example.my")
        token = self.token_from_email()
        with patch("accounts.tokens.MAX_AGE", -1):
            expired = self.confirm(token)
        for response in (expired, self.confirm(token[:-2] + "xx"), self.confirm(default_token_generator.make_token(user))):
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_link")
        user.refresh_from_db()
        self.assertFalse(user.email_confirmed)

    def test_token_stops_working_if_the_email_changes(self):
        self.register()
        user = UserAccount.objects.get(email="new@example.my")
        token = make_confirmation_token(user)
        user.email = "changed@example.my"
        user.save()
        self.assertEqual(self.confirm(token).status_code, 400)

    def test_resend_gives_the_same_answer_and_mails_only_unconfirmed(self):
        self.register()
        UserAccount.objects.create_user(email="done@example.my", full_name="Done", password="x")
        mail.outbox.clear()
        for email in ("new@example.my", "done@example.my", "nobody@example.my"):
            with self.subTest(email=email):
                response = self.client.post(
                    "/api/auth/confirm-email/resend/", {"email": email}, content_type="application/json"
                )
                self.assertEqual(response.json(), RESENT)
        self.assertEqual([m.to for m in mail.outbox], [["new@example.my"]])

    def test_application_still_waits_for_an_administrator_after_confirming(self):
        from accounts.models import Organization
        from django.core.files.uploadedfile import SimpleUploadedFile

        org = Organization.objects.create(name="Mercy Relief", type=Organization.Type.NGO)
        pdf = SimpleUploadedFile("letter.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        with self.settings(MEDIA_ROOT=self.media_root()):
            self.client.post("/api/auth/register/", {
                **form(), "requested_role": UserAccount.Role.NGO_VOLUNTEER,
                "organization": org.pk, "documents": pdf,
            })
        self.confirm(self.token_from_email())
        user = UserAccount.objects.get(email="new@example.my")
        self.assertEqual(user.role, UserAccount.Role.COMMUNITY_MEMBER)
        self.assertEqual(user.verification_status, UserAccount.VerificationStatus.PENDING)

    def test_existing_accounts_are_confirmed(self):
        user = UserAccount.objects.create_user(email="old@example.my", full_name="Old", password="Recovery2026")
        self.assertTrue(user.email_confirmed)
        self.assertEqual(self.login("old@example.my").status_code, 200)

    def media_root(self):
        import shutil
        import tempfile

        path = tempfile.mkdtemp(prefix="highground-test-media-")
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path
