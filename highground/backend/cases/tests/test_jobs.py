"""Help jobs: one household request, several organisations (ADR-020).

Traceability:
  FR6  NGOs claim work atomically — now one job (type of help) at a time
  FR20 Exact location only for district staff and an organisation holding an
       active job on the case
  FR11 Resident confirms completed work — per job
"""

from django.utils import timezone

from cases.models import CaseEventLog, CaseJob, CaseRecord, CaseTask
from cases.tests.test_lifecycle import LifecycleTestCase


def make_jobs(case, *help_types):
    return [CaseJob.objects.create(case=case, help_type=help_type) for help_type in help_types]


class JobTestCase(LifecycleTestCase):
    """The base case is verified; give it a cleanup and a repair job."""

    def setUp(self):
        super().setUp()
        self.cleanup, self.repair = make_jobs(self.case, "cleanup", "repair")

    def post(self, user, path, data=None):
        self.login(user)
        return self.client.post(path, data or {}, content_type="application/json")

    def claim(self, user, job):
        return self.post(user, f"/api/jobs/{job.pk}/claim/")

    def refresh(self):
        self.case.refresh_from_db()
        self.cleanup.refresh_from_db()
        self.repair.refresh_from_db()


class ClaimTests(JobTestCase):
    def test_two_organisations_claim_different_jobs_on_one_case(self):
        self.assertEqual(self.claim(self.mercy_lead, self.cleanup).status_code, 200)
        self.assertEqual(self.claim(self.belia_lead, self.repair).status_code, 200)
        self.refresh()
        self.assertEqual(self.cleanup.claimed_by_org, self.mercy)
        self.assertEqual(self.repair.claimed_by_org, self.belia)
        self.assertEqual(self.case.status, CaseRecord.Status.CLAIMED)

    def test_a_claimed_job_cannot_be_taken_by_another_organisation(self):
        self.claim(self.mercy_lead, self.cleanup)
        self.assertEqual(self.claim(self.belia_lead, self.cleanup).status_code, 409)
        self.cleanup.refresh_from_db()
        self.assertEqual(self.cleanup.claimed_by_org, self.mercy)

    def test_a_retry_by_the_same_organisation_writes_nothing_more(self):
        self.claim(self.mercy_lead, self.cleanup)
        before = CaseEventLog.objects.filter(event_type=CaseEventLog.EventType.CLAIMED).count()
        self.assertEqual(self.claim(self.mercy_lead, self.cleanup).status_code, 200)
        after = CaseEventLog.objects.filter(event_type=CaseEventLog.EventType.CLAIMED).count()
        self.assertEqual(before, after)

    def test_jobs_on_an_unverified_case_cannot_be_claimed(self):
        CaseRecord.objects.filter(pk=self.case.pk).update(status=CaseRecord.Status.SUBMITTED)
        self.assertEqual(self.claim(self.mercy_lead, self.cleanup).status_code, 409)

    def test_only_ngo_responders_claim(self):
        self.assertEqual(self.claim(self.officer, self.cleanup).status_code, 403)
        self.assertEqual(self.claim(self.resident, self.cleanup).status_code, 403)

    def test_release_returns_an_unstarted_job_to_the_queue(self):
        self.claim(self.mercy_lead, self.cleanup)
        response = self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/release/", {"reason": "No crew"})
        self.assertEqual(response.status_code, 200)
        self.refresh()
        self.assertEqual(self.cleanup.status, CaseJob.Status.OPEN)
        self.assertIsNone(self.cleanup.claimed_by_org)
        self.assertEqual(self.case.status, CaseRecord.Status.VERIFIED)


class AccessTests(JobTestCase):
    def detail(self, user):
        self.login(user)
        return self.client.get(f"/api/cases/{self.case.pk}/").json()

    def test_only_organisations_holding_a_job_see_the_full_case(self):
        self.claim(self.mercy_lead, self.cleanup)
        self.assertEqual(self.detail(self.mercy_lead)["detail_access"], "full")
        self.assertEqual(self.detail(self.belia_lead)["detail_access"], "summary")

    def test_access_ends_when_the_organisations_job_is_done(self):
        self.claim(self.mercy_lead, self.cleanup)
        CaseJob.objects.filter(pk=self.cleanup.pk).update(status=CaseJob.Status.DONE)
        self.assertEqual(self.detail(self.mercy_lead)["detail_access"], "summary")

    def test_the_case_lists_its_jobs_for_every_viewer(self):
        self.claim(self.mercy_lead, self.cleanup)
        jobs = {job["help_type"]: job for job in self.detail(self.belia_lead)["jobs"]}
        self.assertEqual(jobs["cleanup"]["claimed_by"], "Mercy Relief")
        self.assertEqual(jobs["repair"]["status"], "open")
        self.assertFalse(jobs["cleanup"]["claimed_by_you"])


class TaskAndCompletionTests(JobTestCase):
    def setUp(self):
        super().setUp()
        self.claim(self.mercy_lead, self.cleanup)
        self.claim(self.belia_lead, self.repair)

    def add_task(self, user, job):
        return self.post(user, f"/api/cases/{self.case.pk}/tasks/", {
            "job_id": job.pk, "title": "Clear mud", "task_type": "cleanup", "lead_user_id": user.pk,
        })

    def finish_task(self, user, task_id):
        self.login(user)
        for status in ("in_progress", "done"):
            response = self.client.patch(
                f"/api/tasks/{task_id}/", {"status": status}, content_type="application/json"
            )
            self.assertEqual(response.status_code, 200, response.content)

    def test_a_task_goes_on_a_job_the_organisation_holds(self):
        self.assertEqual(self.add_task(self.mercy_lead, self.cleanup).status_code, 201)
        self.assertEqual(self.add_task(self.mercy_lead, self.repair).status_code, 403)

    def test_an_organisation_cannot_change_another_organisations_task(self):
        task_id = self.add_task(self.mercy_lead, self.cleanup).json()["id"]
        self.login(self.belia_lead)
        response = self.client.patch(
            f"/api/tasks/{task_id}/", {"note": "Hello"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    def test_completing_one_job_leaves_the_case_open_until_every_job_is_confirmed(self):
        cleanup_task = self.add_task(self.mercy_lead, self.cleanup).json()["id"]
        self.finish_task(self.mercy_lead, cleanup_task)
        self.assertEqual(self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/complete/").status_code, 200)
        self.assertEqual(
            self.post(self.resident, f"/api/jobs/{self.cleanup.pk}/confirm/", {"decision": "confirm"}).status_code,
            200,
        )
        self.refresh()
        self.assertEqual(self.cleanup.status, CaseJob.Status.DONE)
        self.assertNotEqual(self.case.status, CaseRecord.Status.CLOSED)

        repair_task = self.add_task(self.belia_lead, self.repair).json()["id"]
        self.finish_task(self.belia_lead, repair_task)
        self.post(self.belia_lead, f"/api/jobs/{self.repair.pk}/complete/")
        self.post(self.resident, f"/api/jobs/{self.repair.pk}/confirm/", {"decision": "confirm"})
        self.refresh()
        self.assertEqual(self.case.status, CaseRecord.Status.CLOSED)
        self.assertIsNotNone(self.case.closed_at)

    def test_completion_needs_every_task_on_that_job_done(self):
        self.add_task(self.mercy_lead, self.cleanup)
        self.assertEqual(self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/complete/").status_code, 409)

    def test_resident_can_report_a_job_incomplete(self):
        task_id = self.add_task(self.mercy_lead, self.cleanup).json()["id"]
        self.finish_task(self.mercy_lead, task_id)
        self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/complete/")
        response = self.post(
            self.resident, f"/api/jobs/{self.cleanup.pk}/confirm/",
            {"decision": "incomplete", "note": "Kitchen still muddy"},
        )
        self.assertEqual(response.status_code, 200)
        self.refresh()
        self.assertEqual(self.cleanup.status, CaseJob.Status.IN_PROGRESS)

    def test_only_the_household_confirms(self):
        task_id = self.add_task(self.mercy_lead, self.cleanup).json()["id"]
        self.finish_task(self.mercy_lead, task_id)
        self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/complete/")
        self.assertEqual(
            self.post(self.mercy_lead, f"/api/jobs/{self.cleanup.pk}/confirm/", {"decision": "confirm"}).status_code,
            403,
        )

    def test_task_board_shows_only_the_organisations_own_jobs(self):
        self.add_task(self.mercy_lead, self.cleanup)
        self.add_task(self.belia_lead, self.repair)
        self.login(self.mercy_lead)
        board = self.client.get("/api/tasks/").json()
        self.assertEqual({task["job_id"] for task in board["tasks"]}, {self.cleanup.pk})
        self.assertEqual([job["id"] for job in board["jobs"]], [self.cleanup.pk])


class SubmissionCreatesJobsTests(LifecycleTestCase):
    def test_main_help_type_and_extra_types_become_jobs(self):
        from cases.models import LocationArea

        village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.login(self.resident)
        response = self.client.post("/api/cases/", {
            "location_code": village.code, "address": "Lot 7", "household_size": 3,
            "damage_category": "cleanup", "description": "Mud everywhere.",
            "also_need": ["repair", "cleanup", "essential_items"],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        case = CaseRecord.objects.get(pk=response.json()["id"])
        self.assertEqual(
            list(case.jobs.values_list("help_type", flat=True)),
            ["cleanup", "repair", "essential_items"],
        )

    def test_extra_types_arrive_as_json_text_in_a_multipart_form(self):
        # A form with photos is multipart, so the client sends lists as JSON.
        from cases.models import LocationArea

        village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.login(self.resident)
        response = self.client.post("/api/cases/", {
            "location_code": village.code, "address": "Lot 7", "household_size": 3,
            "damage_category": "repair", "description": "Roof gone.",
            "also_need": '["agriculture"]',
        })
        self.assertEqual(response.status_code, 201, response.content)
        case = CaseRecord.objects.get(pk=response.json()["id"])
        self.assertEqual(list(case.jobs.values_list("help_type", flat=True)), ["repair", "agriculture"])

    def test_unknown_help_type_is_rejected(self):
        from cases.models import LocationArea

        village = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE).first()
        self.login(self.resident)
        response = self.client.post("/api/cases/", {
            "location_code": village.code, "address": "Lot 7", "household_size": 3,
            "damage_category": "cleanup", "description": "Mud.", "also_need": ["roofing"],
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)


class UnmetHelpTests(JobTestCase):
    def test_officers_see_open_jobs_by_type_of_help(self):
        self.claim(self.mercy_lead, self.cleanup)
        self.login(self.officer)
        rows = {row["help_type"]: row for row in self.client.get("/api/jobs/unmet/").json()}
        self.assertEqual(rows["repair"]["open_jobs"], 1)
        self.assertNotIn("cleanup", rows)
        self.assertEqual(rows["repair"]["oldest_waiting_days"], 0)

    def test_ngos_and_residents_cannot_see_the_report(self):
        for user in (self.mercy_lead, self.resident):
            self.login(user)
            self.assertEqual(self.client.get("/api/jobs/unmet/").status_code, 403)
