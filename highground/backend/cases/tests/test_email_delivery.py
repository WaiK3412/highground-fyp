"""Real email delivery (FR11, user decision 3 Oct 2026).

Placeholder demo addresses are never mailed; the test command reports
success or the backend's error without exposing credentials.
"""

from io import StringIO
import os
from pathlib import Path
import runpy
from unittest.mock import patch

from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import UserAccount
from cases.models import CaseEventLog, CaseRecord
from cases.notifications import notify


class FailingBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("mail server unreachable")


@override_settings(EMAIL_SKIP_DOMAINS={"hg.my"})
class PlaceholderAddressTests(TestCase):
    def setUp(self):
        self.officer = UserAccount.objects.create_user(
            email="officer@hg.my", full_name="Officer", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER,
        )

    def make_case(self, resident_email):
        resident = UserAccount.objects.create_user(
            email=resident_email, full_name="Resident", password="Recovery2026"
        )
        case = CaseRecord.objects.create(
            reference=f"FRC-77{CaseRecord.objects.count():02d}", submitted_by_user=resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP, description="Mud.",
            village="Kg. Test", address="Lot 1", status=CaseRecord.Status.VERIFIED,
            created_at=timezone.now(),
        )
        CaseEventLog.objects.create(
            case=case, actor_user=self.officer, event_type=CaseEventLog.EventType.VERIFIED,
            detail="Verified.", created_at=timezone.now(),
        )
        return case

    def test_placeholder_domain_is_recorded_not_sent(self):
        case = self.make_case("resident@hg.my")
        rows = notify(case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(rows[0].delivery_status, "skipped_placeholder_address")

    def test_domain_match_is_case_insensitive(self):
        case = self.make_case("Resident2@HG.MY")
        notify(case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_real_domain_is_sent(self):
        case = self.make_case("household@gmail.com")
        rows = notify(case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["household@gmail.com"])
        self.assertEqual(rows[0].delivery_status, "sent")

    @override_settings(EMAIL_BACKEND="cases.tests.test_email_delivery.FailingBackend")
    def test_a_failed_send_keeps_the_in_app_notification(self):
        case = self.make_case("household@gmail.com")
        rows = notify(case, CaseEventLog.EventType.VERIFIED, self.officer)
        self.assertEqual(rows[0].delivery_status, "failed: ConnectionRefusedError")
        self.assertEqual(rows[0].recipient_user.email, "household@gmail.com")


class SendTestEmailCommandTests(TestCase):
    def test_sends_one_message(self):
        out = StringIO()
        call_command("send_test_email", "me@gmail.com", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["me@gmail.com"])
        self.assertIn("Accepted by", out.getvalue())

    @override_settings(EMAIL_BACKEND="cases.tests.test_email_delivery.FailingBackend")
    def test_reports_failure_as_a_command_error(self):
        with self.assertRaisesMessage(CommandError, "ConnectionRefusedError"):
            call_command("send_test_email", "me@gmail.com", stdout=StringIO())

    def test_rejects_an_invalid_address(self):
        with self.assertRaises(CommandError):
            call_command("send_test_email", "not-an-address", stdout=StringIO())

    def test_rejects_placeholder_domain_without_sending(self):
        with override_settings(EMAIL_SKIP_DOMAINS={"hg.my"}):
            with self.assertRaises(CommandError):
                call_command("send_test_email", "someone@HG.MY", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_backend_accepting_zero_messages_is_an_error(self):
        with patch("cases.management.commands.send_test_email.send_mail", return_value=0):
            with self.assertRaises(CommandError):
                call_command("send_test_email", "me@gmail.com", stdout=StringIO())

    def test_backend_exception_text_is_not_exposed(self):
        with patch("cases.management.commands.send_test_email.send_mail", side_effect=RuntimeError("sensitive backend detail")):
            with self.assertRaises(CommandError) as caught:
                call_command("send_test_email", "me@gmail.com", stdout=StringIO())
        self.assertIn("RuntimeError", str(caught.exception))
        self.assertNotIn("sensitive backend detail", str(caught.exception))


class EmailSettingsTests(SimpleTestCase):
    def settings_for(self, **overrides):
        environment = dict(SECRET_KEY="test-only-key", POSTGRES_DB="test", POSTGRES_USER="test",
                           POSTGRES_PASSWORD="test", DB_HOST="localhost", DB_PORT="5433")
        environment.update(overrides)
        # Exercise the settings source using synthetic values; never reload .env.
        with patch.dict(os.environ, environment, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(Path(__file__).resolve().parents[2] / "config" / "settings.py"))

    def test_port_587_uses_starttls_and_a_timeout(self):
        settings = self.settings_for(EMAIL_HOST="smtp.example.com", EMAIL_PORT="587")
        self.assertEqual(settings["EMAIL_BACKEND"], "django.core.mail.backends.smtp.EmailBackend")
        self.assertTrue(settings["EMAIL_USE_TLS"])
        self.assertFalse(settings["EMAIL_USE_SSL"])
        self.assertEqual(settings["EMAIL_TIMEOUT"], 10)

    def test_port_465_uses_implicit_tls_and_configurable_timeout(self):
        settings = self.settings_for(EMAIL_HOST="smtp.example.com", EMAIL_PORT="465", EMAIL_TIMEOUT="4")
        self.assertFalse(settings["EMAIL_USE_TLS"])
        self.assertTrue(settings["EMAIL_USE_SSL"])
        self.assertEqual(settings["EMAIL_TIMEOUT"], 4)

    def test_console_fallback_and_placeholder_domains_are_normalised(self):
        settings = self.settings_for(EMAIL_SKIP_DOMAINS=" HG.MY , example.invalid, ")
        self.assertEqual(settings["EMAIL_BACKEND"], "django.core.mail.backends.console.EmailBackend")
        self.assertEqual(settings["EMAIL_SKIP_DOMAINS"], {"hg.my", "example.invalid"})
