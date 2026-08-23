"""Tests for self-registration and role application (ADR-012).

Traceability — requirements covered by this file:
  FR2  Applicants register and are verified before a role is granted
  FR20 Role-based permissions; privilege is never self-asserted

These cover the endpoint the registration screen posts to, including the
multipart path it switches to when an application carries documents.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import Organization, RegistrationDocument, UserAccount

S = UserAccount.VerificationStatus
R = UserAccount.Role

URL = "/api/auth/register/"

# A FileField writes to MEDIA_ROOT for real, so without this every test run
# would leave uploads behind in the working media/ directory.
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="highground-test-media-")


def a_pdf(name="registration.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake", content_type="application/pdf")


class ResidentRegistrationTests(TestCase):

    def test_a_resident_registers_without_review(self):
        """The ordinary path: no role asked for, so nothing to verify."""
        response = self.client.post(
            URL,
            {
                "full_name": "Siti binti Rahman",
                "email": "siti@test.my",
                "phone": "012-345 6789",
                "password": "Recovery2026",
                "password_confirm": "Recovery2026",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        user = UserAccount.objects.get(email="siti@test.my")
        self.assertEqual(user.role, R.COMMUNITY_MEMBER)
        self.assertEqual(user.verification_status, S.NOT_REQUIRED)
        self.assertIsNone(user.requested_role)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class RoleApplicationTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.org = Organization.objects.create(
            name="Mercy Relief", type=Organization.Type.NGO
        )

    def application(self, **overrides):
        payload = {
            "full_name": "Aisyah Tan",
            "email": "aisyah@test.my",
            "phone": "016-220 9931",
            "password": "Recovery2026",
            "password_confirm": "Recovery2026",
            "requested_role": R.NGO_VOLUNTEER,
            "organization": self.org.pk,
            "documents": a_pdf(),
        }
        payload.update(overrides)
        return payload

    def test_an_application_is_held_pending_and_grants_nothing(self):
        """The heart of ADR-012: asking for a role does not get you the role."""
        response = self.client.post(URL, self.application())
        self.assertEqual(response.status_code, 201)

        user = UserAccount.objects.get(email="aisyah@test.my")
        self.assertEqual(user.role, R.COMMUNITY_MEMBER)
        self.assertEqual(user.requested_role, R.NGO_VOLUNTEER)
        self.assertEqual(user.verification_status, S.PENDING)

    def test_the_uploaded_document_is_stored_against_the_applicant(self):
        """Evidence is the point of the review; it has to survive the request."""
        self.client.post(URL, self.application())

        user = UserAccount.objects.get(email="aisyah@test.my")
        self.assertEqual(RegistrationDocument.objects.filter(user=user).count(), 1)

    def test_an_application_without_documents_is_refused(self):
        """Nothing to check means nothing to approve."""
        payload = self.application()
        del payload["documents"]

        response = self.client.post(URL, payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("documents", response.json())
        self.assertFalse(UserAccount.objects.filter(email="aisyah@test.my").exists())

    def test_a_role_sent_in_the_request_body_is_ignored(self):
        """The privilege-escalation attempt this endpoint exists to close.

        A caller who posts role=system_admin directly must still come out a
        community_member — the granted role is decided by the view, never by
        the request.
        """
        response = self.client.post(
            URL, self.application(role=R.SYSTEM_ADMIN, is_staff=True, is_superuser=True)
        )
        self.assertEqual(response.status_code, 201)

        user = UserAccount.objects.get(email="aisyah@test.my")
        self.assertEqual(user.role, R.COMMUNITY_MEMBER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_system_admin_cannot_be_applied_for(self):
        """Not an offered choice, and the serializer refuses it outright."""
        response = self.client.post(
            URL, self.application(requested_role=R.SYSTEM_ADMIN)
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserAccount.objects.filter(email="aisyah@test.my").exists())
