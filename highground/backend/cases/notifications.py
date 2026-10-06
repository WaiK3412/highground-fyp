"""Turning case events into notifications (ADR-004, GAPS C6).

There is no notification table. `case_event_log` already records everything
that happens to a case, so a notification is one of those rows with a
`recipient_user` set — the notifications list is a filtered query, exactly as
ADR-004 intended.

Email is a nudge back into the app, nothing more. Whether someone *read* an
email cannot be known reliably — tracking pixels are proxied or blocked, and
read receipts need the recipient to opt in — and putting a tracking pixel in a
flood victim's inbox is not a thing this project will do. So:

    read_at          = they opened it in the app. Reliable, we own that page.
    delivery_status  = the SMTP server accepted or refused the message.
    was it opened?   = unknowable, and deliberately not attempted.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import UserAccount

from .models import CaseEventLog


# ---------------------------------------------------------------------------
# The recipient rules (who is told what about whose case).
#
#   event                 | goes to                          | why
#   ----------------------|----------------------------------|---------------------------
#   submitted             | the case's district officers      | a request is waiting to be checked
#   info_provided         | the case's district officers      | the household answered; re-check
#   escalated             | the case's district officers      | (no endpoint creates this yet)
#   verified              | the household                     | with the priority class folded in
#   needs_info            | the household                     | GAPS C6: they must notice this one
#   rejected              | the household                     | with the reason given
#   claimed / released    | the household                     | who is (or is no longer) helping
#   completion_requested  | the household                     | they confirm each job
#   closed / dup. closed  | the household                     | it is finished
#   closed / reopened     | the organisation that did the job | when the household confirms or
#                         |                                   | reports incomplete work
#
# The rule underneath all of it: never notify somebody about their own action.
# Officers act for one district (ADR-024): the district of the case's village.

TO_HOUSEHOLD = {
    CaseEventLog.EventType.VERIFIED,
    CaseEventLog.EventType.NEEDS_INFO,
    CaseEventLog.EventType.REJECTED,
    CaseEventLog.EventType.CLAIMED,
    CaseEventLog.EventType.RELEASED,
    CaseEventLog.EventType.COMPLETION_REQUESTED,
    CaseEventLog.EventType.CLOSED,
    CaseEventLog.EventType.DUPLICATE_CLOSED,
}

TO_OFFICERS = {
    CaseEventLog.EventType.INFO_PROVIDED,
    CaseEventLog.EventType.SUBMITTED,
    CaseEventLog.EventType.ESCALATED,
}

TO_CLAIMING_ORGANISATION = {
    CaseEventLog.EventType.CLOSED,
    CaseEventLog.EventType.REOPENED,
}


def recipients_for(case, event_type, actor, job=None):
    """Who should be told about this event. Returns a list of users."""
    # Completion decisions are made by the household, so the organisation
    # that did that job needs the notification, not the person who pressed it.
    if (
        event_type in TO_CLAIMING_ORGANISATION
        and actor == case.submitted_by_user
        and job is not None
        and job.claimed_by_org_id
    ):
        return list(
            UserAccount.objects.filter(
                role=UserAccount.Role.NGO_VOLUNTEER,
                organization_id=job.claimed_by_org_id,
                is_active=True,
            )
            .exclude(pk=getattr(actor, "pk", None))
            .order_by("id")
        )

    if event_type in TO_HOUSEHOLD:
        household = case.submitted_by_user
        # Nobody needs telling about something they did themselves.
        return [household] if household and household != actor else []

    if event_type in TO_OFFICERS:
        # Only the officers of the district the case is filed in (ADR-024).
        # A case with no village, or a district with no officer, tells nobody;
        # administrators still see the case in Django Admin.
        district_id = case.location_area.parent_id if case.location_area_id else None
        if district_id is None:
            return []
        return list(
            UserAccount.objects.filter(
                role=UserAccount.Role.DISASTER_OFFICER, is_active=True, district_id=district_id
            ).exclude(pk=getattr(actor, "pk", None))
        )

    return []


# ---------------------------------------------------------------------------
# Plumbing below.
# ---------------------------------------------------------------------------

# What the household reads. Deliberately plain: the audience has just been
# flooded and may be reading on a phone with a poor signal.
HEADLINES = {
    CaseEventLog.EventType.INFO_PROVIDED: "A household answered a request for more information",
    CaseEventLog.EventType.SUBMITTED: "A new request is waiting for review",
    CaseEventLog.EventType.VERIFIED: "Your request has been verified",
    CaseEventLog.EventType.NEEDS_INFO: "More information needed on your request",
    CaseEventLog.EventType.REJECTED: "Your request was not accepted",
    CaseEventLog.EventType.CLAIMED: "An organisation is taking on your case",
    CaseEventLog.EventType.RELEASED: "Your case is available to response organisations again",
    CaseEventLog.EventType.COMPLETION_REQUESTED: "Please confirm whether the recovery work is complete",
    CaseEventLog.EventType.CLOSED: "Your case has been closed",
    CaseEventLog.EventType.DUPLICATE_CLOSED: "Your request was closed as a duplicate",
    CaseEventLog.EventType.REOPENED: "A resident reported that work is incomplete",
    CaseEventLog.EventType.ESCALATED: "A case has been escalated",
}


def headline(case, event_type):
    text = HEADLINES.get(event_type, "Your case was updated")
    if event_type == CaseEventLog.EventType.VERIFIED and case.priority_class is not None:
        # Fold the class in rather than sending a second, near-identical
        # notification seconds later.
        return f"{text} — priority class {case.priority_class} ({case.get_priority_class_display()})"
    return text


def notify(case, event_type, actor, detail="", job=None):
    """Address the event to its recipients, and email each of them.

    The caller has already written the audit row for the action. The first
    recipient is attached to *that* row rather than getting a copy of it —
    otherwise a claimed case would carry two "claimed" rows and the audit
    trail would answer "how many times was this claimed?" wrongly.

    Only when an event goes to several people (a new case reaching every
    officer) are extra rows created, because read state is per person.
    """
    people = recipients_for(case, event_type, actor, job)
    if not people:
        return []

    audit_row = (
        CaseEventLog.objects.filter(
            case=case, event_type=event_type, recipient_user__isnull=True
        )
        .order_by("-created_at")
        .first()
    )

    rows = []
    for index, user in enumerate(people):
        if index == 0 and audit_row is not None:
            row = audit_row
            row.recipient_user = user
        else:
            row = CaseEventLog.objects.create(
                case=case,
                actor_user=actor,
                recipient_user=user,
                notification_copy_of=audit_row,
                event_type=event_type,
                detail=detail or headline(case, event_type),
                created_at=timezone.now(),
            )
        row.delivery_status = _send_email(user, case, event_type, detail)
        row.save(update_fields=["recipient_user", "delivery_status"])
        rows.append(row)
    return rows


def _send_email(user, case, event_type, detail):
    """Send the nudge. Returns what to record in delivery_status.

    A failure here must never lose the notification: the in-app row is already
    written, and email is the secondary channel.
    """
    if not user.email:
        return "no_address"

    domain = user.email.rsplit("@", 1)[-1].lower()
    if domain in getattr(settings, "EMAIL_SKIP_DOMAINS", set()):
        # A seeded demo address on a domain we do not own: record, never send.
        return "skipped_placeholder_address"

    subject = f"[HighGround] {headline(case, event_type)} — {case.reference}"
    body = (
        "Hello,\n\n"
        f"{headline(case, event_type)}.\n\n"
        f"Case {case.reference}\n\n"
        f"Sign in to HighGround to see the details and reply.\n\n"
        f"This message is for information only. If someone is in immediate danger, "
        f"call 999.\n"
    )

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return "sent"
    except Exception as exc:  # noqa: BLE001 — any failure is the same to us here
        return f"failed: {type(exc).__name__}"
