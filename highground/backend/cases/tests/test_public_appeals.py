"""Open supply appeals on the public landing page (ADR-025).

Requirement covered: visitors who are not signed in see what relief
organisations currently need, and nothing else: no closed or out-of-date
appeals, no donations and no details of who posted them.
"""

from django.core.cache import cache

from cases.models import Donation, SupplyAppeal
from cases.tests.test_appeals import AppealTestCase

URL = "/api/public/appeals/"


class PublicAppealTests(AppealTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def results(self):
        self.client.logout()
        return self.client.get(URL).json()["results"]

    def test_anonymous_sees_open_in_date_appeals(self):
        appeal = self.make()
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()["results"]], [appeal.pk])

    def test_closed_and_expired_appeals_are_excluded(self):
        self.make(status=SupplyAppeal.Status.CLOSED)
        self.make(days=-1)
        self.assertEqual(self.results(), [])

    def test_at_most_six_soonest_first(self):
        for days in (9, 3, 7, 1, 5, 8, 2):
            self.make(days=days)
        rows = self.results()
        self.assertEqual(len(rows), 6)
        dates = [row["needed_until"] for row in rows]
        self.assertEqual(dates, sorted(dates))

    def test_only_public_fields_are_returned(self):
        appeal = self.make()
        Donation.objects.create(appeal=appeal, donor_user=self.resident, items="Rice")
        row = self.results()[0]
        self.assertEqual(
            set(row),
            {"id", "title", "items", "needed_until", "organization", "organization_contact", "drop_off_point"},
        )
        self.assertEqual(set(row["drop_off_point"]), {"id", "name", "address", "area"})
        self.assertNotIn(self.resident.full_name, str(row))

    def test_public_appeals_are_throttled(self):
        statuses = [self.client.get(URL).status_code for _ in range(61)]
        self.assertEqual(statuses[-1], 429)
