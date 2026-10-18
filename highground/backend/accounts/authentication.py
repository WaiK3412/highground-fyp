"""Session authentication that also requires the authenticator code where it applies (ADR-026)."""

from rest_framework.authentication import SessionAuthentication

from .two_factor import requires_two_factor


class VerifiedSessionAuthentication(SessionAuthentication):
    """A staff session that has not passed the code step counts as signed out.

    The sign-in flow never creates such a session, but this also covers
    sessions from before two-factor sign-in existed, and any other way in.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user = result[0]
        # Checked in this order so a verified session costs no extra query.
        if not user.is_verified() and requires_two_factor(user):
            return None
        return result
