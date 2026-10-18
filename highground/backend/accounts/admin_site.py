"""Who may open the Django admin, the platform administrator's console.

Two rules, kept in one place:
- only platform administrators, never officers, even with is_staff (ADR-024),
  because the admin's case and account screens are not district-scoped;
- only after the authenticator code, like every staff sign-in (ADR-026).
  django-otp's OTPAdminSite also adds the code field to the admin login page.
"""

from django.conf import settings
from django.contrib.admin import AdminSite
from django_otp.admin import OTPAdminSite

from .models import UserAccount


class HighGroundAdminSite(OTPAdminSite):
    def has_permission(self, request):
        if not AdminSite.has_permission(self, request):  # active staff account
            return False
        if request.user.role != UserAccount.Role.SYSTEM_ADMIN:
            return False
        # Switched off only by the test runner, so older tests can sign in directly.
        return not settings.TWO_FACTOR_REQUIRED or request.user.is_verified()
