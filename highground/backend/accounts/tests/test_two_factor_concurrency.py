"""Two setup requests at the same moment (a double click, or React running an
effect twice in development) must leave one authenticator device, not two; and
one backup code sent twice at the same moment must sign in only once."""

from django.test import Client, TransactionTestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import BackupCode, UserAccount
from accounts.two_factor import new_backup_codes, use_backup_code
from cases.tests.race_helpers import GazetteerReloadMixin, race


@override_settings(TWO_FACTOR_REQUIRED=True)
class SetupRaceTests(GazetteerReloadMixin, TransactionTestCase):
    def test_simultaneous_setup_requests_share_one_device(self):
        resident = UserAccount.objects.create_user(email="r@example.my", full_name="R", password="x")

        def start_setup():
            client = Client()
            client.force_login(resident)
            return client.post("/api/auth/two-factor/enable/").json()["setup_key"]

        keys = race(start_setup, start_setup)

        self.assertEqual(TOTPDevice.objects.filter(user=resident).count(), 1)
        self.assertEqual(keys[0], keys[1])

    def test_one_backup_code_sent_twice_at_once_works_once(self):
        # ADR-028: one DELETE both checks and spends the code.
        resident = UserAccount.objects.create_user(email="r@example.my", full_name="R", password="x")
        code = new_backup_codes(resident)[0]

        results = race(lambda: use_backup_code(resident, code), lambda: use_backup_code(resident, code))

        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(BackupCode.objects.filter(user=resident).count(), 9)
