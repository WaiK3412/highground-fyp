"""Email helpers shared by notifications, password reset and email confirmation."""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .tokens import make_confirmation_token


def is_placeholder_address(email):
    """True for seeded demo addresses on a domain we do not own; never email those."""
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in getattr(settings, "EMAIL_SKIP_DOMAINS", set())


def send_account_email(user, subject, template, **context):
    """Send one plain-text account email from a template. Returns True if it went.

    A failure must not break the request that triggered it: the person can ask
    for the email again.
    """
    if is_placeholder_address(user.email):
        return False
    body = render_to_string(template, {"user": user, "app_origin": settings.APP_ORIGIN, **context})
    try:
        send_mail(f"[HighGround] {subject}", body, settings.DEFAULT_FROM_EMAIL, [user.email])
        return True
    except Exception:  # noqa: BLE001 — any failure is the same to us here
        return False


def send_confirmation_email(user):
    return send_account_email(
        user, "Confirm your email address", "registration/confirm_email.txt",
        token=make_confirmation_token(user),
    )


def send_account_exists_email(user):
    return send_account_email(
        user, "Someone tried to register with your email", "registration/account_exists_email.txt"
    )
