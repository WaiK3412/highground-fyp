from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from django.utils import timezone

from .models import (
    Organization,
    RegistrationDocument,
    UserAccount,
    VolunteerProfile,
)


class RegistrationDocumentInline(admin.TabularInline):
    """The evidence an admin reads before deciding. Read-only: an application's
    documents are what the applicant submitted, not something staff edit."""

    model = RegistrationDocument
    extra = 0
    readonly_fields = ("file", "label", "uploaded_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="Approve selected role applications")
def approve_applications(modeladmin, request, queryset):
    approved, skipped = 0, 0
    for user in queryset:
        try:
            user.approve_application(admin=request.user)
            approved += 1
        except ValueError:
            # Not pending — already decided, or never applied. Skip rather than
            # abort, so one stale row cannot block a whole batch.
            skipped += 1
    modeladmin.message_user(
        request,
        f"{approved} approved."
        + (f" {skipped} skipped (not awaiting a decision)." if skipped else ""),
    )


@admin.register(UserAccount)
class UserAccountAdmin(UserAdmin):
    """Subclasses Django's UserAdmin so the password renders as the
    change-password widget rather than an editable hash field."""

    ordering = ("email",)
    list_display = (
        "email", "full_name", "role", "requested_role",
        "verification_status", "organization", "is_active",
    )
    list_filter = ("verification_status", "role", "organization", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    actions = [approve_applications]
    inlines = [RegistrationDocumentInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("full_name", "phone")}),
        ("Role & organisation", {"fields": ("role", "organization")}),
        (
            "Role application (ADR-012)",
            {
                "fields": (
                    "requested_role",
                    "verification_status",
                    "verification_note",
                    "verified_by_user",
                    "verified_at",
                ),
                "description": (
                    "Approving copies the requested role into role. To reject, set the "
                    "status to Rejected and give a reason in the note — the reason is "
                    "required and the role is left untouched."
                ),
            },
        ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Dates", {"fields": ("last_login", "created_at")}),
    )
    readonly_fields = ("created_at", "last_login", "verified_by_user", "verified_at")

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "organization", "password1", "password2"),
            },
        ),
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "service_area", "contact_no")
    list_filter = ("type",)
    search_fields = ("name", "service_area")


@admin.register(VolunteerProfile)
class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "availability", "vehicle_access", "verified_by_user")
    list_filter = ("vehicle_access",)


@admin.register(RegistrationDocument)
class RegistrationDocumentAdmin(admin.ModelAdmin):
    list_display = ("label", "user", "uploaded_at")
    search_fields = ("user__email", "label")
