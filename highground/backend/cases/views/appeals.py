"""Supply appeals (ADR-021): NGO writes and signed-in reads."""

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from accounts.permissions import IsNgoVolunteer
from ..models import DropOffPoint, SupplyAppeal
from ..serializers.appeals import DropOffPointSerializer, PublicAppealSerializer, SupplyAppealSerializer


def _is_ngo_responder(request):
    return IsNgoVolunteer().has_permission(request, None)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def appeals(request):
    if request.method == "POST":
        if not _is_ngo_responder(request):
            return Response({"detail": IsNgoVolunteer.message}, status=403)
        serializer = SupplyAppealSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The organisation is the caller's, never a posted value.
        appeal = serializer.save(
            organization=request.user.organization, created_by_user=request.user
        )
        return Response(SupplyAppealSerializer(appeal).data, status=201)

    queryset = SupplyAppeal.objects.select_related("organization", "drop_off_point")
    if request.query_params.get("mine") == "1":
        if not _is_ngo_responder(request):
            return Response({"detail": IsNgoVolunteer.message}, status=403)
        # "open" sorts after "closed", so descending puts open appeals first.
        queryset = queryset.filter(organization=request.user.organization).order_by(
            "-status", "needed_until", "pk"
        )
    else:
        # An out-of-date appeal drops off on its own; nobody has to close it.
        queryset = queryset.open_now()
    return Response({"results": SupplyAppealSerializer(queryset, many=True).data})


@api_view(["PATCH"])
@permission_classes([IsNgoVolunteer])
@transaction.atomic
def appeal_detail(request, pk):
    # Serialize edits with closure so a stale edit cannot reopen a closed appeal.
    appeal = SupplyAppeal.objects.select_for_update().filter(
        pk=pk, organization=request.user.organization
    ).first()
    if appeal is None:
        # 404, not 403: another organisation's appeal is not this caller's business.
        return Response({"detail": "Not found."}, status=404)
    if appeal.status == SupplyAppeal.Status.CLOSED:
        return Response({"detail": "A closed appeal cannot be changed."}, status=409)

    if "status" in request.data:
        if request.data["status"] != SupplyAppeal.Status.CLOSED:
            return Response({"status": ["An appeal can only be closed."]}, status=400)
        appeal.status = SupplyAppeal.Status.CLOSED
        appeal.closed_at = timezone.now()
        appeal.save(update_fields=["status", "closed_at"])
        return Response(SupplyAppealSerializer(appeal).data)

    serializer = SupplyAppealSerializer(appeal, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


class PublicReadThrottle(AnonRateThrottle):
    scope = "public"


@api_view(["GET"])
@permission_classes([AllowAny])  # the landing page, for visitors not signed in (ADR-025)
@throttle_classes([PublicReadThrottle])
def public_appeals(request):
    """The few most urgent open appeals, with only what a visitor needs to help."""
    appeals = (
        SupplyAppeal.objects.open_now()
        .select_related("organization", "drop_off_point")
        .order_by("needed_until", "pk")[:6]
    )
    return Response({"results": PublicAppealSerializer(appeals, many=True).data})


@api_view(["GET"])
@permission_classes([IsNgoVolunteer])
def drop_off_points(request):
    points = DropOffPoint.objects.filter(active=True).order_by("name")
    return Response({"results": DropOffPointSerializer(points, many=True).data})
