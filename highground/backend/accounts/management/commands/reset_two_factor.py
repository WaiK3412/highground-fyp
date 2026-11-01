"""Remove someone's authenticator app (lost phone), so their next sign-in sets up a new one."""

from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import UserAccount
from accounts.two_factor import remove_two_factor


class Command(BaseCommand):
    help = "Remove an account's authenticator app and backup codes so the next sign-in sets up a new one (ADR-026)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="The account's email address")

    def handle(self, *args, **options):
        user = UserAccount.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("No account uses that email address.")
        removed = TOTPDevice.objects.filter(user=user).count()
        remove_two_factor(user)
        self.stdout.write(self.style.SUCCESS(f"Removed {removed} authenticator device(s) and the backup codes for {user.email}."))
