"""Real two-connection races for the duplicate workflow (NFR6).

TransactionTestCase commits for real, and each thread gets its own database
connection, so row locks genuinely contend. A barrier releases both requests
together; which one wins is up to PostgreSQL, so each test asserts the
invariant that must hold either way.

Traceability: FR9, NFR6 — one effective decision per flag; a case is never
both claimed and closed as a duplicate.
"""

from django.test import Client, TransactionTestCase

from cases import duplicate_services as svc
from cases.models import CaseEventLog, CaseRecord, DuplicateCaseMatch

from .duplicate_helpers import DuplicateWorld
from .job_helpers import give_job
from .race_helpers import GazetteerReloadMixin, race


class DuplicateRaceTests(GazetteerReloadMixin, DuplicateWorld, TransactionTestCase):
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
        job = give_job(self.newer)

        claim, confirm = race(
            self.poster(self.ngo, f"/api/jobs/{job.pk}/claim/"),
            self.poster(self.officer, f"/api/duplicates/{self.match.pk}/decide/", {"decision": "confirm"}),
        )
        self.newer.refresh_from_db()
        self.match.refresh_from_db()
        job.refresh_from_db()
        claimed = job.claimed_by_org_id is not None
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
