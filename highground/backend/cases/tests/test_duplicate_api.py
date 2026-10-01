"""Duplicate review API, verification gate and privacy (screen 12, §3.7.8).

Traceability — requirements covered by this file:
  FR14 Officers review flagged duplicates; nothing is merged automatically
  FR20 Every endpoint has an explicit role policy, tested per role
  NFR3 Residents see only their own case; NGOs never see comparison data
"""

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import Client, TestCase

from cases import duplicate_services as svc
from cases.models import CaseEventLog, CaseRecord, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld, make_case
from .job_helpers import give_job

Event = CaseEventLog.EventType


class ApiWorld(DuplicateWorld):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        svc.scan_duplicate_area(self.area.pk)
        self.match = DuplicateCaseMatch.objects.get()
        mail.outbox = []

    def as_user(self, user):
        self.client.force_login(user)

    def decide(self, decision, match=None):
        return self.client.post(
            f"/api/duplicates/{(match or self.match).pk}/decide/",
            {"decision": decision}, content_type="application/json",
        )


class PermissionTests(ApiWorld, TestCase):
    def endpoints(self):
        return [
            ("get", "/api/duplicates/"),
            ("get", f"/api/duplicates/{self.match.pk}/"),
            ("post", f"/api/duplicates/{self.match.pk}/decide/"),
        ]

    def test_only_disaster_officers_reach_duplicate_endpoints(self):
        # The claiming NGO is included: claiming a case gives no right to
        # compare it with another household's.
        give_job(self.older, self.org)
        for user in (self.resident, self.relative, self.ngo, self.other_ngo, self.admin_user):
            self.as_user(user)
            for method, url in self.endpoints():
                response = getattr(self.client, method)(url, {"decision": "dismiss"}, content_type="application/json") \
                    if method == "post" else self.client.get(url)
                self.assertEqual(response.status_code, 403, (user.email, url))
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, DuplicateCaseMatch.Status.OPEN)

    def test_anonymous_callers_are_refused(self):
        self.client.logout()
        for method, url in self.endpoints():
            response = getattr(self.client, method)(url)
            self.assertIn(response.status_code, (401, 403))

    def test_decision_without_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.officer)
        response = client.post(
            f"/api/duplicates/{self.match.pk}/decide/", {"decision": "confirm"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, DuplicateCaseMatch.Status.OPEN)


    def test_vite_fallback_origin_accepts_a_valid_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.officer)
        client.get("/api/auth/csrf/")
        token = client.cookies["csrftoken"].value
        response = client.post(
            f"/api/duplicates/{self.match.pk}/decide/", {"decision": "dismiss"},
            content_type="application/json",
            HTTP_ORIGIN="http://127.0.0.1:5174",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "rejected")


class ListAndDetailTests(ApiWorld, TestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.officer)

    def test_list_defaults_to_open_flags_with_compact_rows(self):
        data = self.client.get("/api/duplicates/").json()
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(
            set(row),
            {"id", "status", "method", "similarity_score", "classification", "matched_rules",
             "case_a", "case_b"},
        )
        self.assertEqual(row["case_a"], {"id": self.older.pk, "reference": "FRC-5001"})
        self.assertEqual(row["case_b"]["reference"], "FRC-5002")

    def test_queue_badge_and_case_review_ids_are_officer_only(self):
        queue = self.client.get("/api/cases/").json()["results"]
        by_ref = {row["reference"]: row for row in queue}
        self.assertTrue(by_ref["FRC-5001"]["has_open_duplicate"])
        self.assertTrue(by_ref["FRC-5002"]["has_open_duplicate"])
        older = self.client.get(f"/api/cases/{self.older.pk}/").json()
        newer = self.client.get(f"/api/cases/{self.newer.pk}/").json()
        self.assertEqual(older["duplicate_review"]["blocking_match_ids"], [])
        self.assertEqual(newer["duplicate_review"]["blocking_match_ids"], [self.match.pk])
        self.assertIsNone(newer["duplicate_review"]["confirmed_match_id"])

        self.as_user(self.relative)
        resident = self.client.get("/api/cases/").json()["results"][0]
        self.assertNotIn("has_open_duplicate", resident)
        self.assertIsNone(self.client.get(f"/api/cases/{self.newer.pk}/").json()["duplicate_review"])

        self.older.status = CaseRecord.Status.VERIFIED
        self.older.save(update_fields=["status"])
        give_job(self.older, self.org, status="claimed")
        self.as_user(self.ngo)
        ngo = self.client.get("/api/cases/").json()["results"]
        self.assertTrue(ngo)
        self.assertTrue(all("has_open_duplicate" not in row for row in ngo))
        self.assertIsNone(self.client.get(f"/api/cases/{self.older.pk}/").json()["duplicate_review"])

    def test_list_filters_by_status_and_rejects_unknown_ones(self):
        self.assertEqual(self.client.get("/api/duplicates/?status=rejected").json()["count"], 0)
        response = self.client.get("/api/duplicates/?status=bogus")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_status")

    def test_detail_shows_both_cases_and_keeps_stored_and_current_evidence_apart(self):
        data = self.client.get(f"/api/duplicates/{self.match.pk}/").json()
        self.assertEqual(data["method"], "rules-1.0")
        self.assertIsNone(data["similarity_score"])
        self.assertEqual(data["case_b"]["submitter_name"], "Ahmad Ismail")
        self.assertEqual(data["case_a"]["village"], "Kampung Sireh")
        current = data["current_comparison"]
        self.assertEqual(current["basis"], "current_inputs")
        self.assertEqual(current["method"], "rules-1.0")
        self.assertTrue(current["matched"])
        self.assertTrue(all(set(r) == {"rule", "text"} for r in current["reasons"]))
        self.assertTrue(data["can_confirm"])
        self.assertTrue(data["verification_blocked"])
        self.assertIsNone(data["decided_by"])

    def test_viewing_never_changes_the_stored_rules(self):
        self.newer.address = "Lot 12, Jalan Sekolah"
        self.newer.save()
        before = self.match.matched_rules
        data = self.client.get(f"/api/duplicates/{self.match.pk}/").json()
        self.match.refresh_from_db()
        self.assertEqual(self.match.matched_rules, before)
        # The current check reflects the edit; the stored flag does not.
        self.assertNotIn("same_house_and_address", [r["rule"] for r in data["current_comparison"]["reasons"]])
        self.assertIn("Same house or lot number and the same address", [r["text"] for r in data["matched_rules"]])

    def test_current_check_shows_contradictions_and_pin_distance(self):
        self.newer.address = "Lot 89, Jalan Masjid, Kampung Sireh"
        self.newer.save()
        current = self.client.get(f"/api/duplicates/{self.match.pk}/").json()["current_comparison"]
        self.assertEqual(
            current["contradictions"],
            [{"rule": "different_house_number", "text": "Different house or lot numbers"}],
        )
        self.assertIsNone(current["pin_distance_metres"])  # neither case has a pin

    def test_each_side_lists_its_types_of_help(self):
        give_job(self.older)
        data = self.client.get(f"/api/duplicates/{self.match.pk}/").json()
        self.assertEqual(
            data["case_a"]["jobs"], [{"help_type_display": "Repair", "status_display": "Waiting for an organisation"}]
        )
        self.assertEqual(data["case_b"]["jobs"], [])

    def test_rules_flag_serialises_method_and_rule_texts(self):
        row = self.client.get("/api/duplicates/").json()["results"][0]
        self.assertEqual(row["method"], "rules-1.0")
        self.assertIsNone(row["similarity_score"])
        self.assertIsNone(row["classification"])
        self.assertIn({"rule": "same_phone", "text": "Same phone number"}, row["matched_rules"])

    def test_legacy_dup_1_1_flag_still_displays(self):
        self.match.delete()
        legacy = DuplicateCaseMatch.objects.create(
            case_a=self.older, case_b=self.newer, similarity_score=Decimal("37.05"),
            method="dup-1.1", matched_rules=[],
        )
        row = self.client.get("/api/duplicates/").json()["results"][0]
        self.assertEqual(row["method"], "dup-1.1")
        self.assertEqual(row["similarity_score"], "37.05")
        self.assertEqual(row["classification"], "possible")
        self.assertEqual(row["matched_rules"], [])
        self.assertEqual(self.client.get(f"/api/duplicates/{legacy.pk}/").status_code, 200)

    def test_unknown_match_is_404(self):
        self.assertEqual(self.client.get("/api/duplicates/999999/").status_code, 404)
        self.assertEqual(self.decide("confirm", DuplicateCaseMatch(pk=999999)).status_code, 404)

    def test_comparison_failure_is_a_sanitised_503(self):
        with mock.patch.object(svc, "compare_by_rules", side_effect=RuntimeError("Lot 88 secret")):
            with self.assertLogs("cases.api", level="WARNING") as logs:
                response = self.client.get(f"/api/duplicates/{self.match.pk}/")
        self.assertNotIn("Lot 88", logs.output[0])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "comparison_unavailable")
        self.assertNotIn("Lot 88", response.content.decode())


class DecisionApiTests(ApiWorld, TestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.officer)

    def test_confirm_returns_compact_result_and_notifies_the_newer_household_once(self):
        response = self.decide("confirm")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "confirmed")
        self.assertEqual(data["newer_case"], {"id": self.newer.pk, "reference": "FRC-5002", "status": "closed"})
        self.assertEqual(data["decided_by"], "Encik Zulkifli")

        notes = CaseEventLog.objects.filter(recipient_user__isnull=False, event_type=Event.DUPLICATE_CLOSED)
        self.assertEqual(list(notes.values_list("recipient_user", flat=True)), [self.relative.pk])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("FRC-5002", mail.outbox[0].body)
        self.assertNotIn("FRC-5001", mail.outbox[0].body)

        # A retry is harmless: same answer, no second notification.
        again = self.decide("confirm")
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["changed"])
        self.assertEqual(notes.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_household_is_told_even_when_the_deciding_officer_filed_the_case(self):
        self.newer.submitted_by_user = self.officer
        self.newer.save()
        self.decide("confirm")
        self.assertTrue(
            CaseEventLog.objects.filter(recipient_user=self.officer, event_type=Event.DUPLICATE_CLOSED).exists()
        )

    def test_email_failure_keeps_the_closure_and_in_app_notification(self):
        with mock.patch("cases.notifications.send_mail", side_effect=OSError):
            response = self.decide("confirm")
        self.assertEqual(response.status_code, 200)
        self.newer.refresh_from_db()
        self.assertEqual(self.newer.status, CaseRecord.Status.CLOSED)
        note = CaseEventLog.objects.get(recipient_user=self.relative)
        self.assertTrue(note.delivery_status.startswith("failed"))

    def test_invalid_decision_is_400_and_conflicts_are_409(self):
        response = self.decide("merge")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_decision")
        self.decide("dismiss")
        response = self.decide("confirm")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "conflicting_decision")

    def test_optional_note_is_internal_bounded_and_not_duplicated_on_retry(self):
        url = f"/api/duplicates/{self.match.pk}/decide/"
        too_long = self.client.post(url, {"decision": "dismiss", "note": "x" * 1001}, content_type="application/json")
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(too_long.json()["code"], "invalid_note")
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, DuplicateCaseMatch.Status.OPEN)

        payload = {"decision": "dismiss", "note": "  Two separate households.  "}
        self.assertEqual(self.client.post(url, payload, content_type="application/json").status_code, 200)
        events = CaseEventLog.objects.filter(event_type=Event.DUPLICATE_DISMISSED)
        self.assertEqual(events.count(), 2)
        self.assertTrue(all("Officer note: Two separate households." in event.detail for event in events))
        self.assertEqual(self.client.post(url, payload, content_type="application/json").json()["changed"], False)
        self.assertEqual(events.count(), 2)
        self.as_user(self.resident)
        self.assertNotIn("Two separate households", str(self.client.get(f"/api/cases/{self.older.pk}/").json()))

    def test_confirmation_note_stays_out_of_household_notice(self):
        url = f"/api/duplicates/{self.match.pk}/decide/"
        response = self.client.post(url, {"decision": "confirm", "note": "Private comparison note"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Private comparison note", CaseEventLog.objects.filter(
            case=self.newer, event_type=Event.DUPLICATE_CONFIRMED
        ).get().detail)
        self.assertNotIn("Private comparison note", mail.outbox[0].body)
        self.as_user(self.relative)
        self.assertNotIn("Private comparison note", str(self.client.get(f"/api/cases/{self.newer.pk}/").json()))


class VerificationGateTests(ApiWorld, TestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.officer)
        from cases.management.commands.seed_demo import RUBRIC_V3
        from django.utils import timezone
        from scoring.models import PriorityRubricCriterion, PriorityRubricVersion

        version = PriorityRubricVersion.objects.create(
            label="v3.0", status=PriorityRubricVersion.Status.PUBLISHED, published_at=timezone.now(),
        )
        for key, name, weight, max_points, rule in RUBRIC_V3:
            PriorityRubricCriterion.objects.create(
                version=version, key=key, name=name, weight=weight, max_points=max_points, rule_text=rule,
            )

    def verify(self, case, decision="verified", note=""):
        return self.client.post(
            f"/api/cases/{case.pk}/verify/", {"decision": decision, "note": note},
            content_type="application/json",
        )

    def test_open_flag_blocks_verifying_the_newer_case(self):
        response = self.verify(self.newer)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "duplicate_review_required")
        self.assertEqual(response.json()["duplicate_match_ids"], [self.match.pk])
        self.newer.refresh_from_db()
        self.assertEqual(self.newer.status, CaseRecord.Status.SUBMITTED)
        self.assertIsNone(self.newer.score_total)

    def test_needs_info_and_reject_stay_available(self):
        self.assertEqual(self.verify(self.newer, "needs_info", "Which lot?").status_code, 200)

    def test_dismissal_unblocks_verification(self):
        self.decide("dismiss")
        self.assertEqual(self.verify(self.newer).status_code, 200)

    def test_pending_check_blocks_verification(self):
        fresh = make_case(self.neighbour, self.area, reference="FRC-5009", address="Lot 3")
        response = self.verify(fresh)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "duplicate_check_pending")
        self.assertEqual(response.json()["duplicate_match_ids"], [])

    def test_a_linked_duplicate_cannot_be_reopened_by_any_verification_decision(self):
        self.decide("confirm")
        for decision, note in (("verified", ""), ("needs_info", "x"), ("rejected", "x")):
            response = self.verify(self.newer, decision, note)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["code"], "case_linked_duplicate")
            self.assertEqual(response.json()["duplicate_match_ids"], [self.match.pk])


class SubmissionHookTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        make_case(self.resident, self.area, reference="FRC-5001", minutes_ago=120)
        self.client.force_login(self.relative)

    def submit(self):
        return self.client.post("/api/cases/", {
            "location_code": self.area.code,
            "address": "Lot 88 Jln Masjid Kg Sireh",
            "household_size": 4,
            "damage_category": "repair",
            "description": "Air masuk rumah paras pinggang, dapur rosak dan tilam basah.",
            "needs_flags": ["food", "water"],
        }, content_type="application/json")

    def test_submission_runs_detection_and_reports_only_the_check_state(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["duplicate_check"], "completed")
        self.assertNotIn("FRC-5001", response.content.decode())
        self.assertEqual(DuplicateCaseMatch.objects.count(), 1)

    def test_a_submitted_pin_at_the_same_spot_fires_the_pin_rule(self):
        """The resident pin is what lets real submissions use the same-pin
        rule; without it only seeded cases had pins."""
        CaseRecord.objects.filter(reference="FRC-5001").update(
            latitude=Decimal("6.100510"), longitude=Decimal("102.200290")
        )
        payload = {
            "location_code": self.area.code,
            "address": "Lot 88 Jln Masjid Kg Sireh",
            "household_size": 4,
            "damage_category": "repair",
            "description": "Air masuk rumah paras pinggang, dapur rosak dan tilam basah.",
            "needs_flags": ["food", "water"],
            # Equal to FRC-5001's pin at 4 decimal places (about 11 m).
            "latitude": 6.10049, "longitude": 102.20031,
        }
        response = self.client.post("/api/cases/", payload, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)

        match = DuplicateCaseMatch.objects.get()
        self.assertIn("same_pin", match.matched_rules)
        current = [r["rule"] for r in svc.current_duplicate_comparison(match)["reasons"]]
        self.assertIn("same_pin", current)

    def test_detection_failure_never_loses_the_submission(self):
        with mock.patch.object(svc, "compare_by_rules", side_effect=RuntimeError):
            with self.assertLogs("cases.duplicate_services", level="WARNING"):
                response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["duplicate_check"], "pending")
        case = CaseRecord.objects.get(pk=response.json()["id"])
        self.assertTrue(CaseEventLog.objects.filter(case=case, event_type=Event.SUBMITTED).exists())
        self.assertFalse(DuplicateCaseMatch.objects.exists())

        # A later successful scan clears the pending state.
        svc.scan_duplicate_area(self.area.pk)
        self.assertEqual(svc.duplicate_check_state(case), "completed")


class PrivacyTests(ApiWorld, TestCase):
    """Comparison data must not leak through any shared channel."""

    INTERNAL = {e.value for e in svc.INTERNAL_DUPLICATE_EVENTS}

    def setUp(self):
        super().setUp()
        self.as_user(self.officer)
        self.decide("confirm")

    def timeline(self, user, case):
        self.as_user(user)
        return self.client.get(f"/api/cases/{case.pk}/").json()

    def test_resident_sees_only_the_safe_closure_event(self):
        data = self.timeline(self.relative, self.newer)
        types = {event["event_type"] for event in data["events"]}
        self.assertFalse(types & self.INTERNAL)
        self.assertIn("duplicate_closed", types)
        self.assertNotIn("FRC-5001", str(data))
        self.assertIsNone(data["duplicate_review"])
        self.assertEqual(data["duplicate_check"], "completed")

    def test_other_household_cannot_see_the_closed_case_at_all(self):
        self.as_user(self.neighbour)
        self.assertEqual(self.client.get(f"/api/cases/{self.newer.pk}/").status_code, 404)

    def test_claiming_ngo_timeline_hides_internal_duplicate_events(self):
        self.older.status = CaseRecord.Status.CLAIMED
        self.older.save()
        give_job(self.older, self.org)
        data = self.timeline(self.ngo, self.older)
        self.assertFalse({e["event_type"] for e in data["events"]} & self.INTERNAL)
        self.assertNotIn("FRC-5002", str(data))
        self.assertIsNone(data["duplicate_check"])
        self.assertIsNone(data["duplicate_review"])

    def test_lifecycle_responses_filter_events_too(self):
        # claim_case returns CaseDetailSerializer without case_detail's
        # prefetch; the serializer itself must filter.
        self.older.status = CaseRecord.Status.VERIFIED
        self.older.save()
        job = give_job(self.older)
        self.as_user(self.ngo)
        data = self.client.post(f"/api/jobs/{job.pk}/claim/").json()
        self.assertFalse({e["event_type"] for e in data["events"]} & self.INTERNAL)

    def test_officer_sees_the_audit_trail_and_review_summary(self):
        data = self.timeline(self.officer, self.newer)
        self.assertIn("duplicate_confirmed", {e["event_type"] for e in data["events"]})
        self.assertEqual(data["duplicate_review"]["duplicate_of"], "FRC-5001")
        self.assertEqual(data["duplicate_review"]["verification_block"], "case_linked_duplicate")

    def test_resident_notifications_carry_no_counterpart_details(self):
        self.as_user(self.relative)
        body = self.client.get("/api/notifications/").content.decode()
        self.assertIn("FRC-5002", body)
        self.assertNotIn("FRC-5001", body)
        self.assertNotIn("Ahmad bin Ismail", body)
