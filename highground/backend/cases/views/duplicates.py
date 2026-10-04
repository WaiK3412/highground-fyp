"""Officer-only duplicate review (ADR-019); comparison and decisions."""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from accounts.permissions import IsDisasterOfficer
from ..models import CaseEventLog
from ..serializers.duplicates import (
    DuplicateCaseSerializer,
    DuplicateDecisionSerializer,
    DuplicateSummarySerializer,
)


# ---------------------------------------------------------------------------
# Duplicate review — screen 12 (report §3.7.8). District officers only: the
# comparison shows two households' details side by side, so none of it goes
# through the shared case serializers.
# ---------------------------------------------------------------------------


def _error(code, detail, status):
    return Response({"code": code, "detail": detail}, status=status)


def _decided_by(match):
    return match.decided_by_user.full_name if match.decided_by_user_id else None


@api_view(["GET"])
@permission_classes([IsDisasterOfficer])
def duplicate_list(request):
    """Flags for review, oldest flag first; ?status= defaults to open."""
    from rest_framework.pagination import PageNumberPagination

    from ..models import DuplicateCaseMatch

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
        # rules-1.0 flags have no score to sort by, so the oldest flag comes first.
        .order_by("pk")
    )
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(DuplicateSummarySerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([IsDisasterOfficer])
def duplicate_detail(request, pk):
    """Side-by-side comparison, stored evidence and current evidence kept apart."""
    import logging

    from ..duplicate_services import (
        confirm_block_reason,
        current_duplicate_comparison,
        duplicate_verification_block,
    )
    from ..models import DuplicateCaseMatch

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
    from ..duplicate_services import DuplicateConflict, decide_duplicate_match

    serializer = DuplicateDecisionSerializer(data=request.data)
    if not serializer.is_valid():
        if "note" in serializer.errors and "decision" not in serializer.errors:
            return _error("invalid_note", "The officer note must be at most 1000 characters.", 400)
        return _error("invalid_decision", "decision must be confirm or dismiss.", 400)
    decision = serializer.validated_data["decision"]
    note = serializer.validated_data.get("note", "")

    try:
        outcome = decide_duplicate_match(pk, request.user, decision, note)
    except DuplicateConflict as conflict:
        return _error(conflict.code, conflict.detail, 409)
    if outcome is None:
        return _error("not_found", "Not found.", 404)

    match = outcome.match
    newer = match.case_b
    if outcome.changed and decision == "confirm":
        from ..notifications import notify

        # After the commit, once. actor=None so the household is told even in
        # the odd case where the deciding officer filed the request themselves.
        from ..duplicate_services import DUPLICATE_CLOSED_DETAIL

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
