"""Controlled locations: the coded places a case is filed under.

Traceability:
  FR3  A household files its request under a controlled village
  FR20 Every endpoint has an explicit permission policy

State and district rows are the official HDX/OCHA P-codes; villages extend
them with project codes that are issued once and never reused.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import UserAccount
from cases.models import LocationArea

Level = LocationArea.Level


class LocationDataTests(TestCase):
    def test_every_kelantan_district_carries_its_official_p_code(self):
        state = LocationArea.objects.get(code="MY03")
        districts = LocationArea.objects.filter(parent=state, level=Level.DISTRICT)

        self.assertEqual(state.level, Level.STATE)
        self.assertEqual(districts.count(), 10)
        self.assertEqual(LocationArea.objects.get(code="MY0307").name, "Pasir Mas")
        self.assertEqual(LocationArea.objects.get(code="MY0304").name, "Kota Bharu")
        self.assertEqual(set(districts.values_list("centroid_source", flat=True)), {"official"})

    def test_starter_villages_are_valid_and_coded_under_their_district(self):
        villages = LocationArea.objects.filter(level=Level.VILLAGE)

        self.assertGreaterEqual(villages.count(), 10)
        for village in villages:
            village.full_clean()
            self.assertTrue(village.code.startswith(f"{village.parent.code}-V"), village.code)
            self.assertIn(village.centroid_source, {"osm", "approximate"})


class VillageRuleTests(TestCase):
    def setUp(self):
        self.state = LocationArea.objects.get(code="MY03")
        self.pasir_mas = LocationArea.objects.get(code="MY0307")

    def test_next_code_continues_from_the_highest_issued(self):
        self.assertEqual(LocationArea.next_village_code(self.pasir_mas), "MY0307-V008")

    def test_a_retired_village_keeps_its_number(self):
        highest = LocationArea.objects.get(code="MY0307-V007")
        highest.active = False
        highest.save()

        self.assertEqual(LocationArea.next_village_code(self.pasir_mas), "MY0307-V008")

    def test_a_district_without_villages_starts_at_one(self):
        bachok = LocationArea.objects.get(code="MY0301")
        self.assertEqual(LocationArea.next_village_code(bachok), "MY0301-V001")

    def test_a_village_needs_a_centre_point(self):
        village = LocationArea(code="MY0307-V900", name="No Point", parent=self.pasir_mas)
        with self.assertRaises(ValidationError) as raised:
            village.full_clean()
        self.assertIn("latitude", raised.exception.message_dict)

    def test_a_village_must_sit_under_a_district(self):
        village = LocationArea(
            code="MY03-V900", name="Wrong Parent", parent=self.state,
            latitude=Decimal("6.0"), longitude=Decimal("102.1"),
        )
        with self.assertRaises(ValidationError) as raised:
            village.full_clean()
        self.assertIn("parent", raised.exception.message_dict)

    def test_a_published_code_cannot_be_changed(self):
        village = LocationArea.objects.get(code="MY0307-V001")
        village.code = "MY0307-V999"
        with self.assertRaises(ValidationError) as raised:
            village.full_clean()
        self.assertIn("code", raised.exception.message_dict)


class LocationAdminTests(TestCase):
    """The admin is where villages are added after launch (ADR-002)."""

    def setUp(self):
        self.admin = UserAccount.objects.create_superuser(
            email="locations-admin@example.my", full_name="Locations Admin", password="Recovery2026",
        )
        self.client.force_login(self.admin)
        self.pasir_mas = LocationArea.objects.get(code="MY0307")

    def test_adding_a_village_issues_the_next_code(self):
        response = self.client.post(
            "/admin/cases/locationarea/add/",
            {
                "parent": self.pasir_mas.pk,
                "name": "Kampung Baharu Test",
                "latitude": "6.050000",
                "longitude": "102.150000",
                "centroid_source": "approximate",
                "active": "on",
            },
        )

        self.assertEqual(response.status_code, 302, response.content[:2000])
        village = LocationArea.objects.get(name="Kampung Baharu Test")
        self.assertEqual(village.code, "MY0307-V008")
        self.assertEqual(village.level, Level.VILLAGE)

    def test_a_village_without_a_centre_point_is_refused(self):
        response = self.client.post(
            "/admin/cases/locationarea/add/",
            {"parent": self.pasir_mas.pk, "name": "No Point", "centroid_source": "", "active": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LocationArea.objects.filter(name="No Point").exists())

    def test_areas_cannot_be_deleted(self):
        village = LocationArea.objects.get(code="MY0307-V001")
        response = self.client.get(f"/admin/cases/locationarea/{village.pk}/delete/")
        self.assertEqual(response.status_code, 403)


class LocationListApiTests(TestCase):
    URL = "/api/locations/"

    def setUp(self):
        self.resident = UserAccount.objects.create_user(
            email="locations-resident@example.my", full_name="Locations Resident", password="Recovery2026",
        )

    def test_anonymous_users_are_refused(self):
        self.assertIn(self.client.get(self.URL).status_code, {401, 403})

    def test_a_resident_gets_active_villages_with_their_district_and_no_coordinates(self):
        LocationArea.objects.filter(code="MY0304-V005").update(active=False)
        self.client.force_login(self.resident)

        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        codes = {row["code"] for row in rows}
        self.assertIn("MY0307-V001", codes)
        self.assertNotIn("MY0304-V005", codes)
        self.assertNotIn("MY0307", codes)
        tendong = next(row for row in rows if row["code"] == "MY0307-V001")
        self.assertEqual(tendong, {
            "code": "MY0307-V001",
            "name": "Kampung Tendong",
            "district": "Pasir Mas",
            "district_code": "MY0307",
        })

    def test_every_role_can_read_the_list(self):
        for role in (UserAccount.Role.DISASTER_OFFICER, UserAccount.Role.NGO_VOLUNTEER):
            user = UserAccount.objects.create_user(
                email=f"locations-{role}@example.my", full_name=f"Locations {role}",
                password="Recovery2026", role=role,
            )
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.URL).status_code, 200)
