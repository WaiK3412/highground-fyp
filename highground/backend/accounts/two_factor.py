"""Who must give an authenticator code (staff always, residents by choice), and the half-way state between the
password and the code (ADR-026).

After a correct password a staff member is *not* signed in. The session only
remembers who they are, for five minutes, until the code arrives.
"""

import secrets
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib.auth.hashers import get_hasher
from django.db import transaction
from django.utils.crypto import get_random_string
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import BackupCode, UserAccount

STAFF_ROLES = {
    UserAccount.Role.DISASTER_OFFICER,
    UserAccount.Role.NGO_VOLUNTEER,
    UserAccount.Role.SYSTEM_ADMIN,
}
PENDING_KEY = "pending_two_factor"
PENDING_SECONDS = 5 * 60
BACKUP_CODE_COUNT = 10
# No 0/o, 1/l/i: the codes are often copied from paper.
BACKUP_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


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


# ---------------------------------------------------------------------------
# Backup codes: ten one-time codes for when the phone is lost or broken.
# ---------------------------------------------------------------------------


def _hash_backup_code(code, salt):
    """The code under Django's password hasher, as NIST SP 800-63B-4 asks for
    look-up secrets shorter than 112 bits (ADR-028).

    Dashes, spaces and capitals are ignored, so "ABCDE-FGHJK" and "abcdefghjk" match.
    """
    normalised = "".join(code.split()).replace("-", "").lower()
    return get_hasher("default").encode(normalised, salt)


def new_backup_codes(user):
    """Replace the account's backup codes and return the new ones; they cannot be shown again."""
    codes = [
        "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(10))
        for _ in range(BACKUP_CODE_COUNT)
    ]
    # One salt per account, so checking a code costs one hash instead of ten.
    salt = get_random_string(22)
    # Each hash takes about 0.4 s; the hashing releases the GIL, so threads run them together.
    with ThreadPoolExecutor() as pool:
        hashes = list(pool.map(lambda code: _hash_backup_code(code, salt), codes))
    with transaction.atomic():
        BackupCode.objects.filter(user=user).delete()
        BackupCode.objects.bulk_create(BackupCode(user=user, salt=salt, code_hash=h) for h in hashes)
    return [f"{code[:5]}-{code[5:]}" for code in codes]


def use_backup_code(user, code):
    """True if the code was one of the account's unused codes, which is then gone.

    One DELETE both checks and spends the code, so two requests with the same
    code at the same moment cannot both succeed. (Nothing points at BackupCode,
    so Django deletes in one statement instead of selecting rows first.)
    """
    salt = BackupCode.objects.filter(user=user).values_list("salt", flat=True).first()
    if salt is None:
        return False
    deleted, _ = BackupCode.objects.filter(user=user, code_hash=_hash_backup_code(code, salt)).delete()
    return deleted == 1


def backup_codes_left(user):
    return BackupCode.objects.filter(user=user).count()


def remove_two_factor(user):
    """Remove the authenticator and its backup codes (switched off, or a lost phone)."""
    TOTPDevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()
