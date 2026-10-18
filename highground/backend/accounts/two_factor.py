"""Who must give an authenticator code (staff always, residents by choice), and the half-way state between the
password and the code (ADR-026).

After a correct password a staff member is *not* signed in. The session only
remembers who they are, for five minutes, until the code arrives.
"""

import time

from django.conf import settings
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import UserAccount

STAFF_ROLES = {
    UserAccount.Role.DISASTER_OFFICER,
    UserAccount.Role.NGO_VOLUNTEER,
    UserAccount.Role.SYSTEM_ADMIN,
}
PENDING_KEY = "pending_two_factor"
PENDING_SECONDS = 5 * 60


def is_staff_account(user):
    """Staff roles and anyone who can open the Django admin: for them the code is compulsory."""
    return user.role in STAFF_ROLES or user.is_staff or user.is_superuser


def requires_two_factor(user):
    """Staff always; residents only if they switched it on for themselves."""
    return settings.TWO_FACTOR_REQUIRED and (
        is_staff_account(user) or confirmed_device(user) is not None
    )


def confirmed_device(user):
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def setup_device(user):
    """The authenticator being set up: one unconfirmed device, reused until confirmed.

    The account row is locked first, so two requests at once (a double click, or
    React running an effect twice) share one device instead of making two.
    """
    with transaction.atomic():
        UserAccount.objects.select_for_update().filter(pk=user.pk).first()
        device, _ = TOTPDevice.objects.get_or_create(
            user=user, confirmed=False, defaults={"name": "Authenticator app"}
        )
    return device


def start_pending(request, user):
    request.session[PENDING_KEY] = {"user": user.pk, "at": time.time()}


def pending_user(request):
    """The person half-way through signing in, or None if there is none or it timed out."""
    pending = request.session.get(PENDING_KEY)
    if not pending or time.time() - pending["at"] > PENDING_SECONDS:
        return None
    return UserAccount.objects.filter(pk=pending["user"], is_active=True).first()


def clear_pending(request):
    request.session.pop(PENDING_KEY, None)
