"""Tests for a household submitting an aid request.

Traceability — requirements covered by this file:
  FR3  Resident submits an aid or recovery request
  FR20 Role-based permissions on every endpoint
  FR21 Submission is recorded in the append-only event log

The tests that matter here are the refusals, not the happy path. A create
endpoint that accepts everything it is sent would let a household set its own
priority score, which is the one thing the whole rubric exists to prevent.
"""

import json
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import UserAccount
from cases.models import CaseEventLog, CasePhoto, CaseRecord, LocationArea

URL = "/api/cases/"

# Kampung Tendong, Pasir Mas — one of the starter villages loaded by migration.
VALID = {
    "location_code": "MY0307-V001",
    "address": "No. 14, Jalan Masjid",
    "household_size": 5,
    "damage_category": "cleanup",
    "description": "Waist-deep water, thick mud in every room.",
    "flood_depth": "waist",
    "liveability": "partial",
    "access_level": "four_wd",
    "urgency": "medical_disrupted",
    "vulnerability_flags": ["elderly", "disability"],
    "needs_flags": ["water", "bedding"],
}


class SubmissionTestCase(TestCase):
    def setUp(self):
        self.resident = UserAccount.objects.create_user(
            email="siti@example.my", full_name="Siti binti Rahman", password="Recovery2026",
        )

    def post(self, **overrides):
        payload = {**VALID, **overrides}
        return self.client.post(URL, payload, content_type="application/json")


class PermissionTests(SubmissionTestCase):
    def test_anonymous_cannot_submit(self):
        response = self.post()
        self.assertIn(response.status_code, {401, 403})
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_a_resident_can_submit(self):
        self.client.force_login(self.resident)
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CaseRecord.objects.count(), 1)

    def test_the_case_belongs_to_the_submitting_user(self):
        """Ownership comes from the session, never from the request body."""
        other = UserAccount.objects.create_user(
            email="someone@example.my", full_name="Someone Else", password="Recovery2026",
        )
        self.client.force_login(self.resident)
        self.post(submitted_by_user=other.pk)

        case = CaseRecord.objects.get()
        self.assertEqual(case.submitted_by_user, self.resident)


class FieldWhitelistTests(SubmissionTestCase):
    """The serializer's field list is the security boundary.

    Each of these posts a field a household must not control. The endpoint
    must ignore it rather than honour it — a 201 whose stored value is the
    server's, not the client's.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.resident)

    def test_a_household_cannot_set_its_own_score(self):
        self.post(score_total=100)
        self.assertIsNone(CaseRecord.objects.get().score_total)

    def test_a_household_cannot_submit_an_already_verified_case(self):
        self.post(status=CaseRecord.Status.VERIFIED)
        self.assertEqual(CaseRecord.objects.get().status, CaseRecord.Status.SUBMITTED)

    def test_a_household_cannot_mark_itself_verified_by_an_officer(self):
        officer = UserAccount.objects.create_user(
            email="officer@example.my", full_name="Officer", password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        self.post(verified_by_user=officer.pk)
        self.assertIsNone(CaseRecord.objects.get().verified_by_user)

    def test_a_household_cannot_choose_its_own_reference(self):
        self.post(reference="FRC-0001")
        self.assertNotEqual(CaseRecord.objects.get().reference, "FRC-0001")

    def test_a_household_cannot_write_a_free_text_village(self):
        """The village name comes from the chosen area, not from the body."""
        self.post(village="Somewhere Invented")
        self.assertEqual(CaseRecord.objects.get().village, "Kampung Tendong")


class ValidationTests(SubmissionTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.resident)

    def test_unknown_needs_flags_are_refused(self):
        """The engine awards points per flag, so an open list is a way to
        inflate your own priority."""
        response = self.post(needs_flags=["water", "helicopter", "cash"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_unknown_vulnerability_flags_are_refused(self):
        response = self.post(vulnerability_flags=["elderly", "vip"])
        self.assertEqual(response.status_code, 400)

    def test_repeated_flags_are_counted_once(self):
        self.post(needs_flags=["water", "water", "water"])
        self.assertEqual(CaseRecord.objects.get().needs_flags, ["water"])

    def test_an_empty_description_is_refused(self):
        response = self.post(description="   ")
        self.assertEqual(response.status_code, 400)

    def test_a_household_of_zero_is_refused(self):
        response = self.post(household_size=0)
        self.assertEqual(response.status_code, 400)


class LocationTests(SubmissionTestCase):
    """A case is filed under a controlled village, never under free text."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.resident)

    def test_the_case_stores_the_area_and_its_name(self):
        response = self.post()

        self.assertEqual(response.status_code, 201, response.content)
        case = CaseRecord.objects.get()
        self.assertEqual(case.location_area.code, "MY0307-V001")
        self.assertEqual(case.village, "Kampung Tendong")
        self.assertEqual(response.json()["village"], "Kampung Tendong")

    def test_a_village_is_required(self):
        payload = {key: value for key, value in VALID.items() if key != "location_code"}
        response = self.client.post(URL, payload, content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("location_code", response.json())

    def test_an_unknown_code_is_refused(self):
        response = self.post(location_code="MY0307-V999")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_a_retired_village_is_refused(self):
        LocationArea.objects.filter(code="MY0307-V001").update(active=False)
        response = self.post()
        self.assertEqual(response.status_code, 400)

    def test_a_district_is_not_a_village(self):
        response = self.post(location_code="MY0307")
        self.assertEqual(response.status_code, 400)


class SubmittedStateTests(SubmissionTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.resident)

    def test_a_new_case_is_unscored_and_awaiting_verification(self):
        """Screen 17: a request is checked by an officer 'before it is scored
        and released to the NGO queue'. Scoring is FR13's job, not FR3's."""
        self.post()
        case = CaseRecord.objects.get()

        self.assertEqual(case.status, CaseRecord.Status.SUBMITTED)
        self.assertIsNone(case.score_total)
        self.assertEqual(case.score_components.count(), 0)

    def test_submission_is_written_to_the_event_log(self):
        self.post()
        event = CaseEventLog.objects.get(
            case=CaseRecord.objects.get(), event_type=CaseEventLog.EventType.SUBMITTED
        )

        self.assertEqual(event.event_type, CaseEventLog.EventType.SUBMITTED)
        self.assertEqual(event.actor_user, self.resident)

    def test_references_do_not_collide(self):
        self.post()
        self.post(description="A second, separate request.")

        references = set(CaseRecord.objects.values_list("reference", flat=True))
        self.assertEqual(len(references), 2)

    def test_the_submitter_can_see_their_own_new_case(self):
        self.post()
        listing = self.client.get(URL)

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["results"]), 1)


# A FileField writes for real, even in tests. Without this every run would add
# more files to backend/media/.
TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class PhotoUploadTests(SubmissionTestCase):
    """Photos attached to a submission (FR3).

    A submission carrying files arrives as multipart rather than JSON, which
    changes how the flag lists travel — hence the JSON-encoded flags below.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.client.force_login(self.resident)

    def photo(self, name="damage.jpg", content_type="image/jpeg", size=32):
        return SimpleUploadedFile(name, b"x" * size, content_type=content_type)

    def post_multipart(self, photos, **overrides):
        payload = {**VALID, **overrides}
        # multipart cannot carry a list, so the client JSON-encodes them
        payload["needs_flags"] = json.dumps(payload["needs_flags"])
        payload["vulnerability_flags"] = json.dumps(payload["vulnerability_flags"])
        if photos:
            payload["photos"] = photos
        return self.client.post(URL, payload)

    def test_a_submitted_photo_is_stored(self):
        response = self.post_multipart([self.photo()])
        self.assertEqual(response.status_code, 201, response.content)

        case = CaseRecord.objects.get()
        self.assertEqual(case.photos.count(), 1)
        self.assertTrue(case.photos.get().file_path.name.endswith(".jpg"))

    def test_several_photos_are_all_stored(self):
        self.post_multipart([self.photo("a.jpg"), self.photo("b.png", "image/png")])
        self.assertEqual(CaseRecord.objects.get().photos.count(), 2)

    def test_flags_survive_a_multipart_submission(self):
        """The JSON-encoded lists must arrive as lists, not as one string."""
        self.post_multipart([self.photo()])
        case = CaseRecord.objects.get()

        self.assertEqual(case.needs_flags, ["bedding", "water"])
        self.assertEqual(case.vulnerability_flags, ["disability", "elderly"])

    def test_a_submission_without_photos_still_works(self):
        response = self.post_multipart([])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CaseRecord.objects.get().photos.count(), 0)

    def test_more_than_five_photos_is_refused(self):
        response = self.post_multipart([self.photo(f"{i}.jpg") for i in range(6)])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_a_non_image_is_refused(self):
        response = self.post_multipart(
            [self.photo("notes.pdf", content_type="application/pdf")]
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_an_oversized_photo_is_refused(self):
        response = self.post_multipart([self.photo(size=6 * 1024 * 1024)])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseRecord.objects.count(), 0)

    def test_the_event_log_records_how_many_photos_came_with_it(self):
        self.post_multipart([self.photo("a.jpg"), self.photo("b.jpg")])
        event = CaseEventLog.objects.get(
            case=CaseRecord.objects.get(), event_type=CaseEventLog.EventType.SUBMITTED
        )

        self.assertIn("2 photo(s)", event.detail)

    def test_a_photo_is_refused_when_the_case_is_refused(self):
        """Validation failure must not leave an orphan photo behind."""
        response = self.post_multipart([self.photo()], description="   ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CasePhoto.objects.count(), 0)
