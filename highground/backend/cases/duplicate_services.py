"""Duplicate detection and officer review — the database side (report §3.7.8).

The comparison itself lives in cases/duplicate_rules.py (pure, rules-1.0).
The shared pure module cases/normalise.py supplies normalisers and
DuplicateInput.
This module decides which cases are compared, stores flags, tracks whether a
case's check has finished, and applies an officer's decision.

Three rules shape it:

1. A resident's submission is never lost to a detection failure. The case is
   committed first; detection runs afterwards in its own transaction. If it
   fails, only its own writes roll back and the case stays "check pending".
2. Pending is the default. A case is checked only once its latest check-state
   event is "completed"; no events at all means pending. Verification waits
   for a completed check and for every open flag on the newer case.
3. Lock order, everywhere: village (LocationArea) rows, then case rows, then
   match rows, each by primary key. Two transactions taking locks in the same
   order cannot deadlock on each other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import combinations

from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from accounts.models import UserAccount

from .duplicate_rules import RULES_VERSION, compare_by_rules, contradictions, pin_distance_metres
from .normalise import DuplicateInput
from .models import CaseEventLog, CaseJob, CaseRecord, CaseTask, DuplicateCaseMatch, LocationArea

logger = logging.getLogger(__name__)

Event = CaseEventLog.EventType
Status = CaseRecord.Status
MatchStatus = DuplicateCaseMatch.Status

CHECK_EVENTS = (Event.DUPLICATE_CHECK_PENDING, Event.DUPLICATE_CHECK_COMPLETED)

# Events that name the other household's case. Officers and administrators
# see them; residents and NGOs never do (DUPLICATE_CLOSED is the safe version).
INTERNAL_DUPLICATE_EVENTS = frozenset({
    Event.DUPLICATE_CHECK_PENDING,
    Event.DUPLICATE_CHECK_COMPLETED,
    Event.DUPLICATE_FLAGGED,
    Event.DUPLICATE_CONFIRMED,
    Event.DUPLICATE_DISMISSED,
    Event.DUPLICATE_SUPERSEDED,
})

# Closing a case that already has an organisation working on it would strand
# that work, so confirmation refuses these.
OPERATIONAL_STATUSES = {Status.CLAIMED, Status.IN_PROGRESS, Status.PENDING_CONFIRM}

DUPLICATE_CLOSED_DETAIL = (
    "Your request {reference} was closed after an officer confirmed it duplicates "
    "an existing request. Contact the district office if you believe this "
    "decision is incorrect."
)


class DuplicateConflict(Exception):
    """A decision that cannot be applied in the current state (HTTP 409)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


# --- Inputs ---------------------------------------------------------------


def description_for_matching(case: CaseRecord) -> str:
    """Keep description text in the shared input for offline comparison.

    Rules-1.0 does not read it; a future translation step can plug in here.
    """
    return case.description


def duplicate_input_for_case(case: CaseRecord, submitter: UserAccount | None = None) -> DuplicateInput:
    """Build the comparator's input from a case.

    Name and phone are the submitting account's, not the household's: an
    acknowledged limitation, since a relative filing uses their own account.
    Coordinates are the case's own pin only; the village centroid is never
    used, because every case in the village shares it.
    """
    submitter = submitter or case.submitted_by_user
    return DuplicateInput(
        description_text=description_for_matching(case),
        submitter_name=submitter.full_name,
        address=case.address,
        phone=submitter.phone,
        latitude=float(case.latitude) if case.latitude is not None else None,
        longitude=float(case.longitude) if case.longitude is not None else None,
        damage_category=case.damage_category,
        needs=tuple(case.needs_flags or ()),
    )


def eligible_duplicate_cases(location_area_id):
    """The blocking rule: cases in the same controlled village that are still
    live and are not already someone's duplicate."""
    return CaseRecord.objects.filter(
        location_area_id=location_area_id, duplicate_of_case__isnull=True
    ).exclude(status__in=[Status.REJECTED, Status.CLOSED])


def is_eligible(case: CaseRecord) -> bool:
    return (
        case.location_area_id is not None
        and case.duplicate_of_case_id is None
        and case.status not in (Status.REJECTED, Status.CLOSED)
    )


def canonical_pair(a: CaseRecord, b: CaseRecord) -> tuple[CaseRecord, CaseRecord]:
    """(older, newer) by submission time, then id for identical times."""
    return (a, b) if (a.created_at, a.pk) <= (b.created_at, b.pk) else (b, a)


# --- Check state ------------------------------------------------------------


def latest_check_event_subquery():
    """For annotating a case queryset without a query per row."""
    return Subquery(
        CaseEventLog.objects.filter(case=OuterRef("pk"), event_type__in=CHECK_EVENTS)
        .order_by("-pk")
        .values("event_type")[:1]
    )


def duplicate_check_state(case: CaseRecord) -> str:
    latest = getattr(case, "latest_duplicate_check", None)
    if latest is None and not hasattr(case, "latest_duplicate_check"):
        latest = (
            CaseEventLog.objects.filter(case=case, event_type__in=CHECK_EVENTS)
            .order_by("-pk")
            .values_list("event_type", flat=True)
            .first()
        )
    return "completed" if latest == Event.DUPLICATE_CHECK_COMPLETED else "pending"


def open_review_matches(case: CaseRecord):
    """Open flags where this case is the newer one, i.e. the one that would
    be closed; these block its verification."""
    return DuplicateCaseMatch.objects.filter(case_b=case, status=MatchStatus.OPEN)


def open_match_annotation():
    """One SQL existence check per queryset, without exposing pair details."""
    return Exists(
        DuplicateCaseMatch.objects.filter(
            Q(case_a_id=OuterRef("pk")) | Q(case_b_id=OuterRef("pk")),
            status=MatchStatus.OPEN,
        )
    )


def duplicate_verification_block(case: CaseRecord) -> tuple[str, str] | None:
    """Why this case may not be verified yet, as (code, detail), or None."""
    if case.duplicate_of_case_id is not None:
        return ("case_linked_duplicate", "This case was closed as a duplicate and cannot be verified.")
    if duplicate_check_state(case) != "completed":
        return (
            "duplicate_check_pending",
            "The duplicate check for this case has not finished. Run scan_duplicates "
            "or wait for it to complete.",
        )
    if open_review_matches(case).exists():
        return (
            "duplicate_review_required",
            "This case may duplicate an earlier request. Review the flag before verifying.",
        )
    return None


def _log_event(case, event_type, detail, actor=None):
    return CaseEventLog.objects.create(
        case_id=case if isinstance(case, int) else case.pk, actor_user=actor,
        event_type=event_type, detail=detail, created_at=timezone.now(),
    )


def mark_duplicate_check_pending(case_ids, actor=None) -> None:
    """Commit a pending marker before (re)checking, so a failed attempt can
    never leave an earlier "completed" standing as if it covered this one."""
    with transaction.atomic():
        cases = CaseRecord.objects.select_for_update().filter(pk__in=case_ids).order_by("pk")
        for case in cases:
            _log_event(case, Event.DUPLICATE_CHECK_PENDING,
                       f"Duplicate check started ({RULES_VERSION}).", actor)


# --- Detection ----------------------------------------------------------------


@dataclass
class ScanResult:
    examined: int = 0
    created: int = 0
    existing: int = 0
    skipped: int = 0


def _existing_pairs(case_ids) -> set[frozenset]:
    rows = DuplicateCaseMatch.objects.filter(
        Q(case_a_id__in=case_ids) | Q(case_b_id__in=case_ids)
    ).values_list("case_a_id", "case_b_id")
    return {frozenset(row) for row in rows}


def _lock_village(area_id):
    LocationArea.objects.select_for_update().filter(pk=area_id).first()


def _locked_eligible(area_id) -> list[CaseRecord]:
    # Base rows only: select_for_update with a nullable join would try to lock
    # the joined table too, which PostgreSQL refuses for outer joins.
    cases = list(eligible_duplicate_cases(area_id).select_for_update().order_by("pk"))
    users = UserAccount.objects.in_bulk({case.submitted_by_user_id for case in cases})
    for case in cases:
        case._submitter = users[case.submitted_by_user_id]
    return cases


def _flag_pair(a, b, result, actor=None) -> DuplicateCaseMatch:
    older, newer = canonical_pair(a, b)
    match = DuplicateCaseMatch.objects.create(
        case_a=older, case_b=newer, similarity_score=None,
        method=RULES_VERSION, matched_rules=[hit.rule for hit in result.hits],
        status=MatchStatus.OPEN,
    )
    detail = (
        f"Possible duplicate: {older.reference} (older) and {newer.reference} (newer), "
        f"{RULES_VERSION}: {'; '.join(hit.text for hit in result.hits)}, match #{match.pk}."
    )
    _log_event(older, Event.DUPLICATE_FLAGGED, detail, actor)
    _log_event(newer, Event.DUPLICATE_FLAGGED, detail, actor)
    return match


def _compare_pairs(pairs, cases, dry_run, actor=None) -> ScanResult:
    """Compare each (a, b) once with the rules-1.0 comparator; flag if any rule fires."""
    result = ScanResult()
    inputs = {case.pk: duplicate_input_for_case(case, case._submitter) for case in cases}
    existing = _existing_pairs([case.pk for case in cases])
    for a, b in pairs:
        result.examined += 1
        if frozenset((a.pk, b.pk)) in existing:
            # Never recompare or reopen a pair: an officer may have decided it.
            result.existing += 1
            continue
        comparison = compare_by_rules(inputs[a.pk], inputs[b.pk])
        if comparison.needs_review:
            result.created += 1
            if not dry_run:
                _flag_pair(a, b, comparison, actor)
    return result


def detect_duplicates_for_case(case_id) -> ScanResult:
    """Compare one newly submitted case with the live cases in its village.

    Runs in its own transaction after the submission has committed. The
    completed marker is written in the same transaction as the flags, so
    either both land or neither does.
    """
    with transaction.atomic():
        area_id = (
            CaseRecord.objects.filter(pk=case_id).values_list("location_area_id", flat=True).first()
        )
        if area_id is None:
            # A legacy case without a controlled village cannot be blocked
            # into a comparison set, so it stays pending rather than being
            # waved through as checked.
            return ScanResult(skipped=1)
        _lock_village(area_id)
        cases = _locked_eligible(area_id)
        target = next((case for case in cases if case.pk == case_id), None)
        if target is None:
            # Closed, rejected or already linked: nothing to compare.
            target = CaseRecord.objects.select_for_update().get(pk=case_id)
            result = ScanResult()
        else:
            pairs = [(target, other) for other in cases if other.pk != target.pk]
            result = _compare_pairs(pairs, cases, dry_run=False)
        _log_event(target, Event.DUPLICATE_CHECK_COMPLETED,
                   f"Duplicate check completed ({RULES_VERSION}): "
                   f"{result.examined} compared, {result.created} flagged.")
    return result


def run_detection_after_submission(case: CaseRecord) -> None:
    """Called by the submission view after its transaction commits.

    Any failure is logged by id and exception type only, never with the
    household's text, phone or location, and the case simply stays pending.
    """
    try:
        detect_duplicates_for_case(case.pk)
    except Exception as exc:  # noqa: BLE001 — the submission must survive any failure
        logger.warning(
            "Duplicate detection failed for case id=%s (%s); the case stays pending.",
            case.pk, type(exc).__name__,
        )


def scan_duplicate_area(location_area_id, dry_run=False) -> ScanResult:
    """Backfill one village: every unordered pair of live cases, once.

    Pending markers are committed first, so a failure part-way leaves every
    case in the village pending, never falsely completed. Existing pairs keep
    their stored rules (or legacy score) and status, including officer decisions.
    """
    ids = list(eligible_duplicate_cases(location_area_id).values_list("pk", flat=True))
    if not dry_run and ids:
        mark_duplicate_check_pending(ids)
    with transaction.atomic():
        _lock_village(location_area_id)
        cases = _locked_eligible(location_area_id)
        result = _compare_pairs(combinations(cases, 2), cases, dry_run=dry_run)
        if not dry_run:
            for case in cases:
                _log_event(case, Event.DUPLICATE_CHECK_COMPLETED,
                           f"Duplicate check completed by village scan ({RULES_VERSION}).")
    return result


# --- Current comparison for display ---------------------------------------------


def current_duplicate_comparison(match: DuplicateCaseMatch) -> dict:
    """Re-run the rules on the pair as it stands now, for the review screen.

    The stored matched_rules (or a legacy dup-1.1 score) are what the officer
    was flagged with and are never changed here; case details edited since
    can make these differ.
    """
    a, b = duplicate_input_for_case(match.case_a), duplicate_input_for_case(match.case_b)
    result = compare_by_rules(a, b)
    return {
        "basis": "current_inputs",
        "method": RULES_VERSION,
        "matched": result.needs_review,
        "reasons": [{"rule": hit.rule, "text": hit.text} for hit in result.hits],
        # What disagrees, and how far apart the pins are: shown so the officer
        # weighs both sides. Neither changes whether the pair was flagged.
        "contradictions": [{"rule": c.rule, "text": c.text} for c in contradictions(a, b)],
        "pin_distance_metres": pin_distance_metres(a, b),
    }


# --- Officer decisions ------------------------------------------------------------


def confirm_block_reason(match: DuplicateCaseMatch) -> tuple[str, str] | None:
    """Why this flag cannot be confirmed now, or None. Read-only check; the
    decision re-runs it under locks."""
    older, newer = match.case_a, match.case_b
    if match.status != MatchStatus.OPEN:
        return ("match_not_open", "This flag has already been resolved.")
    if not (is_eligible(older) and is_eligible(newer)) or older.location_area_id != newer.location_area_id:
        return ("stale_pair", "One of these cases has since closed, been rejected, linked, or moved village.")
    if canonical_pair(older, newer) != (older, newer):
        return ("stale_pair", "The stored order of this pair no longer matches submission times.")
    if newer.jobs.exclude(claimed_by_org=None).exists() or newer.status in OPERATIONAL_STATUSES:
        return ("active_case", "An organisation is working on the newer case; it cannot be closed as a duplicate.")
    if CaseTask.objects.filter(case=newer).exclude(status=CaseTask.Status.DONE).exists():
        return ("active_case", "The newer case has unfinished tasks.")
    if CaseRecord.objects.filter(duplicate_of_case=newer).exists():
        # Linking it would make a chain A <- B <- C; keep every duplicate one
        # step from its canonical case.
        return ("duplicate_chain", "Other cases are already linked to the newer case.")
    return None


@dataclass
class DecisionOutcome:
    match: DuplicateCaseMatch
    changed: bool
    superseded_ids: list[int]


DECISION_STATUS = {"confirm": MatchStatus.CONFIRMED, "dismiss": MatchStatus.REJECTED}


def decide_duplicate_match(match_id, actor, decision, note="") -> DecisionOutcome | None:
    """Confirm or dismiss one flag. Returns None if the match does not exist.

    Retrying the same decision returns the stored result without writing
    anything, so a double-clicked button adds no second audit row or
    notification. The opposite decision on a decided flag is a conflict.
    """
    if decision not in DECISION_STATUS:
        raise ValueError(decision)

    ids = DuplicateCaseMatch.objects.filter(pk=match_id).values_list("case_a_id", "case_b_id").first()
    if ids is None:
        return None

    with transaction.atomic():
        area_ids = sorted(
            {area for area in CaseRecord.objects.filter(pk__in=ids).values_list("location_area_id", flat=True) if area}
        )
        for area_id in area_ids:
            _lock_village(area_id)
        cases = {case.pk: case for case in CaseRecord.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
        match_ids = sorted(
            set(
                DuplicateCaseMatch.objects.filter(
                    Q(pk=match_id)
                    | (Q(status=MatchStatus.OPEN) & (Q(case_a_id=ids[1]) | Q(case_b_id=ids[1])))
                ).values_list("pk", flat=True)
            )
        )
        locked = {m.pk: m for m in DuplicateCaseMatch.objects.select_for_update().filter(pk__in=match_ids).order_by("pk")}
        match = locked[match_id]
        match.case_a, match.case_b = cases[ids[0]], cases[ids[1]]
        wanted = DECISION_STATUS[decision]

        if match.status == wanted:
            return DecisionOutcome(match, changed=False, superseded_ids=[])
        if match.status == MatchStatus.SUPERSEDED:
            raise DuplicateConflict(
                "match_superseded",
                "This flag was closed automatically when a related duplicate was confirmed.",
            )
        if match.status != MatchStatus.OPEN:
            raise DuplicateConflict(
                "conflicting_decision", f"This flag was already {match.get_status_display().lower()}."
            )

        now = timezone.now()
        older, newer = match.case_a, match.case_b
        superseded = []
        note_detail = f" Officer note: {note}" if note else ""
        if decision == "dismiss":
            # Allowed even for a stale pair, so it can leave the queue.
            detail = (
                f"{actor.full_name} dismissed the possible duplicate {older.reference} / "
                f"{newer.reference} (match #{match.pk}): different households.{note_detail}"
            )
            _log_event(older, Event.DUPLICATE_DISMISSED, detail, actor)
            _log_event(newer, Event.DUPLICATE_DISMISSED, detail, actor)
        else:
            block = confirm_block_reason(match)
            if block:
                raise DuplicateConflict(*block)
            # One rule (ADR-020): any type of help the older request does not
            # have yet is added to it as an open job, so closing the newer
            # request never loses help only it asked for (the merge pattern of
            # Dataverse/Salesforce; "complete" data fusion, Bleiholder &
            # Naumann 2009). Help both asked for is already on the older one.
            older_types = set(older.jobs.values_list("help_type", flat=True))
            added = []
            for job in newer.jobs.order_by("id"):
                if job.help_type not in older_types:
                    CaseJob.objects.create(case=older, help_type=job.help_type)
                    older_types.add(job.help_type)
                    added.append(job.get_help_type_display())
            newer.duplicate_of_case = older
            newer.status = Status.CLOSED
            newer.closed_at = now
            newer.save(update_fields=["duplicate_of_case", "status", "closed_at"])
            moved = f" {', '.join(added)} added to {older.reference}." if added else ""
            detail = (
                f"{actor.full_name} confirmed {newer.reference} duplicates {older.reference} "
                f"(match #{match.pk}); {newer.reference} closed.{moved} Photos, history and "
                f"priority of both cases are kept.{note_detail}"
            )
            _log_event(older, Event.DUPLICATE_CONFIRMED, detail, actor)
            _log_event(newer, Event.DUPLICATE_CONFIRMED, detail, actor)
            # Other open flags on the closed case no longer have a question to
            # answer. Marked superseded, not rejected: no officer judged them.
            for other in locked.values():
                if other.pk == match.pk or other.status != MatchStatus.OPEN:
                    continue
                other.status = MatchStatus.SUPERSEDED
                other.decided_at = now
                other.save(update_fields=["status", "decided_at"])
                superseded.append(other.pk)
                note = (
                    f"Flag #{other.pk} superseded: {newer.reference} was closed as a duplicate "
                    f"of {older.reference} by {actor.full_name} (match #{match.pk})."
                )
                for case_id in (other.case_a_id, other.case_b_id):
                    _log_event(case_id, Event.DUPLICATE_SUPERSEDED, note, actor)
            # The one event the household may read: their own reference only.
            _log_event(
                newer, Event.DUPLICATE_CLOSED,
                DUPLICATE_CLOSED_DETAIL.format(reference=newer.reference), actor,
            )

        match.status = wanted
        match.decided_by_user = actor
        match.decided_at = now
        match.save(update_fields=["status", "decided_by_user", "decided_at"])
    return DecisionOutcome(match, changed=True, superseded_ids=superseded)
