"""Confirming an email address after sign-up, and sending the link again (ADR-026)."""

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api import LoginRateThrottle, _public_csrf_rejection
from .mail import send_confirmation_email
from .models import UserAccount
from .tokens import read_confirmation_token

LINK_RESENT = "If that address needs confirming, we've emailed a new link."
INVALID_LINK = {"detail": "This confirmation link is invalid or has expired.", "code": "invalid_link"}


class ConfirmEmailRateThrottle(LoginRateThrottle):
    scope = "confirm_email"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ConfirmEmailRateThrottle])
def confirm_email(request):
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    user = read_confirmation_token(request.data.get("token", ""))
    if user is None:
        return Response(INVALID_LINK, status=400)
    if not user.email_confirmed:
        user.email_confirmed = True
        user.save(update_fields=["email_confirmed"])
    return Response({"detail": "Email confirmed. You can now log in."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ConfirmEmailRateThrottle])
def resend_confirmation(request):
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    email = str(request.data.get("email", "")).strip()
    user = UserAccount.objects.filter(email__iexact=email, is_active=True, email_confirmed=False).first()
    if user is not None:
        send_confirmation_email(user)
    # The same answer for every address, confirmed, unconfirmed or unknown.
    return Response({"detail": LINK_RESENT})
