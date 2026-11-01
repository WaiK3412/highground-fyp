"""Two-step sign-in (ADR-026): the code step after the password, and the
settings where a resident switches it on or off for their own account."""

import base64

import qrcode
import qrcode.image.svg
from django.contrib.auth import login
from django_otp import login as otp_login
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .api import LoginRateThrottle, UserSerializer, _public_csrf_rejection
from .two_factor import (
    backup_codes_left,
    clear_pending,
    confirmed_device,
    is_staff_account,
    new_backup_codes,
    pending_user,
    remove_two_factor,
    setup_device,
    use_backup_code,
)

PENDING_EXPIRED = {
    "detail": "Your sign-in timed out. Enter your password again.",
    "code": "pending_expired",
}
INVALID_CODE = {
    "detail": "That code is not right. Check your authenticator app and try again.",
    "code": "invalid_code",
}
INVALID_BACKUP_CODE = {
    "detail": "That backup code is not right, or it has already been used.",
    "code": "invalid_code",
}


class TwoFactorRateThrottle(LoginRateThrottle):
    scope = "two_factor"


@api_view(["POST"])  # POST, not GET: it creates the device being set up
@permission_classes([AllowAny])  # the person is half-way through signing in
def two_factor_setup(request):
    """The QR code (and the same key as text) for adding HighGround to an authenticator app."""
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    user = pending_user(request)
    if user is None:
        return Response(PENDING_EXPIRED, status=403)
    if confirmed_device(user) is not None:
        # An administrator removes the old device first (lost phone): setup cannot replace it.
        return Response({"detail": "An authenticator app is already set up for this account."}, status=409)
    return Response(_setup_details(setup_device(user)))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([TwoFactorRateThrottle])
def two_factor_verify(request):
    """Check the 6-digit code, or a backup code; only now is the person signed in."""
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    user = pending_user(request)
    if user is None:
        return Response(PENDING_EXPIRED, status=403)

    backup_code = str(request.data.get("backup_code", "")).strip()
    device = confirmed_device(user)
    if backup_code:
        # Only once an app is set up: a backup code cannot skip the first setup.
        if device is None or not use_backup_code(user, backup_code):
            return Response(INVALID_BACKUP_CODE, status=400)
        first_setup = False
    else:
        device = device or setup_device(user)
        # verify_token also refuses a code that was already used, and slows repeated failures.
        if not device.verify_token(_code(request)):
            return Response(INVALID_CODE, status=400)
        first_setup = not device.confirmed
        if first_setup:
            device.confirmed = True
            device.save(update_fields=["confirmed"])

    clear_pending(request)
    # django-otp records the verified device on login; a backup code stands in for the app.
    user.otp_device = device
    login(request, user)
    data = UserSerializer(user).data
    if first_setup:
        data["backup_codes"] = new_backup_codes(user)
    return Response(data)


# ---------------------------------------------------------------------------
# Settings for a signed-in account: residents may switch it on or off;
# for staff it is always on.
# ---------------------------------------------------------------------------


def _status(user):
    return {
        "enabled": confirmed_device(user) is not None,
        "required": is_staff_account(user),
        "backup_codes_left": backup_codes_left(user),
    }


def _code(request):
    return str(request.data.get("code", "")).strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def two_factor_status(request):
    return Response(_status(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def two_factor_enable(request):
    """Start switching it on: the QR code to scan. It is on only once a code is confirmed."""
    if confirmed_device(request.user) is not None:
        return Response({"detail": "Two-step sign-in is already on."}, status=409)
    return Response(_setup_details(setup_device(request.user)))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([TwoFactorRateThrottle])
def two_factor_enable_confirm(request):
    user = request.user
    if confirmed_device(user) is not None:
        return Response({"detail": "Two-step sign-in is already on."}, status=409)
    device = setup_device(user)
    if not device.verify_token(_code(request)):
        return Response(INVALID_CODE, status=400)
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    # This session has just proved the code, so it stays signed in.
    otp_login(request, device)
    codes = new_backup_codes(user)
    return Response({**_status(user), "backup_codes": codes})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([TwoFactorRateThrottle])
def two_factor_backup_codes(request):
    """New backup codes in place of the old ones; needs a current code from the app."""
    user = request.user
    device = confirmed_device(user)
    if device is None:
        return Response({"detail": "Turn on two-step sign-in first."}, status=409)
    if not device.verify_token(_code(request)):
        return Response(INVALID_CODE, status=400)
    codes = new_backup_codes(user)
    return Response({**_status(user), "backup_codes": codes})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([TwoFactorRateThrottle])
def two_factor_disable(request):
    """Switch it off; needs a current code, so a stolen password alone cannot."""
    user = request.user
    if is_staff_account(user):
        return Response({"detail": "Two-step sign-in is required for staff accounts."}, status=403)
    device = confirmed_device(user)
    if device is None:
        return Response(_status(user))
    if not device.verify_token(_code(request)):
        return Response(INVALID_CODE, status=400)
    remove_two_factor(user)
    return Response(_status(user))


def _setup_details(device):
    return {"qr_data_uri": _qr_data_uri(device.config_url), "setup_key": _setup_key(device)}


def _qr_data_uri(text):
    svg = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage).to_string()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


def _setup_key(device):
    """The secret as authenticator apps expect it typed: base32, without padding."""
    return base64.b32encode(device.bin_key).decode().rstrip("=")
