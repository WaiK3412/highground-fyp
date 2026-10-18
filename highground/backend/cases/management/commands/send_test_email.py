"""Send one message through the configured email backend.

    python manage.py send_test_email you@example.com

Use before a demo to prove the SMTP settings in .env work. Prints which
backend accepted the message; never prints credentials.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.mail import is_placeholder_address


class Command(BaseCommand):
    help = "Send one test message through the configured email backend."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Address to send the test message to")

    def handle(self, *args, **options):
        to = options["to"].strip()
        try:
            validate_email(to)
        except ValidationError:
            raise CommandError(f"{to!r} is not a valid email address.")

        if is_placeholder_address(to):
            raise CommandError("That domain is reserved for placeholder addresses; choose a real inbox.")

        backend = settings.EMAIL_BACKEND.rsplit(".", 2)[-2]
        try:
            accepted = send_mail(
                "[HighGround] Test message",
                "This is a test message from HighGround. If you can read it, "
                "notification email is working.",
                settings.DEFAULT_FROM_EMAIL,
                [to],
                fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001 — report any failure the same way
            raise CommandError(f"Sending through the {backend} backend failed: {type(exc).__name__}")

        if accepted != 1:
            raise CommandError(f"The {backend} backend did not accept the test message.")

        self.stdout.write(self.style.SUCCESS(f"Accepted by the {backend} backend for {to}."))
        if backend == "console":
            self.stdout.write("Nothing left this machine: EMAIL_HOST is not set in .env.")
