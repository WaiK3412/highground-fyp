"""A disaster officer acts for one district (ADR-024).

Traceability — requirements covered by this file:
  FR20 Role-based permissions on every endpoint: an officer sees and acts only on
       cases filed under their district's villages; another district's case answers
       404, an officer with no district is refused with a reason, administrators see
       every district, and Django Admin is the administrator's console only
  NFR3 Exact locations and household details are need-to-know (report §3.5)
"""

import shutil
import tempfile
from decimal import Decimal

from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.models import Organization, RoleApplication, UserAccount
from accounts.permissions import NO_DISTRICT
from cases.models import (
    CaseEventLog, CaseJob, CasePhoto, CaseRecord, CaseTask, DuplicateCaseMatch, LocationArea,
)
from cases.tests.job_helpers import give_job

PASSWORD = "Recovery2026"
MEDIA = tempfile.mkdtemp(prefix="highground-district-test-")


def jpeg():
    return SimpleUploadedFile("private.jpg", b"\xff\xd8\xffphoto", content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class DistrictScopingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # Two gazetteer districts (migration 0008): Kota Bharu and Pasir Mas.
        self.kb_village = LocationArea.objects.get(code="MY0304-V001")
        self.pm_village = LocationArea.objects.get(code="MY0307-V001")

        def user(email, role, **extra):
            return UserAccount.objects.create_user(
                email=email, full_name=email.split("@")[0], password=PASSWORD, role=role, **extra,
            )

        Role = UserAccount.Role
        self.kb_officer = user("kb-officer@example.my", Role.DISASTER_OFFICER, district=self.kb_village.parent)
        self.pm_officer = user("pm-officer@example.my", Role.DISASTER_OFFICER, district=self.pm_village.parent)
        self.no_district = user("unassigned@example.my", Role.DISASTER_OFFICER)
        self.admin = user("admin@example.my", Role.SYSTEM_ADMIN)
        self.resident = user("resident@example.my", Role.COMMUNITY_MEMBER)
        self.org = Organization.objects.create(name="Mercy Relief", type=Organization.Type.NGO)

        self.kb_case = self.case("FRC-7001", self.kb_village)
        self.pm_case = self.case("FRC-7002", self.pm_village)

    def case(self, reference, village, status=CaseRecord.Status.SUBMITTED, **fields):
        return CaseRecord.objects.create(
            reference=reference, submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud through the ground floor.", village=village.name,
            address="Lot 1", location_area=village, status=status,
            created_at=timezone.now(), **fields,
        )

    def as_user(self, user):
        self.client.force_login(user)
        return self.client

    def post(self, user, path, payload):
        return self.as_user(user).post(path, payload, content_type="application/json")

    # -- reading ---------------------------------------------------------------

    def test_the_queue_lists_only_the_officers_district_and_admins_see_both(self):
        for user, expected in (
            (self.kb_officer, {"FRC-7001"}),
            (self.pm_officer, {"FRC-7002"}),
            (self.admin, {"FRC-7001", "FRC-7002"}),
        ):
            rows = self.as_user(user).get("/api/cases/").json()["results"]
            self.assertEqual({row["reference"] for row in rows}, expected, user.email)

    def test_another_districts_case_answers_404_not_403(self):
        response = self.as_user(self.kb_officer).get(f"/api/cases/{self.pm_case.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"/api/cases/{self.kb_case.pk}/").status_code, 200)

    def test_the_map_and_stats_count_only_the_officers_district(self):
        CaseRecord.objects.filter(pk=self.kb_case.pk).update(
            latitude=Decimal("6.111111"), longitude=Decimal("102.222222"),
        )
        CaseRecord.objects.filter(pk=self.pm_case.pk).update(
            latitude=Decimal("6.071111"), longitude=Decimal("102.211111"),
        )
        client = self.as_user(self.kb_officer)
        response = client.get("/api/cases/map/")
        points = response.json()["points"]
        self.assertEqual([p["reference"] for p in points], ["FRC-7001"])
        self.assertEqual(points[0]["precision"], "exact")  # their own household pin
        self.assertNotContains(response, "6.071111")  # the other district's pin
        self.assertEqual(client.get("/api/cases/stats/").json()["total"], 1)

    def test_an_officer_without_a_district_is_refused_everywhere_and_told_why(self):
        photo = CasePhoto.objects.create(case=self.kb_case, file_path=jpeg())
        client = self.as_user(self.no_district)
        for path in (
            "/api/cases/", "/api/cases/stats/", "/api/cases/map/", f"/api/cases/{self.kb_case.pk}/",
            f"/api/cases/{self.kb_case.pk}/tasks/", f"/api/case-photos/{photo.pk}/file/",
            "/api/notifications/", "/api/duplicates/", "/api/jobs/unmet/",
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.json()["detail"], NO_DISTRICT, path)
        for path, payload in (
            (f"/api/cases/{self.kb_case.pk}/verify/", {"decision": "verified"}),
            ("/api/notifications/read-all/", {}),
        ):
            response = self.post(self.no_district, path, payload)
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.json()["detail"], NO_DISTRICT, path)

    def test_task_reads_and_private_photos_stay_in_the_district(self):
        photo = CasePhoto.objects.create(case=self.pm_case, file_path=jpeg())
        job = give_job(self.pm_case, self.org, CaseJob.Status.CLAIMED)
        CaseTask.objects.create(
            case=self.pm_case, job=job, title="Remove flood debris",
            task_type=CaseTask.TaskType.CLEANUP, status=CaseTask.Status.OPEN,
        )
        client = self.as_user(self.kb_officer)
        self.assertEqual(client.get(f"/api/cases/{self.pm_case.pk}/tasks/").status_code, 404)
        self.assertEqual(client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 404)
        client = self.as_user(self.pm_officer)
        tasks = client.get(f"/api/cases/{self.pm_case.pk}/tasks/").json()
        self.assertEqual([task["title"] for task in tasks], ["Remove flood debris"])
        self.assertEqual(client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 200)

    def test_unmet_help_counts_only_the_officers_district(self):
        CaseRecord.objects.filter(pk=self.pm_case.pk).update(status=CaseRecord.Status.VERIFIED)
        give_job(self.pm_case)  # an open job nobody holds
        kb_rows = self.as_user(self.kb_officer).get("/api/jobs/unmet/").json()
        pm_rows = self.as_user(self.pm_officer).get("/api/jobs/unmet/").json()
        self.assertEqual(kb_rows, [])
        self.assertEqual(sum(row["open_jobs"] for row in pm_rows), 1)

    def test_notifications_follow_the_officers_current_district(self):
        """A row addressed to an officer while posted to Pasir Mas stays in the
        audit log, but is not listed, counted or markable once they move."""
        from cases.notifications import notify

        notify(self.pm_case, CaseEventLog.EventType.SUBMITTED, self.resident)
        row = CaseEventLog.objects.get(recipient_user=self.pm_officer)
        self.assertEqual(self.as_user(self.pm_officer).get("/api/notifications/").json()["unread"], 1)

        self.pm_officer.district = self.kb_village.parent  # reassigned to Kota Bharu
        self.pm_officer.save(update_fields=["district"])
        listing = self.as_user(self.pm_officer).get("/api/notifications/").json()
        self.assertEqual((listing["unread"], listing["results"]), (0, []))
        self.assertEqual(self.post(self.pm_officer, f"/api/notifications/{row.pk}/read/", {}).status_code, 404)
        self.assertEqual(self.post(self.pm_officer, "/api/notifications/read-all/", {}).json()["marked_read"], 0)
        row.refresh_from_db()
        self.assertIsNone(row.read_at)

        self.pm_officer.district = self.pm_village.parent  # posted back to Pasir Mas
        self.pm_officer.save(update_fields=["district"])
        response = self.post(self.pm_officer, f"/api/notifications/{row.pk}/read/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["case_reference"], "FRC-7002")
        row.refresh_from_db()
        self.assertIsNotNone(row.read_at)

    # -- acting ----------------------------------------------------------------

    def test_an_officer_cannot_verify_another_districts_request(self):
        response = self.post(
            self.kb_officer, f"/api/cases/{self.pm_case.pk}/verify/", {"decision": "rejected", "note": "x"},
        )
        self.assertEqual(response.status_code, 404)
        self.pm_case.refresh_from_db()
        self.assertEqual(self.pm_case.status, CaseRecord.Status.SUBMITTED)

        from cases.duplicate_services import detect_duplicates_for_case

        detect_duplicates_for_case(self.pm_case.pk)
        response = self.post(self.pm_officer, f"/api/cases/{self.pm_case.pk}/verify/", {"decision": "verified"})
        self.assertEqual(response.status_code, 200, response.content)

    def test_an_officer_cannot_override_another_districts_priority(self):
        CaseRecord.objects.filter(pk=self.pm_case.pk).update(status=CaseRecord.Status.VERIFIED, priority_class=3)
        response = self.post(
            self.kb_officer, f"/api/cases/{self.pm_case.pk}/priority-override/",
            {"priority_class": 1, "reason": "Dialysis patient at home."},
        )
        self.assertEqual(response.status_code, 404)
        self.pm_case.refresh_from_db()
        self.assertEqual(self.pm_case.priority_class, 3)

    def test_an_officer_cannot_close_another_districts_case(self):
        CaseRecord.objects.filter(pk=self.pm_case.pk).update(status=CaseRecord.Status.PENDING_CONFIRM)
        self.pm_case.refresh_from_db()
        job = give_job(self.pm_case, self.org, CaseJob.Status.PENDING_CONFIRM)
        response = self.post(
            self.kb_officer, f"/api/cases/{self.pm_case.pk}/close/",
            {"outcome": "household_unreachable", "note": "Called twice; no answer."},
        )
        self.assertEqual(response.status_code, 404)
        job.refresh_from_db()
        self.assertEqual(job.status, CaseJob.Status.PENDING_CONFIRM)

    def test_duplicate_review_is_limited_to_the_officers_district(self):
        older = self.case("FRC-7003", self.pm_village)
        match = DuplicateCaseMatch.objects.create(case_a=older, case_b=self.pm_case, similarity_score=90)

        kb = self.as_user(self.kb_officer)
        self.assertEqual(kb.get("/api/duplicates/").json()["count"], 0)
        self.assertEqual(kb.get(f"/api/duplicates/{match.pk}/").status_code, 404)
        response = self.post(self.kb_officer, f"/api/duplicates/{match.pk}/decide/", {"decision": "dismiss"})
        self.assertEqual(response.status_code, 404)
        match.refresh_from_db()
        self.assertEqual(match.status, DuplicateCaseMatch.Status.OPEN)

        pm = self.as_user(self.pm_officer)
        self.assertEqual(pm.get("/api/duplicates/").json()["count"], 1)
        self.assertEqual(pm.get(f"/api/duplicates/{match.pk}/").status_code, 200)

    def test_the_duplicate_service_rechecks_the_district_under_its_locks(self):
        """The view checks first; the service checks again after locking both cases."""
        from cases.duplicate_services import decide_duplicate_match

        older = self.case("FRC-7003", self.pm_village)
        match = DuplicateCaseMatch.objects.create(case_a=older, case_b=self.pm_case, similarity_score=90)
        self.assertIsNone(decide_duplicate_match(match.pk, self.kb_officer, "dismiss"))
        match.refresh_from_db()
        self.assertEqual(match.status, DuplicateCaseMatch.Status.OPEN)
        outcome = decide_duplicate_match(match.pk, self.pm_officer, "dismiss", "Different households.")
        self.assertTrue(outcome.changed)
        match.refresh_from_db()
        self.assertEqual(match.status, DuplicateCaseMatch.Status.REJECTED)

    # -- accounts --------------------------------------------------------------

    def test_an_officer_application_needs_a_district_before_approval(self):
        applicant = UserAccount.objects.create_user(
            email="applicant@example.my", full_name="Applicant", password=PASSWORD,
            requested_role=UserAccount.Role.DISASTER_OFFICER,
            verification_status=UserAccount.VerificationStatus.PENDING,
        )
        with self.assertRaises(ValueError):
            applicant.approve_application(admin=self.admin)
        applicant.refresh_from_db()
        self.assertEqual(applicant.role, UserAccount.Role.COMMUNITY_MEMBER)
        self.assertEqual(applicant.verification_status, UserAccount.VerificationStatus.PENDING)

        applicant.district = self.kb_village.parent
        applicant.save(update_fields=["district"])
        applicant.approve_application(admin=self.admin)
        applicant.refresh_from_db()
        self.assertEqual(applicant.role, UserAccount.Role.DISASTER_OFFICER)
        self.assertEqual(applicant.verification_status, UserAccount.VerificationStatus.VERIFIED)
        self.assertEqual(applicant.verified_by_user, self.admin)

    def test_me_names_the_officers_district(self):
        self.assertEqual(self.as_user(self.kb_officer).get("/api/auth/me/").json()["district"], "Kota Bharu")
        self.assertIsNone(self.as_user(self.resident).get("/api/auth/me/").json()["district"])

    # -- Django Admin ----------------------------------------------------------

    def admin_form(self, model_admin, obj, data):
        # Without change permission Django Admin builds a form with no editable
        # fields, which validates trivially, so act as the console's superuser.
        UserAccount.objects.filter(pk=self.admin.pk).update(is_staff=True, is_superuser=True)
        self.admin.refresh_from_db()
        request = RequestFactory().post("/")
        request.user = self.admin
        form_class = model_admin.get_form(request, obj, change=obj is not None)
        return form_class(data=data, instance=obj)

    def test_a_pending_officer_applicant_can_get_a_district_before_bulk_approval(self):
        applicant = UserAccount.objects.create_user(
            email="applicant@example.my", full_name="Applicant", password=PASSWORD,
            requested_role=UserAccount.Role.DISASTER_OFFICER,
            verification_status=UserAccount.VerificationStatus.PENDING,
        )
        application = RoleApplication.objects.get(pk=applicant.pk)
        application_admin = admin.site._registry[RoleApplication]
        form = self.admin_form(application_admin, application, {
            "district": self.kb_village.parent_id, "verification_status": "pending", "verification_note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        # Approving without a district is refused beside the field, not with a 500.
        form = self.admin_form(application_admin, application, {
            "district": "", "verification_status": "verified", "verification_note": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("district", form.errors)

    def test_the_add_account_form_requires_a_district_for_an_officer(self):
        account_admin = admin.site._registry[UserAccount]
        data = {
            "email": "new-officer@example.my", "full_name": "New Officer",
            "role": UserAccount.Role.DISASTER_OFFICER, "usable_password": "true",
            "password1": "Recovery2026!x", "password2": "Recovery2026!x",
        }
        form = self.admin_form(account_admin, None, data)
        self.assertFalse(form.is_valid())
        self.assertIn("district", form.errors)
        form = self.admin_form(account_admin, None, {**data, "district": self.kb_village.parent_id})
        self.assertTrue(form.is_valid(), form.errors)
        resident = {**data, "role": UserAccount.Role.COMMUNITY_MEMBER, "district": self.kb_village.parent_id}
        self.assertIn("district", self.admin_form(account_admin, None, resident).errors)

    def test_django_admin_is_for_system_administrators_only(self):
        UserAccount.objects.filter(pk__in=[self.kb_officer.pk, self.admin.pk]).update(is_staff=True)
        self.kb_officer.refresh_from_db()
        self.admin.refresh_from_db()
        self.assertEqual(self.as_user(self.kb_officer).get("/admin/").status_code, 302)  # to the login page
        self.assertEqual(self.as_user(self.admin).get("/admin/").status_code, 200)

    def test_a_case_with_duplicate_history_cannot_move_to_another_district(self):
        newer = self.case("FRC-7004", self.kb_village)
        DuplicateCaseMatch.objects.create(case_a=self.kb_case, case_b=newer, similarity_score=90)
        case_admin = admin.site._registry[CaseRecord]
        form = self.admin_form(case_admin, newer, {"location_area": self.pm_village.pk, "village": "Moved"})
        self.assertFalse(form.is_valid())
        self.assertIn("location_area", form.errors)
        same_district = LocationArea.objects.get(code="MY0304-V002")
        form = self.admin_form(case_admin, newer, {"location_area": same_district.pk, "village": "Moved"})
        self.assertTrue(form.is_valid(), form.errors)
        # The older side of the pair is held the same way.
        form = self.admin_form(case_admin, self.kb_case, {"location_area": self.pm_village.pk, "village": "Moved"})
        self.assertIn("location_area", form.errors)
        # So are both ends of a confirmed duplicate link, even after the flag itself is gone.
        DuplicateCaseMatch.objects.all().delete()
        CaseRecord.objects.filter(pk=newer.pk).update(duplicate_of_case=self.kb_case)
        for case in (newer, self.kb_case):
            case.refresh_from_db()
            form = self.admin_form(case_admin, case, {"location_area": self.pm_village.pk, "village": "Moved"})
            self.assertIn("location_area", form.errors, case.reference)
        # Without duplicate history a case may be corrected to any district.
        form = self.admin_form(case_admin, self.pm_case, {"location_area": self.kb_village.pk, "village": "Moved"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_django_admin_correction_runs_the_district_check_in_its_own_save(self):
        """The real change-form POST: the error shows beside the field, and an
        allowed move saves and is audited in the same transaction."""
        UserAccount.objects.filter(pk=self.admin.pk).update(is_staff=True, is_superuser=True)
        newer = self.case("FRC-7004", self.kb_village)
        DuplicateCaseMatch.objects.create(case_a=self.kb_case, case_b=newer, similarity_score=90)
        client = self.as_user(self.admin)
        inlines = {f"{prefix}-{key}": "0" for prefix in ("jobs", "photos", "tasks")
                   for key in ("TOTAL_FORMS", "INITIAL_FORMS")}
        url = f"/admin/cases/caserecord/{newer.pk}/change/"

        response = client.post(url, {"location_area": self.pm_village.pk, "village": "Moved", **inlines})
        self.assertContains(response, "cannot move to another district")
        newer.refresh_from_db()
        self.assertEqual(newer.location_area, self.kb_village)

        same_district = LocationArea.objects.get(code="MY0304-V002")
        response = client.post(url, {"location_area": same_district.pk, "village": same_district.name, **inlines})
        self.assertEqual(response.status_code, 302, response.content[:500])
        newer.refresh_from_db()
        self.assertEqual(newer.location_area, same_district)
        self.assertTrue(CaseEventLog.objects.filter(
            case=newer, event_type=CaseEventLog.EventType.ADMIN_CORRECTED,
        ).exists())
