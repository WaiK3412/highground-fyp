"""End-to-end rules for the NGO task and resident-completion workflow.

Since ADR-020 an organisation claims a job (one type of help) on a case,
not the whole case; these tests run with one cleanup job.

Traceability:
  FR6  A responding organisation owns the work it claimed
  FR7  The organisation assigns and updates recovery tasks
  FR8  The household confirms or disputes completion
  FR20 Every task action enforces role and organisation boundaries
  FR21 Task and lifecycle changes are append-only audit events
"""

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseJob, CaseRecord, CaseTask


class TaskWorkflowTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name="Mercy Relief",
            type=Organization.Type.NGO,
            contact_no="03-1000",
            service_area="Kelantan",
        )
        self.other_org = Organization.objects.create(
            name="Neighbour Aid",
            type=Organization.Type.NGO,
            contact_no="03-2000",
            service_area="Kelantan",
        )
        self.resident = UserAccount.objects.create_user(
            email="resident-tasks@example.my",
            full_name="Resident Owner",
            password="Recovery2026",
        )
        self.other_resident = UserAccount.objects.create_user(
            email="other-resident-tasks@example.my",
            full_name="Other Resident",
            password="Recovery2026",
        )
        self.responder = UserAccount.objects.create_user(
            email="lead@example.my",
            full_name="Response Lead",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.org,
        )
        self.colleague = UserAccount.objects.create_user(
            email="colleague@example.my",
            full_name="Second Responder",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.org,
        )
        self.other_responder = UserAccount.objects.create_user(
            email="other-lead@example.my",
            full_name="Other Organisation Lead",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.other_org,
        )
        self.officer = UserAccount.objects.create_user(
            email="officer-tasks@example.my",
            full_name="District Officer",
            password="Recovery2026",
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-8101",
            submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Mud and damaged furniture throughout the house.",
            village="Kg. Task Test",
            address="Lot 8",
            status=CaseRecord.Status.CLAIMED,
            created_at=timezone.now(),
        )
        self.job = CaseJob.objects.create(
            case=self.case, help_type=CaseRecord.DamageCategory.CLEANUP,
            status=CaseJob.Status.CLAIMED, claimed_by_org=self.org,
        )

    def create_task(self, *, status=CaseTask.Status.ASSIGNED, lead=None):
        return CaseTask.objects.create(
            case=self.case,
            job=self.job,
            lead_user=self.responder if lead is None else lead,
            title="Remove flood debris",
            task_type=CaseTask.TaskType.CLEANUP,
            status=status,
            assigned_at=timezone.now() if status != CaseTask.Status.OPEN else None,
            completed_at=timezone.now() if status == CaseTask.Status.DONE else None,
        )

    def test_claiming_organisation_can_create_an_assigned_task(self):
        self.client.force_login(self.responder)
        response = self.client.post(
            f"/api/cases/{self.case.pk}/tasks/",
            {"job_id": self.job.pk, 
                "title": "Clear the kitchen",
                "task_type": "cleanup",
                "lead_user_id": self.colleague.pk,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        task = CaseTask.objects.get()
        self.assertEqual(task.lead_user, self.colleague)
        self.assertEqual(task.status, CaseTask.Status.ASSIGNED)
        event = CaseEventLog.objects.get(task=task)
        self.assertEqual(event.event_type, CaseEventLog.EventType.TASK_ASSIGNED)
        self.assertNotIn(self.colleague.full_name, event.detail)

    def test_task_lead_must_be_an_active_responder_in_the_claiming_org(self):
        self.client.force_login(self.responder)
        for lead_id in (self.other_responder.pk, self.resident.pk):
            response = self.client.post(
                f"/api/cases/{self.case.pk}/tasks/",
                {"job_id": self.job.pk, "title": "Unsafe assignment", "task_type": "repair", "lead_user_id": lead_id},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(CaseTask.objects.count(), 0)

    def test_other_organisation_cannot_read_or_create_tasks(self):
        task = self.create_task()
        self.client.force_login(self.other_responder)
        get_response = self.client.get(f"/api/cases/{self.case.pk}/tasks/")
        post_response = self.client.post(
            f"/api/cases/{self.case.pk}/tasks/",
            {"job_id": self.job.pk, "title": "Take over", "task_type": "cleanup"},
            content_type="application/json",
        )
        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(post_response.status_code, 404)
        self.assertEqual(
            self.client.patch(
                f"/api/tasks/{task.pk}/",
                {"status": "in_progress"},
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/api/jobs/{self.job.pk}/complete/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/jobs/{self.job.pk}/release/",
                {"reason": "No capacity"},
                content_type="application/json",
            ).status_code,
            404,
        )

    def test_officer_can_read_tasks_but_cannot_manage_ngo_work(self):
        task = self.create_task()
        self.client.force_login(self.officer)

        self.assertEqual(
            self.client.get(f"/api/cases/{self.case.pk}/tasks/").status_code, 200
        )
        self.assertEqual(self.client.get("/api/tasks/").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/cases/{self.case.pk}/tasks/",
                {"job_id": self.job.pk, "title": "Officer task", "task_type": "assessment"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/tasks/{task.pk}/",
                {"status": "in_progress"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/api/jobs/{self.job.pk}/complete/").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/jobs/{self.job.pk}/release/",
                {"reason": "Officer cannot release NGO claims"},
                content_type="application/json",
            ).status_code,
            403,
        )

    def test_resident_reads_only_their_own_case_tasks(self):
        task = self.create_task()
        CaseEventLog.objects.create(
            case=self.case,
            task=task,
            actor_user=self.responder,
            event_type=CaseEventLog.EventType.TASK_UPDATED,
            detail="Gate key is under the blue flowerpot.",
            created_at=timezone.now(),
        )
        self.client.force_login(self.resident)
        response = self.client.get(f"/api/cases/{self.case.pk}/tasks/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("updates", response.json()[0])
        self.assertNotContains(response, "flowerpot")
        self.assertEqual(self.client.get("/api/tasks/").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/cases/{self.case.pk}/tasks/",
                {"job_id": self.job.pk, "title": "Resident task", "task_type": "cleanup"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/tasks/{task.pk}/",
                {"status": "in_progress"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(f"/api/jobs/{self.job.pk}/complete/").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/jobs/{self.job.pk}/release/",
                {"reason": "Resident cannot release NGO claims"},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.client.force_login(self.other_resident)
        self.assertEqual(
            self.client.get(f"/api/cases/{self.case.pk}/tasks/").status_code, 404
        )

    def test_task_board_contains_only_the_callers_organisation(self):
        own_task = self.create_task()
        other_case = CaseRecord.objects.create(
            reference="FRC-8102",
            submitted_by_user=self.other_resident,
            damage_category=CaseRecord.DamageCategory.REPAIR,
            description="Roof damage.",
            village="Kg. Other",
            address="Lot 9",
            status=CaseRecord.Status.IN_PROGRESS,
            created_at=timezone.now(),
        )
        other_job = CaseJob.objects.create(
            case=other_case, help_type=CaseRecord.DamageCategory.REPAIR,
            status=CaseJob.Status.IN_PROGRESS, claimed_by_org=self.other_org,
        )
        CaseTask.objects.create(
            case=other_case,
            job=other_job,
            lead_user=self.other_responder,
            title="Repair roof",
            task_type=CaseTask.TaskType.REPAIR,
            status=CaseTask.Status.IN_PROGRESS,
        )
        self.client.force_login(self.responder)

        payload = self.client.get("/api/tasks/").json()

        self.assertEqual([task["id"] for task in payload["tasks"]], [own_task.id])
        self.assertEqual(
            {person["id"] for person in payload["responders"]},
            {self.responder.id, self.colleague.id},
        )

    def test_task_must_follow_the_state_machine(self):
        task = self.create_task()
        self.client.force_login(self.responder)

        invalid = self.client.patch(
            f"/api/tasks/{task.pk}/",
            {"status": "done"},
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 409)

        started = self.client.patch(
            f"/api/tasks/{task.pk}/",
            {"status": "in_progress", "note": "Debris removal started at the rear entrance."},
            content_type="application/json",
        )
        self.assertEqual(started.status_code, 200, started.content)
        self.case.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(task.status, CaseTask.Status.IN_PROGRESS)
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)
        self.assertTrue(
            CaseEventLog.objects.filter(
                task=task,
                event_type=CaseEventLog.EventType.TASK_UPDATED,
                detail__contains="rear entrance",
            ).exists()
        )

        finished = self.client.patch(
            f"/api/tasks/{task.pk}/",
            {"status": "done"},
            content_type="application/json",
        )
        self.assertEqual(finished.status_code, 200)
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)

    def test_completion_requires_at_least_one_task_and_all_tasks_done(self):
        self.client.force_login(self.responder)
        self.assertEqual(
            self.client.post(f"/api/jobs/{self.job.pk}/complete/").status_code,
            409,
        )
        self.create_task(status=CaseTask.Status.IN_PROGRESS)
        self.assertEqual(
            self.client.post(f"/api/jobs/{self.job.pk}/complete/").status_code,
            409,
        )

    def test_all_done_tasks_request_resident_confirmation(self):
        self.create_task(status=CaseTask.Status.DONE)
        self.client.force_login(self.responder)

        response = self.client.post(f"/api/jobs/{self.job.pk}/complete/")

        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.PENDING_CONFIRM)
        event = CaseEventLog.objects.get(
            case=self.case,
            event_type=CaseEventLog.EventType.COMPLETION_REQUESTED,
            notification_copy_of__isnull=True,
        )
        self.assertEqual(event.recipient_user, self.resident)

    def test_owner_can_confirm_and_close_the_case(self):
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        CaseJob.objects.filter(pk=self.job.pk).update(status=CaseJob.Status.PENDING_CONFIRM)
        self.create_task(status=CaseTask.Status.DONE)
        self.client.force_login(self.resident)

        response = self.client.post(
            f"/api/jobs/{self.job.pk}/confirm/",
            {"decision": "confirm"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.CLOSED)
        self.assertIsNotNone(self.case.closed_at)
        event = CaseEventLog.objects.get(
            case=self.case,
            event_type=CaseEventLog.EventType.CLOSED,
            notification_copy_of__isnull=True,
        )
        self.assertEqual(event.recipient_user, self.responder)

    def test_resident_dispute_requires_a_note_and_reopens_the_case(self):
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        CaseJob.objects.filter(pk=self.job.pk).update(status=CaseJob.Status.PENDING_CONFIRM)
        self.create_task(status=CaseTask.Status.DONE)
        self.client.force_login(self.resident)

        missing = self.client.post(
            f"/api/jobs/{self.job.pk}/confirm/",
            {"decision": "incomplete", "note": ""},
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)

        response = self.client.post(
            f"/api/jobs/{self.job.pk}/confirm/",
            {"decision": "incomplete", "note": "The rear room still has flood debris."},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)
        self.assertTrue(
            CaseEventLog.objects.filter(
                case=self.case,
                event_type=CaseEventLog.EventType.REOPENED,
                detail__contains="rear room",
            ).exists()
        )

    def test_another_resident_cannot_confirm_the_case(self):
        self.case.status = CaseRecord.Status.PENDING_CONFIRM
        self.case.save(update_fields=["status"])
        CaseJob.objects.filter(pk=self.job.pk).update(status=CaseJob.Status.PENDING_CONFIRM)
        self.client.force_login(self.other_resident)
        response = self.client.post(
            f"/api/jobs/{self.job.pk}/confirm/",
            {"decision": "confirm"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_release_requires_a_reason_and_no_existing_tasks(self):
        self.client.force_login(self.responder)
        missing = self.client.post(
            f"/api/jobs/{self.job.pk}/release/",
            {"reason": ""},
            content_type="application/json",
        )
        self.assertEqual(missing.status_code, 400)

        self.create_task(status=CaseTask.Status.OPEN, lead=None)
        blocked = self.client.post(
            f"/api/jobs/{self.job.pk}/release/",
            {"reason": "Outside our service area."},
            content_type="application/json",
        )
        self.assertEqual(blocked.status_code, 409)

    def test_unstarted_case_can_be_released_to_the_verified_queue(self):
        self.client.force_login(self.responder)
        response = self.client.post(
            f"/api/jobs/{self.job.pk}/release/",
            {"reason": "Our cleanup equipment is unavailable."},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.VERIFIED)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.claimed_by_org)
        self.assertEqual(self.job.status, CaseJob.Status.OPEN)
        self.assertTrue(
            CaseEventLog.objects.filter(
                case=self.case,
                event_type=CaseEventLog.EventType.RELEASED,
                detail__contains="equipment",
            ).exists()
        )


class CaseDetailPrivacyTests(TestCase):
    def setUp(self):
        self.claiming_org = Organization.objects.create(
            name="Claiming NGO", type=Organization.Type.NGO
        )
        self.other_org = Organization.objects.create(
            name="Browsing NGO", type=Organization.Type.NGO
        )
        self.resident = UserAccount.objects.create_user(
            email="privacy-resident@example.my",
            full_name="Privacy Resident",
            password="Recovery2026",
        )
        self.claiming_responder = UserAccount.objects.create_user(
            email="privacy-owner@example.my",
            full_name="Claiming Responder",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.claiming_org,
        )
        self.browsing_responder = UserAccount.objects.create_user(
            email="privacy-browser@example.my",
            full_name="Browsing Responder",
            password="Recovery2026",
            role=UserAccount.Role.NGO_VOLUNTEER,
            organization=self.other_org,
        )
        self.case = CaseRecord.objects.create(
            reference="FRC-8201",
            submitted_by_user=self.resident,
            damage_category=CaseRecord.DamageCategory.CLEANUP,
            description="Sensitive household description.",
            village="Kg. Privacy",
            address="Exact private address",
            vulnerability_flags=["disability"],
            needs_flags=["medicine"],
            status=CaseRecord.Status.CLAIMED,
            created_at=timezone.now(),
        )
        CaseJob.objects.create(
            case=self.case, help_type=CaseRecord.DamageCategory.CLEANUP,
            status=CaseJob.Status.CLAIMED, claimed_by_org=self.claiming_org,
        )
        CaseEventLog.objects.create(
            case=self.case,
            actor_user=self.claiming_responder,
            event_type=CaseEventLog.EventType.TASK_UPDATED,
            detail="Sensitive operational note.",
            created_at=timezone.now(),
        )

    def test_other_ngo_gets_only_the_coordination_summary(self):
        self.client.force_login(self.browsing_responder)
        response = self.client.get(f"/api/cases/{self.case.pk}/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail_access"], "summary")
        self.assertEqual(payload["location"]["precision"], "village")
        for private_field in (
            "description",
            "photos",
            "events",
            "vulnerability_flags",
            "needs_flags",
            "priority_reasons",
            "tasks",
        ):
            self.assertNotIn(private_field, payload)

    def test_other_ngo_cannot_search_private_description(self):
        self.client.force_login(self.browsing_responder)
        response = self.client.get("/api/cases/?q=Sensitive%20household")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

        self.client.force_login(self.claiming_responder)
        response = self.client.get("/api/cases/?q=Sensitive%20household")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["results"]], [self.case.id]
        )

    def test_claiming_ngo_and_resident_get_the_full_detail(self):
        for user in (self.claiming_responder, self.resident):
            self.client.force_login(user)
            payload = self.client.get(f"/api/cases/{self.case.pk}/").json()
            self.assertEqual(payload["detail_access"], "full")
            self.assertEqual(payload["description"], "Sensitive household description.")
            self.assertIn("events", payload)


class TaskSafetyTests(TestCase):
    """FR7/FR20/FR21: starts require the lead's fresh warning acknowledgement."""

    def setUp(self):
        TaskWorkflowTests.setUp(self)

    def create_task(self, note="Unstable floor near the rear door."):
        return CaseTask.objects.create(
            case=self.case,
            job=self.job,
            lead_user=self.responder,
            title="Remove flood debris",
            task_type=CaseTask.TaskType.CLEANUP,
            status=CaseTask.Status.ASSIGNED,
            assigned_at=timezone.now(),
            safety_note=note,
        )

    def patch_task(self, task, payload):
        return self.client.patch(
            f"/api/tasks/{task.pk}/", payload, content_type="application/json"
        )

    def test_creation_strips_note_and_keeps_it_out_of_resident_visible_event(self):
        self.client.force_login(self.responder)
        response = self.client.post(
            f"/api/cases/{self.case.pk}/tasks/",
            {"job_id": self.job.pk, "title": "Clear entry", "task_type": "cleanup", "lead_user_id": self.responder.pk,
             "safety_note": "  Wear boots near broken glass.  "},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["safety_note"], "Wear boots near broken glass.")
        self.assertIsNone(response.json()["safety_acknowledgement"])
        task = CaseTask.objects.get()
        self.assertEqual(task.safety_note, "Wear boots near broken glass.")
        self.assertNotIn("broken glass", CaseEventLog.objects.get(task=task).detail)

        too_long = self.client.post(
            f"/api/cases/{self.case.pk}/tasks/",
            {"job_id": self.job.pk, "title": "Another task", "task_type": "cleanup", "safety_note": "x" * 501},
            content_type="application/json",
        )
        self.assertEqual(too_long.status_code, 400)
        blank = self.client.post(
            f"/api/cases/{self.case.pk}/tasks/",
            {"job_id": self.job.pk, "title": "Blank note", "task_type": "cleanup", "safety_note": "   "},
            content_type="application/json",
        )
        self.assertEqual(blank.status_code, 201, blank.content)
        self.assertEqual(blank.json()["safety_note"], "")

    def test_start_requires_lead_and_acknowledgement_without_partial_writes(self):
        task = self.create_task()
        self.client.force_login(self.colleague)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 403)
        self.client.force_login(self.responder)
        for payload in ({"status": "in_progress"}, {"status": "in_progress", "safety_acknowledged": False}):
            response = self.patch_task(task, payload)
            self.assertEqual(response.status_code, 400, response.content)
            self.assertIn("safety_acknowledged", response.json())
        task.refresh_from_db()
        self.assertEqual(task.status, CaseTask.Status.ASSIGNED)
        self.assertFalse(CaseEventLog.objects.filter(task=task).exists())

        response = self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["safety_acknowledgement"]["by"], self.responder.full_name)
        events = list(CaseEventLog.objects.filter(task=task).order_by("created_at", "pk"))
        self.assertEqual([event.event_type for event in events], [
            CaseEventLog.EventType.SAFETY_ACKNOWLEDGED,
            CaseEventLog.EventType.TASK_UPDATED,
        ])
        self.assertEqual(events[0].actor_user, self.responder)
        self.assertIn(task.safety_note, events[0].detail)
        self.assertIn("not that the site is safe", events[0].detail)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)

    def test_no_note_starts_without_ack_and_rejects_meaningless_ack(self):
        task = self.create_task(note="")
        self.client.force_login(self.colleague)
        self.assertEqual(self.patch_task(task, {"status": "in_progress"}).status_code, 403)
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 400)
        response = self.patch_task(task, {"status": "in_progress"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["safety_acknowledgement"])
        self.assertFalse(CaseEventLog.objects.filter(task=task, event_type=CaseEventLog.EventType.SAFETY_ACKNOWLEDGED).exists())

    def test_colleague_can_add_notes_and_finish_after_the_lead_starts(self):
        task = self.create_task()
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        self.client.force_login(self.colleague)
        self.assertEqual(self.patch_task(task, {"note": "Debris removed from the entrance."}).status_code, 200)
        self.assertEqual(self.patch_task(task, {"status": "done"}).status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, CaseTask.Status.DONE)
        self.assertEqual(task.lead_user, self.responder)

    def test_note_only_and_done_update_cannot_acknowledge(self):
        task = self.create_task()
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"note": "Prepared tools", "safety_acknowledged": True}).status_code, 400)
        self.assertFalse(CaseEventLog.objects.filter(task=task).exists())
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        count = CaseEventLog.objects.filter(task=task).count()
        self.assertEqual(self.patch_task(task, {"status": "done", "safety_acknowledged": True}).status_code, 400)
        self.assertEqual(CaseEventLog.objects.filter(task=task).count(), count)

    def test_reassignment_needs_a_fresh_ack_even_when_assigned_back(self):
        task = self.create_task()
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        first_assigned_at = task.assigned_at
        self.client.force_login(self.colleague)
        response = self.patch_task(task, {"lead_user_id": self.colleague.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "assigned")
        self.assertIsNone(response.json()["safety_acknowledgement"])
        task.refresh_from_db()
        self.assertGreater(task.assigned_at, first_assigned_at)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, CaseRecord.Status.IN_PROGRESS)
        reset = CaseEventLog.objects.filter(task=task, event_type=CaseEventLog.EventType.TASK_ASSIGNED).get()
        self.assertIn("returns to Assigned", reset.detail)
        self.assertEqual(self.patch_task(task, {"status": "in_progress"}).status_code, 400)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)

        self.assertEqual(self.patch_task(task, {"lead_user_id": self.responder.pk}).status_code, 200)
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress"}).status_code, 400)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        actors = list(CaseEventLog.objects.filter(task=task, event_type=CaseEventLog.EventType.SAFETY_ACKNOWLEDGED).order_by("pk").values_list("actor_user_id", flat=True))
        self.assertEqual(actors, [self.responder.pk, self.colleague.pk, self.responder.pk])

    def test_first_assignment_of_open_task_is_not_described_as_a_reset(self):
        # Residents read TASK_ASSIGNED detail, so a first assignment must not
        # claim that work was interrupted.
        task = CaseTask.objects.create(
            case=self.case,
            job=self.job,
            title="Remove flood debris",
            task_type=CaseTask.TaskType.CLEANUP,
            status=CaseTask.Status.OPEN,
        )
        self.client.force_login(self.responder)
        response = self.patch_task(task, {"lead_user_id": self.colleague.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "assigned")
        event = CaseEventLog.objects.get(task=task, event_type=CaseEventLog.EventType.TASK_ASSIGNED)
        self.assertIn("assigned a responder to", event.detail)
        self.assertNotIn("returns to Assigned", event.detail)

    def test_reassign_and_status_are_separate_and_done_cannot_be_reassigned(self):
        task = self.create_task()
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"lead_user_id": self.colleague.pk, "status": "in_progress"}).status_code, 400)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        self.assertEqual(self.patch_task(task, {"status": "done"}).status_code, 200)
        self.assertEqual(self.patch_task(task, {"lead_user_id": self.colleague.pk}).status_code, 409)
        task.refresh_from_db()
        self.assertEqual(task.status, CaseTask.Status.DONE)
        self.assertEqual(task.lead_user, self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress"}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/tasks/").json()[0]["safety_acknowledgement"]["by"], self.responder.full_name)

    def test_role_views_keep_safety_note_from_residents(self):
        task = self.create_task()
        self.client.force_login(self.responder)
        self.assertEqual(self.patch_task(task, {"status": "in_progress", "safety_acknowledged": True}).status_code, 200)
        admin = UserAccount.objects.create_user(
            email="admin-safety@example.my", full_name="System Admin",
            password="Recovery2026", role=UserAccount.Role.SYSTEM_ADMIN,
        )
        for user in (self.responder, self.officer, admin):
            self.client.force_login(user)
            response = self.client.get(f"/api/cases/{self.case.pk}/tasks/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["safety_note"], task.safety_note)
        self.client.force_login(self.responder)
        self.assertEqual(self.client.get("/api/tasks/").json()["tasks"][0]["safety_note"], task.safety_note)
        self.client.force_login(self.other_responder)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/tasks/").status_code, 404)
        self.assertEqual(self.patch_task(task, {"note": "No access"}).status_code, 404)

        self.client.force_login(self.resident)
        for url in (f"/api/cases/{self.case.pk}/tasks/", f"/api/cases/{self.case.pk}/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, task.safety_note)
            self.assertNotContains(response, "safety_acknowledged")
            self.assertNotContains(response, "safety_note")
        self.assertEqual(self.patch_task(task, {"note": "No access"}).status_code, 403)
        self.client.force_login(self.other_resident)
        self.assertEqual(self.client.get(f"/api/cases/{self.case.pk}/tasks/").status_code, 404)
