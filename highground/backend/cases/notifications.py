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

from accounts.mail import is_placeholder_address
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


def tells_organisation(case, event_type, actor, job):
    """Completion decisions are made by the household, so the organisation
    that did that job needs the notification, not the person who pressed it."""
    return (
        event_type in TO_CLAIMING_ORGANISATION
        and actor == case.submitted_by_user
        and job is not None
        and bool(job.claimed_by_org_id)
    )


def recipients_for(case, event_type, actor, job=None):
    """Who should be told about this event. Returns a list of users."""
    if tells_organisation(case, event_type, actor, job):
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


# The same events, worded for the organisation that did the job: it is not their case.
ORGANISATION_HEADLINES = {
    CaseEventLog.EventType.CLOSED: "A resident confirmed the work is complete",
}


def headline(case, event_type, to_organisation=False):
    if to_organisation and event_type in ORGANISATION_HEADLINES:
        return ORGANISATION_HEADLINES[event_type]
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
    text = headline(case, event_type, to_organisation=tells_organisation(case, event_type, actor, job))
    return _address(
        people,
        audit_row,
        copy_fields={
            "case": case, "actor_user": actor, "event_type": event_type,
            "detail": detail or text,
        },
        subject=f"[HighGround] {text} — {case.reference}",
        body=_email_body(f"{text}.\n\nCase {case.reference}"),
    )


# ---------------------------------------------------------------------------
# Donations (ADR-025): the same rows and delivery, about a donation instead.
#
#   event               | goes to                                  | why
#   --------------------|------------------------------------------|------------------------
#   donation_recorded   | active members of the appeal's org        | items are on their way
#   donation_cancelled  | active members of the appeal's org        | stop expecting them
#   donation_received   | the donor                                 | their items arrived
# ---------------------------------------------------------------------------

DONATION_HEADLINES = {
    CaseEventLog.EventType.DONATION_RECORDED: "New donation coming for {title}",
    CaseEventLog.EventType.DONATION_CANCELLED: "A donation for {title} was cancelled",
    CaseEventLog.EventType.DONATION_RECEIVED: "Your donation to {title} was received",
}


def donation_headline(donation, event_type):
    return DONATION_HEADLINES[event_type].format(title=donation.appeal.title)


def donation_recipients(donation, event_type, actor):
    if event_type == CaseEventLog.EventType.DONATION_RECEIVED:
        people = [donation.donor_user]
    else:
        people = list(
            UserAccount.objects.filter(
                role=UserAccount.Role.NGO_VOLUNTEER,
                organization_id=donation.appeal.organization_id,
                is_active=True,
            ).order_by("id")
        )
    return [person for person in people if person != actor]


def notify_donation(audit_row):
    """Address a donation's audit row to the people it concerns, as notify() does for cases."""
    donation = audit_row.donation
    people = donation_recipients(donation, audit_row.event_type, audit_row.actor_user)
    if not people:
        return []
    text = donation_headline(donation, audit_row.event_type)
    return _address(
        people,
        audit_row,
        copy_fields={
            "donation": donation, "actor_user": audit_row.actor_user,
            "event_type": audit_row.event_type, "detail": audit_row.detail,
        },
        subject=f"[HighGround] {text}",
        body=_email_body(f"{text}.\n\nItems: {donation.items}"),
    )


# ---------------------------------------------------------------------------
# Role-application decisions (ADR-027): the row is about the recipient's own
# account, so it has neither a case nor a donation.
# ---------------------------------------------------------------------------

APPLICATION_HEADLINES = {
    CaseEventLog.EventType.APPLICATION_APPROVED: "Your {role} application was approved",
    CaseEventLog.EventType.APPLICATION_REJECTED: "Your {role} application was not approved",
    CaseEventLog.EventType.APPROVAL_REVOKED: "Your {role} access was removed",
}


ADMIN_NOTE = "Note from the administrator: "


def application_headline(user, event_type):
    return APPLICATION_HEADLINES[event_type].format(role=user.get_requested_role_display())


def notify_application_decision(user, event_type, admin, note=""):
    """Record the decision in the event log and tell the applicant, in the app and by email."""
    audit_row = CaseEventLog.objects.create(
        event_type=event_type, actor_user=admin, detail=note, created_at=timezone.now()
    )
    text = application_headline(user, event_type)
    summary = f"{text}.\n\n{ADMIN_NOTE}{note}" if note else f"{text}."
    return _address(
        [user], audit_row, copy_fields={}, subject=f"[HighGround] {text}", body=_email_body(summary)
    )


# ---------------------------------------------------------------------------
# Plumbing shared by all of them.
# ---------------------------------------------------------------------------


def _address(people, audit_row, copy_fields, subject, body):
    """Give each recipient a row (the audit row first, then copies) and email them."""
    rows = []
    for index, user in enumerate(people):
        if index == 0 and audit_row is not None:
            row = audit_row
            row.recipient_user = user
        else:
            row = CaseEventLog.objects.create(
                **copy_fields,
                recipient_user=user,
                notification_copy_of=audit_row,
                created_at=timezone.now(),
            )
        row.delivery_status = _send_email(user, subject, body)
        row.save(update_fields=["recipient_user", "delivery_status"])
        rows.append(row)
    return rows


def _email_body(summary):
    return (
        "Hello,\n\n"
        f"{summary}\n\n"
        "Sign in to HighGround to see the details and reply.\n\n"
        "This message is for information only. If someone is in immediate danger, "
        "call 999.\n"
    )


def _send_email(user, subject, body):
    """Send the nudge. Returns what to record in delivery_status.

    A failure here must never lose the notification: the in-app row is already
    written, and email is the secondary channel.
    """
    if not user.email:
        return "no_address"
    if is_placeholder_address(user.email):
        # A seeded demo address on a domain we do not own: record, never send.
        return "skipped_placeholder_address"

    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return "sent"
    except Exception as exc:  # noqa: BLE001 — any failure is the same to us here
        return f"failed: {type(exc).__name__}"
