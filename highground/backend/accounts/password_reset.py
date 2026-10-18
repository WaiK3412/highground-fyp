"""Password reset by email, using Django's own reset form and one-time tokens.

The token is tied to the current password and last login, so it stops working
once used. Both endpoints are public; neither says whether an address has an
account.
"""

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .api import LoginRateThrottle, _public_csrf_rejection
from .mail import is_placeholder_address
from .models import UserAccount

LINK_SENT = "If an account uses that address, we've emailed a link."
INVALID_LINK = {"detail": "This reset link is invalid or has expired.", "code": "invalid_link"}


class PasswordResetRateThrottle(LoginRateThrottle):
    scope = "password_reset"


class ResetForm(PasswordResetForm):
    """Django's form, minus the seeded demo addresses we must never email."""

    def get_users(self, email):
        return (user for user in super().get_users(email) if not is_placeholder_address(user.email))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def password_reset_request(request):
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    form = ResetForm(data={"email": str(request.data.get("email", ""))})
    if form.is_valid():
        form.save(
            # The link points at the app from settings, never at the request's Host header.
            domain_override="HighGround",
            subject_template_name="registration/password_reset_subject.txt",
            email_template_name="registration/password_reset_email.txt",
            extra_email_context={"app_origin": settings.APP_ORIGIN},
        )
    # The same answer whether or not the address has an account.
    return Response({"detail": LINK_SENT})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetRateThrottle])
def password_reset_confirm(request):
    rejection = _public_csrf_rejection(request)
    if rejection is not None:
        return rejection
    user = user_from_link(request.data.get("uid"), request.data.get("token"))
    if user is None:
        return Response(INVALID_LINK, status=400)
    passwords = {key: request.data.get(key, "") for key in ("new_password1", "new_password2")}
    form = SetPasswordForm(user, data=passwords)  # applies AUTH_PASSWORD_VALIDATORS
    if not form.is_valid():
        return Response(form.errors, status=400)
    form.save()  # a new password also signs out the account's other sessions
    # The link reached this inbox, which is all the confirmation email proves.
    if not user.email_confirmed:
        user.email_confirmed = True
        user.save(update_fields=["email_confirmed"])
    return Response({"detail": "Password changed. You can now log in."})


def user_from_link(uid, token):
    """The active account a reset link was made for, or None if the link is not valid."""
    try:
        pk = int(urlsafe_base64_decode(str(uid)).decode())
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    user = UserAccount.objects.filter(pk=pk, is_active=True).first()
    if user is None or not default_token_generator.check_token(user, str(token)):
        return None
    return user
