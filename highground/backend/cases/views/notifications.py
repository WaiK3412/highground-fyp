"""Recipient-scoped notification reads and coordinator priority rules."""

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from accounts.permissions import IsCoordinator
from ..models import CaseEventLog
from ..serializers.notifications import NotificationSerializer


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
            "results": NotificationSerializer(rows, many=True, context={"request": request}).data,
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

    return Response(NotificationSerializer(row, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    updated = CaseEventLog.objects.filter(
        recipient_user=request.user, read_at__isnull=True
    ).update(read_at=timezone.now())
    return Response({"marked_read": updated})


@api_view(["GET"])
@permission_classes([IsCoordinator])
def priority_rules(request):
    """Screen 18, "how priority works": the classes-1.0 rules and their sources."""
    from scoring.classes import CLASS_RULES_VERSION, RULES

    return Response(
        {
            "version": CLASS_RULES_VERSION,
            "classes": RULES,
            "order": "Class first; within a class, the earliest submitted case first.",
        }
    )
