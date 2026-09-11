"""Case endpoints.

Querysets are narrowed by role before serialising, so guessing an id gets a
resident nothing.
"""

import json

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsCoordinator,
    IsDisasterOfficer,
    IsNgoVolunteer,
    may_see_exact_location,
    visible_cases,
)

from .models import CaseEventLog, CasePhoto, CaseRecord


class ScoreComponentSerializer(serializers.Serializer):
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
            "created_at",
        ]

    def get_days_waiting(self, obj):
        from django.utils import timezone

        return (timezone.now() - obj.created_at).days


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
        CaseEventLog.EventType.TASK_ASSIGNED,
        CaseEventLog.EventType.CLOSED,
        CaseEventLog.EventType.REOPENED,
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


class CaseDetailSerializer(CaseListSerializer):
    score_components = ScoreComponentSerializer(many=True, read_only=True)
    photos = CasePhotoSerializer(many=True, read_only=True)
    events = CaseEventSerializer(many=True, read_only=True)
    location = serializers.SerializerMethodField()
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
        ]

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

    class Meta:
        model = CaseRecord
        fields = [
            "village",
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
        queryset = CaseRecord.objects.select_related(
            "claimed_by_org", "submitted_by_user"
        ).all()
        queryset = visible_cases(self.request.user, queryset)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("q")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(village__icontains=search)
                | Q(description__icontains=search)
            )
        return queryset

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

        return Response(CaseListSerializer(case).data, status=201)



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def case_detail(request, pk):
    queryset = visible_cases(
        request.user,
        CaseRecord.objects.select_related("claimed_by_org").prefetch_related(
            "score_components__criterion",
            "photos",
            # Oldest first: a timeline reads downwards.
            Prefetch(
                "events",
                queryset=CaseEventLog.objects.filter(
                    notification_copy_of__isnull=True
                )
                .select_related("actor_user__organization")
                .order_by("created_at"),
            ),
        ),
    )
    case = queryset.filter(pk=pk).first()
    if case is None:
        # 404 rather than 403: do not confirm that a hidden case exists.
        return Response({"detail": "Not found."}, status=404)
    return Response(CaseDetailSerializer(case, context={"request": request}).data)


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
    NGO volunteer with an organisation.

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
