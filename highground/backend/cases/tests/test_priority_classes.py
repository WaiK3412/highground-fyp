"""Traceability: FR10 (case prioritisation) under classes-1.0 (ADR-018)."""

from datetime import timedelta

from django.utils import timezone

from cases.duplicate_services import detect_duplicates_for_case
from cases.models import CaseEventLog, CaseRecord, LocationArea
from cases.tests.test_lifecycle import LifecycleTestCase


class VerificationClassifiesTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.case.status = CaseRecord.Status.SUBMITTED
        self.case.location_area = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.case.save()
        detect_duplicates_for_case(self.case.pk)

    def verify(self):
        self.login(self.officer)
        return self.client.post(
            f"/api/cases/{self.case.pk}/verify/", {"decision": "verified"},
            content_type="application/json",
        )

    def set_answers(self, **fields):
        CaseRecord.objects.filter(pk=self.case.pk).update(**fields)
        self.case.refresh_from_db()

    def test_submission_leaves_class_empty(self):
        self.assertIsNone(self.case.priority_class)

    def test_verification_stores_class_and_reasons(self):
        self.set_answers(urgency="medical_disrupted")
        self.assertEqual(self.verify().status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.priority_class, 1)
        self.assertTrue(self.case.priority_reasons[0].startswith("Health-critical"))

    def test_verification_logs_the_class(self):
        self.set_answers(urgency="none", vulnerability_flags=["elderly"], access_level="normal")
        self.verify()
        event = CaseEventLog.objects.get(
            case=self.case, event_type=CaseEventLog.EventType.SCORE_COMPUTED
        )
        self.assertIn("class 2 (At risk)", event.detail)
        self.assertIn("classes-1.0", event.detail)

    def test_verification_does_not_need_a_rubric(self):
        # The retired weighted score refused to run without a published rubric.
        self.set_answers(urgency="none", vulnerability_flags=[], access_level="normal")
        self.assertEqual(self.verify().status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.priority_class, 3)
        self.assertIsNone(self.case.score_total)

    def test_reverification_recomputes_from_corrected_answers(self):
        self.set_answers(urgency="urgent")
        self.verify()
        self.set_answers(
            urgency="none", vulnerability_flags=[], access_level="normal",
            status=CaseRecord.Status.SUBMITTED,
        )
        self.verify()
        self.case.refresh_from_db()
        self.assertEqual(self.case.priority_class, 3)


class QueueOrderAndFilterTests(LifecycleTestCase):
    def make(self, ref, priority_class, days_ago, status=CaseRecord.Status.VERIFIED):
        return CaseRecord.objects.create(
            reference=ref, submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud.", village="Kg. Test", address="Lot 1",
            status=status, priority_class=priority_class,
            created_at=timezone.now() - timedelta(days=days_ago),
        )

    def setUp(self):
        super().setUp()
        self.case.delete()  # the base fixture case has no class; start clean
        # Oldest first within a class; unverified (NULL) last.
        self.c3_old = self.make("FRC-9101", 3, 5)
        self.c1_new = self.make("FRC-9102", 1, 1)
        self.c2 = self.make("FRC-9103", 2, 3)
        self.unverified = self.make("FRC-9104", None, 9, status=CaseRecord.Status.SUBMITTED)
        self.c3_new = self.make("FRC-9105", 3, 2)
        self.login(self.officer)

    def rows(self, params=None):
        data = self.client.get("/api/cases/", params or {}).json()
        return data["results"] if isinstance(data, dict) else data

    def refs(self, params=None):
        return [row["id"] for row in self.rows(params)]

    def test_order_is_class_then_oldest_first_then_unverified(self):
        self.assertEqual(
            self.refs(),
            [self.c1_new.pk, self.c2.pk, self.c3_old.pk, self.c3_new.pk, self.unverified.pk],
        )

    def test_same_timestamp_ties_break_by_pk(self):
        CaseRecord.objects.filter(pk__in=[self.c3_old.pk, self.c3_new.pk]).update(
            created_at=self.c3_old.created_at
        )
        ids = self.refs({"priority": "3"})
        self.assertEqual(ids, sorted(ids))

    def test_priority_filter(self):
        self.assertEqual(self.refs({"priority": "1"}), [self.c1_new.pk])

    def test_bad_priority_filter_is_400(self):
        self.assertEqual(self.client.get("/api/cases/", {"priority": "high"}).status_code, 400)

    def test_list_exposes_class_fields(self):
        row = self.rows()[0]
        self.assertEqual(row["priority_class"], 1)
        self.assertEqual(row["priority_label"], "Health-critical")
        self.assertNotIn("score_total", row)

    def test_unverified_row_has_no_label(self):
        row = self.rows()[-1]
        self.assertIsNone(row["priority_class"])
        self.assertIsNone(row["priority_label"])

    def test_stats_counts_class_1(self):
        self.assertEqual(self.client.get("/api/cases/stats/").json()["health_critical"], 1)

    def test_map_area_takes_the_highest_class(self):
        village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        CaseRecord.objects.filter(pk__in=[self.c3_old.pk, self.c2.pk]).update(location_area=village)
        self.login(self.mercy_lead)  # an unclaimed NGO sees village groups, not points
        data = self.client.get("/api/cases/map/").json()
        area = next(a for a in data["areas"] if a["code"] == village.code)
        self.assertEqual(area["highest_class"], 2)

    def test_priority_rules_endpoint(self):
        data = self.client.get("/api/priority-rules/").json()
        self.assertEqual(data["version"], "classes-1.0")
        self.assertEqual([c["priority_class"] for c in data["classes"]], [1, 2, 3])

    def test_unclaimed_ngo_summary_hides_the_reasons(self):
        # Reasons name household vulnerabilities (disability, older person);
        # an NGO that has not claimed the case gets the class label only.
        CaseRecord.objects.filter(pk=self.c2.pk).update(priority_reasons=["At risk: older person in the household"])
        self.login(self.mercy_lead)
        data = self.client.get(f"/api/cases/{self.c2.pk}/").json()
        self.assertEqual(data["detail_access"], "summary")
        self.assertEqual(data["priority_label"], "At risk")
        self.assertNotIn("priority_reasons", data)
        self.login(self.officer)
        self.assertEqual(
            self.client.get(f"/api/cases/{self.c2.pk}/").json()["priority_reasons"],
            ["At risk: older person in the household"],
        )
