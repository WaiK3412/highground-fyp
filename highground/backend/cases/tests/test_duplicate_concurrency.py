"""Real two-connection races for the duplicate workflow (NFR6).

TransactionTestCase commits for real, and each thread gets its own database
connection, so row locks genuinely contend. A barrier releases both requests
together; which one wins is up to PostgreSQL, so each test asserts the
invariant that must hold either way.

Traceability: FR14, NFR6 — one effective decision per flag; a case is never
both claimed and closed as a duplicate.
"""

import threading

from django.db import connection
from django.test import Client, TransactionTestCase

from cases import duplicate_services as svc
from cases.models import CaseEventLog, CaseRecord, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld


def race(*requests):
    """Run each zero-argument callable in its own thread, released together."""
    barrier = threading.Barrier(len(requests))
    results = [None] * len(requests)

    def run(index, request):
        try:
            barrier.wait()
            results[index] = request()
        finally:
            connection.close()  # this thread's own connection

    threads = [threading.Thread(target=run, args=(i, r)) for i, r in enumerate(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


class DuplicateRaceTests(DuplicateWorld, TransactionTestCase):
    @classmethod
    def tearDownClass(cls):
        # TransactionTestCase empties every table after each test, including
        # the gazetteer rows migration 0008 loaded. Reload them with that
        # migration's own loader so other tests, and a --keepdb rerun, find them.
        from importlib import import_module

        from django.apps import apps

        import_module("cases.migrations.0008_load_kelantan_locations").load(apps, None)
        super().tearDownClass()

    def setUp(self):
        self.build_world()
        self.older, self.newer = self.older_and_newer()
        svc.scan_duplicate_area(self.area.pk)
        self.match = DuplicateCaseMatch.objects.get()

    def poster(self, user, url, data=None):
        def post():
            client = Client()
            client.force_login(user)
            response = client.post(url, data or {}, content_type="application/json")
            return response.status_code, response.json()
        return post

    def test_competing_confirmations_take_effect_once_and_notify_once(self):
        url = f"/api/duplicates/{self.match.pk}/decide/"
        results = race(
            self.poster(self.officer, url, {"decision": "confirm"}),
            self.poster(self.officer, url, {"decision": "confirm"}),
        )
        self.assertEqual(sorted(status for status, _ in results), [200, 200])
        self.assertEqual(sorted(body["changed"] for _, body in results), [False, True])
        self.assertEqual(
            CaseEventLog.objects.filter(
                event_type=CaseEventLog.EventType.DUPLICATE_CONFIRMED, case=self.newer
            ).count(),
            1,
        )
        self.assertEqual(
            CaseEventLog.objects.filter(
                event_type=CaseEventLog.EventType.DUPLICATE_CLOSED, recipient_user__isnull=False
            ).count(),
            1,
        )

    def test_claim_and_confirm_never_both_succeed(self):
        # A case verified before a later rescan flagged it: claimable, and the
        # open flag is still waiting for review.
        self.newer.status = CaseRecord.Status.VERIFIED
        self.newer.save()

        claim, confirm = race(
            self.poster(self.ngo, f"/api/cases/{self.newer.pk}/claim/"),
            self.poster(self.officer, f"/api/duplicates/{self.match.pk}/decide/", {"decision": "confirm"}),
        )
        self.newer.refresh_from_db()
        self.match.refresh_from_db()
        claimed = self.newer.claimed_by_org_id is not None
        linked = self.newer.duplicate_of_case_id is not None

        self.assertNotEqual(claimed, linked, "exactly one of claim or confirm must win")
        if claimed:
            self.assertEqual(claim[0], 200)
            self.assertEqual((confirm[0], confirm[1]["code"]), (409, "active_case"))
            self.assertEqual(self.match.status, DuplicateCaseMatch.Status.OPEN)
        else:
            self.assertEqual(confirm[0], 200)
            self.assertEqual(claim[0], 409)
            self.assertEqual(self.newer.status, CaseRecord.Status.CLOSED)
