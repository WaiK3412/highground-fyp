"""FR2: a signed-in user manages their own profile.

Email is the login identity and role is granted only by an admin (ADR-012),
so neither can be changed here.
"""

from django.test import TestCase

from accounts.models import UserAccount


class ProfileTests(TestCase):
    def setUp(self):
        self.user = UserAccount.objects.create_user(
            email="r@example.my", full_name="Old Name", password="Recovery2026", phone="011-1"
        )
        self.client.force_login(self.user)

    def patch(self, data):
        return self.client.patch("/api/auth/me/", data, content_type="application/json")

    def test_name_and_phone_can_be_changed(self):
        response = self.patch({"full_name": "New Name", "phone": "012-3456789"})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.full_name, self.user.phone), ("New Name", "012-3456789"))
        self.assertEqual(response.json()["phone"], "012-3456789")

    def test_email_and_role_are_ignored(self):
        self.patch({"email": "x@example.my", "role": "disaster_officer"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "r@example.my")
        self.assertEqual(self.user.role, UserAccount.Role.COMMUNITY_MEMBER)

    def test_invalid_profile_fields_are_refused_without_saving(self):
        cases = (
            ("blank name", {"full_name": "  "}, 400),
            ("blank phone", {"phone": " "}, 400),
            ("overlong phone", {"phone": "1" * 21}, 400),
            ("overlong name", {"full_name": "x" * 101}, 400),
        )
        for value, payload, expected_status in cases:
            with self.subTest(value=value):
                self.assertEqual(self.patch(payload).status_code, expected_status)
        self.user.refresh_from_db()
        self.assertEqual((self.user.full_name, self.user.phone), ("Old Name", "011-1"))

    def test_anonymous_cannot_patch(self):
        self.client.logout()
        self.assertIn(self.patch({"full_name": "x"}).status_code, {401, 403})

    def test_each_signed_in_role_can_edit_its_own_profile(self):
        for role in UserAccount.Role:
            with self.subTest(role=role):
                UserAccount.objects.filter(pk=self.user.pk).update(role=role)
                self.assertEqual(self.patch({"full_name": "Updated Name"}).status_code, 200)

    def test_phone_is_available_when_loading_the_session(self):
        self.assertEqual(self.client.get("/api/auth/me/").json()["phone"], "011-1")

    def test_ownership_and_privilege_fields_are_ignored(self):
        other = UserAccount.objects.create_user(email="other@example.my", full_name="Other")
        self.patch({"id": other.pk, "full_name": "Changed", "is_staff": True,
                    "is_superuser": True, "organization": 999, "verification_status": "verified"})
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(other.full_name, "Other")
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertIsNone(self.user.organization_id)
        self.assertEqual(self.user.verification_status, UserAccount.VerificationStatus.NOT_REQUIRED)
