"""Case read shapes: list, NGO summary and full detail, with their parts.

Each shape decides what a role may see; the queryset in accounts.permissions
decides which cases it may see at all.
"""

from django.db.models import Q
from django.urls import reverse
from rest_framework import serializers

from accounts.models import UserAccount
from accounts.permissions import may_see_exact_location, may_see_private_case_details
from priority.classes import HEALTH_CRITICAL_URGENCY

from ..models import CaseEventLog, CaseJob, CaseRecord, CaseTask
from ..privacy import safe_case_text


# Self-reported, unverified. Used only to order the verification list so an
# officer sees a possible health-critical request first; it never sets a
# class or releases a case to NGOs (ESI-style front-door sorting, ADR-018).
REPORTED_URGENT = tuple(HEALTH_CRITICAL_URGENCY)


class CaseJobSerializer(serializers.ModelSerializer):
    """One type of help on a case and who, if anyone, is doing it.

    Shown to every role that can see the case: which help is still needed
    and which organisation holds each job is coordination information, not
    household detail (the address and evidence stay behind the job claim).
    """

    help_type_display = serializers.CharField(source="get_help_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    claimed_by = serializers.CharField(source="claimed_by_org.name", default=None, read_only=True)
    claimed_by_you = serializers.SerializerMethodField()

    class Meta:
        model = CaseJob
        fields = [
            "id", "help_type", "help_type_display", "status", "status_display",
            "claimed_by", "claimed_by_you",
        ]

    def get_claimed_by_you(self, obj):
        request = self.context.get("request")
        org_id = getattr(getattr(request, "user", None), "organization_id", None)
        return bool(org_id and obj.claimed_by_org_id == org_id)


class CaseListSerializer(serializers.ModelSerializer):
    # classes-1.0. The label is safe on the shared queue (it is the class
    # name, nothing about the household); the reasons name vulnerabilities,
    # so they travel only with the full detail.
    priority_label = serializers.CharField(
        source="get_priority_class_display", read_only=True, default=None
    )
    damage_category_display = serializers.CharField(
        source="get_damage_category_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    jobs = CaseJobSerializer(many=True, read_only=True)
    days_waiting = serializers.SerializerMethodField()
    duplicate_check = serializers.SerializerMethodField()
    has_open_duplicate = serializers.SerializerMethodField()
    reported_urgent = serializers.SerializerMethodField()
    awaiting_confirmation_since = serializers.SerializerMethodField()

    class Meta:
        model = CaseRecord
        fields = [
            "id",
            "reference",
            "village",
            "damage_category",
            "damage_category_display",
            "status",
            "status_display",
            "priority_class",
            "priority_label",
            "household_size",
            "jobs",
            "days_waiting",
            "duplicate_check",
            "has_open_duplicate",
            "reported_urgent",
            "awaiting_confirmation_since",
            "created_at",
        ]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        if request is None or request.user.role != UserAccount.Role.DISASTER_OFFICER:
            data.pop("has_open_duplicate", None)
            data.pop("reported_urgent", None)
        if request is None or not _is_district_staff(request.user):
            data.pop("awaiting_confirmation_since", None)
        return data

    def get_awaiting_confirmation_since(self, obj):
        request = self.context.get("request")
        if request is None or not _is_district_staff(request.user):
            return None
        dates = [
            job.completed_at for job in obj.jobs.all()
            if job.status == CaseJob.Status.PENDING_CONFIRM and job.completed_at is not None
        ]
        # Historical pending jobs have no timestamp; never invent a waiting date.
        return serializers.DateTimeField().to_representation(min(dates)) if dates else None

    def get_reported_urgent(self, obj):
        return obj.priority_class is None and obj.urgency in REPORTED_URGENT

    def get_has_open_duplicate(self, obj):
        request = self.context.get("request")
        if request is None or request.user.role != UserAccount.Role.DISASTER_OFFICER:
            return None
        annotated = getattr(obj, "has_open_duplicate", None)
        if annotated is not None:
            return annotated
        from ..models import DuplicateCaseMatch

        return DuplicateCaseMatch.objects.filter(
            Q(case_a=obj) | Q(case_b=obj), status=DuplicateCaseMatch.Status.OPEN
        ).exists()

    def get_days_waiting(self, obj):
        from django.utils import timezone

        return (timezone.now() - obj.created_at).days

    def get_duplicate_check(self, obj):
        """Pending or completed, for the household and district staff only.

        Only the state: never which case it was compared with or why. Other
        roles get null.
        """
        request = self.context.get("request")
        if request is None or not _may_see_duplicate_state(request.user, obj):
            return None
        from ..duplicate_services import duplicate_check_state

        return duplicate_check_state(obj)


def _is_district_staff(user):
    return user.role in {UserAccount.Role.DISASTER_OFFICER, UserAccount.Role.SYSTEM_ADMIN}


def _may_see_duplicate_state(user, case):
    return _is_district_staff(user) or case.submitted_by_user_id == user.id


def _visible_events(case, user):
    """The timeline this user may read, however the case was loaded.

    Applied in the serializer, not only in case_detail's prefetch, so the
    lifecycle actions that return a case (claim, complete, confirm...) cannot
    leak events the detail page would hide.
    """
    from ..duplicate_services import INTERNAL_DUPLICATE_EVENTS

    events = [event for event in case.events.all() if event.notification_copy_of_id is None]
    if not _is_district_staff(user):
        # Duplicate review names another household's case.
        events = [e for e in events if e.event_type not in INTERNAL_DUPLICATE_EVENTS]
    if user.role == UserAccount.Role.COMMUNITY_MEMBER:
        events = [e for e in events if e.event_type != CaseEventLog.EventType.SAFETY_ACKNOWLEDGED]
    return sorted(events, key=lambda e: (e.created_at, e.pk))


class CaseEventSerializer(serializers.Serializer):
    """One entry in a case's history.

    The timeline uses canonical audit actions. Extra rows that only give a
    second notification recipient independent read state are excluded.
    """

    event_type = serializers.CharField(read_only=True)
    event_display = serializers.CharField(source="get_event_type_display", read_only=True)
    detail = serializers.SerializerMethodField()
    actor = serializers.CharField(source="actor_user.full_name", default=None, read_only=True)
    actor_org = serializers.CharField(
        source="actor_user.organization.name", default=None, read_only=True
    )
    created_at = serializers.DateTimeField(read_only=True)

    # These notes were deliberately written for the household. Other event
    # detail may contain operational context; residents still see the event and
    # its plain-language title, but not the internal note.
    RESIDENT_DETAIL_TYPES = {
        CaseEventLog.EventType.VERIFIED,
        CaseEventLog.EventType.NEEDS_INFO,
        CaseEventLog.EventType.INFO_PROVIDED,
        CaseEventLog.EventType.REJECTED,
        CaseEventLog.EventType.CLAIMED,
        CaseEventLog.EventType.RELEASED,
        CaseEventLog.EventType.TASK_ASSIGNED,
        CaseEventLog.EventType.COMPLETION_REQUESTED,
        CaseEventLog.EventType.CLOSED,
        CaseEventLog.EventType.REOPENED,
        CaseEventLog.EventType.DUPLICATE_CLOSED,
    }

    def get_detail(self, obj):
        request = self.context.get("request")
        if (
            request
            and request.user.role == "community_member"
            and obj.event_type not in self.RESIDENT_DETAIL_TYPES
        ):
            return ""
        return safe_case_text(obj.case, request.user if request else None, obj.detail)


class CasePhotoSerializer(serializers.Serializer):
    url = serializers.SerializerMethodField()
    caption = serializers.SerializerMethodField()
    stage = serializers.CharField(read_only=True)
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)
    task_id = serializers.IntegerField(read_only=True, allow_null=True)
    job_id = serializers.IntegerField(source="task.job_id", default=None, read_only=True)
    uploaded_by_org = serializers.SerializerMethodField()
    uploaded_at = serializers.DateTimeField(read_only=True)

    def get_url(self, obj):
        return reverse("case-photo", kwargs={"pk": obj.pk})

    def get_caption(self, obj):
        request = self.context.get("request")
        return safe_case_text(obj.case, request.user if request else None, obj.caption or "")

    def get_uploaded_by_org(self, obj):
        if obj.stage == "resident" or obj.uploaded_by_user_id is None:
            return None
        organisation = obj.uploaded_by_user.organization
        return organisation.name if organisation else None


class CaseTaskSummarySerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    lead_name = serializers.CharField(source="lead_user.full_name", default=None, read_only=True)
    photos = serializers.SerializerMethodField()

    class Meta:
        model = CaseTask
        fields = [
            "id",
            "title",
            "task_type",
            "task_type_display",
            "status",
            "status_display",
            "lead_name",
            "assigned_at",
            "completed_at",
            "photos",
        ]

    def get_title(self, obj):
        request = self.context.get("request")
        return safe_case_text(obj.case, request.user if request else None, obj.title)

    def get_photos(self, obj):
        request = self.context.get("request")
        # Task history remains readable after work ends; photo access does not.
        if request is None or not may_see_private_case_details(request.user, obj.case):
            return []
        return CasePhotoSerializer(obj.photos.all(), many=True, context=self.context).data


class CaseSummaryDetailSerializer(CaseListSerializer):
    """A coordination summary for an NGO that has not claimed the case."""

    detail_access = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    household_contact = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + ["detail_access", "location", "household_contact"]

    def get_household_contact(self, obj):
        return None

    def get_detail_access(self, obj):
        return "summary"

    def get_location(self, obj):
        return {
            "precision": "village",
            "address": obj.village,
            "latitude": None,
            "longitude": None,
        }


class CaseDetailSerializer(CaseListSerializer):
    description = serializers.SerializerMethodField()
    photos = CasePhotoSerializer(many=True, read_only=True)
    events = serializers.SerializerMethodField()
    tasks = CaseTaskSummarySerializer(many=True, read_only=True)
    location = serializers.SerializerMethodField()
    detail_access = serializers.SerializerMethodField()
    duplicate_review = serializers.SerializerMethodField()
    household_contact = serializers.SerializerMethodField()
    # The raw values are enum members like "medical_disrupted"; the model
    # already carries the wording a person should read, so send that too rather
    # than leaving each client to invent its own labels.
    urgency_display = serializers.CharField(source="get_urgency_display", read_only=True)
    flood_depth_display = serializers.CharField(
        source="get_flood_depth_display", read_only=True
    )
    liveability_display = serializers.CharField(
        source="get_liveability_display", read_only=True
    )
    access_level_display = serializers.CharField(
        source="get_access_level_display", read_only=True
    )

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            "description",
            "urgency",
            "urgency_display",
            "flood_depth",
            "flood_depth_display",
            "liveability",
            "liveability_display",
            "access_level",
            "access_level_display",
            "needs_flags",
            "vulnerability_flags",
            "priority_reasons",
            "location",
            "photos",
            "events",
            "tasks",
            "detail_access",
            "duplicate_review",
            "household_contact",
        ]

    def get_household_contact(self, obj):
        request = self.context.get("request")
        if request is None or not may_see_private_case_details(request.user, obj):
            return None
        return {"name": obj.submitted_by_user.full_name, "phone": obj.submitted_by_user.phone}

    def get_detail_access(self, obj):
        return "full"

    def get_description(self, obj):
        return safe_case_text(obj, self.context["request"].user, obj.description)

    def get_events(self, obj):
        user = self.context["request"].user
        return CaseEventSerializer(_visible_events(obj, user), many=True, context=self.context).data

    def get_duplicate_review(self, obj):
        """What the verification workspace needs; officers and admins only."""
        if not _is_district_staff(self.context["request"].user):
            return None
        from ..duplicate_services import duplicate_check_state, duplicate_verification_block
        from ..models import DuplicateCaseMatch

        block = duplicate_verification_block(obj)
        open_ids = DuplicateCaseMatch.objects.filter(
            Q(case_a=obj) | Q(case_b=obj), status=DuplicateCaseMatch.Status.OPEN
        ).values_list("pk", flat=True)
        blocking_ids = DuplicateCaseMatch.objects.filter(
            case_b=obj, status=DuplicateCaseMatch.Status.OPEN
        ).order_by("pk").values_list("pk", flat=True)
        confirmed_id = DuplicateCaseMatch.objects.filter(
            case_b=obj, status=DuplicateCaseMatch.Status.CONFIRMED
        ).order_by("-pk").values_list("pk", flat=True).first()
        return {
            "check": duplicate_check_state(obj),
            "open_match_ids": sorted(open_ids),
            "blocking_match_ids": list(blocking_ids),
            "confirmed_match_id": confirmed_id,
            "verification_block": block[0] if block else None,
            "duplicate_of": obj.duplicate_of_case.reference if obj.duplicate_of_case_id else None,
        }

    def get_location(self, obj):
        """Coordinates go to the district office and the claiming org; everyone
        else gets the village only. Withholding is the default, not a toggle.
        """
        user = self.context["request"].user
        if may_see_exact_location(user, obj):
            return {
                "precision": "exact",
                "address": obj.address,
                "latitude": str(obj.latitude) if obj.latitude else None,
                "longitude": str(obj.longitude) if obj.longitude else None,
            }
        return {"precision": "village", "address": obj.village, "latitude": None, "longitude": None}
