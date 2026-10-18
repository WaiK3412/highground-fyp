"""Donations to supply appeals (ADR-025): residents record them, the owning NGO confirms.

Two steps only: a donation waits for drop-off until the NGO marks it received,
or until the donor cancels it. Either way the change is final.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsCommunityMember, IsNgoVolunteer
from ..models import CaseEventLog, Donation, SupplyAppeal
from ..notifications import notify_donation
from ..serializers.donations import DonationSerializer, OrgDonationSerializer

NO_LONGER_OPEN = "This appeal is no longer accepting donations."
ALREADY_SETTLED = "This donation has already been received or cancelled."


def _record(donation, actor, event_type):
    """Write the audit row for this action and notify the people it concerns."""
    audit_row = CaseEventLog.objects.create(
        donation=donation,
        actor_user=actor,
        event_type=event_type,
        detail=donation.items,
        created_at=timezone.now(),
    )
    notify_donation(audit_row)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def appeal_donations(request, pk):
    """POST: a resident records a donation. GET: the owning NGO lists them."""
    if request.method == "POST":
        return _donate(request, pk)
    return _list_for_organisation(request, pk)


def _donate(request, pk):
    if not IsCommunityMember().has_permission(request, None):
        return Response({"detail": "Only residents can record a donation."}, status=403)
    serializer = DonationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        # Locked so the NGO cannot close the appeal between the check and the save.
        appeal = SupplyAppeal.objects.select_for_update().filter(pk=pk).first()
        if appeal is None:
            return Response({"detail": "Not found."}, status=404)
        if not appeal.is_open_now():
            return Response({"detail": NO_LONGER_OPEN}, status=400)
        donation = serializer.save(appeal=appeal, donor_user=request.user)
        _record(donation, request.user, CaseEventLog.EventType.DONATION_RECORDED)

    return Response(DonationSerializer(donation).data, status=201)


def _list_for_organisation(request, pk):
    if not IsNgoVolunteer().has_permission(request, None):
        return Response({"detail": IsNgoVolunteer.message}, status=403)
    appeal = SupplyAppeal.objects.filter(pk=pk, organization=request.user.organization).first()
    if appeal is None:
        # 404, not 403: another organisation's donors are not this caller's business.
        return Response({"detail": "Not found."}, status=404)
    donations = appeal.donations.select_related(
        "appeal__organization", "appeal__drop_off_point", "donor_user", "received_by_user"
    )
    return Response({"results": OrgDonationSerializer(donations, many=True).data})


@api_view(["GET"])
@permission_classes([IsCommunityMember])
def my_donations(request):
    donations = Donation.objects.filter(donor_user=request.user).select_related(
        "appeal__organization", "appeal__drop_off_point", "received_by_user"
    )
    return Response({"results": DonationSerializer(donations, many=True).data})


@api_view(["POST"])
@permission_classes([IsCommunityMember])
def cancel_donation(request, pk):
    return _settle(
        request,
        Donation.objects.filter(donor_user=request.user),
        pk,
        Donation.Status.CANCELLED,
        CaseEventLog.EventType.DONATION_CANCELLED,
        DonationSerializer,
        cancelled_at=timezone.now(),
    )


@api_view(["POST"])
@permission_classes([IsNgoVolunteer])
def receive_donation(request, pk):
    # Still allowed after the appeal closes: the items may arrive on the last day.
    return _settle(
        request,
        Donation.objects.filter(appeal__organization=request.user.organization),
        pk,
        Donation.Status.RECEIVED,
        CaseEventLog.EventType.DONATION_RECEIVED,
        OrgDonationSerializer,
        received_at=timezone.now(),
        received_by_user=request.user,
    )


def _settle(request, allowed, pk, status, event_type, serializer_class, **changes):
    """Move a waiting donation to its final status, once.

    `allowed` is what this caller may act on; anything else is a 404. The row is
    locked, so a cancel and a receipt arriving together cannot both succeed.
    """
    with transaction.atomic():
        donation = allowed.select_for_update(of=("self",)).filter(pk=pk).first()
        if donation is None:
            return Response({"detail": "Not found."}, status=404)
        if donation.status != Donation.Status.WAITING:
            return Response({"detail": ALREADY_SETTLED}, status=409)
        donation.status = status
        for field, value in changes.items():
            setattr(donation, field, value)
        donation.save(update_fields=["status", *changes])
        _record(donation, request.user, event_type)

    return Response(serializer_class(donation).data)
