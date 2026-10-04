"""Case submission, role-scoped reading, queue ordering and locations."""

from django.db import transaction
from django.db.models import Case, F, IntegerField, Prefetch, Q, Value, When
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import (
    IsCoordinator,
    may_see_exact_location,
    holds_active_job,
    may_see_private_case_details,
    visible_cases,
)
from accounts.models import UserAccount
from ..models import CaseEventLog, CaseJob, CasePhoto, CaseRecord, LocationArea
from ..images import UnreadableImage, clean_photo
from ..upload_validation import has_expected_signature
from ..serializers.cases import (
    CaseDetailSerializer,
    CaseListSerializer,
    CaseSummaryDetailSerializer,
    REPORTED_URGENT,
)
from ..serializers.submission import (
    ALLOWED_PHOTO_TYPES,
    CaseCreateSerializer,
    MAX_PHOTOS,
    MAX_PHOTO_BYTES,
)


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


def _filter_priority_class(queryset, value):
    """Filter by classes-1.0 priority class; blank means all, unclassified included."""
    if value in ("", None):
        return queryset
    if value not in ("1", "2", "3"):
        raise ValidationError({"priority": ["Choose 1, 2 or 3."]})
    return queryset.filter(priority_class=int(value))


def _queue_queryset(request):
    """The queue as this user may see it, with the list's filters applied.

    Shared by the list, map, and stats so they agree about which
    cases exist for a user.
    """
    queryset = CaseRecord.objects.select_related("submitted_by_user").prefetch_related(
        "jobs__claimed_by_org"
    )
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
                    jobs__claimed_by_org=request.user.organization,
                    jobs__status__in=CaseJob.ACTIVE,
                    description__icontains=search,
                )
        else:
            search_query |= Q(description__icontains=search)
        queryset = queryset.filter(search_query)
    help_type = request.query_params.get("help", "")
    if help_type:
        # Cases that still need this type of help: an NGO filters to the work
        # it can do, and the class order below still applies within it.
        if help_type not in CaseRecord.DamageCategory.values:
            raise ValidationError({"help": ["Choose a listed type of help."]})
        queryset = queryset.filter(
            pk__in=CaseJob.objects.filter(help_type=help_type, status=CaseJob.Status.OPEN)
            .values("case_id")
        )
    queryset = _filter_priority_class(queryset, request.query_params.get("priority", ""))
    # Class first, then first come, first served; unverified cases last, with
    # self-reported health-critical requests at the front of that tail.
    return queryset.distinct().annotate(
        unverified_urgent_first=Case(
            When(priority_class__isnull=True, urgency__in=REPORTED_URGENT, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by(
        F("priority_class").asc(nulls_last=True), "unverified_urgent_first", "created_at", "pk"
    )


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
        from ..duplicate_services import latest_check_event_subquery, open_match_annotation

        # One subquery instead of a check-state query per row.
        queryset = _queue_queryset(self.request).annotate(
            latest_duplicate_check=latest_check_event_subquery()
        )
        if self.request.user.role == UserAccount.Role.DISASTER_OFFICER:
            queryset = queryset.annotate(has_open_duplicate=open_match_annotation())
        return queryset

    def create(self, request, *args, **kwargs):
        """Create a case from a household's submission (FR3).

        Classification deliberately does not happen here. Screen 17 is
        explicit that a request is checked by an officer before it is
        prioritised and released to the NGO queue, so a new case carries
        priority_class=None until it is verified.
        """
        if request.user.role != UserAccount.Role.COMMUNITY_MEMBER:
            return Response({"detail": "Only residents may submit a request."}, status=403)
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
            if upload.content_type not in ALLOWED_PHOTO_TYPES or not has_expected_signature(upload):
                return Response(
                    {"photos": [f"{upload.name} must be a JPEG, PNG or WebP image."]},
                    status=400,
                )

        try:
            cleaned_photos = [clean_photo(upload) for upload in photos]
        except UnreadableImage as exc:
            return Response({"photos": [str(exc)]}, status=400)

        also_need = serializer.validated_data.pop("also_need", [])
        # Main type first, then the extras in the form's order, each once.
        order = list(CaseRecord.DamageCategory.values)
        help_types = list(dict.fromkeys(
            [serializer.validated_data["damage_category"], *sorted(also_need, key=order.index)]
        ))

        with transaction.atomic():
            case = serializer.save(
                submitted_by_user=request.user,
                reference=_next_reference(),
                status=CaseRecord.Status.SUBMITTED,
                created_at=timezone.now(),
            )
            for upload in cleaned_photos:
                CasePhoto.objects.create(
                    case=case, file_path=upload, stage=CasePhoto.Stage.RESIDENT,
                    uploaded_by_user=request.user,
                )
            for help_type in help_types:
                CaseJob.objects.create(case=case, help_type=help_type)

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
        from ..duplicate_services import run_detection_after_submission

        run_detection_after_submission(case)

        # Outside the transaction: sending mail is slow and can fail, and a
        # failed nudge must not roll back a submitted case.
        from ..notifications import notify

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
        CaseRecord.objects.prefetch_related(
            "jobs__claimed_by_org",
            "photos__task",
            "photos__uploaded_by_user__organization",
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
    queryset = _queue_queryset(request)
    return Response(
        {
            "total": queryset.count(),
            "health_critical": queryset.filter(priority_class=1).count(),
            # Cases with at least one type of help no organisation has taken.
            "unclaimed": queryset.filter(
                pk__in=CaseJob.objects.filter(status=CaseJob.Status.OPEN).values("case_id")
            ).count(),
            "in_progress": queryset.filter(status="in_progress").count(),
        }
    )


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
    cases = _queue_queryset(request).select_related("location_area")
    if request.user.role == UserAccount.Role.DISASTER_OFFICER:
        from ..duplicate_services import open_match_annotation

        cases = cases.annotate(has_open_duplicate=open_match_annotation())
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
            point = {
                    "id": case.id,
                    "reference": case.reference,
                    "village": case.village,
                    "latitude": str(latitude),
                    "longitude": str(longitude),
                    "precision": precision,
                    "status": case.status,
                    "status_display": case.get_status_display(),
                    "priority_class": case.priority_class,
                    "priority_label": (
                        case.get_priority_class_display() if case.priority_class else None
                    ),
                    "claimed_by": ", ".join(
                        sorted({job.claimed_by_org.name for job in case.jobs.all() if job.claimed_by_org_id})
                    ) or None,
                    "claimed_by_you": holds_active_job(request.user, case),
                }
            if request.user.role == UserAccount.Role.DISASTER_OFFICER:
                point["has_open_duplicate"] = case.has_open_duplicate
            points.append(point)
        elif area_placed:
            entry = areas.setdefault(
                area.code,
                {
                    "code": area.code,
                    "name": area.name,
                    "latitude": str(area.latitude),
                    "longitude": str(area.longitude),
                    "case_count": 0,
                    # 1 is the most urgent, so "highest" is the smallest number.
                    "highest_class": None,
                },
            )
            entry["case_count"] += 1
            if case.priority_class and (
                entry["highest_class"] is None or case.priority_class < entry["highest_class"]
            ):
                entry["highest_class"] = case.priority_class
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

    Public geography, but still behind login like the rest of the API. Each
    village's centre point is included so the submit form can centre its pin
    map; it is the published place, never a household's location.
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
                "latitude": str(village.latitude),
                "longitude": str(village.longitude),
            }
            for village in villages
        ]
    )
