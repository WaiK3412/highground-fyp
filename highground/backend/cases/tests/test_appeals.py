"""Supply appeals: an NGO lists the relief items it needs (ADR-021).

Traceability: FR7 (replaced: residents see what is needed and where to take
it; no pledge is recorded), FR20 role-based permissions on every endpoint.
"""

from datetime import timedelta

from django.utils import timezone

from cases.models import DropOffPoint, SupplyAppeal
from cases.tests.test_lifecycle import LifecycleTestCase
from accounts.models import UserAccount


class AppealTestCase(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.point = DropOffPoint.objects.create(
            name="Balai Raya Pasir Mas", address="Jalan Che Latiff", area="Pasir Mas", active=True
        )
        self.closed_point = DropOffPoint.objects.create(
            name="Old hall", address="Jalan Lama", area="Pasir Mas", active=False
        )

    def payload(self, **overrides):
        data = {
            "title": "Cleaning supplies for Kg. Test",
            "items": "Mops, buckets, bleach, rubber boots",
            "needed_until": (timezone.localdate() + timedelta(days=7)).isoformat(),
            "drop_off_point_id": self.point.pk,
        }
        data.update(overrides)
        return data

    def post(self, user, data):
        self.login(user)
        return self.client.post("/api/appeals/", data, content_type="application/json")

    def patch(self, user, appeal, data):
        self.login(user)
        return self.client.patch(
            f"/api/appeals/{appeal.pk}/", data, content_type="application/json"
        )

    def make(self, org=None, lead=None, days=7, status=SupplyAppeal.Status.OPEN):
        return SupplyAppeal.objects.create(
            organization=org or self.mercy,
            created_by_user=lead or self.mercy_lead,
            drop_off_point=self.point,
            title="Water",
            items="Bottled water",
            needed_until=timezone.localdate() + timedelta(days=days),
            status=status,
        )

    def resident_list(self):
        self.login(self.resident)
        return self.client.get("/api/appeals/").json()["results"]


class PostingTests(AppealTestCase):
    def test_ngo_responder_posts_for_their_own_organisation(self):
        response = self.post(self.mercy_lead, self.payload(organization=self.belia.pk))
        self.assertEqual(response.status_code, 201)
        appeal = SupplyAppeal.objects.get()
        self.assertEqual(appeal.organization, self.mercy)  # posted org is ignored
        self.assertEqual(appeal.created_by_user, self.mercy_lead)
        self.assertEqual(response.json()["drop_off_point"]["name"], "Balai Raya Pasir Mas")

    def test_residents_and_officers_cannot_post(self):
        cases = (
            ("resident", self.resident, 403),
            ("officer", self.officer, 403),
        )
        for actor, user, expected_status in cases:
            with self.subTest(actor=actor):
                self.assertEqual(self.post(user, self.payload()).status_code, expected_status)
        self.assertFalse(SupplyAppeal.objects.exists())

    def test_invalid_appeal_fields_are_refused_with_field_errors(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        cases = (
            ("past date", {"needed_until": yesterday}, 400, "needed_until"),
            ("inactive drop-off point", {"drop_off_point_id": self.closed_point.pk}, 400, "drop_off_point_id"),
            ("blank items", {"items": "   "}, 400, "items"),
        )
        for value, payload, expected_status, error_field in cases:
            with self.subTest(value=value):
                response = self.post(self.mercy_lead, self.payload(**payload))
                self.assertEqual(response.status_code, expected_status)
                self.assertIn(error_field, response.json())


class ReadingTests(AppealTestCase):
    def test_resident_sees_open_appeals_only(self):
        live = self.make()
        self.make(status=SupplyAppeal.Status.CLOSED)
        self.make(days=-1)  # date passed: hidden without anyone closing it
        self.assertEqual([row["id"] for row in self.resident_list()], [live.pk])

    def test_an_appeal_due_today_is_still_shown(self):
        today = self.make(days=0)
        self.assertEqual([row["id"] for row in self.resident_list()], [today.pk])

    def test_officers_can_read_the_list(self):
        self.make()
        self.login(self.officer)
        self.assertEqual(self.client.get("/api/appeals/").status_code, 200)

    def test_anonymous_visitors_cannot_read(self):
        self.make()
        self.assertIn(self.client.get("/api/appeals/").status_code, {401, 403})

    def test_mine_lists_own_organisation_including_closed(self):
        own_closed = self.make(status=SupplyAppeal.Status.CLOSED)
        own_open = self.make()
        self.make(org=self.belia, lead=self.belia_lead)
        self.login(self.mercy_lead)
        rows = self.client.get("/api/appeals/", {"mine": "1"}).json()["results"]
        self.assertEqual({row["id"] for row in rows}, {own_open.pk, own_closed.pk})

    def test_mine_is_for_ngo_responders_only(self):
        self.login(self.resident)
        self.assertEqual(self.client.get("/api/appeals/", {"mine": "1"}).status_code, 403)


class EditingTests(AppealTestCase):
    def test_owner_can_edit_items(self):
        appeal = self.make()
        response = self.patch(self.mercy_lead, appeal, {"items": "Bottled water, rice"})
        self.assertEqual(response.status_code, 200)
        appeal.refresh_from_db()
        self.assertEqual(appeal.items, "Bottled water, rice")

    def test_owner_can_close(self):
        appeal = self.make()
        response = self.patch(self.mercy_lead, appeal, {"status": "closed"})
        self.assertEqual(response.status_code, 200)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, SupplyAppeal.Status.CLOSED)
        self.assertIsNotNone(appeal.closed_at)

    def test_a_closed_appeal_cannot_be_changed(self):
        appeal = self.make(status=SupplyAppeal.Status.CLOSED)
        self.assertEqual(self.patch(self.mercy_lead, appeal, {"items": "x"}).status_code, 409)

    def test_status_can_only_be_set_to_closed(self):
        appeal = self.make()
        self.assertEqual(self.patch(self.mercy_lead, appeal, {"status": "open"}).status_code, 400)

    def test_another_organisation_cannot_edit_or_close(self):
        appeal = self.make()
        self.assertEqual(self.patch(self.belia_lead, appeal, {"status": "closed"}).status_code, 404)
        self.assertEqual(self.patch(self.officer, appeal, {"status": "closed"}).status_code, 403)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, SupplyAppeal.Status.OPEN)


class DropOffPointTests(AppealTestCase):
    def test_ngo_responder_gets_active_points_only(self):
        self.login(self.mercy_lead)
        rows = self.client.get("/api/drop-off-points/").json()["results"]
        self.assertEqual([row["id"] for row in rows], [self.point.pk])

    def test_residents_cannot_list_drop_off_points(self):
        self.login(self.resident)
        self.assertEqual(self.client.get("/api/drop-off-points/").status_code, 403)


class PermissionPolicyTests(AppealTestCase):
    def test_anonymous_cannot_post_edit_or_list_points(self):
        appeal = self.make()
        self.assertEqual(self.client.post("/api/appeals/", self.payload()).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/appeals/{appeal.pk}/", {"status": "closed"}, content_type="application/json").status_code, 403)
        self.assertEqual(self.client.get("/api/drop-off-points/").status_code, 403)

    def test_resident_cannot_edit_and_officer_cannot_list_points_or_mine(self):
        self.assertEqual(self.patch(self.resident, self.make(), {"items": "Rice"}).status_code, 403)
        self.login(self.officer)
        self.assertEqual(self.client.get("/api/drop-off-points/").status_code, 403)
        self.assertEqual(self.client.get("/api/appeals/?mine=1").status_code, 403)

    def test_ngo_without_an_organisation_has_read_access_only(self):
        user = UserAccount.objects.create_user(
            email="unattached@example.my", full_name="Unattached", role=UserAccount.Role.NGO_VOLUNTEER
        )
        self.login(user)
        self.assertEqual(self.client.get("/api/appeals/").status_code, 200)
        self.assertEqual(self.post(user, self.payload()).status_code, 403)
        self.assertEqual(self.client.get("/api/appeals/?mine=1").status_code, 403)
        self.assertEqual(self.client.get("/api/drop-off-points/").status_code, 403)

    def test_admin_can_read_but_cannot_use_ngo_write_endpoints(self):
        user = UserAccount.objects.create_user(
            email="admin@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN
        )
        appeal = self.make()
        self.login(user)
        self.assertEqual(self.client.get("/api/appeals/").status_code, 200)
        self.assertEqual(self.post(user, self.payload()).status_code, 403)
        self.assertEqual(self.patch(user, appeal, {"status": "closed"}).status_code, 403)
        self.assertEqual(self.client.get("/api/appeals/?mine=1").status_code, 403)
        self.assertEqual(self.client.get("/api/drop-off-points/").status_code, 403)
