"""Case endpoints.

Querysets are narrowed by role before serialising, so guessing an id gets a
resident nothing.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.decorators import api_view, permission_classes
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import (
    IsDisasterOfficer,
    IsNgoVolunteer,
    may_see_exact_location,
    visible_cases,
)

from .models import CaseEventLog, CaseRecord


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


class CaseDetailSerializer(CaseListSerializer):
    score_components = ScoreComponentSerializer(many=True, read_only=True)
    location = serializers.SerializerMethodField()

    class Meta(CaseListSerializer.Meta):
        fields = CaseListSerializer.Meta.fields + [
            "description",
            "urgency",
            "flood_depth",
            "liveability",
            "access_level",
            "needs_flags",
            "vulnerability_flags",
            "score_components",
            "location",
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


class CaseListView(ListAPIView):
    serializer_class = CaseListSerializer
    permission_classes = [IsAuthenticated]

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def case_detail(request, pk):
    queryset = visible_cases(
        request.user,
        CaseRecord.objects.select_related("claimed_by_org").prefetch_related(
            "score_components__criterion"
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

    return Response(CaseDetailSerializer(case, context={"request": request}).data)
