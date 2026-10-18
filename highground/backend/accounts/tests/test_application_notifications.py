"""Role-application notices (ADR-027).

Requirement covered: FR2. Administrators are emailed when an application is
waiting, and the applicant learns that it was approved, rejected or revoked,
in the app and by email, without having to notice that their screens changed.
"""

from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import UserAccount
from accounts.tokens import make_confirmation_token
from cases.models import CaseEventLog, LocationArea
from .throttle_helpers import ThrottleTestCase

S = UserAccount.VerificationStatus
R = UserAccount.Role
E = CaseEventLog.EventType


@override_settings(EMAIL_SKIP_DOMAINS={"hg.my"})
class ApplicationDecisionNotificationTests(TestCase):
    def setUp(self):
        self.admin = UserAccount.objects.create_user(
            email="admin@test.my", full_name="Admin", password="Recovery2026", role=R.SYSTEM_ADMIN
        )
        self.applicant = UserAccount.objects.create_user(
            email="aisyah@test.my", full_name="Aisyah Tan", password="Recovery2026",
            requested_role=R.NGO_VOLUNTEER, verification_status=S.PENDING,
        )

    def notifications(self, user):
        self.client.force_login(user)
        return self.client.get("/api/notifications/").json()

    def test_approval_notifies_in_app_and_by_email(self):
        self.applicant.approve_application(admin=self.admin)
        row = CaseEventLog.objects.get(recipient_user=self.applicant)
        self.assertEqual((row.event_type, row.actor_user, row.delivery_status), (E.APPLICATION_APPROVED, self.admin, "sent"))
        self.assertEqual(mail.outbox[0].to, ["aisyah@test.my"])
        self.assertIn("NGO volunteer application was approved", mail.outbox[0].subject)

        listed = self.notifications(self.applicant)
        self.assertEqual(listed["unread"], 1)
        item = listed["results"][0]
        self.assertEqual((item["case_id"], item["donation_id"]), (None, None))
        self.assertIn("approved", item["detail"])

    def test_rejection_and_revocation_carry_the_reason(self):
        self.applicant.reject_application(admin=self.admin, note="The letter is unsigned.")
        other = UserAccount.objects.create_user(
            email="farid@test.my", full_name="Farid", password="Recovery2026",
            requested_role=R.NGO_VOLUNTEER, verification_status=S.PENDING,
        )
        other.approve_application(admin=self.admin)
        other.revoke_approval(admin=self.admin, note="Left the organisation.")

        rejected = CaseEventLog.objects.get(recipient_user=self.applicant)
        revoked = CaseEventLog.objects.get(recipient_user=other, event_type=E.APPROVAL_REVOKED)
        self.assertEqual((rejected.event_type, rejected.detail), (E.APPLICATION_REJECTED, "The letter is unsigned."))
        self.assertEqual(revoked.detail, "Left the organisation.")
        self.assertIn("Note from the administrator: The letter is unsigned.", mail.outbox[0].body)
        self.assertIn("The letter is unsigned.", self.notifications(self.applicant)["results"][0]["detail"])

    def test_an_approved_officer_sees_it_despite_district_scoping(self):
        district = LocationArea.objects.create(code="TST-D01", name="Daerah Ujian", level=LocationArea.Level.DISTRICT)
        officer = UserAccount.objects.create_user(
            email="zul@test.my", full_name="Zul", password="Recovery2026",
            requested_role=R.DISASTER_OFFICER, verification_status=S.PENDING, district=district,
        )
        officer.approve_application(admin=self.admin)
        self.assertEqual(self.notifications(officer)["unread"], 1)

    def test_placeholder_address_gets_the_in_app_notice_only(self):
        demo = UserAccount.objects.create_user(
            email="ngo9@hg.my", full_name="Demo", password="Recovery2026",
            requested_role=R.NGO_VOLUNTEER, verification_status=S.PENDING,
        )
        demo.approve_application(admin=self.admin)
        row = CaseEventLog.objects.get(recipient_user=demo)
        self.assertEqual(row.delivery_status, "skipped_placeholder_address")
        self.assertEqual(mail.outbox, [])

    def test_nobody_else_sees_it(self):
        self.applicant.approve_application(admin=self.admin)
        self.assertEqual(self.notifications(self.admin)["unread"], 0)

    def test_a_refused_decision_notifies_nobody(self):
        self.applicant.approve_application(admin=self.admin)
        with self.assertRaises(ValueError):
            self.applicant.approve_application(admin=self.admin)
        self.assertEqual(CaseEventLog.objects.filter(recipient_user=self.applicant).count(), 1)

    def test_a_row_without_case_or_donation_must_be_an_application_decision(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CaseEventLog.objects.create(event_type=E.CLAIMED, created_at=timezone.now())


@override_settings(EMAIL_SKIP_DOMAINS={"hg.my"})
class NewApplicationEmailTests(ThrottleTestCase):
    """Administrators hear about an application once its email is confirmed (ADR-027)."""

    def setUp(self):
        super().setUp()
        self.admin = UserAccount.objects.create_user(
            email="admin@test.my", full_name="Admin", password="Recovery2026", role=R.SYSTEM_ADMIN
        )

    def sign_up(self, requested_role=R.NGO_VOLUNTEER):
        return UserAccount.objects.create_user(
            email="aisyah@test.my", full_name="Aisyah Tan", password="Recovery2026", email_confirmed=False,
            requested_role=requested_role, verification_status=S.PENDING if requested_role else S.NOT_REQUIRED,
        )

    def confirm(self, user):
        return self.client.post(
            "/api/auth/confirm-email/", {"token": make_confirmation_token(user)}, content_type="application/json"
        )

    def to_admins(self):
        return [m for m in mail.outbox if m.to == ["admin@test.my"]]

    def test_confirming_an_application_emails_each_administrator_once(self):
        UserAccount.objects.create_user(email="admin@hg.my", full_name="Demo", password="x", role=R.SYSTEM_ADMIN)
        UserAccount.objects.create_user(
            email="old@test.my", full_name="Old", password="x", role=R.SYSTEM_ADMIN, is_active=False
        )
        applicant = self.sign_up()
        self.confirm(applicant)
        self.confirm(applicant)  # opening the link twice is not a second application
        self.assertEqual([m.to for m in mail.outbox], [["admin@test.my"]])
        message = mail.outbox[0]
        self.assertIn("NGO volunteer application", message.subject)
        self.assertIn("/admin/accounts/roleapplication/", message.body)
        # Like other emails it only says what happened: the details stay behind sign-in.
        self.assertNotIn("Aisyah", message.body)

    def test_a_resident_sign_up_emails_no_administrator(self):
        self.confirm(self.sign_up(requested_role=None))
        self.assertEqual(self.to_admins(), [])
