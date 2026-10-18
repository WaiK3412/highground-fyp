"""Recipient-scoped notification reads and coordinator priority rules."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.models import UserAccount
from accounts.permissions import HasDistrictIfOfficer, IsCoordinator, officer_district_q
from ..models import CaseEventLog, CaseRecord
from ..serializers.notifications import NotificationSerializer


def _my_notifications(user):
    """This user's notification rows, as far as they may still see them.

    An officer sees only rows about cases in the district they act for now
    (ADR-024). Rows addressed to them while posted elsewhere stay in the audit
    log untouched; they just stop being listed, counted or markable here.
    """
    rows = CaseEventLog.objects.filter(recipient_user=user)
    if user.role == UserAccount.Role.DISASTER_OFFICER:
        # Rows about their own account (ADR-027) belong to no district.
        rows = rows.filter(officer_district_q(user, "case__") | Q(event_type__in=CaseEventLog.ACCOUNT_EVENTS))
    return rows


@api_view(["GET"])
@permission_classes([IsAuthenticated, HasDistrictIfOfficer])
def notifications(request):
    """This user's notifications — a filtered query over the event log (ADR-004).

    No notification table exists: these are the same rows that serve the case
    timeline and the audit trail, selected by recipient.
    """
    rows = _my_notifications(request.user).select_related("case", "donation__appeal").order_by("-created_at")[:50]
    return Response(
        {
            "unread": _my_notifications(request.user).filter(read_at__isnull=True).count(),
            "results": NotificationSerializer(rows, many=True, context={"request": request}).data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, HasDistrictIfOfficer])
def mark_notification_read(request, pk):
    """Mark one as read.

    This is the one write the event log allows. ADR-004 keeps read_at and
    delivery_status as notification-delivery state; the audit fields — actor,
    event type, detail, timestamp — are never touched.
    """
    with transaction.atomic():
        # Hold the case still while checking and marking (ADR-024): a village
        # correction updates the same row, so it cannot move the case into
        # another district between the check and the response.
        case_id = (
            CaseEventLog.objects.filter(pk=pk, recipient_user=request.user)
            .values_list("case_id", flat=True).first()
        )
        if case_id is not None:
            CaseRecord.objects.select_for_update().filter(pk=case_id).first()
        row = _my_notifications(request.user).filter(pk=pk).first()
        if row is None:
            return Response({"detail": "Not found."}, status=404)

        if row.read_at is None:
            row.read_at = timezone.now()
            row.save(update_fields=["read_at"])
        data = NotificationSerializer(row, context={"request": request}).data

    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated, HasDistrictIfOfficer])
def mark_all_notifications_read(request):
    updated = _my_notifications(request.user).filter(read_at__isnull=True).update(read_at=timezone.now())
    return Response({"marked_read": updated})


@api_view(["GET"])
@permission_classes([IsCoordinator])
def priority_rules(request):
    """Screen 18, "how priority works": the classes-1.0 rules and their sources."""
    from priority.classes import CLASS_RULES_VERSION, RULES

    return Response(
        {
            "version": CLASS_RULES_VERSION,
            "classes": RULES,
            "order": "Class first; within a class, the earliest submitted case first.",
        }
    )
