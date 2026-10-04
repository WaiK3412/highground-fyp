"""Two organisations press Claim on the same job at the same moment (NFR6, FR17).

Real threads, real connections: TransactionTestCase commits, so the row locks
in claim_job genuinely contend. Which organisation wins is up to PostgreSQL;
the test asserts that exactly one does.
"""

from django.test import Client, TransactionTestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseJob, CaseRecord

from .race_helpers import GazetteerReloadMixin, race


class ClaimRaceTests(GazetteerReloadMixin, TransactionTestCase):
    def setUp(self):
        self.mercy = Organization.objects.create(
            name="Mercy Relief", type=Organization.Type.NGO, contact_no="03-1", service_area="Kelantan"
        )
        self.belia = Organization.objects.create(
            name="Persatuan Belia", type=Organization.Type.VOLUNTEER_GROUP, contact_no="03-2", service_area="Pasir Mas"
        )
        self.mercy_lead = UserAccount.objects.create_user(
            email="m@example.my", full_name="Mercy Lead", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.mercy,
        )
        self.belia_lead = UserAccount.objects.create_user(
            email="b@example.my", full_name="Belia Lead", password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.belia,
        )
        resident = UserAccount.objects.create_user(
            email="r@example.my", full_name="Resident", password="Recovery2026"
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-9901", submitted_by_user=resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP, description="Mud.",
            village="Kg. Test", address="Lot 1", status=CaseRecord.Status.VERIFIED,
            priority_class=3, created_at=timezone.now(),
        )
        self.job = CaseJob.objects.create(case=self.case, help_type="cleanup")

    def claimer(self, user):
        def post():
            client = Client()
            client.force_login(user)
            return client.post(f"/api/jobs/{self.job.pk}/claim/").status_code
        return post

    def test_two_organisations_racing_for_one_job_exactly_one_wins(self):
        results = race(self.claimer(self.mercy_lead), self.claimer(self.belia_lead))
        self.assertEqual(sorted(results), [200, 409])
        self.job.refresh_from_db()
        self.assertIn(self.job.claimed_by_org_id, {self.mercy.pk, self.belia.pk})
        self.assertEqual(
            CaseEventLog.objects.filter(
                case=self.case, event_type=CaseEventLog.EventType.CLAIMED,
                notification_copy_of__isnull=True,
            ).count(),
            1,
        )
