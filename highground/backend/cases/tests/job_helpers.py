"""Test helper (not a test module): give a case a help job (ADR-020).

Before jobs, tests set case.claimed_by_org. Now an organisation holds a job
on the case; this creates that job for the case's main type of help.
"""

from cases.models import CaseJob, CaseRecord

# A case's lifecycle status and the job status that goes with it.
JOB_STATUS_FOR_CASE = {
    CaseRecord.Status.CLAIMED: CaseJob.Status.CLAIMED,
    CaseRecord.Status.IN_PROGRESS: CaseJob.Status.IN_PROGRESS,
    CaseRecord.Status.PENDING_CONFIRM: CaseJob.Status.PENDING_CONFIRM,
    CaseRecord.Status.CLOSED: CaseJob.Status.DONE,
}


def give_job(case, org=None, status=None):
    """Create (or update) the main job; held by `org` if given."""
    if status is None:
        status = JOB_STATUS_FOR_CASE.get(case.status, CaseJob.Status.CLAIMED) if org else CaseJob.Status.OPEN
    job, _ = CaseJob.objects.update_or_create(
        case=case, help_type=case.damage_category,
        defaults={"claimed_by_org": org, "status": status},
    )
    return job
