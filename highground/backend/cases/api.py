"""Case endpoints.

Querysets are narrowed by role before serialising, so guessing an id gets a
resident nothing.
"""

import json

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsCommunityMember,
    IsCoordinator,
    IsDisasterOfficer,
    IsNgoVolunteer,
    may_see_exact_location,
    may_see_private_case_details,
    visible_cases,
)
from accounts.models import UserAccount

from .models import CaseEventLog, CasePhoto, CaseRecord, CaseTask, LocationArea


class ScoreComponentSerializer(serializers.Serializer):
    key = serializers.CharField(source="criterion.key")
    name = serializers.CharField(source="criterion.name")
    weight = serializers.IntegerField(source="criterion.weight")
    points = serializers.IntegerField()
    reason = serializers.CharField()


class CaseListSerializer(serializers.ModelSerializer):
    priority_band = serializers.CharField(read_only=True)
    damage_category_display = serializers.CharField(
        source="get_damage_category_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    claimed_by = serializers.CharField(source="claimed_by_org.name", default=None, read_only=True)
    days_waiting = serializers.SerializerMethodField()
    duplicate_check = serializers.SerializerMethodField()

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
            "score_total",
            "priority_band",
            "household_size",
            "claimed_by",
            "days_waiting",
            "duplicate_check",
            "created_at",
        ]

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
        from .duplicate_services import duplicate_check_state

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
    from .duplicate_services import INTERNAL_DUPLICATE_EVENTS

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
        return obj.detail


class CasePhotoSerializer(serializers.Serializer):
    url = serializers.CharField(source="file_path.url", read_only=True)
    caption = serializers.CharField(read_only=True)
    uploaded_at = serializers.DateTimeField(read_only=True)


class CaseTaskSummarySerializer(serializers.ModelSerializer):
    task_type_display = serializers.CharField(source="get_task_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    lead_name = serializers.CharField(source="lead_user.full_name", default=None, read_only=True)

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
        ]


class CaseSummaryDetailSerializer(CaseListSerializer):
    """A coordination summary for an NGO that has not claimed the case."""

    detail_access = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    # Which rubric produced the score (FR22) — public, like the rubric page.
    rubric_label = serializers.CharField(source="rubric_version.label", default=None, read_only=True)

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + ["detail_access", "location", "rubric_label"]

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
    score_components = ScoreComponentSerializer(many=True, read_only=True)
    photos = CasePhotoSerializer(many=True, read_only=True)
    events = serializers.SerializerMethodField()
    tasks = CaseTaskSummarySerializer(many=True, read_only=True)
    location = serializers.SerializerMethodField()
    detail_access = serializers.SerializerMethodField()
    duplicate_review = serializers.SerializerMethodField()
    rubric_label = serializers.CharField(source="rubric_version.label", default=None, read_only=True)
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
            "score_components",
            "location",
            "photos",
            "events",
            "tasks",
            "detail_access",
            "rubric_label",
            "duplicate_review",
        ]

    def get_detail_access(self, obj):
        return "full"

    def get_events(self, obj):
        user = self.context["request"].user
        return CaseEventSerializer(_visible_events(obj, user), many=True, context=self.context).data

    def get_duplicate_review(self, obj):
        """What the verification workspace needs; officers and admins only."""
        if not _is_district_staff(self.context["request"].user):
            return None
        from .duplicate_services import duplicate_check_state, duplicate_verification_block
        from .models import DuplicateCaseMatch

        block = duplicate_verification_block(obj)
        open_ids = DuplicateCaseMatch.objects.filter(
            Q(case_a=obj) | Q(case_b=obj), status=DuplicateCaseMatch.Status.OPEN
        ).values_list("pk", flat=True)
        return {
            "check": duplicate_check_state(obj),
            "open_match_ids": sorted(open_ids),
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


# The scoring engine awards points per flag, so an unchecked list is a way to
# inflate your own priority. These vocabularies are the engine's own
# (scoring/engine.py) — anything outside them is not a need we recognise.
# Same limits as registration documents (accounts/api.py) — a household on a
# phone connection should not be asked to upload more than this.
MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}

VULNERABILITY_VOCAB = {"elderly", "child_under_5", "disability", "single_parent"}
NEEDS_VOCAB = {"food", "water", "hygiene", "bedding", "medicine", "baby_supplies"}


def _known_flags(values, vocabulary, field):
    # A multipart submission (one carrying photos) cannot hold a real list, so
    # the client sends the flags as a JSON string. Accept either shape.
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            raise serializers.ValidationError("Expected a list.")
    if not isinstance(values, list):
        raise serializers.ValidationError("Expected a list.")
    unknown = sorted({str(v) for v in values} - vocabulary)
    if unknown:
        raise serializers.ValidationError(f"Unrecognised {field}: {', '.join(unknown)}.")
    # De-duplicated: the engine counts entries, so a repeated flag would score twice.
    return sorted(set(values))


class CaseCreateSerializer(serializers.ModelSerializer):
    """What a household may put in a new case (FR3).

    The field list IS the security boundary, and it is deliberately short.
    Everything a resident must not control — status, score_total,
    verified_by_user, claimed_by_org, rubric_version, reference,
    submitted_by_user — is simply absent, so DRF drops it instead of trusting
    it. Posting score_total=100 is not an error; it is ignored.

    Same rule as ADR-012 registration: the request records what you want, the
    server decides what you get.
    """

    # A code from /api/locations/, not free text: a household cannot file
    # under a retired or invented place, and every case lands on the map.
    location_code = serializers.SlugRelatedField(
        source="location_area",
        slug_field="code",
        queryset=LocationArea.objects.filter(
            level=LocationArea.Level.VILLAGE, active=True, parent__active=True
        ),
        write_only=True,
        error_messages={
            "required": "Choose your village.",
            "null": "Choose your village.",
            "does_not_exist": "Choose a village from the list.",
        },
    )

    class Meta:
        model = CaseRecord
        fields = [
            "location_code",
            "address",
            "household_size",
            "damage_category",
            "description",
            "flood_depth",
            "liveability",
            "access_level",
            "urgency",
            "vulnerability_flags",
            "needs_flags",
        ]

    def validate_household_size(self, value):
        if value < 1:
            raise serializers.ValidationError("A household has at least one person.")
        return value

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Describe the damage and what you need.")
        return value.strip()

    def validate_vulnerability_flags(self, value):
        return _known_flags(value, VULNERABILITY_VOCAB, "vulnerability flags")

    def validate_needs_flags(self, value):
        return _known_flags(value, NEEDS_VOCAB, "needs flags")

    def validate(self, attrs):
        # The name as filed stays on the case, so it still reads the same if
        # the area is later renamed or retired.
        attrs["village"] = attrs["location_area"].name
        return attrs


def _next_reference():
    """Next FRC- number, continuing the seed data's series.

    Known limitation: two simultaneous submissions can read the same maximum.
    `reference` is unique, so the loser gets an IntegrityError rather than a
    duplicate reference — noisy, but never wrong. A database sequence is the
    real fix and is not worth building before submissions are concurrent.
    """
    last = (
        CaseRecord.objects.filter(reference__startswith="FRC-")
        .order_by("-reference")
        .values_list("reference", flat=True)
        .first()
    )
    try:
        return f"FRC-{int(last.split('-')[1]) + 1}"
    except (AttributeError, IndexError, ValueError):
        return "FRC-1042"


def _queue_queryset(request):
    """The queue as this user may see it, with the list's filters applied.

    Shared by the list and the map so the two can never disagree about which
    cases exist for a user.
    """
    queryset = CaseRecord.objects.select_related(
        "claimed_by_org", "submitted_by_user"
    ).all()
    queryset = visible_cases(request.user, queryset)

    status_filter = request.query_params.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    search = request.query_params.get("q")
    if search:
        from django.db.models import Q

        # The controlled village name as well as the text a case was filed
        # with, so a village marker's name finds older free-text cases too.
        search_query = (
            Q(reference__icontains=search)
            | Q(village__icontains=search)
            | Q(location_area__name__icontains=search)
        )
        # An NGO may browse the shared coordination queue, but private
        # household descriptions only become searchable after its own
        # organisation claims the case. Otherwise even a yes/no search
        # result could reveal sensitive circumstances.
        if request.user.role == UserAccount.Role.NGO_VOLUNTEER:
            if request.user.organization_id:
                search_query |= Q(
                    claimed_by_org=request.user.organization,
                    description__icontains=search,
                )
        else:
            search_query |= Q(description__icontains=search)
        queryset = queryset.filter(search_query)
    return queryset


class CaseListView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    # A photo cannot travel inside JSON, so a submission with images arrives as
    # multipart. JSON is kept for submissions without any.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        # Reading and writing are different shapes: the list carries computed
        # fields a client may never set.
        return CaseCreateSerializer if self.request.method == "POST" else CaseListSerializer

    def get_queryset(self):
        from .duplicate_services import latest_check_event_subquery

        # One subquery instead of a check-state query per row.
        return _queue_queryset(self.request).annotate(
            latest_duplicate_check=latest_check_event_subquery()
        )

    def create(self, request, *args, **kwargs):
        """Create a case from a household's submission (FR3).

        Scoring deliberately does not happen here. Screen 17 is explicit that
        a request is checked by an officer "before it is scored and released
        to the NGO queue", so a new case carries score_total=None until it is
        verified.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        photos = request.FILES.getlist("photos")
        if len(photos) > MAX_PHOTOS:
            return Response(
                {"photos": [f"Attach at most {MAX_PHOTOS} photos."]}, status=400
            )
        for upload in photos:
            if upload.size > MAX_PHOTO_BYTES:
                return Response({"photos": [f"{upload.name} is larger than 5 MB."]}, status=400)
            if upload.content_type not in ALLOWED_PHOTO_TYPES:
                return Response(
                    {"photos": [f"{upload.name} must be a JPEG, PNG or WebP image."]},
                    status=400,
                )

        with transaction.atomic():
            case = serializer.save(
                submitted_by_user=request.user,
                reference=_next_reference(),
                status=CaseRecord.Status.SUBMITTED,
                created_at=timezone.now(),
            )
            for upload in photos:
                CasePhoto.objects.create(case=case, file_path=upload)

            CaseEventLog.objects.create(
                case=case,
                actor_user=request.user,
                event_type=CaseEventLog.EventType.SUBMITTED,
                detail=f"Request submitted by {request.user.full_name}."
                + (f" {len(photos)} photo(s) attached." if photos else ""),
                created_at=timezone.now(),
            )

        # After the commit, in its own transaction: a detection failure rolls
        # back only its own writes and leaves the case "check pending", which
        # blocks verification until scan_duplicates succeeds. The household's
        # request itself is never lost to it.
        from .duplicate_services import run_detection_after_submission

        run_detection_after_submission(case)

        # Outside the transaction: sending mail is slow and can fail, and a
        # failed nudge must not roll back a submitted case.
        from .notifications import notify

        notify(
            case,
            CaseEventLog.EventType.SUBMITTED,
            request.user,
            f"{case.get_damage_category_display()} in {case.village}, "
            f"household of {case.household_size}.",
        )

        return Response(CaseListSerializer(case, context={"request": request}).data, status=201)



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def case_detail(request, pk):
    events = CaseEventLog.objects.filter(notification_copy_of__isnull=True)
    if request.user.role == UserAccount.Role.COMMUNITY_MEMBER:
        events = events.exclude(event_type=CaseEventLog.EventType.SAFETY_ACKNOWLEDGED)
    queryset = visible_cases(
        request.user,
        CaseRecord.objects.select_related("claimed_by_org").prefetch_related(
            "score_components__criterion",
            "photos",
            "tasks__lead_user",
            # Oldest first: a timeline reads downwards.
            Prefetch(
                "events",
                queryset=events.select_related("actor_user__organization").order_by("created_at"),
            ),
        ),
    )
    case = queryset.filter(pk=pk).first()
    if case is None:
        # 404 rather than 403: do not confirm that a hidden case exists.
        return Response({"detail": "Not found."}, status=404)
    serializer_class = (
        CaseDetailSerializer
        if may_see_private_case_details(request.user, case)
        else CaseSummaryDetailSerializer
    )
    return Response(serializer_class(case, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def queue_stats(request):
    """Header strip counts. Plain COUNTs — no chart library (ADR C10.8)."""
    queryset = visible_cases(request.user, CaseRecord.objects.all())
    return Response(
        {
            "total": queryset.count(),
            "high": queryset.filter(score_total__gte=70).count(),
            "unclaimed": queryset.filter(claimed_by_org__isnull=True).count(),
            "in_progress": queryset.filter(status="in_progress").count(),
        }
    )


BAND_RANK = {"High": 3, "Medium": 2, "Low": 1}


@api_view(["GET"])
@permission_classes([IsCoordinator])
def case_map(request):
    """The visible queue on a map, at the precision each role may see.

    Same cases and filters as the list, and never more about them. A case
    whose exact location this user may see (may_see_exact_location) is a
    point; any other case is only counted into its village. Published points
    can be re-identified to a household even at low resolution (Brownstein et
    al. 2006), and the village is already on the list, so counting it adds
    nothing an NGO could not already read.
    """
    cases = _queue_queryset(request).select_related("location_area", "rubric_version")
    points, areas, unmapped = [], {}, 0
    for case in cases:
        area = case.location_area
        area_placed = area is not None and area.latitude is not None
        if may_see_exact_location(request.user, case):
            if case.latitude is not None and case.longitude is not None:
                latitude, longitude, precision = case.latitude, case.longitude, "exact"
            elif area_placed:
                # No household pin yet (resident pin-drop is deferred).
                latitude, longitude, precision = area.latitude, area.longitude, "village"
            else:
                unmapped += 1
                continue
            points.append(
                {
                    "id": case.id,
                    "reference": case.reference,
                    "village": case.village,
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "precision": precision,
                    "status": case.status,
                    "status_display": case.get_status_display(),
                    "score_total": case.score_total,
                    "priority_band": case.priority_band,
                    "claimed_by": case.claimed_by_org.name if case.claimed_by_org_id else None,
                    "claimed_by_you": bool(
                        case.claimed_by_org_id
                        and case.claimed_by_org_id == request.user.organization_id
                    ),
                }
            )
        elif area_placed:
            entry = areas.setdefault(
                area.code,
                {
                    "code": area.code,
                    "name": area.name,
                    "latitude": str(area.latitude),
                    "longitude": str(area.longitude),
                    "case_count": 0,
                    "highest_band": "unscored",
                },
            )
            entry["case_count"] += 1
            band = case.priority_band
            if BAND_RANK.get(band, 0) > BAND_RANK.get(entry["highest_band"], 0):
                entry["highest_band"] = band
        else:
            unmapped += 1
    return Response(
        {
            "points": points,
            "areas": sorted(areas.values(), key=lambda entry: entry["code"]),
            "unmapped": unmapped,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def locations(request):
    """The villages a household can file a case under, grouped by district.

    Public geography, but still behind login like the rest of the API. Centre
    points stay out: the form needs names and codes, not coordinates.
    """
    villages = (
        LocationArea.objects.filter(
            level=LocationArea.Level.VILLAGE, active=True, parent__active=True
        )
        .select_related("parent")
        .order_by("parent__name", "name")
    )
    return Response(
        [
            {
                "code": village.code,
                "name": village.name,
                "district": village.parent.name,
                "district_code": village.parent.code,
            }
            for village in villages
        ]
    )


class CaseTaskBoardSerializer(CaseTaskSummarySerializer):
    case_id = serializers.IntegerField(source="case.id", read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    case_village = serializers.CharField(source="case.village", read_only=True)
    case_score_total = serializers.IntegerField(source="case.score_total", read_only=True)
    case_priority_band = serializers.CharField(source="case.priority_band", read_only=True)
    case_status = serializers.CharField(source="case.status", read_only=True)
    case_status_display = serializers.CharField(
        source="case.get_status_display", read_only=True
    )
    lead = serializers.SerializerMethodField()
    updates = serializers.SerializerMethodField()
    safety_acknowledgement = serializers.SerializerMethodField()

    class Meta(CaseTaskSummarySerializer.Meta):
        fields = CaseTaskSummarySerializer.Meta.fields + [
            "case_id",
            "case_reference",
            "case_village",
            "case_score_total",
            "case_priority_band",
            "case_status",
            "case_status_display",
            "lead",
            "updates",
            "safety_note",
            "safety_acknowledgement",
        ]

    def get_lead(self, obj):
        if obj.lead_user_id is None:
            return None
        return {"id": obj.lead_user_id, "full_name": obj.lead_user.full_name}

    def get_safety_acknowledgement(self, obj):
        if not obj.safety_note or not obj.lead_user_id or not obj.assigned_at:
            return None
        acknowledgements = [
            event for event in obj.events.all()
            if event.notification_copy_of_id is None
            and event.event_type == CaseEventLog.EventType.SAFETY_ACKNOWLEDGED
            and event.actor_user_id == obj.lead_user_id
            and event.created_at >= obj.assigned_at
        ]
        if not acknowledgements:
            return None
        latest = max(acknowledgements, key=lambda event: (event.created_at, event.pk))
        return {"by": latest.actor_user.full_name, "at": latest.created_at}

    def get_updates(self, obj):
        rows = [
            event
            for event in obj.events.all()
            if event.notification_copy_of_id is None
            and event.event_type == CaseEventLog.EventType.TASK_UPDATED
        ]
        rows.sort(key=lambda event: event.created_at)
        return [
            {
                "detail": event.detail,
                "actor": event.actor_user.full_name if event.actor_user else None,
                "created_at": event.created_at,
            }
            for event in rows[-5:]
        ]


class CaseTaskCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    task_type = serializers.ChoiceField(choices=CaseTask.TaskType.choices)
    lead_user_id = serializers.IntegerField(required=False, allow_null=True)
    safety_note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the task a title.")
        return value

    def validate_safety_note(self, value):
        return value.strip()


class CaseTaskUpdateSerializer(serializers.Serializer):
    lead_user_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=CaseTask.Status.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    safety_acknowledged = serializers.BooleanField(required=False)


def _lead_for_organisation(lead_id, organisation):
    if lead_id is None:
        return None
    return UserAccount.objects.filter(
        pk=lead_id,
        role=UserAccount.Role.NGO_VOLUNTEER,
        organization=organisation,
        is_active=True,
    ).first()


def _may_read_tasks(user, case):
    if user.role in {UserAccount.Role.DISASTER_OFFICER, UserAccount.Role.SYSTEM_ADMIN}:
        return True
    if user.role == UserAccount.Role.COMMUNITY_MEMBER:
        return case.submitted_by_user_id == user.id
    return (
        user.role == UserAccount.Role.NGO_VOLUNTEER
        and case.claimed_by_org_id == user.organization_id
    )


def _task_queryset():
    return CaseTask.objects.select_related("case", "lead_user").prefetch_related(
        "events__actor_user"
    )


@api_view(["GET"])
@permission_classes([IsNgoVolunteer])
def task_board(request):
    """The claiming organisation's tasks, active cases and assignable responders."""
    from datetime import timedelta
    from django.db.models import Q

    recent = timezone.now() - timedelta(days=7)
    tasks = (
        _task_queryset()
        .filter(case__claimed_by_org=request.user.organization)
        .filter(
            Q(
                case__status__in=[
                    CaseRecord.Status.CLAIMED,
                    CaseRecord.Status.IN_PROGRESS,
                    CaseRecord.Status.PENDING_CONFIRM,
                ]
            )
            | Q(status=CaseTask.Status.DONE, completed_at__gte=recent)
        )
        .order_by("case__reference", "id")
    )
    cases = CaseRecord.objects.filter(
        claimed_by_org=request.user.organization,
        status__in=[
            CaseRecord.Status.CLAIMED,
            CaseRecord.Status.IN_PROGRESS,
            CaseRecord.Status.PENDING_CONFIRM,
        ],
    )
    responders = UserAccount.objects.filter(
        role=UserAccount.Role.NGO_VOLUNTEER,
        organization=request.user.organization,
        is_active=True,
    ).order_by("full_name")
    return Response(
        {
            "tasks": CaseTaskBoardSerializer(tasks, many=True).data,
            "cases": CaseListSerializer(cases, many=True).data,
            "responders": [
                {"id": responder.id, "full_name": responder.full_name}
                for responder in responders
            ],
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def case_tasks(request, pk):
    case = CaseRecord.objects.select_related("claimed_by_org").filter(pk=pk).first()
    if case is None or not _may_read_tasks(request.user, case):
        return Response({"detail": "Not found."}, status=404)

    if request.method == "GET":
        tasks = _task_queryset().filter(case=case).order_by("id")
        # Residents can follow task status and the accountable lead, but NGO
        # progress notes remain operational records and may contain access or
        # safety details that are not appropriate for the household timeline.
        serializer_class = (
            CaseTaskSummarySerializer
            if request.user.role == UserAccount.Role.COMMUNITY_MEMBER
            else CaseTaskBoardSerializer
        )
        return Response(serializer_class(tasks, many=True).data)

    if (
        request.user.role != UserAccount.Role.NGO_VOLUNTEER
        or request.user.organization_id is None
        or case.claimed_by_org_id != request.user.organization_id
    ):
        return Response(
            {"detail": "Only the claiming organisation may create tasks."}, status=403
        )
    if case.status not in {CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS}:
        return Response(
            {"detail": "Tasks can only be added while a claimed case is active."},
            status=409,
        )

    serializer = CaseTaskCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    lead_id = serializer.validated_data.get("lead_user_id")
    lead = _lead_for_organisation(lead_id, request.user.organization)
    if lead_id is not None and lead is None:
        return Response(
            {"lead_user_id": ["Choose an active responder from your organisation."]},
            status=400,
        )

    with transaction.atomic():
        locked_case = CaseRecord.objects.select_for_update().get(pk=case.pk)
        if (
            locked_case.claimed_by_org_id != request.user.organization_id
            or locked_case.status
            not in {CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS}
        ):
            return Response(
                {"detail": "This case is no longer available for task changes."},
                status=409,
            )
        task = CaseTask.objects.create(
            case=locked_case,
            lead_user=lead,
            title=serializer.validated_data["title"],
            task_type=serializer.validated_data["task_type"],
            safety_note=serializer.validated_data.get("safety_note", ""),
            status=CaseTask.Status.ASSIGNED if lead else CaseTask.Status.OPEN,
            assigned_at=timezone.now() if lead else None,
        )
        event_type = (
            CaseEventLog.EventType.TASK_ASSIGNED
            if lead
            else CaseEventLog.EventType.TASK_UPDATED
        )
        detail = (
            f"{request.user.organization.name} assigned a responder to {task.title}."
            if lead
            else f"Task created: {task.title}."
        )
        CaseEventLog.objects.create(
            case=locked_case,
            task=task,
            actor_user=request.user,
            event_type=event_type,
            detail=detail,
            created_at=timezone.now(),
        )

    return Response(CaseTaskBoardSerializer(task).data, status=201)


TASK_TRANSITIONS = {
    CaseTask.Status.OPEN: {CaseTask.Status.ASSIGNED},
    CaseTask.Status.ASSIGNED: {CaseTask.Status.IN_PROGRESS},
    CaseTask.Status.IN_PROGRESS: {CaseTask.Status.DONE},
    # A resident may report incomplete work after every task was marked done.
    CaseTask.Status.DONE: {CaseTask.Status.IN_PROGRESS},
}


@api_view(["PATCH"])
@permission_classes([IsNgoVolunteer])
def update_task(request, pk):
    serializer = CaseTaskUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data:
        return Response({"detail": "Provide a lead, status or progress note."}, status=400)

    with transaction.atomic():
        task = (
            CaseTask.objects.select_for_update()
            # `lead_user` is nullable, and PostgreSQL cannot apply FOR UPDATE
            # to the nullable side of that outer join. The lead id is already
            # on the task row; load the related user lazily for the response.
            .select_related("case")
            .filter(pk=pk, case__claimed_by_org=request.user.organization)
            .first()
        )
        if task is None:
            return Response({"detail": "Not found."}, status=404)
        if task.case.status not in {CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS}:
            return Response(
                {"detail": "This task cannot change while the case awaits confirmation or is closed."},
                status=409,
            )

        lead_supplied = "lead_user_id" in serializer.validated_data
        status_supplied = "status" in serializer.validated_data
        if lead_supplied and status_supplied:
            return Response(
                {"detail": "Change the lead and the status in separate steps."}, status=400
            )
        old_lead_id = task.lead_user_id
        old_status = task.status
        if lead_supplied:
            lead_id = serializer.validated_data["lead_user_id"]
            lead = _lead_for_organisation(lead_id, request.user.organization)
            if lead_id is not None and lead is None:
                return Response(
                    {"lead_user_id": ["Choose an active responder from your organisation."]},
                    status=400,
                )
            if lead is None and task.status == CaseTask.Status.IN_PROGRESS:
                return Response(
                    {"lead_user_id": ["A task in progress must keep its accountable lead."]},
                    status=409,
                )
            if task.status == CaseTask.Status.DONE and lead_id != old_lead_id:
                return Response(
                    {"lead_user_id": ["Reopen the task before reassigning it."]},
                    status=409,
                )
            task.lead_user = lead

        lead_changed = old_lead_id != task.lead_user_id
        target_status = serializer.validated_data.get("status", task.status)
        if lead_changed:
            if task.status == CaseTask.Status.OPEN:
                target_status = CaseTask.Status.ASSIGNED
            elif task.status == CaseTask.Status.ASSIGNED and task.lead_user_id is None:
                target_status = CaseTask.Status.OPEN
            elif task.status == CaseTask.Status.IN_PROGRESS:
                target_status = CaseTask.Status.ASSIGNED

        if target_status != task.status:
            if not lead_changed and target_status not in TASK_TRANSITIONS.get(task.status, set()):
                return Response(
                    {"status": [f"Cannot move a task from {task.status} to {target_status}."]},
                    status=409,
                )
        if target_status != CaseTask.Status.OPEN and task.lead_user_id is None:
            return Response(
                {"lead_user_id": ["Assign an accountable responder before moving this task."]},
                status=400,
            )

        status_changed = target_status != task.status
        starting = task.status == CaseTask.Status.ASSIGNED and target_status == CaseTask.Status.IN_PROGRESS
        acknowledgement_supplied = "safety_acknowledged" in serializer.validated_data
        if acknowledgement_supplied and (not starting or not task.safety_note):
            return Response(
                {"safety_acknowledged": ["Acknowledge a safety note only when starting its task."]},
                status=400,
            )
        if starting and task.lead_user_id != request.user.id:
            return Response(
                {"detail": "Only the task's accountable lead can start it. Reassign the task first if someone else will do the work."},
                status=403,
            )
        if starting and task.safety_note and serializer.validated_data.get("safety_acknowledged") is not True:
            return Response(
                {"safety_acknowledged": ["Read and acknowledge the safety note before starting."]},
                status=400,
            )
        note = serializer.validated_data.get("note", "").strip()
        if not lead_changed and not status_changed and not note:
            return Response({"detail": "Nothing changed."}, status=400)

        task.status = target_status
        if task.lead_user_id and (task.assigned_at is None or lead_changed):
            task.assigned_at = timezone.now()
        if target_status == CaseTask.Status.OPEN:
            task.assigned_at = None
        if target_status == CaseTask.Status.DONE:
            task.completed_at = timezone.now()
        elif status_changed:
            task.completed_at = None
        task.save(
            update_fields=["lead_user", "status", "assigned_at", "completed_at"]
        )

        if starting and task.safety_note:
            CaseEventLog.objects.create(
                case=task.case,
                task=task,
                actor_user=request.user,
                event_type=CaseEventLog.EventType.SAFETY_ACKNOWLEDGED,
                detail=(
                    f'The task lead acknowledged the safety note shown before starting "{task.title}". '
                    f'This confirms the warning was presented, not that the site is safe. '
                    f'Note: {task.safety_note}'
                ),
                created_at=timezone.now(),
            )

        if target_status == CaseTask.Status.IN_PROGRESS and task.case.status == CaseRecord.Status.CLAIMED:
            task.case.status = CaseRecord.Status.IN_PROGRESS
            task.case.save(update_fields=["status"])

        event_type = (
            CaseEventLog.EventType.TASK_ASSIGNED
            if lead_changed and task.lead_user_id
            else CaseEventLog.EventType.TASK_UPDATED
        )
        if event_type == CaseEventLog.EventType.TASK_ASSIGNED:
            # Only a started task is reset; a first assignment is not a handover.
            if old_status == CaseTask.Status.IN_PROGRESS:
                detail = (
                    f'{request.user.organization.name} reassigned "{task.title}"; '
                    'it returns to Assigned until the new lead starts it.'
                )
            else:
                detail = f"{request.user.organization.name} assigned a responder to {task.title}."
        elif note:
            detail = note
        else:
            detail = f"{task.title} moved to {task.get_status_display().lower()}."
        CaseEventLog.objects.create(
            case=task.case,
            task=task,
            actor_user=request.user,
            event_type=event_type,
            detail=detail,
            created_at=timezone.now(),
        )

    return Response(CaseTaskBoardSerializer(task).data)


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def complete_case(request, pk):
    with transaction.atomic():
        case = (
            CaseRecord.objects.select_for_update()
            .filter(pk=pk, claimed_by_org=request.user.organization)
            .first()
        )
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        if case.status not in {CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS}:
            return Response({"detail": "This case is not ready for completion."}, status=409)
        tasks = case.tasks.all()
        if not tasks.exists():
            return Response(
                {"detail": "Create and complete at least one task first."}, status=409
            )
        if tasks.exclude(status=CaseTask.Status.DONE).exists():
            return Response(
                {"detail": "Every task must be done before requesting confirmation."},
                status=409,
            )

        case.status = CaseRecord.Status.PENDING_CONFIRM
        case.save(update_fields=["status"])
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.COMPLETION_REQUESTED,
            detail=f"{request.user.organization.name} marked the recovery work complete. Please confirm the result.",
            created_at=timezone.now(),
        )

    from .notifications import notify

    notify(case, CaseEventLog.EventType.COMPLETION_REQUESTED, request.user)
    return Response(CaseDetailSerializer(case, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsCommunityMember])
def confirm_case(request, pk):
    decision = request.data.get("decision")
    if decision not in {"confirm", "incomplete"}:
        return Response(
            {"decision": ["Choose confirm or incomplete."]}, status=400
        )
    note = (request.data.get("note") or "").strip()
    if decision == "incomplete" and not note:
        return Response(
            {"note": ["Explain what still needs attention."]}, status=400
        )

    with transaction.atomic():
        case = (
            CaseRecord.objects.select_for_update()
            .filter(pk=pk, submitted_by_user=request.user)
            .first()
        )
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        if case.status != CaseRecord.Status.PENDING_CONFIRM:
            return Response(
                {"detail": "This case is not waiting for resident confirmation."},
                status=409,
            )

        if decision == "confirm":
            case.status = CaseRecord.Status.CLOSED
            case.closed_at = timezone.now()
            event_type = CaseEventLog.EventType.CLOSED
            detail = "The resident confirmed that the recovery work is complete."
            update_fields = ["status", "closed_at"]
        else:
            case.status = CaseRecord.Status.IN_PROGRESS
            case.closed_at = None
            event_type = CaseEventLog.EventType.REOPENED
            detail = f"The resident reported incomplete work: {note}"
            update_fields = ["status", "closed_at"]
        case.save(update_fields=update_fields)
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=event_type,
            detail=detail,
            created_at=timezone.now(),
        )

    from .notifications import notify

    notify(case, event_type, request.user, detail)
    return Response(CaseDetailSerializer(case, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def release_case(request, pk):
    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response({"reason": ["Give a reason for releasing the case."]}, status=400)

    with transaction.atomic():
        case = (
            CaseRecord.objects.select_for_update()
            .filter(pk=pk, claimed_by_org=request.user.organization)
            .first()
        )
        if case is None:
            return Response({"detail": "Not found."}, status=404)
        if case.status != CaseRecord.Status.CLAIMED:
            return Response(
                {"detail": "Only a claimed case whose work has not started can be released."},
                status=409,
            )
        if case.tasks.exists():
            return Response(
                {"detail": "A case with tasks needs an explicit operational handover; it cannot be returned to the public queue."},
                status=409,
            )

        organisation_name = request.user.organization.name
        case.claimed_by_org = None
        case.status = CaseRecord.Status.VERIFIED
        case.save(update_fields=["claimed_by_org", "status"])
        detail = f"{organisation_name} released the case back to the verified queue: {reason}"
        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.RELEASED,
            detail=detail,
            created_at=timezone.now(),
        )

    from .notifications import notify

    notify(case, CaseEventLog.EventType.RELEASED, request.user, detail)
    return Response(CaseSummaryDetailSerializer(case, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


class AlreadyClaimed(APIException):
    status_code = 409
    default_detail = "This case has already been claimed by another organisation."


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def claim_case(request, pk):
    """Claim a verified case for the caller's organisation.

    Two NGOs can press this in the same millisecond. Unlocked, both read
    claimed_by_org IS NULL, both believe the case is free, and the later write
    silently wins — a lost update. The row lock makes the second caller wait,
    then see the truth.

    ------------------------------------------------------------------
    YOURS TO WRITE. Run `python manage.py test cases` after each step.
    `IsNgoVolunteer` has already checked the role, so request.user is an
    NGO responder with an organisation.

    1. Open a transaction:            with transaction.atomic():
    2. Fetch the case WITH A ROW LOCK:
           CaseRecord.objects.select_for_update().filter(pk=pk).first()
    3. If it is None                  -> return 404 {"detail": "Not found."}
    4. If case.claimed_by_org_id is not None:
         - if it equals request.user.organization_id, this is a retry of a
           claim that already succeeded: return the serialised case, 200,
           writing NOTHING (no second audit row)
         - otherwise                  -> raise AlreadyClaimed(...)
    5. If case.status is not VERIFIED -> return 409, only verified cases
    6. Set claimed_by_org and status, then
           case.save(update_fields=["claimed_by_org", "status"])
    7. Write the audit row:
           CaseEventLog.objects.create(case=..., actor_user=request.user,
               event_type=CaseEventLog.EventType.CLAIMED, detail="...",
               created_at=timezone.now())
    8. Outside the `with`, return:
           Response(CaseDetailSerializer(case, context={"request": request}).data)

    The order of 4 and 5 is deliberate — think about which check should win
    if a case is somehow both claimed and not yet verified.
    ------------------------------------------------------------------
    """
    with transaction.atomic():
        case =  CaseRecord.objects.select_for_update().filter(pk=pk).first()

        if case is None:

            return Response({"detail":"Not Found"},status =404)

        if case.claimed_by_org is not None:

            if case.claimed_by_org_id == request.user.organization_id:
                return Response(CaseDetailSerializer(case, context={"request": request}).data)
            raise AlreadyClaimed(f'Already claimed by {case.claimed_by_org.name}.')

        if case.status != CaseRecord.Status.VERIFIED:
            return Response({"detail": "Only verified cases can be claimed."}, status=409)

        case.claimed_by_org = request.user.organization
        case.status =  CaseRecord.Status.CLAIMED
        case.save(update_fields=['claimed_by_org','status'])

        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=CaseEventLog.EventType.CLAIMED,
            detail=f"Case claimed by {request.user.organization.name}.",
            created_at=timezone.now(),
        )

    from .notifications import notify

    notify(
        case,
        CaseEventLog.EventType.CLAIMED,
        request.user,
        f"{request.user.organization.name} will be in touch about your case.",
    )

    return Response(CaseDetailSerializer(case, context={"request": request}).data)


    


DECISIONS = {
    "verified": (CaseRecord.Status.VERIFIED, CaseEventLog.EventType.VERIFIED),
    "needs_info": (CaseRecord.Status.NEEDS_INFO, CaseEventLog.EventType.NEEDS_INFO),
    "rejected": (CaseRecord.Status.REJECTED, CaseEventLog.EventType.REJECTED),
}


@api_view(["POST"])
@permission_classes([IsDisasterOfficer])
def verify_case(request, pk):
    """Verify, request more information, or reject.

    Attributed to the officer, so no status change in the audit trail is
    anonymous.
    """
    decision = request.data.get("decision")
    if decision not in DECISIONS:
        return Response(
            {"detail": f"decision must be one of {', '.join(DECISIONS)}."}, status=400
        )

    note = (request.data.get("note") or "").strip()
    if decision in {"needs_info", "rejected"} and not note:
        return Response(
            {"detail": "A note is required when asking for more information or rejecting."},
            status=400,
        )

    with transaction.atomic():
        case = CaseRecord.objects.select_for_update().filter(pk=pk).first()
        if case is None:
            return Response({"detail": "Not found."}, status=404)

        if case.claimed_by_org_id is not None:
            return Response(
                {"detail": "A claimed case cannot be re-verified."}, status=409
            )

        # Duplicate review comes before verification (report §3.7.8): a
        # possible duplicate is resolved by an officer before it is scored and
        # released to NGOs. Asking for information or rejecting stays open.
        from .duplicate_services import duplicate_verification_block

        block = duplicate_verification_block(case)
        if block and (decision == "verified" or block[0] == "case_linked_duplicate"):
            code, detail = block
            return Response({"code": code, "detail": detail}, status=409)

        new_status, event_type = DECISIONS[decision]
        case.status = new_status
        case.verified_by_user = request.user
        case.save(update_fields=["status", "verified_by_user"])

        CaseEventLog.objects.create(
            case=case,
            actor_user=request.user,
            event_type=event_type,
            detail=note or f"Marked {case.get_status_display().lower()} by {request.user.full_name}.",
            created_at=timezone.now(),
        )

        # Scoring happens at verification, not submission: screen 17 has an
        # officer check a request "before it is scored and released to the NGO
        # queue". Inside the transaction, so a scoring failure undoes the
        # verification rather than leaving a verified case with no score.
        if decision == "verified":
            # Imported here, not at module level: services imports the models
            # this module also imports, and at import time that loop cannot
            # resolve. Inside the function it runs after both are loaded.
            from .services import score_case_record

            score_case_record(case, request.user)

    from .notifications import notify

    case.refresh_from_db()  # so a verification notification carries the score
    notify(case, event_type, request.user, note)

    return Response(CaseDetailSerializer(case, context={"request": request}).data)


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    case_id = serializers.IntegerField(source="case.id", read_only=True)
    event_type = serializers.CharField(read_only=True)
    event_display = serializers.CharField(source="get_event_type_display", read_only=True)
    detail = serializers.CharField(read_only=True)
    read_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notifications(request):
    """This user's notifications — a filtered query over the event log (ADR-004).

    No notification table exists: these are the same rows that serve the case
    timeline and the audit trail, selected by recipient.
    """
    rows = (
        CaseEventLog.objects.filter(recipient_user=request.user)
        .select_related("case")
        .order_by("-created_at")[:50]
    )
    return Response(
        {
            "unread": CaseEventLog.objects.filter(
                recipient_user=request.user, read_at__isnull=True
            ).count(),
            "results": NotificationSerializer(rows, many=True).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, pk):
    """Mark one as read.

    This is the one write the event log allows. ADR-004 keeps read_at and
    delivery_status as notification-delivery state; the audit fields — actor,
    event type, detail, timestamp — are never touched.
    """
    row = CaseEventLog.objects.filter(pk=pk, recipient_user=request.user).first()
    if row is None:
        return Response({"detail": "Not found."}, status=404)

    if row.read_at is None:
        row.read_at = timezone.now()
        row.save(update_fields=["read_at"])

    return Response(NotificationSerializer(row).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    updated = CaseEventLog.objects.filter(
        recipient_user=request.user, read_at__isnull=True
    ).update(read_at=timezone.now())
    return Response({"marked_read": updated})


@api_view(["GET"])
@permission_classes([IsCoordinator])
def rubric(request):
    """The published rubric, read-only — screen 18, "how scoring works".

    Criteria, weights and thresholds belong to the published version. Point
    bands remain explicit code rules; each raw band is scaled by its criterion
    weight exactly as the scoring engine does.
    """
    from scoring.engine import (
        ACCESS_POINTS,
        NEEDS_POINTS_EACH,
        PARTIAL_DEPTH_POINTS,
        URGENCY_POINTS,
        VULNERABILITY_POINTS,
        WAITING_POINTS_PER_DAY,
    )
    from scoring.models import PriorityRubricVersion

    version = (
        PriorityRubricVersion.objects.filter(
            status=PriorityRubricVersion.Status.PUBLISHED
        )
        .order_by("-published_at")
        .first()
    )
    if version is None:
        return Response({"detail": "No rubric has been published."}, status=404)

    # Raw value-function bands. Additive criteria combine these severity values
    # before the engine caps and scales the result to the versioned weight.
    raw_bands = {
        "safety": [(k, v) for k, v in URGENCY_POINTS.items()],
        "damage": [("cosmetic", 4)]
        + [(f"partially unliveable, {k}", v) for k, v in PARTIAL_DEPTH_POINTS.items()],
        "vulnerability": [(k, v) for k, v in VULNERABILITY_POINTS.items()],
        "needs": [("each shortage category", NEEDS_POINTS_EACH)],
        "access": [(k, v) for k, v in ACCESS_POINTS.items()],
        "waiting": [("each day waiting", WAITING_POINTS_PER_DAY)],
    }

    criteria = []
    for stored in version.criteria.all():
        bands = list(raw_bands.get(stored.key, []))
        if stored.key == "damage":
            bands.append(("fully unliveable", stored.max_points))
        criteria.append(
            {
                "key": stored.key,
                "name": stored.name,
                "weight": stored.weight,
                "max_points": stored.max_points,
                "rule_text": stored.rule_text,
                "bands": [
                    {"when": label, "points": raw}
                    for label, raw in bands
                ],
            }
        )

    return Response(
        {
            "label": version.label,
            "published_at": version.published_at,
            "thresholds": {
                "high": version.high_threshold,
                "medium": version.medium_threshold,
            },
            "criteria": criteria,
        }
    )


# ---------------------------------------------------------------------------
# Duplicate review — screen 12 (report §3.7.8). District officers only: the
# comparison shows two households' details side by side, so none of it goes
# through the shared case serializers.
# ---------------------------------------------------------------------------


def _error(code, detail, status):
    return Response({"code": code, "detail": detail}, status=status)


class DuplicateCaseRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    reference = serializers.CharField()


class DuplicateSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    similarity_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    classification = serializers.SerializerMethodField()
    case_a = DuplicateCaseRefSerializer()
    case_b = DuplicateCaseRefSerializer()

    def get_classification(self, obj):
        # Derived from the stored score with the engine's frozen thresholds,
        # exactly as it was classified when flagged.
        from .duplicates import classify_score

        return classify_score(float(obj.similarity_score))


class DuplicateCaseSerializer(serializers.Serializer):
    """One side of the comparison. Officers are district staff, who may see
    exact locations (B6), so coordinates are included when a pin exists."""

    id = serializers.IntegerField()
    reference = serializers.CharField()
    created_at = serializers.DateTimeField()
    status = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display")
    submitter_name = serializers.CharField(source="submitted_by_user.full_name")
    submitter_phone = serializers.CharField(source="submitted_by_user.phone")
    description = serializers.CharField()
    address = serializers.CharField()
    village = serializers.CharField(source="location_area.name", default=None)
    household_size = serializers.IntegerField()
    damage_category = serializers.CharField()
    damage_category_display = serializers.CharField(source="get_damage_category_display")
    needs_flags = serializers.ListField(child=serializers.CharField())
    photo_count = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()

    def get_photo_count(self, obj):
        return obj.photos.count()

    def get_latitude(self, obj):
        return str(obj.latitude) if obj.latitude is not None else None

    def get_longitude(self, obj):
        return str(obj.longitude) if obj.longitude is not None else None


class DuplicateDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["confirm", "dismiss"])


def _decided_by(match):
    return match.decided_by_user.full_name if match.decided_by_user_id else None


@api_view(["GET"])
@permission_classes([IsDisasterOfficer])
def duplicate_list(request):
    """Flags for review, highest evidence first; ?status= defaults to open."""
    from rest_framework.pagination import PageNumberPagination

    from .models import DuplicateCaseMatch

    status_filter = request.query_params.get("status", DuplicateCaseMatch.Status.OPEN)
    if status_filter not in DuplicateCaseMatch.Status.values:
        return _error(
            "invalid_status",
            f"status must be one of {', '.join(DuplicateCaseMatch.Status.values)}.",
            400,
        )
    queryset = (
        DuplicateCaseMatch.objects.filter(status=status_filter)
        .select_related("case_a", "case_b")
        .order_by("-similarity_score", "pk")
    )
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(DuplicateSummarySerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([IsDisasterOfficer])
def duplicate_detail(request, pk):
    """Side-by-side comparison, stored evidence and current evidence kept apart."""
    import logging

    from .duplicate_services import (
        confirm_block_reason,
        current_duplicate_comparison,
        duplicate_verification_block,
    )
    from .models import DuplicateCaseMatch

    match = (
        DuplicateCaseMatch.objects.select_related(
            "case_a__submitted_by_user", "case_a__location_area",
            "case_b__submitted_by_user", "case_b__location_area",
            "decided_by_user",
        )
        .filter(pk=pk)
        .first()
    )
    if match is None:
        return _error("not_found", "Not found.", 404)

    try:
        comparison = current_duplicate_comparison(match)
    except Exception as exc:  # noqa: BLE001 — never leak household text in an error
        logging.getLogger(__name__).warning(
            "Current duplicate comparison failed for match id=%s (%s).", match.pk, type(exc).__name__
        )
        return _error("comparison_unavailable", "The comparison could not be computed right now.", 503)

    block = confirm_block_reason(match)
    data = DuplicateSummarySerializer(match).data
    data.update(
        {
            "case_a": DuplicateCaseSerializer(match.case_a).data,
            "case_b": DuplicateCaseSerializer(match.case_b).data,
            "current_comparison": comparison,
            "can_confirm": block is None,
            "confirm_block_reason": block[0] if block else None,
            "verification_blocked": duplicate_verification_block(match.case_b) is not None,
            "decided_by": _decided_by(match),
            "decided_at": match.decided_at,
        }
    )
    return Response(data)


@api_view(["POST"])
@permission_classes([IsDisasterOfficer])
def decide_duplicate(request, pk):
    """Confirm (close the newer case as a duplicate) or dismiss a flag."""
    from .duplicate_services import DuplicateConflict, decide_duplicate_match

    serializer = DuplicateDecisionSerializer(data=request.data)
    if not serializer.is_valid():
        return _error("invalid_decision", "decision must be confirm or dismiss.", 400)
    decision = serializer.validated_data["decision"]

    try:
        outcome = decide_duplicate_match(pk, request.user, decision)
    except DuplicateConflict as conflict:
        return _error(conflict.code, conflict.detail, 409)
    if outcome is None:
        return _error("not_found", "Not found.", 404)

    match = outcome.match
    newer = match.case_b
    if outcome.changed and decision == "confirm":
        from .notifications import notify

        # After the commit, once. actor=None so the household is told even in
        # the odd case where the deciding officer filed the request themselves.
        from .duplicate_services import DUPLICATE_CLOSED_DETAIL

        notify(
            newer, CaseEventLog.EventType.DUPLICATE_CLOSED, None,
            DUPLICATE_CLOSED_DETAIL.format(reference=newer.reference),
        )

    return Response(
        {
            "id": match.pk,
            "status": match.status,
            "changed": outcome.changed,
            "decided_by": _decided_by(match),
            "decided_at": match.decided_at,
            "newer_case": {"id": newer.pk, "reference": newer.reference, "status": newer.status},
            "superseded_match_ids": outcome.superseded_ids,
        }
    )
