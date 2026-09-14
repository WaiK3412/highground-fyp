"""Case workflow models — report §3.6.

case_record is the hub; everything else hangs off it. Table names are the ERD's
own, so the diagram and the schema can be read against each other.
"""

from django.conf import settings
from django.db import models

from accounts.models import Organization


class DropOffPoint(models.Model):
    """Fixed list of official collection points for pledged relief items."""

    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    area = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "drop_off_point"

    def __str__(self):
        return self.name


class CaseRecord(models.Model):
    """A household's aid/recovery request — the hub of the whole system."""

    class DamageCategory(models.TextChoices):
        CLEANUP = "cleanup", "Cleanup"
        REPAIR = "repair", "Repair"
        ESSENTIAL_ITEMS = "essential_items", "Essential items"
        AGRICULTURE = "agriculture", "Agriculture"
        OTHER = "other", "Other"

    class Urgency(models.TextChoices):
        NONE = "none", "No immediate risk"
        HEALTH_RISK = "health_risk", "Health risk"
        MEDICAL_DISRUPTED = "medical_disrupted", "Medical needs disrupted"
        URGENT = "urgent", "Urgent"

    class FloodDepth(models.TextChoices):
        ANKLE = "ankle", "Ankle deep"
        KNEE = "knee", "Knee deep"
        WAIST = "waist", "Waist deep"
        ABOVE_HEAD = "above_head", "Above head height"

    class Liveability(models.TextChoices):
        LIVEABLE = "liveable", "Liveable"
        PARTIAL = "partial", "Partially unliveable"
        UNLIVEABLE = "unliveable", "Fully unliveable"

    class AccessLevel(models.TextChoices):
        NORMAL = "normal", "Normal access"
        FOUR_WD = "four_wd", "4x4 only"
        FOOT = "foot", "On foot only"
        CUT_OFF = "cut_off", "Cut off"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        NEEDS_INFO = "needs_info", "Needs info"
        REJECTED = "rejected", "Rejected"
        VERIFIED = "verified", "Verified"
        CLAIMED = "claimed", "Claimed"
        IN_PROGRESS = "in_progress", "In progress"
        PENDING_CONFIRM = "pending_confirm", "Pending confirmation"
        CLOSED = "closed", "Closed"

    reference = models.CharField(max_length=20, unique=True)

    submitted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_cases",
    )
    claimed_by_org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="claimed_cases",
    )
    verified_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="verified_cases",
    )
    duplicate_of_case = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
    )
    rubric_version = models.ForeignKey(
        "scoring.PriorityRubricVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="scored_cases",
    )

    damage_category = models.CharField(max_length=20, choices=DamageCategory)
    description = models.TextField()
    village = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    household_size = models.IntegerField(default=1)

    urgency = models.CharField(max_length=20, choices=Urgency, default=Urgency.NONE)
    flood_depth = models.CharField(max_length=20, choices=FloodDepth, blank=True)
    liveability = models.CharField(max_length=20, choices=Liveability, default=Liveability.LIVEABLE)
    access_level = models.CharField(max_length=20, choices=AccessLevel, default=AccessLevel.NORMAL)

    needs_flags = models.JSONField(default=list, blank=True)
    vulnerability_flags = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=Status, default=Status.SUBMITTED)
    score_total = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "case_record"
        ordering = ["-score_total", "created_at"]

    def __str__(self):
        return f"{self.reference} — {self.village}"

    @property
    def priority_band(self):
        """The band defined by the rubric version that produced this score."""
        if self.score_total is None:
            return "unscored"
        from scoring.engine import band_for

        if self.rubric_version_id:
            return band_for(
                self.score_total,
                self.rubric_version.high_threshold,
                self.rubric_version.medium_threshold,
            )
        return band_for(self.score_total)


class CasePhoto(models.Model):
    case = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="photos")
    # Still file_path VARCHAR(255) in the database, as the report's ERD specifies —
    # a FileField is a varchar column that also knows how to save the upload.
    file_path = models.FileField(upload_to="cases/%Y/%m/", max_length=255)
    caption = models.CharField(max_length=255, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "case_photo"

    def __str__(self):
        return self.caption or self.file_path


class CaseTask(models.Model):
    class TaskType(models.TextChoices):
        CLEANUP = "cleanup", "Cleanup"
        REPAIR = "repair", "Repair"
        DELIVERY = "delivery", "Delivery"
        ASSESSMENT = "assessment", "Assessment"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    case = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="tasks")
    lead_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="led_tasks",
    )
    title = models.CharField(max_length=150)
    safety_note = models.CharField(max_length=500, blank=True, default="")
    task_type = models.CharField(max_length=20, choices=TaskType)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "case_task"

    def __str__(self):
        return self.title


class DuplicateCaseMatch(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"

    case_a = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="matches_as_a")
    case_b = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="matches_as_b")
    decided_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="duplicate_decisions",
    )
    similarity_score = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "duplicate_case_match"

    def __str__(self):
        return f"{self.case_a.reference} ~ {self.case_b.reference} ({self.similarity_score}%)"


class CaseEventLog(models.Model):
    """Timeline, notifications and audit in one table (ADR-004).

    A canonical row records each action. When one action must notify several
    people, extra rows point back through ``notification_copy_of`` so each
    recipient has independent read state without inflating the audit trail.
    Audit fields remain append-only; only delivery/read state is updated.
    """

    class EventType(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        VERIFIED = "verified", "Verified"
        NEEDS_INFO = "needs_info", "Needs info requested"
        REJECTED = "rejected", "Rejected"
        SCORE_COMPUTED = "score_computed", "Score computed"
        CLAIMED = "claimed", "Claimed"
        RELEASED = "released", "Released"
        TASK_ASSIGNED = "task_assigned", "Task assigned"
        TASK_UPDATED = "task_updated", "Task updated"
        SAFETY_ACKNOWLEDGED = "safety_acknowledged", "Safety note acknowledged"
        COMPLETION_REQUESTED = "completion_requested", "Completion requested"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"
        PLEDGE_UPDATED = "pledge_updated", "Pledge updated"
        SCORE_OVERRIDDEN = "score_overridden", "Score overridden"
        RUBRIC_PUBLISHED = "rubric_published", "Rubric published"

    case = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="events")
    task = models.ForeignKey(
        CaseTask, on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    notification_copy_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notification_copies",
        help_text="Canonical event when this row only stores another recipient's read state.",
    )
    event_type = models.CharField(max_length=30, choices=EventType)
    detail = models.TextField(blank=True)
    delivery_status = models.CharField(max_length=30, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = "case_event_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.case.reference}: {self.get_event_type_display()}"


class CommunityPledge(models.Model):
    """Two states only (ERD §1): Pledged, then the NGO marks Received."""

    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged"
        RECEIVED = "received", "Received"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pledges"
    )
    allocated_case = models.ForeignKey(
        CaseRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="pledges"
    )
    drop_off_point = models.ForeignKey(
        DropOffPoint, on_delete=models.PROTECT, related_name="pledges"
    )
    item_category = models.CharField(max_length=80)
    quantity = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status, default=Status.PLEDGED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_pledge"

    def __str__(self):
        return f"{self.item_category} x{self.quantity}"
