"""Remove someone's authenticator app (lost phone), so their next sign-in sets up a new one."""

from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import UserAccount


class Command(BaseCommand):
    help = "Remove an account's authenticator app so the next sign-in sets up a new one (ADR-026)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="The account's email address")

    def handle(self, *args, **options):
        user = UserAccount.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("No account uses that email address.")
        removed, _ = TOTPDevice.objects.filter(user=user).delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {removed} authenticator device(s) for {user.email}."))
