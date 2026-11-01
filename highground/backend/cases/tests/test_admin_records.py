"""Reference records an administrator keeps in Django Admin (FR21).

Organisations are added only here, and an applicant can choose one only once it
exists (FR1, FR20); drop-off points are added and withdrawn here and supply
appeals can use only the active ones (FR19). Every test goes through the admin
pages themselves, so a broken form or a missing registration fails here.
"""

from django.urls import reverse

from accounts.models import Organization, UserAccount
from cases.models import DropOffPoint
from cases.tests.test_lifecycle import LifecycleTestCase

SCREENS = ("admin:accounts_organization_changelist", "admin:cases_dropoffpoint_changelist")


class AdminRecordTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.admin = UserAccount.objects.create_superuser(
            email="admin-records@example.my", full_name="Records Admin", password="Recovery2026",
        )
        self.officer.is_staff = True  # staff flag alone must not open the console (ADR-024)
        self.officer.save(update_fields=["is_staff"])

    def test_only_administrators_can_open_these_screens(self):
        for user, allowed in ((self.admin, True), (self.officer, False), (self.mercy_lead, False),
                              (self.resident, False), (None, False)):
            for screen in SCREENS:
                with self.subTest(user=getattr(user, "email", "anonymous"), screen=screen):
                    self.client.logout()
                    if user is not None:
                        self.login(user)
                    response = self.client.get(reverse(screen))
                    if allowed:
                        self.assertEqual(response.status_code, 200)
                    else:
                        self.assertEqual(response.status_code, 302)
                        self.assertIn("/admin/login/", response["Location"])

    def add_organisation(self, **overrides):
        data = {"name": "Kelantan Relief Network", "type": Organization.Type.NGO,
                "contact_no": "09-7471234", "service_area": "Kota Bharu"}
        data.update(overrides)
        self.login(self.admin)
        return self.client.post(reverse("admin:accounts_organization_add"), data)

    def test_an_organisation_needs_every_field(self):
        for field in ("name", "type", "contact_no", "service_area"):
            with self.subTest(missing=field):
                response = self.add_organisation(**{field: ""})
                self.assertEqual(response.status_code, 200)  # the form comes back with its errors
                self.assertIn(field, response.context["adminform"].form.errors)
                self.assertFalse(Organization.objects.filter(name="Kelantan Relief Network").exists())

    def test_an_added_organisation_can_be_chosen_when_applying(self):
        self.assertEqual(self.add_organisation().status_code, 302)
        self.client.logout()
        names = [row["name"] for row in self.client.get("/api/organizations/").json()]
        self.assertIn("Kelantan Relief Network", names)

    def test_drop_off_points_are_added_and_withdrawn_in_the_admin(self):
        self.login(self.admin)
        response = self.client.post(reverse("admin:cases_dropoffpoint_add"), {
            "name": "Dewan Orang Ramai Tumpat", "address": "Jalan Pasar", "area": "Tumpat", "active": "on",
        })
        self.assertEqual(response.status_code, 302)
        point = DropOffPoint.objects.get(name="Dewan Orang Ramai Tumpat")

        def offered():
            self.login(self.mercy_lead)
            return [row["id"] for row in self.client.get("/api/drop-off-points/").json()["results"]]

        self.assertIn(point.pk, offered())

        self.login(self.admin)
        response = self.client.post(reverse("admin:cases_dropoffpoint_change", args=[point.pk]), {
            "name": point.name, "address": point.address, "area": point.area,  # active unticked
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(point.pk, offered())
