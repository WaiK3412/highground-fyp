"""The case map: the visible queue, at the precision each role may see.

Traceability:
  FR20 Every endpoint enforces role and organisation boundaries
  NFR  Exact coordinates only for the district office and the claiming
       organisation (report §3.5)

The rule under test: the map never shows a role more than its list does. A
case whose exact location the viewer may see is a point; any other visible
case is only counted into its village, because published points can be
re-identified to a household.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseRecord, DuplicateCaseMatch, LocationArea
from scoring.models import PriorityRubricVersion

URL = "/api/cases/map/"


class CaseMapTests(TestCase):
    def setUp(self):
        self.org_a = Organization.objects.create(name="Map NGO A", type=Organization.Type.NGO)
        self.org_b = Organization.objects.create(name="Map NGO B", type=Organization.Type.NGO)

        def user(email, role=UserAccount.Role.COMMUNITY_MEMBER, org=None):
            return UserAccount.objects.create_user(
                email=email, full_name=email.split("@")[0], password="Recovery2026",
                role=role, organization=org,
            )

        self.resident = user("map-resident@example.my")
        self.officer = user("map-officer@example.my", UserAccount.Role.DISASTER_OFFICER)
        self.admin = user("map-admin@example.my", UserAccount.Role.SYSTEM_ADMIN)
        self.ngo_a = user("map-ngo-a@example.my", UserAccount.Role.NGO_VOLUNTEER, self.org_a)
        self.ngo_b = user("map-ngo-b@example.my", UserAccount.Role.NGO_VOLUNTEER, self.org_b)

        self.tendong = LocationArea.objects.get(code="MY0307-V001")
        self.salor = LocationArea.objects.get(code="MY0304-V002")

        def case(ref, status, area, lat, lng, address, score, org=None):
            return CaseRecord.objects.create(
                reference=ref, submitted_by_user=self.resident, claimed_by_org=org,
                damage_category=CaseRecord.DamageCategory.CLEANUP,
                description="Private household description.",
                location_area=area, village=area.name if area else "Kg. Unknown",
                address=address,
                latitude=Decimal(lat) if lat else None,
                longitude=Decimal(lng) if lng else None,
                status=status, score_total=score, created_at=timezone.now(),
            )

        S = CaseRecord.Status
        self.a_claimed = case("FRC-9101", S.IN_PROGRESS, self.tendong, "6.071111", "102.211111", "Lot 1 Secret Lane", 81, self.org_a)
        self.open_exact = case("FRC-9102", S.VERIFIED, self.tendong, "6.072222", "102.212222", "Lot 2 Hidden Road", 55)
        self.b_claimed = case("FRC-9103", S.CLAIMED, self.salor, "6.028888", "102.183333", "Lot 3 Quiet Path", 30, self.org_b)
        self.open_no_pin = case("FRC-9104", S.VERIFIED, self.tendong, None, None, "Lot 4 No Pin", 75)
        self.no_location = case("FRC-9105", S.VERIFIED, None, None, None, "Lot 5 Nowhere", 45)
        self.submitted = case("FRC-9106", S.SUBMITTED, self.salor, "6.029999", "102.184444", "Lot 6 New Case", None)

    def get(self, user, **params):
        self.client.force_login(user)
        response = self.client.get(URL, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    @staticmethod
    def refs(payload):
        return {point["reference"] for point in payload["points"]}

    def test_district_staff_see_every_visible_case_as_a_point(self):
        for user in (self.officer, self.admin):
            payload = self.get(user).json()

            self.assertEqual(self.refs(payload), {"FRC-9101", "FRC-9102", "FRC-9103", "FRC-9104", "FRC-9106"})
            self.assertEqual(payload["areas"], [])
            self.assertEqual(payload["unmapped"], 1)

    def test_duplicate_markers_are_officer_only_even_for_a_claiming_ngo(self):
        DuplicateCaseMatch.objects.create(
            case_a=self.a_claimed, case_b=self.open_exact, similarity_score=85,
        )
        points = {row["reference"]: row for row in self.get(self.officer).json()["points"]}
        self.assertTrue(points["FRC-9101"]["has_open_duplicate"])
        self.assertTrue(points["FRC-9102"]["has_open_duplicate"])
        self.assertFalse(points["FRC-9103"]["has_open_duplicate"])

        ngo_response = self.get(self.ngo_a)
        self.assertNotIn("has_open_duplicate", ngo_response.json()["points"][0])

    def test_a_case_without_a_pin_is_placed_at_its_village_centre(self):
        payload = self.get(self.officer).json()
        point = next(p for p in payload["points"] if p["reference"] == "FRC-9104")

        self.assertEqual(point["precision"], "village")
        self.assertEqual(Decimal(point["latitude"]), self.tendong.latitude)
        exact = next(p for p in payload["points"] if p["reference"] == "FRC-9101")
        self.assertEqual(exact["precision"], "exact")
        self.assertEqual(Decimal(exact["latitude"]), Decimal("6.071111"))

    def test_an_ngo_sees_its_own_case_exactly_and_others_only_as_village_counts(self):
        response = self.get(self.ngo_a)
        payload = response.json()

        self.assertEqual(self.refs(payload), {"FRC-9101"})
        self.assertTrue(payload["points"][0]["claimed_by_you"])
        areas = {area["code"]: area for area in payload["areas"]}
        self.assertEqual(areas["MY0307-V001"]["case_count"], 2)  # 9102 + 9104
        self.assertEqual(areas["MY0307-V001"]["highest_band"], "High")  # 9104 scores 75
        self.assertEqual(areas["MY0304-V002"]["case_count"], 1)  # 9103; 9106 is not yet verified
        self.assertEqual(areas["MY0304-V002"]["highest_band"], "Low")
        self.assertEqual(payload["unmapped"], 1)
        self.assertEqual(
            set(areas["MY0307-V001"]),
            {"code", "name", "latitude", "longitude", "case_count", "highest_band"},
        )
        for private in ("6.072222", "102.212222", "Hidden Road", "6.028888", "Quiet Path",
                        "FRC-9102", "FRC-9103", "FRC-9104", "FRC-9106", "New Case"):
            self.assertNotContains(response, private)

    def test_the_other_ngo_cannot_see_where_the_claimed_household_is(self):
        response = self.get(self.ngo_b)
        payload = response.json()

        self.assertEqual(self.refs(payload), {"FRC-9103"})
        areas = {area["code"]: area for area in payload["areas"]}
        self.assertEqual(areas["MY0307-V001"]["case_count"], 3)
        for private in ("6.071111", "102.211111", "Secret Lane", "FRC-9101"):
            self.assertNotContains(response, private)

    def test_residents_and_anonymous_users_get_no_map(self):
        self.assertIn(self.client.get(URL).status_code, {401, 403})
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_filters_match_the_list(self):
        payload = self.get(self.ngo_a, status="verified").json()
        self.assertEqual(payload["points"], [])
        self.assertEqual({a["code"]: a["case_count"] for a in payload["areas"]}, {"MY0307-V001": 2})
        self.assertEqual(payload["unmapped"], 1)

        payload = self.get(self.ngo_a, q="FRC-9102").json()
        self.assertEqual({a["code"]: a["case_count"] for a in payload["areas"]}, {"MY0307-V001": 1})

    def test_searching_a_village_name_finds_cases_filed_under_older_spellings(self):
        """A village marker filters the list by its name; older cases keep the
        free text they were filed with, so search must also match the area."""
        CaseRecord.objects.filter(pk=self.open_exact.pk).update(village="Kg. Tendong")
        self.client.force_login(self.ngo_a)

        listed = self.client.get("/api/cases/", {"q": "Kampung Tendong"}).json()
        self.assertIn("FRC-9102", {row["reference"] for row in listed["results"]})

    def test_the_map_accounts_for_exactly_the_cases_the_list_shows(self):
        for user in (self.officer, self.ngo_a, self.ngo_b):
            for params in ({}, {"status": "verified"}, {"q": "Tendong"}):
                payload = self.get(user, **params).json()
                listed = self.client.get("/api/cases/", params).json()["count"]
                mapped = (
                    len(payload["points"])
                    + sum(area["case_count"] for area in payload["areas"])
                    + payload["unmapped"]
                )
                self.assertEqual(mapped, listed, (user.email, params))

    def test_band_filters_use_each_cases_rubric_and_keep_all_three_views_in_sync(self):
        # A score below 70 can be High, and one above 70 can be Medium,
        # because the rubric version that produced the score owns its cutoffs.
        custom_high = PriorityRubricVersion.objects.create(
            label="map-high", high_threshold=55, medium_threshold=20,
        )
        custom_medium = PriorityRubricVersion.objects.create(
            label="map-medium", high_threshold=80, medium_threshold=75,
        )
        CaseRecord.objects.filter(pk=self.a_claimed.pk).update(score_total=70)
        CaseRecord.objects.filter(pk=self.open_exact.pk).update(rubric_version=custom_high)
        CaseRecord.objects.filter(pk=self.open_no_pin.pk).update(rubric_version=custom_medium)
        CaseRecord.objects.filter(pk=self.no_location.pk).update(score_total=40)
        CaseRecord.objects.create(
            reference="FRC-9107", submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="A separate household.", location_area=self.tendong,
            village=self.tendong.name, address="Lot 7", status=CaseRecord.Status.VERIFIED,
            score_total=19, rubric_version=custom_high, created_at=timezone.now(),
        )

        for user in (self.officer, self.admin, self.ngo_a, self.ngo_b):
            for params in (
                {}, {"band": "high"}, {"band": "medium"}, {"band": "low"},
                {"band": "high", "status": "verified"},
                {"band": "medium", "q": "Tendong"},
                {"band": "low", "q": "nothing-matches"},
            ):
                with self.subTest(user=user.email, params=params):
                    self.client.force_login(user)
                    listing = self.client.get("/api/cases/", params).json()
                    stats = self.client.get("/api/cases/stats/", params).json()
                    mapped = self.client.get(URL, params).json()
                    rows = listing["results"]
                    count = len(mapped["points"]) + sum(
                        area["case_count"] for area in mapped["areas"]
                    ) + mapped["unmapped"]
                    self.assertEqual(listing["count"], count)
                    self.assertEqual(stats["total"], count)
                    self.assertEqual(stats["high"], sum(
                        row["priority_band"] == "High" for row in rows
                    ))
                    self.assertEqual(stats["unclaimed"], sum(
                        row["claimed_by"] is None for row in rows
                    ))
                    self.assertEqual(stats["in_progress"], sum(
                        row["status"] == "in_progress" for row in rows
                    ))
                    if params.get("band"):
                        self.assertTrue(all(
                            row["priority_band"].lower() == params["band"] for row in rows
                        ))

        self.client.force_login(self.officer)
        high = self.client.get("/api/cases/", {"band": "high"}).json()["results"]
        self.assertEqual({row["reference"] for row in high}, {"FRC-9101", "FRC-9102"})
        medium = self.client.get("/api/cases/", {"band": "medium"}).json()["results"]
        self.assertEqual({row["reference"] for row in medium}, {"FRC-9104", "FRC-9105"})
        low = self.client.get("/api/cases/", {"band": "low"}).json()["results"]
        self.assertEqual({row["reference"] for row in low}, {"FRC-9103", "FRC-9107"})
        all_rows = self.client.get("/api/cases/").json()["results"]
        self.assertEqual(
            {row["reference"] for row in all_rows if row["priority_band"] == "unscored"},
            {"FRC-9106"},
        )

    def test_unscored_needs_info_is_only_in_all_and_invalid_band_is_rejected(self):
        CaseRecord.objects.filter(pk=self.submitted.pk).update(status=CaseRecord.Status.NEEDS_INFO)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get("/api/cases/", {"status": "needs_info"}).json()["count"], 1)
        for band in ("high", "medium", "low"):
            params = {"status": "needs_info", "band": band}
            self.assertEqual(self.client.get("/api/cases/", params).json()["count"], 0)
            self.assertEqual(self.client.get("/api/cases/stats/", params).json()["total"], 0)
            self.assertEqual(self.client.get(URL, params).json()["points"], [])
        for path in ("/api/cases/", "/api/cases/stats/", URL):
            self.assertEqual(self.client.get(path, {"band": "urgent"}).status_code, 400)

    def test_filtered_stats_keep_resident_ownership_and_anonymous_denial(self):
        other = UserAccount.objects.create_user(
            email="other-resident@example.my", full_name="Other resident",
            password="Recovery2026", role=UserAccount.Role.COMMUNITY_MEMBER,
        )
        CaseRecord.objects.filter(pk=self.open_exact.pk).update(submitted_by_user=other)
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get("/api/cases/stats/").json()["total"], 5)
        self.assertEqual(self.client.get("/api/cases/stats/", {"band": "high"}).json()["total"], 2)
        self.client.logout()
        self.assertIn(self.client.get("/api/cases/stats/", {"band": "high"}).status_code, {401, 403})
