"""Every case action, through the real API, tells exactly the right people.

Requirements covered: FR10 and FR22. The recipient rules are unit-tested in
test_notifications.py by calling notify() directly; this walks one household's
case from submission to closure through the endpoints the app uses, and after
each action checks who got an in-app notification and who got an email. Each
step expects the two lists to match: email is the nudge for the in-app row.
Each step must also write exactly one audit record of its own action, naming
the person who acted and the time (FR22).
"""

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseJob, CaseRecord, CaseTask, LocationArea
from cases.tests.test_submission import VALID

PASSWORD = "Recovery2026"


@override_settings(EMAIL_SKIP_DOMAINS=set())
class NotificationJourneyTests(TestCase):
    def setUp(self):
        village = LocationArea.objects.get(code=VALID["location_code"])
        self.resident = self.person("siti@example.my")
        self.officer = self.person("zul@example.my", role=UserAccount.Role.DISASTER_OFFICER, district_id=village.parent_id)
        # Another district's officer must hear nothing about this household.
        elsewhere = LocationArea.objects.filter(level=LocationArea.Level.DISTRICT).exclude(pk=village.parent_id).first()
        self.person("far@example.my", role=UserAccount.Role.DISASTER_OFFICER, district=elsewhere)
        mercy = Organization.objects.create(name="Mercy Relief", type=Organization.Type.NGO)
        self.ngo = self.person("aisyah@example.my", role=UserAccount.Role.NGO_VOLUNTEER, organization=mercy)
        self.ngo_colleague = self.person("hafiz@example.my", role=UserAccount.Role.NGO_VOLUNTEER, organization=mercy)
        other = Organization.objects.create(name="Belia", type=Organization.Type.VOLUNTEER_GROUP)
        self.person("other@example.my", role=UserAccount.Role.NGO_VOLUNTEER, organization=other)

    def person(self, email, **fields):
        return UserAccount.objects.create_user(email=email, full_name=email.split("@")[0], password=PASSWORD, **fields)

    def act(self, user, url, data=None, *, tells, records):
        """Do one action as `user`; check its audit record and who was told in the app and by email."""
        last_row = CaseEventLog.objects.order_by("-id").values_list("id", flat=True).first() or 0
        sent_before = len(mail.outbox)
        self.client.force_login(user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, data or {}, content_type="application/json")
        self.assertLess(response.status_code, 300, f"{url}: {response.content}")

        # One canonical row for the action itself; extra recipients only get copies of it.
        audit = CaseEventLog.objects.filter(id__gt=last_row, event_type=records, notification_copy_of__isnull=True)
        self.assertEqual(audit.count(), 1, f"audit rows for {records} after {url}")
        self.assertEqual(audit.get().actor_user, user, f"actor after {url}")
        self.assertIsNotNone(audit.get().created_at, f"time after {url}")

        in_app = set(
            CaseEventLog.objects.filter(id__gt=last_row, recipient_user__isnull=False)
            .values_list("recipient_user__email", flat=True)
        )
        emailed = {address for message in mail.outbox[sent_before:] for address in message.to}
        expected = {person.email for person in tells}
        self.assertEqual(in_app, expected, f"in-app after {url}")
        self.assertEqual(emailed, expected, f"email after {url}")
        return response

    def job(self, case):
        return CaseJob.objects.get(case=case)

    def finish_the_work(self, job):
        # Task assignment notifies nobody, so the task is made directly.
        CaseTask.objects.update_or_create(
            case=job.case, job=job,
            defaults={
                "lead_user": self.ngo, "title": "Clear the mud", "task_type": CaseTask.TaskType.CLEANUP,
                "status": CaseTask.Status.DONE,
            },
        )

    def test_a_case_from_submission_to_closure(self):
        response = self.act(self.resident, "/api/cases/", VALID, tells=[self.officer], records=CaseEventLog.EventType.SUBMITTED)
        case = CaseRecord.objects.get(pk=response.json()["id"])
        verify = f"/api/cases/{case.pk}/verify/"

        self.act(self.officer, verify, {"decision": "needs_info", "note": "Which rooms?"}, tells=[self.resident], records=CaseEventLog.EventType.NEEDS_INFO)
        self.act(self.resident, f"/api/cases/{case.pk}/reply/", {"note": "All of them."}, tells=[self.officer], records=CaseEventLog.EventType.INFO_PROVIDED)
        self.act(self.officer, verify, {"decision": "verified"}, tells=[self.resident], records=CaseEventLog.EventType.VERIFIED)

        job = self.job(case)
        self.act(self.ngo, f"/api/jobs/{job.pk}/claim/", tells=[self.resident], records=CaseEventLog.EventType.CLAIMED)
        self.act(self.ngo, f"/api/jobs/{job.pk}/release/", {"reason": "No boat this week."}, tells=[self.resident], records=CaseEventLog.EventType.RELEASED)
        self.act(self.ngo, f"/api/jobs/{job.pk}/claim/", tells=[self.resident], records=CaseEventLog.EventType.CLAIMED)

        self.finish_the_work(job)
        self.act(self.ngo, f"/api/jobs/{job.pk}/complete/", tells=[self.resident], records=CaseEventLog.EventType.COMPLETION_REQUESTED)
        # The household's answer goes to the whole organisation that did the job.
        self.act(
            self.resident, f"/api/jobs/{job.pk}/confirm/", {"decision": "incomplete", "note": "Kitchen still muddy."},
            tells=[self.ngo, self.ngo_colleague], records=CaseEventLog.EventType.REOPENED,
        )
        self.finish_the_work(job)
        self.act(self.ngo, f"/api/jobs/{job.pk}/complete/", tells=[self.resident], records=CaseEventLog.EventType.COMPLETION_REQUESTED)
        self.act(self.resident, f"/api/jobs/{job.pk}/confirm/", {"decision": "confirm"}, tells=[self.ngo, self.ngo_colleague], records=CaseEventLog.EventType.CLOSED)
        # The organisation did not own the case, so it is not "your case" to them.
        self.assertIn("A resident confirmed the work is complete", mail.outbox[-1].subject)

    def test_rejection_and_closing_on_the_households_behalf(self):
        rejected = self.act(self.resident, "/api/cases/", VALID, tells=[self.officer], records=CaseEventLog.EventType.SUBMITTED).json()["id"]
        self.act(self.officer, f"/api/cases/{rejected}/verify/", {"decision": "rejected", "note": "Outside the flood area."},
                 tells=[self.resident], records=CaseEventLog.EventType.REJECTED)

        second = self.act(self.resident, "/api/cases/", {**VALID, "address": "Lot 9, Jalan Pantai"}, tells=[self.officer], records=CaseEventLog.EventType.SUBMITTED)
        case = CaseRecord.objects.get(pk=second.json()["id"])
        self.act(self.officer, f"/api/cases/{case.pk}/verify/", {"decision": "verified"}, tells=[self.resident], records=CaseEventLog.EventType.VERIFIED)
        job = self.job(case)
        self.act(self.ngo, f"/api/jobs/{job.pk}/claim/", tells=[self.resident], records=CaseEventLog.EventType.CLAIMED)
        self.finish_the_work(job)
        self.act(self.ngo, f"/api/jobs/{job.pk}/complete/", tells=[self.resident], records=CaseEventLog.EventType.COMPLETION_REQUESTED)
        # The household cannot be reached, so the officer closes it for them.
        CaseJob.objects.filter(pk=job.pk).update(completed_at=timezone.now() - timezone.timedelta(days=30))
        self.act(
            self.officer, f"/api/cases/{case.pk}/close/",
            {"outcome": "household_unreachable", "note": "Three calls, no answer."}, tells=[self.resident],
            records=CaseEventLog.EventType.CLOSED,
        )
        self.assertIn("Your case has been closed", mail.outbox[-1].subject)
