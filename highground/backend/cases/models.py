"""Case workflow models — report §3.6.

case_record is the hub; everything else hangs off it. Table names are the ERD's
own, so the diagram and the schema can be read against each other.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.db import models
from django.db.models.functions import Greatest, Least
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Organization, UserAccount


class DropOffPoint(models.Model):
    """Official collection points for supply appeals (ADR-021)."""

    name = models.CharField(max_length=120)
    address = models.CharField(max_length=255)
    area = models.CharField(max_length=120)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "drop_off_point"

    def __str__(self):
        return self.name


class LocationArea(models.Model):
    """A controlled place a case can be filed under (see the locations ADR).

    State and district rows carry the official OCHA P-codes from the HDX
    Malaysia gazetteer (COD-AB, administrative levels 1-2). Nothing official
    and open exists below district, so villages get project codes that extend
    their district's P-code — the extension OCHA's own guidance describes for
    settlements below the lowest coded level.

    A code, once issued, is never reused for a different place: an area is
    retired with `active`, never deleted, and cases keep pointing at it.
    """

    class Level(models.TextChoices):
        STATE = "state", "State"
        DISTRICT = "district", "District"
        VILLAGE = "village", "Village"

    class CentroidSource(models.TextChoices):
        OFFICIAL = "official", "Official gazetteer"
        OSM = "osm", "OpenStreetMap"
        APPROXIMATE = "approximate", "Approximate"

    # Which level each level must sit under. Mukim can slot in between
    # district and village later without changing any existing code.
    PARENT_LEVEL = {Level.DISTRICT: Level.STATE, Level.VILLAGE: Level.DISTRICT}

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    # Villages are the only level that grows after launch (districts come from
    # the gazetteer), so a new row defaults to one.
    level = models.CharField(max_length=10, choices=Level, default=Level.VILLAGE)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    # A representative centre point, not a boundary: enough to place a
    # village marker without claiming precision the data does not have.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    centroid_source = models.CharField(max_length=20, choices=CentroidSource, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "location_area"
        ordering = ["code"]

    def __str__(self):
        return f"{self.name} [{self.code}]"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        expected = self.PARENT_LEVEL.get(self.level)
        if expected is None and self.parent_id is not None:
            errors["parent"] = "A state has no parent area."
        elif expected is not None and (self.parent is None or self.parent.level != expected):
            errors["parent"] = f"A {self.get_level_display().lower()} must sit under a {expected.label.lower()}."
        if self.level == self.Level.VILLAGE and (self.latitude is None or self.longitude is None):
            errors["latitude"] = "A village needs a centre point so it can be placed on the map."
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list("code", flat=True).first()
            if original is not None and original != self.code:
                errors["code"] = "A published code never changes; retire the area instead."
        if errors:
            raise ValidationError(errors)

    @classmethod
    def next_village_code(cls, district):
        """The next unused project code under a district, e.g. MY0307-V008.

        Retired villages keep their rows, so counting from the highest code
        ever issued means a number is never handed to a second place. Two
        simultaneous additions under one district can compute the same code;
        the unique constraint then refuses the second instead of duplicating.
        """
        prefix = f"{district.code}-V"
        numbers = [
            int(code[len(prefix):])
            for code in cls.objects.filter(code__startswith=prefix).values_list("code", flat=True)
            if code[len(prefix):].isdigit()
        ]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"


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

    # Verified and not yet closed: an open job on such a case may be claimed.
    CLAIMABLE = (Status.VERIFIED, Status.CLAIMED, Status.IN_PROGRESS, Status.PENDING_CONFIRM)

    reference = models.CharField(max_length=20, unique=True)

    submitted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_cases",
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
    # The controlled place. `village` below stays as the name at the time of
    # filing, so older free-text cases and the report's ERD column still read.
    location_area = models.ForeignKey(
        LocationArea,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cases",
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

    # classes-1.0 (priority/classes.py). Set at verification; NULL until then.
    class PriorityClass(models.IntegerChoices):
        HEALTH_CRITICAL = 1, "Health-critical"
        AT_RISK = 2, "At risk"
        STANDARD = 3, "Standard"

    priority_class = models.PositiveSmallIntegerField(
        choices=PriorityClass, null=True, blank=True
    )
    priority_reasons = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "case_record"
        # Class first, then first come, first served; unclassified last.
        ordering = [models.F("priority_class").asc(nulls_last=True), "created_at", "pk"]

    def __str__(self):
        return f"{self.reference} — {self.village}"

class CasePhoto(models.Model):
    class Stage(models.TextChoices):
        RESIDENT = "resident", "From the household"
        BEFORE = "before", "Before"
        AFTER = "after", "After"

    case = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="photos")
    # Still file_path VARCHAR(255) in the database, as the report's ERD specifies —
    # a FileField is a varchar column that also knows how to save the upload.
    file_path = models.FileField(upload_to="cases/%Y/%m/", max_length=255)
    caption = models.CharField(max_length=255, null=True, blank=True)
    stage = models.CharField(max_length=10, choices=Stage, default=Stage.RESIDENT)
    # Preserve who supplied evidence and which work it documents.
    uploaded_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="uploaded_case_photos",
    )
    task = models.ForeignKey(
        "CaseTask", on_delete=models.PROTECT,
        null=True, blank=True, related_name="photos",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "case_photo"

    def __str__(self):
        return self.caption or str(self.file_path)


class CaseJob(models.Model):
    """One type of help a household asked for, claimable on its own.

    A household submits one request (CaseRecord): one address, one officer
    verification, one priority class. Each type of help it needs becomes a
    job, and each job can be claimed by a different organisation, as Crisis
    Cleanup does with work types (ADR-020). Only one organisation can hold a
    job, so two NGOs never turn up for the same work.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Waiting for an organisation"
        CLAIMED = "claimed", "Claimed"
        IN_PROGRESS = "in_progress", "In progress"
        PENDING_CONFIRM = "pending_confirm", "Awaiting resident confirmation"
        DONE = "done", "Done"
        CLOSED_UNCONFIRMED = "closed_unconfirmed", "Closed without household confirmation"

    # An organisation holding a job in one of these may see the exact address.
    ACTIVE = (Status.CLAIMED, Status.IN_PROGRESS, Status.PENDING_CONFIRM)
    # Both end operational access, but only DONE records household confirmation.
    FINISHED = (Status.DONE, Status.CLOSED_UNCONFIRMED)

    case = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="jobs")
    help_type = models.CharField(max_length=20, choices=CaseRecord.DamageCategory)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    claimed_by_org = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="claimed_jobs",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "case_job"
        ordering = ["case_id", "id"]
        constraints = [
            models.UniqueConstraint(fields=["case", "help_type"], name="one_job_per_help_type"),
        ]

    def __str__(self):
        return f"{self.case.reference} · {self.get_help_type_display()}"


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
    # The job this work belongs to; its organisation owns the task. Null only
    # for rows created before jobs existed and not yet migrated.
    job = models.ForeignKey(
        CaseJob, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks"
    )
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
        # Closed by the system, not judged by an officer: another confirmation
        # closed one of this pair's cases, so the question no longer arises.
        SUPERSEDED = "superseded", "Superseded"

    # case_a is always the older request (created_at, then pk) and case_b the
    # newer one; only case_b can be closed as a duplicate of case_a.
    case_a = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="matches_as_a")
    case_b = models.ForeignKey(CaseRecord, on_delete=models.CASCADE, related_name="matches_as_b")
    decided_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="duplicate_decisions",
    )
    # rules-1.0 flags store which rules fired and no score. dup-1.1 flags
    # (retired weighted engine) keep their evidence index here.
    similarity_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    method = models.CharField(max_length=20, default="dup-1.1")
    matched_rules = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "duplicate_case_match"
        constraints = [
            # One record per unordered pair, whichever way round a future
            # writer stores it, so a rescan can never re-open a decided pair.
            models.UniqueConstraint(
                Least("case_a", "case_b"),
                Greatest("case_a", "case_b"),
                name="duplicate_pair_unique",
            ),
            models.CheckConstraint(
                condition=~models.Q(case_a=models.F("case_b")),
                name="duplicate_pair_distinct_cases",
            ),
        ]

    def __str__(self):
        # rules-1.0 flags have no score; dup-1.1 flags keep their 0-100 index,
        # which is an evidence index, not a percentage chance.
        if self.similarity_score is None:
            evidence = f"{self.method}: {', '.join(self.matched_rules) or 'no rules'}"
        else:
            evidence = f"{self.method} index {self.similarity_score}"
        return f"{self.case_a.reference} ~ {self.case_b.reference} ({evidence})"


_audit_reset = ContextVar("audit_reset", default=False)


@contextmanager
def demo_audit_reset():
    """Permit the explicitly destructive development seed reset only."""
    if not settings.DEBUG:
        raise ValueError("The demo audit reset is disabled outside development.")
    token = _audit_reset.set(True)
    try:
        yield
    finally:
        _audit_reset.reset(token)


class CaseEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if not set(kwargs) <= {"read_at", "delivery_status", "recipient_user"}:
            raise ValueError("Audit fields cannot be updated.")
        return super().update(**kwargs)

    def delete(self):
        if not _audit_reset.get():
            raise ValueError("Audit rows cannot be deleted.")
        return super().delete()


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
        INFO_PROVIDED = "info_provided", "More information provided"
        ADMIN_CORRECTED = "admin_corrected", "Corrected by an administrator"
        REJECTED = "rejected", "Rejected"
        SCORE_COMPUTED = "score_computed", "Score computed"
        CLAIMED = "claimed", "Claimed"
        RELEASED = "released", "Released"
        TASK_ASSIGNED = "task_assigned", "Task assigned"
        TASK_UPDATED = "task_updated", "Task updated"
        PROGRESS_SHARED = "progress_shared", "Progress update shared with the household"
        SAFETY_ACKNOWLEDGED = "safety_acknowledged", "Safety note acknowledged"
        COMPLETION_REQUESTED = "completion_requested", "Completion requested"
        ESCALATED = "escalated", "Escalated"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"
        SCORE_OVERRIDDEN = "score_overridden", "Priority class changed by an officer"
        # Duplicate detection (report §3.7.8). All but DUPLICATE_CLOSED are
        # internal: they name the other household's case and stay with officers.
        DUPLICATE_CHECK_PENDING = "duplicate_check_pending", "Duplicate check pending"
        DUPLICATE_CHECK_COMPLETED = "duplicate_check_completed", "Duplicate check completed"
        DUPLICATE_FLAGGED = "duplicate_flagged", "Possible duplicate flagged"
        DUPLICATE_CONFIRMED = "duplicate_confirmed", "Duplicate confirmed"
        DUPLICATE_DISMISSED = "duplicate_dismissed", "Duplicate dismissed"
        DUPLICATE_SUPERSEDED = "duplicate_superseded", "Duplicate review superseded"
        DUPLICATE_CLOSED = "duplicate_closed", "Closed as a duplicate"
        # Donations to supply appeals (ADR-025). These rows have no case.
        DONATION_RECORDED = "donation_recorded", "Donation recorded"
        DONATION_CANCELLED = "donation_cancelled", "Donation cancelled"
        DONATION_RECEIVED = "donation_received", "Donation received"
        # Decisions on a role application (ADR-027). These rows have neither a
        # case nor a donation: they are about the recipient's own account.
        APPLICATION_APPROVED = "application_approved", "Application approved"
        APPLICATION_REJECTED = "application_rejected", "Application not approved"
        APPROVAL_REVOKED = "approval_revoked", "Approval revoked"

    ACCOUNT_EVENTS = (EventType.APPLICATION_APPROVED, EventType.APPLICATION_REJECTED, EventType.APPROVAL_REVOKED)

    # Every row is about exactly one thing: a case, a donation (ADR-025), or the
    # recipient's own account (ADR-027).
    case = models.ForeignKey(
        CaseRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="events"
    )
    # PROTECT keeps a donation with history from being deleted (no signal needed).
    donation = models.ForeignKey(
        "Donation", on_delete=models.PROTECT, null=True, blank=True, related_name="events"
    )
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
    objects = CaseEventQuerySet.as_manager()

    class Meta:
        db_table = "case_event_log"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(case__isnull=False, donation__isnull=True)
                    | models.Q(case__isnull=True, donation__isnull=False)
                    | models.Q(case__isnull=True, donation__isnull=True, event_type__in=(
                        # ACCOUNT_EVENTS, spelled out: Meta cannot see the class body.
                        "application_approved", "application_rejected", "approval_revoked",
                    ))
                ),
                name="case_event_log_one_subject",
            )
        ]

    def __str__(self):
        if self.case_id:
            subject = self.case.reference
        elif self.donation_id:
            subject = self.donation.appeal.title
        else:
            subject = "Account"
        return f"{subject}: {self.get_event_type_display()}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"read_at", "delivery_status", "recipient_user"}
            changed = set(kwargs.get("update_fields") or ())
            if not changed or not changed <= allowed:
                raise ValueError("Audit fields cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not _audit_reset.get():
            raise ValueError("Audit rows cannot be deleted.")
        return super().delete(*args, **kwargs)


@receiver(pre_delete, sender=CaseEventLog)
def protect_audit_row(sender, instance, **kwargs):
    # Django's deletion collector bypasses Model.delete for cascades.
    if not _audit_reset.get():
        raise ValueError("Audit rows cannot be deleted.")


@receiver(pre_delete, sender=UserAccount)
def protect_audit_actor(sender, instance, **kwargs):
    # SET_NULL on actor_user would erase attribution without deleting the row.
    if not _audit_reset.get() and CaseEventLog.objects.filter(actor_user=instance).exists():
        raise ValueError("Accounts with audit actions cannot be deleted.")


@receiver(pre_delete, sender=CaseTask)
def protect_audit_task(sender, instance, **kwargs):
    if not _audit_reset.get() and CaseEventLog.objects.filter(task=instance).exists():
        raise ValueError("Tasks with audit actions cannot be deleted.")


class SupplyAppealQuerySet(models.QuerySet):
    def open_now(self):
        """Open and not past its date: what residents see and may donate to."""
        return self.filter(status=SupplyAppeal.Status.OPEN, needed_until__gte=timezone.localdate())


class SupplyAppeal(models.Model):
    """An NGO's notice of the relief items it needs (ADR-021).

    Replaces the pledge flow. Residents read it and take items to the
    drop-off point; nothing is pledged or tracked in the app, so there is no
    pledge lifecycle to verify.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="appeals"
    )
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appeals_created"
    )
    drop_off_point = models.ForeignKey(
        DropOffPoint, on_delete=models.PROTECT, related_name="appeals"
    )
    title = models.CharField(max_length=120)
    items = models.TextField(max_length=1000)
    needed_until = models.DateField()
    status = models.CharField(max_length=10, choices=Status, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = SupplyAppealQuerySet.as_manager()

    class Meta:
        db_table = "supply_appeal"
        ordering = ["needed_until", "pk"]

    def __str__(self):
        return f"{self.organization.name}: {self.title}"

    def is_open_now(self):
        # Appeals due today stay open; dates that have passed close on their own (ADR-021).
        return self.status == self.Status.OPEN and self.needed_until >= timezone.localdate()


class Donation(models.Model):
    """What a resident says they will bring to a supply appeal (ADR-025).

    Supersedes ADR-021's "nothing is pledged": the supervisor asked for the
    NGO to confirm receipt in the app. Two steps only — waiting, then received
    (or cancelled by the donor) — with no quantities or stock tracking.
    """

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for drop-off"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    appeal = models.ForeignKey(SupplyAppeal, on_delete=models.PROTECT, related_name="donations")
    donor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="donations"
    )
    items = models.TextField(max_length=500)
    status = models.CharField(max_length=10, choices=Status, default=Status.WAITING)
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    received_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="donations_received",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "donation"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.appeal.title}: {self.items[:40]}"
