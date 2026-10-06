"""Phase 6: free text, file and audit boundaries (FR20, FR21, NFR3)."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import Organization, RegistrationDocument, UserAccount
from cases.models import CaseEventLog, CasePhoto, CaseRecord, LocationArea
from cases.tests.job_helpers import give_job
from cases.redaction import redact_personal_data


class RedactionTests(SimpleTestCase):
    def test_known_values_and_patterns_are_masked_without_dropping_the_note(self):
        text = (
            "Call Siti binti Rahman at +60 12-345 6789, IC 900101-03-1234. "
            "Visit Lot 14, Jalan Hospital or 6.123456, 102.123456. Bring water."
        )
        result = redact_personal_data(
            text, names=["Siti binti Rahman"], addresses=["Lot 14, Jalan Hospital"]
        )
        for secret in ("Siti", "+60 12-345", "900101", "Lot 14", "6.123456"):
            self.assertNotIn(secret, result)
        self.assertIn("Bring water.", result)
        self.assertEqual(redact_personal_data(result), result)

    def test_blank_and_unrelated_numbers(self):
        self.assertEqual(redact_personal_data(""), "")
        self.assertEqual(redact_personal_data("Case FRC-1042 needs 3 blankets."), "Case FRC-1042 needs 3 blankets.")


MEDIA = tempfile.mkdtemp(prefix="highground-private-test-")


@override_settings(MEDIA_ROOT=MEDIA)
class PrivacyBoundaryTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.org = Organization.objects.create(name="Relief A", type=Organization.Type.NGO)
        self.other_org = Organization.objects.create(name="Relief B", type=Organization.Type.NGO)
        # ADR-024: the case sits in a village of the officer's district.
        self.village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()

        def user(name, role=UserAccount.Role.COMMUNITY_MEMBER, org=None, staff=False):
            return UserAccount.objects.create_user(
                email=f"{name}@example.test", full_name=name, password="ValidTestPass2026",
                role=role, organization=org, is_staff=staff,
                district_id=self.village.parent_id if role == UserAccount.Role.DISASTER_OFFICER else None,
            )
        self.owner = user("Resident One")
        self.other = user("Resident Two")
        self.ngo = user("Responder One", UserAccount.Role.NGO_VOLUNTEER, self.org)
        self.other_ngo = user("Responder Two", UserAccount.Role.NGO_VOLUNTEER, self.other_org)
        self.unattached = user("Responder Three", UserAccount.Role.NGO_VOLUNTEER)
        self.officer = user("Officer One", UserAccount.Role.DISASTER_OFFICER)
        self.admin = user("Admin One", UserAccount.Role.SYSTEM_ADMIN, staff=True)
        self.case = CaseRecord.objects.create(
            reference="FRC-9901", submitted_by_user=self.owner,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Resident One can be reached at 012-345 6789. Bring water.",
            village="Kg. Test", address="Lot 14, Jalan Hospital", location_area=self.village,
            status=CaseRecord.Status.CLAIMED, created_at=timezone.now(),
        )
        self.job = give_job(self.case, self.org)
        self.photo = CasePhoto.objects.create(
            case=self.case,
            file_path=SimpleUploadedFile("private.jpg", b"\xff\xd8\xffphoto", content_type="image/jpeg"),
        )
        self.document = RegistrationDocument.objects.create(
            user=self.ngo,
            file=SimpleUploadedFile("evidence.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            label="Evidence",
        )

    def test_private_photo_requires_case_access(self):
        url = f"/api/case-photos/{self.photo.pk}/file/"
        self.assertIn(self.client.get(url).status_code, (401, 403))
        for allowed in (self.owner, self.ngo, self.officer, self.admin):
            self.client.force_login(allowed)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, allowed.email)
            self.assertEqual(response["Cache-Control"], "private, no-store")
        for denied in (self.other, self.other_ngo, self.unattached):
            self.client.force_login(denied)
            self.assertEqual(self.client.get(url).status_code, 404, denied.email)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(f"/media/{self.photo.file_path.name}").status_code, 404)

    def test_legacy_non_image_photo_downloads_without_inline_html(self):
        legacy = CasePhoto.objects.create(
            case=self.case,
            file_path=SimpleUploadedFile("legacy.html", b"<script>bad()</script>"),
        )
        self.client.force_login(self.owner)
        response = self.client.get(f"/api/case-photos/{legacy.pk}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_registration_document_is_admin_only(self):
        url = f"/api/registration-documents/{self.document.pk}/file/"
        for denied in (self.owner, self.ngo, self.officer, self.unattached):
            self.client.force_login(denied)
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_claiming_ngo_sees_redacted_prose_and_other_ngo_gets_summary(self):
        self.client.force_login(self.ngo)
        payload = self.client.get(f"/api/cases/{self.case.pk}/").json()
        self.assertNotIn("Resident One", payload["description"])
        self.assertNotIn("012-345", payload["description"])
        self.assertIn("Bring water", payload["description"])
        self.client.force_login(self.other_ngo)
        payload = self.client.get(f"/api/cases/{self.case.pk}/").json()
        self.assertEqual(payload["detail_access"], "summary")
        self.assertNotIn("description", payload)

    def test_unattached_ngo_sees_no_unclaimed_case(self):
        give_job(self.case, None)
        self.case.status = CaseRecord.Status.VERIFIED
        self.case.save(update_fields=["status"])
        self.client.force_login(self.unattached)
        self.assertEqual(self.client.get("/api/cases/").json()["count"], 0)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/cases/map/").status_code, 403)

    def test_audit_fields_and_cascading_deletion_are_blocked(self):
        event = CaseEventLog.objects.create(
            case=self.case, actor_user=self.officer, event_type=CaseEventLog.EventType.VERIFIED,
            detail="Verified", created_at=timezone.now(),
        )
        with self.assertRaises(ValueError):
            CaseEventLog.objects.filter(pk=event.pk).update(detail="changed")
        event.detail = "changed"
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.case.delete()
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.officer.delete()
        CaseEventLog.objects.filter(pk=event.pk).update(read_at=timezone.now())
        event.refresh_from_db()
        self.assertIsNotNone(event.read_at)
