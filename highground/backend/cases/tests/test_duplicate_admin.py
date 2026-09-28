"""Admin cannot bypass the duplicate workflow (ADR-002: admin is screens 14/19).

Traceability: FR14, FR21 — links and decisions are made only through the
audited service; the admin shows them read-only.
"""

from django.contrib.admin.sites import site
from django.test import RequestFactory, TestCase

from cases import duplicate_services as svc
from cases.models import CaseRecord, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld


class DuplicateAdminTests(DuplicateWorld, TestCase):
    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        svc.scan_duplicate_area(self.area.pk)
        self.match = DuplicateCaseMatch.objects.get()
        self.request = RequestFactory().get("/admin/")
        self.request.user = self.officer

    def test_matches_cannot_be_added_changed_or_deleted(self):
        admin = site._registry[DuplicateCaseMatch]
        self.assertFalse(admin.has_add_permission(self.request))
        self.assertFalse(admin.has_change_permission(self.request, self.match))
        self.assertFalse(admin.has_delete_permission(self.request, self.match))

    def test_duplicate_link_is_read_only_and_linked_cases_cannot_be_reopened(self):
        admin = site._registry[CaseRecord]
        self.assertIn("duplicate_of_case", admin.get_readonly_fields(self.request, self.older))
        self.assertNotIn("status", admin.get_readonly_fields(self.request, self.older))

        svc.decide_duplicate_match(self.match.pk, self.officer, "confirm")
        self.newer.refresh_from_db()
        fields = admin.get_readonly_fields(self.request, self.newer)
        self.assertIn("status", fields)
        self.assertIn("closed_at", fields)
