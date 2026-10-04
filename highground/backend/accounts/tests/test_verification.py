"""Tests for role-application approval and rejection (ADR-012).

Traceability — requirements covered by this file:
  FR2  Applicants register and are verified before a role is granted
  FR20 Role-based permissions; privilege is never self-asserted
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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

        self.applicant.approve_application(admin=self.admin, note="Docs verified.")

        # ASSERT — reload from the database, so we test what was SAVED rather
        # than what happens to be sitting in memory
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.role, R.NGO_VOLUNTEER)
        self.assertEqual(self.applicant.verification_status, S.VERIFIED)
        self.assertEqual(self.applicant.verified_by_user, self.admin)
        self.assertIsNotNone(self.applicant.verified_at)

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


class AdminRejectionTests(VerificationTestCase):
    """Rejection performed the way an admin actually performs one.

    Every other test in this file calls the model method directly. That is why
    the gap this class covers survived a green suite: reject_application() is
    correct, but nothing proved the admin change page ever reaches it.
    """

    def setUp(self):
        super().setUp()
        # role=system_admin does NOT get you into /admin/. The admin site checks
        # is_staff, which defaults to False. Without these flags the POST below
        # is redirected to the login page — also a 302 — so a status-code
        # assertion would go green without the form ever being touched.
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.admin)

    def change_url(self):
        return reverse("admin:accounts_useraccount_change", args=[self.applicant.pk])

    def form_payload(self, **overrides):
        """Every non-readonly field the change form renders.

        The admin validates the whole form, not just the fields under test, so
        omitting one makes the page re-render with errors and save nothing. The
        four readonly fields (created_at, last_login, verified_by_user,
        verified_at) are not rendered as inputs, so they are absent here.
        """
        payload = {
            "email": self.applicant.email,
            "full_name": self.applicant.full_name,
            "phone": "0123456789",
            "role": self.applicant.role,
            "organization": "",
            "requested_role": self.applicant.requested_role,
            "verification_status": S.PENDING,
            "verification_note": "",
            "is_active": "on",
            # An inline needs its management form even when it has no rows.
            "registration_documents-TOTAL_FORMS": "0",
            "registration_documents-INITIAL_FORMS": "0",
            "registration_documents-MIN_NUM_FORMS": "0",
            "registration_documents-MAX_NUM_FORMS": "1000",
        }
        payload.update(overrides)
        return payload

    def test_rejecting_through_the_admin_records_the_deciding_admin(self):
        """ADR-012 section 5: every decision is audit-logged, with the deciding
        admin recorded. A rejection saved straight to the column records nobody.
        """
        response = self.client.post(
            self.change_url(),
            self.form_payload(
                verification_status=S.REJECTED,
                verification_note="Documents could not be verified.",
            ),
        )
        # 200 here means the form bounced rather than saved; the reason is in
        # response.context["adminform"].form.errors
        self.assertEqual(response.status_code, 302, "the change form did not save")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.verification_status, S.REJECTED)
        self.assertEqual(self.applicant.verified_by_user, self.admin)
        self.assertIsNotNone(self.applicant.verified_at)

    def test_approving_through_the_admin_grants_the_role_and_records_the_admin(self):
        """The same routing must hold for the decision that grants privilege."""
        response = self.client.post(
            self.change_url(),
            self.form_payload(
                verification_status=S.VERIFIED,
                verification_note="Registration letter checked.",
            ),
        )
        self.assertEqual(response.status_code, 302, "the change form did not save")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.role, R.NGO_VOLUNTEER)
        self.assertEqual(self.applicant.verification_status, S.VERIFIED)
        self.assertEqual(self.applicant.verified_by_user, self.admin)

    def test_rejecting_without_a_reason_is_refused_by_the_form(self):
        """The blank-note guard must reach the admin as a field error.

        The model method raises ValueError, which from inside the admin would
        be a 500 page. 200 here means the form re-rendered with the error;
        302 would mean it saved.
        """
        response = self.client.post(
            self.change_url(),
            self.form_payload(verification_status=S.REJECTED, verification_note=""),
        )
        self.assertEqual(response.status_code, 200, "a blank reason was accepted")
        self.assertIn(
            "verification_note", response.context["adminform"].form.errors
        )

        # Nothing was written: the application is still awaiting a decision.
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.verification_status, S.PENDING)
        self.assertIsNone(self.applicant.verified_by_user)

    def test_an_unrelated_edit_made_in_the_same_save_is_kept(self):
        """Deciding and correcting a typo in one save must not lose the typo fix."""
        response = self.client.post(
            self.change_url(),
            self.form_payload(
                full_name="Aisyah binti Tan",
                verification_status=S.REJECTED,
                verification_note="Documents unreadable.",
            ),
        )
        self.assertEqual(response.status_code, 302, "the change form did not save")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.full_name, "Aisyah binti Tan")
        self.assertEqual(self.applicant.verification_status, S.REJECTED)
        self.assertEqual(self.applicant.verified_by_user, self.admin)


class AdminRevocationTests(AdminRejectionTests):
    """Rejecting someone who was already approved.

    The guards only recognise a decision when the applicant was pending, so
    this transition currently slips past both: it saves with no reason and
    leaves the granted role in place.
    """

    def setUp(self):
        super().setUp()


    def test_revoking_without_a_reason_is_refused(self):
        self.applicant.approve_application(admin=self.admin)
        self.applicant.refresh_from_db()

        response = self.client.post(
            self.change_url(),
            self.form_payload(
                verification_status=S.REJECTED,
                verification_note="",
            ),
        )
        self.assertEqual(response.status_code, 200, "the form should have been refused")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.verification_status, S.VERIFIED)
        self.assertEqual(self.applicant.role, R.NGO_VOLUNTEER)

    def test_revoking_removes_the_granted_role(self):
        self.applicant.approve_application(admin=self.admin)
        # Back-date the approval: approve and revoke can otherwise land on the
        # same clock tick, which made this assertion fail intermittently.
        old_verified_at = timezone.now() - timedelta(days=1)
        UserAccount.objects.filter(pk=self.applicant.pk).update(verified_at=old_verified_at)

        response = self.client.post(
            self.change_url(),
            self.form_payload(
                verification_status=S.REJECTED,
                verification_note="Licence expired.",
            ),
        )
        self.assertEqual(response.status_code, 302,"the change form did not save")

        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.verification_status, S.REJECTED)
        self.assertEqual(self.applicant.role, R.COMMUNITY_MEMBER)
        self.assertEqual(self.applicant.verified_by_user, self.admin)
        self.assertGreater(self.applicant.verified_at, old_verified_at)
