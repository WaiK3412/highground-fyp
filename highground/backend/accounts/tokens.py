"""Signed links that confirm an email address (ADR-026).

A purpose-specific salt means a confirmation token can never be used as a
password-reset token, or the other way round. The token carries the address it
was made for, so it stops working if the account's email changes.
"""

from django.core import signing

from .models import UserAccount

SALT = "highground.confirm-email"
MAX_AGE = 24 * 60 * 60  # seconds: a day, for people on poor connections after a flood


def make_confirmation_token(user):
    return signing.dumps({"u": user.pk, "e": user.email}, salt=SALT)


def read_confirmation_token(token):
    """The account the token was made for, or None if it is invalid, expired or out of date."""
    try:
        data = signing.loads(str(token), salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    return UserAccount.objects.filter(pk=data.get("u"), email=data.get("e"), is_active=True).first()
