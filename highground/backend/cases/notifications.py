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
# YOURS — the recipient rules.
#
# This decides who is told what about whose case, which is a permission-shaped
# question, so it belongs in your column rather than mine. Written out so the
# build is not blocked; rewrite it in your own words and the explain-back is
# settled.
#
#   event         | goes to                        | why
#   --------------|--------------------------------|---------------------------
#   submitted     | every disaster officer          | a case is waiting to be seen
#   verified      | the household                   | with the score, folded in
#   needs_info    | the household                   | C6: they must notice this one
#   rejected      | the household                   | with the reason given
#   claimed       | the household                   | someone is coming
#   closed        | the household                   | it is finished
#   escalated     | every disaster officer          | needs a decision above the officer
#
# The rule underneath all of it: never notify somebody about their own action.
# ---------------------------------------------------------------------------

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
    CaseEventLog.EventType.SUBMITTED,
    CaseEventLog.EventType.ESCALATED,
}

TO_CLAIMING_ORGANISATION = {
    CaseEventLog.EventType.CLOSED,
    CaseEventLog.EventType.REOPENED,
}


def recipients_for(case, event_type, actor):
    """Who should be told about this event. Returns a list of users."""
    # Completion decisions are made by the household, so the operational team
    # needs the notification rather than the person who just pressed the button.
    if (
        event_type in TO_CLAIMING_ORGANISATION
        and actor == case.submitted_by_user
        and case.claimed_by_org_id
    ):
        return list(
            UserAccount.objects.filter(
                role=UserAccount.Role.NGO_VOLUNTEER,
                organization=case.claimed_by_org,
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
        return list(
            UserAccount.objects.filter(
                role=UserAccount.Role.DISASTER_OFFICER, is_active=True
            ).exclude(pk=getattr(actor, "pk", None))
        )

    return []


# ---------------------------------------------------------------------------
# Plumbing below.
# ---------------------------------------------------------------------------

# What the household reads. Deliberately plain: the audience has just been
# flooded and may be reading on a phone with a poor signal.
HEADLINES = {
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
    if event_type == CaseEventLog.EventType.VERIFIED and case.score_total is not None:
        # Fold the score in rather than sending a second, near-identical
        # notification seconds later.
        return f"{text} — {case.priority_band} priority, {case.score_total} of 100"
    return text


def notify(case, event_type, actor, detail=""):
    """Address the event to its recipients, and email each of them.

    The caller has already written the audit row for the action. The first
    recipient is attached to *that* row rather than getting a copy of it —
    otherwise a claimed case would carry two "claimed" rows and the audit
    trail would answer "how many times was this claimed?" wrongly.

    Only when an event goes to several people (a new case reaching every
    officer) are extra rows created, because read state is per person.
    """
    people = recipients_for(case, event_type, actor)
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
