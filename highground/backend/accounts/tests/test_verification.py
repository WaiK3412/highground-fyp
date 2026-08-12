"""Tests for role-application approval and rejection (ADR-012).

Traceability — requirements covered by this file:
  FR2  Applicants register and are verified before a role is granted
  FR20 Role-based permissions; privilege is never self-asserted
"""

from django.test import TestCase

from accounts.models import UserAccount

S = UserAccount.VerificationStatus
R = UserAccount.Role


class VerificationTestCase(TestCase):
    """Shared setup: one admin who decides, one applicant awaiting a decision."""

    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            email="admin@test.my",
            full_name="Admin",
            password="Recovery2026",
            role=R.SYSTEM_ADMIN,
        )
        self.applicant = UserAccount.objects.create_user(
            email="aisyah@test.my",
            full_name="Aisyah Tan",
            password="Recovery2026",
            requested_role=R.NGO_VOLUNTEER,
            verification_status=S.PENDING,
        )


class ApprovalTests(VerificationTestCase):

    def test_approving_grants_the_requested_role(self):
        # ARRANGE — setUp() already made a pending applicant. Assert the
        # starting point, so a broken setUp can't make the test pass by luck.
        self.assertEqual(self.applicant.role, R.COMMUNITY_MEMBER)

        # ACT — the one thing under test
        self.applicant.approve_application(admin=self.admin, note="Docs verified.")

        # ASSERT — reload from the database, so we test what was SAVED rather
        # than what happens to be sitting in memory
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.role, R.NGO_VOLUNTEER)
        self.assertEqual(self.applicant.verification_status, S.VERIFIED)
        self.assertEqual(self.applicant.verified_by_user, self.admin)
        self.assertIsNotNone(self.applicant.verified_at)

    # ---- yours ----

    def test_approving_twice_is_refused(self):
        """A decided application cannot be decided again."""
        self.applicant.approve_application(admin=self.admin)

        with self.assertRaises(ValueError):
            self.applicant.approve_application(admin=self.admin)

    def test_an_ordinary_resident_cannot_be_approved(self):
        """Someone who never applied has nothing to approve, so approval cannot
        be used as a back door to hand a resident a role."""
        resident = UserAccount.objects.create_user(
            email="siti@test.my", full_name="Siti", password="Recovery2026",
        )
        self.assertEqual(resident.verification_status, S.NOT_REQUIRED)

        with self.assertRaises(ValueError):
            resident.approve_application(admin=self.admin)

        resident.refresh_from_db()
        self.assertEqual(resident.role, R.COMMUNITY_MEMBER)


class RejectionTests(VerificationTestCase):

    def test_rejecting_requires_a_reason(self):
        """A refused applicant is owed an explanation, and the guard must stop
        the rejection before anything is written."""
        with self.assertRaises(ValueError):
            self.applicant.reject_application(admin=self.admin, note="")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.verification_status, S.PENDING)

    def test_rejecting_leaves_the_role_untouched(self):
        """The security assertion: a rejected applicant stays least-privileged.

        Reject with a real note, then check role is still COMMUNITY_MEMBER,
        status is REJECTED, and the note was stored.
        """
        note = "False documents"

        self.applicant.reject_application(admin=self.admin,note = note)

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.role, R.COMMUNITY_MEMBER)
        self.assertEqual(self.applicant.verification_status, S.REJECTED)
        self.assertEqual(self.applicant.verification_note,note)
