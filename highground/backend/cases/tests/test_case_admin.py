"""The admin cannot move a case through its lifecycle (ADR-002, FR22).

Status, the answers the class reads, and tasks change only through the API,
which locks, audits and notifies. The one correction left in admin, the
village, writes an audit row.
"""

from django.contrib.admin.sites import site
from django.test import RequestFactory
from unittest.mock import patch

from cases.models import CaseEventLog, CaseRecord, CaseTask
from cases.tests.test_lifecycle import LifecycleTestCase

LOCKED = {
    "status", "closed_at", "urgency", "access_level", "vulnerability_flags", "needs_flags",
    "liveability", "flood_depth", "damage_category", "household_size", "description",
    "address", "latitude", "longitude", "submitted_by_user", "verified_by_user", "created_at",
}


class CaseAdminTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get("/admin/")
        self.officer.is_superuser = True
        self.officer.is_staff = True
        self.request.user = self.officer
        self.admin = site._registry[CaseRecord]

    def test_lifecycle_and_assessment_fields_are_read_only(self):
        fields = set(self.admin.get_readonly_fields(self.request, self.case))
        self.assertTrue(LOCKED <= fields, LOCKED - fields)
        self.assertNotIn("location_area", fields)
        self.assertNotIn("village", fields)

    def test_cases_cannot_be_added_in_admin(self):
        self.assertFalse(self.admin.has_add_permission(self.request))

    def test_an_admin_correction_is_audited(self):
        class Form:
            changed_data = ["village"]

        self.case.village = "Kg. Corrected"
        self.admin.save_model(self.request, self.case, Form(), change=True)
        event = CaseEventLog.objects.get(event_type=CaseEventLog.EventType.ADMIN_CORRECTED)
        self.assertIn("village", event.detail)
        self.assertEqual(event.actor_user, self.officer)

    def test_saving_without_changes_writes_nothing(self):
        class Form:
            changed_data = []

        self.admin.save_model(self.request, self.case, Form(), change=True)
        self.assertFalse(
            CaseEventLog.objects.filter(event_type=CaseEventLog.EventType.ADMIN_CORRECTED).exists()
        )

    def test_tasks_cannot_be_changed_in_admin(self):
        task_admin = site._registry[CaseTask]
        self.assertFalse(task_admin.has_change_permission(self.request))

    def test_tasks_cannot_be_added_in_admin_or_inline(self):
        from cases.admin import CaseTaskInline
        self.assertFalse(site._registry[CaseTask].has_add_permission(self.request))
        inline = CaseTaskInline(CaseRecord, site)
        self.assertFalse(inline.has_add_permission(self.request, self.case))
        self.assertEqual(inline.readonly_fields, inline.fields)

    def test_village_correction_does_not_overwrite_a_concurrent_lifecycle_change(self):
        class Form:
            changed_data = ["village"]

        CaseRecord.objects.filter(pk=self.case.pk).update(status=CaseRecord.Status.CLAIMED)
        self.case.village = "Kg. Corrected"
        self.admin.save_model(self.request, self.case, Form(), change=True)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.CLAIMED)

    def test_failed_audit_rolls_back_the_correction(self):
        class Form:
            changed_data = ["village"]

        self.case.village = "Kg. Corrected"
        with patch("cases.admin.CaseEventLog.objects.create", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                self.admin.save_model(self.request, self.case, Form(), change=True)
        self.case.refresh_from_db()
        self.assertEqual(self.case.village, "Kg. Test")
