"""FR3/FR19/NFR3: staged evidence stays optional and inside case permissions."""

import json
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import PROTECT, ProtectedError
from django.utils import timezone
from PIL import Image

from accounts.models import UserAccount
from cases.admin import CasePhotoInline
from cases.images import clean_photo
from cases.models import CaseEventLog, CaseJob, CasePhoto, CaseRecord, CaseTask
from cases.serializers.submission import MAX_PHOTOS, MAX_PHOTO_BYTES
from cases.tests.job_helpers import give_job
from cases.tests.photo_helpers import jpeg_with_gps
from cases.tests.test_lifecycle import LifecycleTestCase
from cases.tests.test_submission import VALID


class PhotoModelTests(LifecycleTestCase):
    def test_legacy_photo_defaults_to_resident_without_an_uploader_or_task(self):
        photo = CasePhoto.objects.create(case=self.case, file_path="cases/legacy.jpg")
        self.assertEqual(photo.stage, "resident")
        self.assertIsNone(photo.uploaded_by_user_id)
        self.assertIsNone(photo.task_id)

    def test_evidence_relations_are_protected_and_admin_columns_are_read_only(self):
        self.assertIs(CasePhoto._meta.get_field("uploaded_by_user").remote_field.on_delete, PROTECT)
        self.assertIs(CasePhoto._meta.get_field("task").remote_field.on_delete, PROTECT)
        for field in ("stage", "uploaded_by_user", "task"):
            self.assertIn(field, CasePhotoInline.readonly_fields)

    def test_a_task_with_photo_evidence_cannot_be_deleted(self):
        job = give_job(self.case, self.mercy)
        task = CaseTask.objects.create(case=self.case, job=job, title="Clear mud", task_type="cleanup")
        CasePhoto.objects.create(
            case=self.case, file_path="cases/work.jpg", stage="before",
            task=task, uploaded_by_user=self.mercy_lead,
        )
        with self.assertRaises(ProtectedError):
            task.delete()

    def test_household_and_officer_details_include_photo_provenance(self):
        job = give_job(self.case, self.mercy)
        task = CaseTask.objects.create(case=self.case, job=job, title="Clear mud", task_type="cleanup")
        CasePhoto.objects.create(
            case=self.case, file_path="cases/work.jpg", stage="after",
            task=task, uploaded_by_user=self.mercy_lead,
        )
        for user in (self.resident, self.officer):
            with self.subTest(role=user.role):
                self.login(user)
                photo = self.client.get(f"/api/cases/{self.case.pk}/").json()["photos"][0]
                self.assertEqual(photo["stage"], "after")
                self.assertEqual(photo["stage_display"], "After")
                self.assertEqual(photo["task_id"], task.pk)
                self.assertEqual(photo["job_id"], job.pk)
                self.assertEqual(photo["uploaded_by_org"], self.mercy.name)

    def test_resident_photo_has_null_task_job_and_organisation(self):
        CasePhoto.objects.create(
            case=self.case, file_path="cases/resident.jpg", uploaded_by_user=self.resident,
        )
        self.login(self.resident)
        photo = self.client.get(f"/api/cases/{self.case.pk}/").json()["photos"][0]
        self.assertEqual(photo["stage"], "resident")
        self.assertIsNone(photo["task_id"])
        self.assertIsNone(photo["job_id"])
        self.assertIsNone(photo["uploaded_by_org"])

    def test_submission_records_resident_stage_and_uploader(self):
        self.login(self.resident)
        payload = {
            **VALID, "photos": [jpeg_with_gps()],
            "needs_flags": json.dumps(VALID["needs_flags"]),
            "vulnerability_flags": json.dumps(VALID["vulnerability_flags"]),
        }
        with tempfile.TemporaryDirectory(prefix="highground-photo-test-") as media, self.settings(MEDIA_ROOT=media):
            response = self.client.post("/api/cases/", payload)
        self.assertEqual(response.status_code, 201, response.content)
        photo = CasePhoto.objects.get()
        self.assertEqual(photo.stage, "resident")
        self.assertEqual(photo.uploaded_by_user, self.resident)
        self.assertIsNone(photo.task_id)


class TaskPhotoUploadTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory(prefix="highground-task-photo-test-")
        self.addCleanup(media.cleanup)
        self.enterContext(self.settings(MEDIA_ROOT=media.name))
        self.case.status = CaseRecord.Status.IN_PROGRESS
        self.case.save(update_fields=["status"])
        self.job = give_job(self.case, self.mercy, CaseJob.Status.IN_PROGRESS)
        self.task = CaseTask.objects.create(
            case=self.case, job=self.job, title="Clear mud", task_type="cleanup",
            lead_user=self.mercy_lead, status=CaseTask.Status.IN_PROGRESS,
        )
        self.login(self.mercy_lead)
        self.url = f"/api/tasks/{self.task.pk}/photos/"

    def upload(self, files=None, **body):
        return self.client.post(self.url, {
            "stage": "after", "photos": [jpeg_with_gps()] if files is None else files, **body,
        })

    def stored_photo(self):
        return CasePhoto.objects.create(
            case=self.case, task=self.task, stage="after",
            uploaded_by_user=self.mercy_lead, file_path=clean_photo(jpeg_with_gps()),
        )

    def test_claiming_responder_uploads_cleaned_photos_with_one_audit_event(self):
        """FR19/NFR3: task evidence is cleaned and attributed, never self-confirmation."""
        response = self.upload([jpeg_with_gps(), jpeg_with_gps("a.jpg", orientation=6)], caption="Mud removed")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(response.json()["photos"]), 2)
        for row in CasePhoto.objects.all():
            self.assertEqual(row.case_id, self.case.pk)
            self.assertEqual(row.task_id, self.task.pk)
            self.assertEqual(row.stage, "after")
            self.assertEqual(row.uploaded_by_user, self.mercy_lead)
            self.assertEqual(row.caption, "Mud removed")
            self.assertRegex(row.file_path.name, r"/[0-9a-f]{32}\.jpg$")
            with row.file_path.open("rb") as stored, Image.open(stored) as image:
                self.assertEqual(dict(image.getexif()), {})
        event = CaseEventLog.objects.get(case=self.case, task=self.task)
        self.assertEqual(event.event_type, CaseEventLog.EventType.TASK_UPDATED)
        self.assertEqual(event.actor_user, self.mercy_lead)
        self.assertEqual(event.detail, 'Mercy Relief added 2 after photo(s) to "Clear mud".')
        self.assertEqual(response.json()["photos"][0]["job_id"], self.job.pk)

    def test_before_photos_are_allowed_before_work_starts(self):
        self.job.status = CaseJob.Status.CLAIMED
        self.job.save(update_fields=["status"])
        self.task.status = CaseTask.Status.ASSIGNED
        self.task.save(update_fields=["status"])
        response = self.upload(stage="before")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CasePhoto.objects.get().stage, "before")

    def test_missing_or_invalid_stage_is_refused(self):
        response = self.client.post(self.url, {"photos": [jpeg_with_gps()]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("stage", response.json())
        for stage in ("resident", "unknown"):
            with self.subTest(stage=stage):
                self.assertEqual(self.upload(stage=stage).status_code, 400)
        self.assertFalse(CasePhoto.objects.exists())

    def test_empty_or_excess_photos_are_refused(self):
        for files in ([], [jpeg_with_gps(f"{i}.jpg") for i in range(MAX_PHOTOS + 1)]):
            with self.subTest(count=len(files)):
                response = self.upload(files)
                self.assertEqual(response.status_code, 400)
                self.assertIn("photos", response.json())
        self.assertFalse(CasePhoto.objects.exists())

    def test_pdf_and_undecodable_images_are_refused_without_partial_uploads(self):
        bad_files = [
            SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf"),
            SimpleUploadedFile("x.jpg", b"\xff\xd8\xffnot an image", content_type="image/jpeg"),
        ]
        for bad_file in bad_files:
            with self.subTest(name=bad_file.name):
                response = self.upload([jpeg_with_gps(), bad_file])
                self.assertEqual(response.status_code, 400, response.content)
                self.assertTrue(response.json()["photos"][0])
        self.assertFalse(CasePhoto.objects.exists())
        self.assertFalse(CaseEventLog.objects.exists())

    def test_decompression_warning_and_error_return_400(self):
        """NFR3, Review Focus 2: resource-limit failures are plain upload errors."""
        for pixel_limit in (500, 100):
            with self.subTest(pixel_limit=pixel_limit), patch.object(Image, "MAX_IMAGE_PIXELS", pixel_limit):
                response = self.upload()
                self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(CasePhoto.objects.exists())

    def test_size_and_signature_rules_match_household_photos(self):
        files = [
            SimpleUploadedFile("large.jpg", b"\xff\xd8\xff" + b"x" * MAX_PHOTO_BYTES, content_type="image/jpeg"),
            SimpleUploadedFile("x.jpg", b"wrong signature", content_type="image/jpeg"),
        ]
        for upload in files:
            with self.subTest(name=upload.name):
                self.assertEqual(self.upload([upload]).status_code, 400)
        self.assertFalse(CasePhoto.objects.exists())

    def test_caption_over_255_characters_is_refused(self):
        response = self.upload(caption="x" * 256)
        self.assertEqual(response.status_code, 400)
        self.assertIn("caption", response.json())

    def test_another_organisation_cannot_upload(self):
        self.login(self.belia_lead)
        self.assertEqual(self.upload().status_code, 404)
        self.assertFalse(CasePhoto.objects.exists())

    def test_resident_officer_admin_and_unattached_ngo_cannot_upload(self):
        admin = UserAccount.objects.create_user(
            email="admin-photos@example.my", full_name="Admin", role=UserAccount.Role.SYSTEM_ADMIN,
        )
        unattached = UserAccount.objects.create_user(
            email="unattached-photos@example.my", full_name="Unattached", role=UserAccount.Role.NGO_VOLUNTEER,
        )
        for user in (self.resident, self.officer, admin, unattached):
            with self.subTest(role=user.role, org=user.organization_id):
                self.login(user)
                self.assertEqual(self.upload().status_code, 403)
        self.assertFalse(CasePhoto.objects.exists())

    def test_anonymous_cannot_upload(self):
        self.client.logout()
        self.assertIn(self.upload().status_code, (401, 403))

    def test_a_colleague_in_the_claiming_organisation_can_upload(self):
        colleague = UserAccount.objects.create_user(
            email="colleague-photos@example.my", full_name="Colleague",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.mercy,
        )
        self.login(colleague)
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(CasePhoto.objects.get().uploaded_by_user, colleague)

    def test_uploads_stop_while_awaiting_confirmation_or_finished(self):
        """FR19, Review Focus 5: evidence freezes with progress notes at completion."""
        for status in (CaseJob.Status.PENDING_CONFIRM, CaseJob.Status.DONE, "closed_unconfirmed"):
            with self.subTest(status=status):
                self.job.status = status
                self.job.save(update_fields=["status"])
                self.assertEqual(self.upload().status_code, 409)
        self.assertFalse(CasePhoto.objects.exists())

    def test_job_status_is_rechecked_after_decoding(self):
        def finish_during_decode(upload):
            result = clean_photo(upload)
            CaseJob.objects.filter(pk=self.job.pk).update(status=CaseJob.Status.PENDING_CONFIRM)
            return result

        with patch("cases.views.tasks.clean_photo", side_effect=finish_during_decode):
            response = self.upload()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(CasePhoto.objects.exists())
        self.assertFalse(CaseEventLog.objects.exists())

    def test_household_gets_stages_but_shared_ngo_summary_and_queue_have_no_photos(self):
        photo = self.stored_photo()
        self.login(self.resident)
        detail = self.client.get(f"/api/cases/{self.case.pk}/").json()
        self.assertEqual(detail["photos"][0]["stage"], "after")
        self.assertEqual(detail["photos"][0]["job_id"], self.job.pk)
        self.login(self.belia_lead)
        self.assertNotIn("photos", self.client.get(f"/api/cases/{self.case.pk}/").json())
        self.assertNotIn("photos", self.client.get("/api/cases/").json()["results"][0])
        self.assertEqual(self.client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 404)

    def test_board_and_case_tasks_include_private_photos_for_an_active_organisation(self):
        photo = self.stored_photo()
        task = self.client.get("/api/tasks/").json()["tasks"][0]
        self.assertEqual(task["photos"][0]["url"], f"/api/case-photos/{photo.pk}/file/")
        self.assertEqual(task["job_status"], "in_progress")
        for user in (self.mercy_lead, self.resident, self.officer):
            self.login(user)
            task = self.client.get(f"/api/cases/{self.case.pk}/tasks/").json()[0]
            self.assertEqual(task["photos"][0]["stage"], "after")

    def test_confirmed_organisation_loses_files_and_photo_lists_in_retained_task_history(self):
        """NFR3, Review Focus 3: uploading a photo never grants lasting ownership access."""
        photo = self.stored_photo()
        self.task.status = CaseTask.Status.DONE
        self.task.completed_at = timezone.now()
        self.task.save(update_fields=["status", "completed_at"])
        self.job.status = CaseJob.Status.PENDING_CONFIRM
        self.job.save(update_fields=["status"])
        self.login(self.resident)
        response = self.client.post(f"/api/jobs/{self.job.pk}/confirm/", {"decision": "confirm"})
        self.assertEqual(response.status_code, 200, response.content)
        self.login(self.mercy_lead)
        self.assertEqual(self.client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 404)
        self.assertEqual(self.client.get("/api/tasks/").json()["tasks"][0]["photos"], [])
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/tasks/").json()[0]["photos"], [])
        self.assertNotIn("photos", self.client.get(f"/api/cases/{self.case.pk}/").json())

    def test_another_household_cannot_view_task_photos(self):
        photo = self.stored_photo()
        other = UserAccount.objects.create_user(email="other-photo-household@example.my", full_name="Other")
        self.login(other)
        self.assertEqual(self.client.get(f"/api/case-photos/{photo.pk}/file/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/tasks/").status_code, 404)

    def test_another_job_awaiting_confirmation_does_not_stop_this_organisations_work(self):
        CaseJob.objects.create(
            case=self.case, help_type="repair", claimed_by_org=self.belia,
            status=CaseJob.Status.PENDING_CONFIRM,
        )
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)

    def test_photos_and_audit_row_roll_back_together_on_audit_failure(self):
        with patch("cases.views.tasks.CaseEventLog.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesMessage(RuntimeError, "audit unavailable"):
                self.upload()
        self.assertFalse(CasePhoto.objects.exists())
