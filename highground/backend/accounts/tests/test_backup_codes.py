"""Backup codes for two-step sign-in (ADR-028).

Requirement covered: someone who has lost or broken the phone with their
authenticator app can still sign in, once per code, with one of ten backup
codes shown when two-step sign-in was set up. Codes are stored only as
hashes, and a new set replaces the old one.
"""

from io import StringIO

from django.core.management import call_command
from django.test import override_settings
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import BackupCode, UserAccount
from accounts.two_factor import new_backup_codes
from .throttle_helpers import ThrottleTestCase

PASSWORD = "Recovery2026"


def code_for(device):
    return f"{totp(device.bin_key):06d}"


@override_settings(TWO_FACTOR_REQUIRED=True)
class BackupCodeTests(ThrottleTestCase):
    def setUp(self):
        super().setUp()
        self.officer = UserAccount.objects.create_user(
            email="officer@example.my", full_name="Officer", password=PASSWORD,
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        self.device = TOTPDevice.objects.create(user=self.officer, name="Authenticator app", confirmed=True)

    def post(self, url, data=None):
        return self.client.post(url, data or {}, content_type="application/json")

    def login(self):
        return self.post("/api/auth/login/", {"email": self.officer.email, "password": PASSWORD})

    def verify_backup(self, code):
        return self.post("/api/auth/two-factor/verify/", {"backup_code": code})

    def test_a_backup_code_signs_in_once(self):
        codes = new_backup_codes(self.officer)
        self.login()
        response = self.verify_backup(codes[0])
        self.assertEqual(response.json()["email"], self.officer.email)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

        self.client.logout()
        self.login()
        reused = self.verify_backup(codes[0])
        self.assertEqual((reused.status_code, reused.json()["code"]), (400, "invalid_code"))
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

    def test_capitals_spaces_and_dashes_are_ignored(self):
        code = new_backup_codes(self.officer)[0]
        self.login()
        response = self.verify_backup(" " + code.upper().replace("-", " ") + " ")
        self.assertEqual(response.status_code, 200)

    def test_wrong_code_is_refused(self):
        new_backup_codes(self.officer)
        self.login()
        self.assertEqual(self.verify_backup("aaaaa-aaaaa").status_code, 400)
        self.assertEqual(BackupCode.objects.filter(user=self.officer).count(), 10)

    def test_another_accounts_code_is_refused(self):
        other = UserAccount.objects.create_user(email="other@example.my", full_name="Other", password=PASSWORD)
        code = new_backup_codes(other)[0]
        self.login()
        self.assertEqual(self.verify_backup(code).status_code, 400)

    def test_backup_code_cannot_skip_first_setup(self):
        # Codes left from an app that an administrator removed (lost phone).
        code = new_backup_codes(self.officer)[0]
        self.device.delete()
        self.assertEqual(self.login().json(), {"two_factor": "setup"})
        self.assertEqual(self.verify_backup(code).status_code, 400)

    def test_backup_code_needs_a_pending_login(self):
        code = new_backup_codes(self.officer)[0]
        self.assertEqual(self.verify_backup(code).status_code, 403)

    def test_only_salted_hashes_are_stored(self):
        codes = new_backup_codes(self.officer)
        self.assertRegex(codes[0], r"^[a-z2-9]{5}-[a-z2-9]{5}$")
        rows = BackupCode.objects.filter(user=self.officer)
        stored = set(rows.values_list("code_hash", flat=True))
        self.assertEqual(len(stored), 10)
        self.assertFalse(any(code.replace("-", "") in h for code in codes for h in stored))
        # NIST SP 800-63B-4 3.1.2.2: a salt of at least 32 bits, stored with each hash.
        salts = set(rows.values_list("salt", flat=True))
        self.assertEqual(len(salts), 1)
        self.assertGreaterEqual(len(salts.pop()), 22)

    def test_each_account_gets_its_own_salt(self):
        other = UserAccount.objects.create_user(email="other@example.my", full_name="Other", password=PASSWORD)
        new_backup_codes(self.officer)
        new_backup_codes(other)
        self.assertEqual(BackupCode.objects.values("salt").distinct().count(), 2)

    def test_first_setup_shows_ten_codes(self):
        self.device.delete()
        self.login()
        self.post("/api/auth/two-factor/setup/")
        device = TOTPDevice.objects.get(user=self.officer)
        response = self.post("/api/auth/two-factor/verify/", {"code": code_for(device)})
        self.assertEqual(len(response.json()["backup_codes"]), 10)
        self.assertEqual(BackupCode.objects.filter(user=self.officer).count(), 10)

    def test_later_sign_ins_show_no_codes(self):
        self.login()
        response = self.post("/api/auth/two-factor/verify/", {"code": code_for(self.device)})
        self.assertNotIn("backup_codes", response.json())

    def test_new_codes_replace_the_old_ones(self):
        old = new_backup_codes(self.officer)
        self.login()
        self.post("/api/auth/two-factor/verify/", {"code": code_for(self.device)})
        self.device.refresh_from_db()
        self.device.last_t -= 1  # let the next code in this 30-second window count as new
        self.device.save()
        response = self.post("/api/auth/two-factor/backup-codes/", {"code": code_for(self.device)})
        self.assertEqual(response.json()["backup_codes_left"], 10)
        new = response.json()["backup_codes"]
        self.assertFalse(set(old) & set(new))

        self.client.logout()
        self.login()
        self.assertEqual(self.verify_backup(old[1]).status_code, 400)
        self.assertEqual(self.verify_backup(new[1]).status_code, 200)

    def test_new_codes_need_a_current_app_code(self):
        new_backup_codes(self.officer)
        self.login()
        self.post("/api/auth/two-factor/verify/", {"code": code_for(self.device)})
        response = self.post("/api/auth/two-factor/backup-codes/", {"code": "000000"})
        self.assertEqual(response.status_code, 400)

    def test_new_codes_need_a_signed_in_account(self):
        self.assertEqual(self.post("/api/auth/two-factor/backup-codes/", {"code": "123456"}).status_code, 403)

    def test_status_counts_the_codes_left(self):
        codes = new_backup_codes(self.officer)
        self.login()
        self.verify_backup(codes[0])
        self.assertEqual(self.client.get("/api/auth/two-factor/").json()["backup_codes_left"], 9)

    def test_reset_two_factor_command_removes_backup_codes(self):
        new_backup_codes(self.officer)
        call_command("reset_two_factor", self.officer.email, stdout=StringIO())
        self.assertFalse(BackupCode.objects.filter(user=self.officer).exists())

    def test_backup_code_attempts_are_throttled(self):
        self.login()
        statuses = [self.verify_backup("aaaaa-aaaaa").status_code for _ in range(6)]
        self.assertEqual(statuses[-1], 429)
