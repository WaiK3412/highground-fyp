"""The queue's overview counts and the two filters they open (2 Nov 2026).

Traceability:
  FR13 An officer monitors the district's queue: requests to verify, help no
       organisation has taken, and help waiting for the household
  FR16 An NGO responder sees the help it could claim and the work its own
       organisation holds

Each count is a door into the list: clicking it applies a filter, so the
count and the filtered list must agree, and both must stay inside what the
role may see.
"""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseJob, CaseRecord, LocationArea
from cases.tests.job_helpers import give_job

STATS = "/api/cases/stats/"
LIST = "/api/cases/"
MAP = "/api/cases/map/"


class QueueOverviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org_a = Organization.objects.create(name="Overview NGO A", type=Organization.Type.NGO)
        cls.org_b = Organization.objects.create(name="Overview NGO B", type=Organization.Type.NGO)

        def user(email, role=UserAccount.Role.COMMUNITY_MEMBER, org=None, district=None):
            return UserAccount.objects.create_user(
                email=email, full_name=email.split("@")[0], password="Recovery2026",
                role=role, organization=org, district=district,
            )

        cls.resident = user("overview-resident@example.my")
        cls.other_resident = user("overview-other@example.my")
        cls.officer = user(
            "overview-officer@example.my", UserAccount.Role.DISASTER_OFFICER,
            district=LocationArea.objects.get(code="MY0307"),  # Pasir Mas
        )
        cls.ngo_a = user("overview-ngo-a@example.my", UserAccount.Role.NGO_VOLUNTEER, cls.org_a)
        cls.ngo_b = user("overview-ngo-b@example.my", UserAccount.Role.NGO_VOLUNTEER, cls.org_b)
        tendong = LocationArea.objects.get(code="MY0307-V001")  # Pasir Mas
        salor = LocationArea.objects.get(code="MY0304-V002")  # Kota Bharu

        def case(ref, status, area, org=None, by=None, priority_class=2):
            record = CaseRecord.objects.create(
                reference=ref, submitted_by_user=by or cls.resident,
                damage_category=CaseRecord.DamageCategory.CLEANUP, description="Private.",
                location_area=area, village=area.name, address="Lot 1",
                status=status, created_at=timezone.now(),
                priority_class=None if status == CaseRecord.Status.SUBMITTED else priority_class,
            )
            give_job(record, org)
            return record

        S = CaseRecord.Status
        cls.submitted = case("FRC-9301", S.SUBMITTED, tendong)
        cls.verified_open = case("FRC-9302", S.VERIFIED, tendong, priority_class=1)
        cls.a_in_progress = case("FRC-9303", S.IN_PROGRESS, tendong, cls.org_a)
        cls.a_awaiting = case("FRC-9304", S.PENDING_CONFIRM, tendong, cls.org_a)
        # Held by B for cleanup, but its repair is still waiting for anyone.
        cls.b_with_open_repair = case("FRC-9305", S.CLAIMED, tendong, cls.org_b)
        CaseJob.objects.create(
            case=cls.b_with_open_repair, help_type=CaseRecord.DamageCategory.REPAIR,
            status=CaseJob.Status.OPEN,
        )
        cls.other_district_open = case("FRC-9306", S.VERIFIED, salor, by=cls.other_resident)

    def stats(self, user, **params):
        self.client.force_login(user)
        response = self.client.get(STATS, params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def refs(self, user, url=LIST, **params):
        self.client.force_login(user)
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["reference"] for row in response.json()["results"]}

    def test_officer_counts_cover_only_the_district(self):
        stats = self.stats(self.officer)
        self.assertEqual(stats["to_verify"], 1)
        # A submitted request's help is not yet claimable, so it is not "waiting for an organisation".
        self.assertEqual(stats["help_waiting"], 2)
        self.assertEqual(stats["awaiting_household"], 1)
        self.assertNotIn("ours", stats)

    def test_ngo_counts_its_own_work_and_the_help_it_could_claim(self):
        stats_a = self.stats(self.ngo_a)
        self.assertEqual(stats_a["help_waiting"], 3)
        self.assertEqual(stats_a["ours"], 2)
        self.assertEqual(stats_a["awaiting_household"], 1)
        # NGOs never see unverified requests, so there is nothing for them to verify.
        self.assertEqual(stats_a["to_verify"], 0)
        self.assertEqual(self.stats(self.ngo_b)["ours"], 1)

    def test_the_help_waiting_filter_matches_its_count_on_list_map_and_stats(self):
        for user, expected in (
            (self.officer, {"FRC-9302", "FRC-9305"}),
            (self.ngo_a, {"FRC-9302", "FRC-9305", "FRC-9306"}),
        ):
            with self.subTest(user=user.email):
                self.assertEqual(self.refs(user, open_help="1"), expected)
                self.assertEqual(self.stats(user, open_help="1")["total"], len(expected))
                self.client.force_login(user)
                body = self.client.get(MAP, {"open_help": "1"}).json()
                mapped = len(body["points"]) + sum(a["case_count"] for a in body["areas"]) + body["unmapped"]
                self.assertEqual(mapped, len(expected))

    def test_the_ours_filter_shows_only_the_organisations_active_work(self):
        self.assertEqual(self.refs(self.ngo_a, mine="1"), {"FRC-9303", "FRC-9304"})
        self.assertEqual(self.refs(self.ngo_b, mine="1"), {"FRC-9305"})

    def test_only_an_ngo_may_ask_for_its_own_work(self):
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(LIST, {"mine": "1"}).status_code, 400)

    def test_filter_values_other_than_1_are_refused(self):
        self.client.force_login(self.ngo_a)
        for params in ({"open_help": "yes"}, {"mine": "true"}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(LIST, params).status_code, 400)

    def test_a_resident_counts_only_their_own_requests(self):
        stats = self.stats(self.other_resident)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["help_waiting"], 1)
        self.assertNotIn("ours", stats)
