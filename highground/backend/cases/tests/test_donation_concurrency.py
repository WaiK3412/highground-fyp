"""A donor cancelling while the NGO confirms must end in exactly one outcome."""

from datetime import timedelta

from django.test import Client, TransactionTestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import Donation, DropOffPoint, SupplyAppeal
from .race_helpers import GazetteerReloadMixin, race


class DonationRaceTests(GazetteerReloadMixin, TransactionTestCase):
    def test_cancel_and_receive_at_once_leave_one_outcome(self):
        org = Organization.objects.create(name="Test NGO", type=Organization.Type.NGO)
        ngo = UserAccount.objects.create_user(
            email="ngo@example.my", full_name="NGO responder",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=org,
        )
        donor = UserAccount.objects.create_user(email="donor@example.my", full_name="Donor")
        point = DropOffPoint.objects.create(name="Test hall", address="Jalan Test", area="Test")
        appeal = SupplyAppeal.objects.create(
            organization=org, created_by_user=ngo, drop_off_point=point,
            title="Water", items="Bottled water",
            needed_until=timezone.localdate() + timedelta(days=1),
        )
        donation = Donation.objects.create(appeal=appeal, donor_user=donor, items="Water")

        def post_as(user, action):
            def request():
                client = Client()
                client.force_login(user)
                return client.post(f"/api/donations/{donation.pk}/{action}/").status_code
            return request

        results = race(post_as(donor, "cancel"), post_as(ngo, "receive"))

        self.assertEqual(sorted(results), [200, 409])
        donation.refresh_from_db()
        self.assertIn(donation.status, (Donation.Status.CANCELLED, Donation.Status.RECEIVED))
