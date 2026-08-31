from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.utils.html import format_html, format_html_join

from django.utils import timezone

from .models import (
    Organization,
    RegistrationDocument,
    RoleApplication,
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


class UserAccountChangeForm(UserChangeForm):
    """Adds the ADR-012 rule that a rejection must carry a reason.

    reject_application() already refuses a blank note, but it does so with a
    ValueError, which from inside the admin would reach the user as a 500 page.
    Checking here instead puts the message beside the field, which is the only
    place the admin can act on it.
    """

    class Meta(UserChangeForm.Meta):
        model = UserAccount
        fields = "__all__"
        field_classes = {}

    def clean(self):
        cleaned = super().clean()
        S = UserAccount.VerificationStatus

        was = self.initial.get("verification_status")
        now = cleaned.get("verification_status")
        note = (cleaned.get("verification_note") or "").strip()

        if was == S.PENDING and now == S.REJECTED and not note:
            self.add_error(
                "verification_note",
                "A rejected applicant is owed a reason (ADR-012).",
            )
        return cleaned


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
    form = UserAccountChangeForm

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

    def save_model(self, request, obj, form, change):
        """Route a pending application's decision through the model methods.

        By the time this runs the form has already written the new status onto
        `obj` in memory, so approve_application/reject_application would see a
        non-pending application and refuse. The pre-edit value is recovered
        from form.initial and put back, so the guard reads the state the
        database is actually in.

        Saving the column straight from the form is what this exists to
        prevent: ADR-012 section 5 requires the deciding admin and the time of
        the decision to be recorded, and only the model methods do that.
        """
        S = UserAccount.VerificationStatus

        was = form.initial.get("verification_status")
        now = form.cleaned_data.get("verification_status")

        decided = (
            change
            and "verification_status" in form.changed_data
            and was == S.PENDING
            and now in {S.VERIFIED, S.REJECTED}
        )

        if not decided:
            super().save_model(request, obj, form, change)
            return

        # Persist the rest of the form first with the status still pending, so
        # an unrelated edit made in the same save is not lost, and the decision
        # itself is left to the method below.
        obj.verification_status = was
        super().save_model(request, obj, form, change)

        note = form.cleaned_data.get("verification_note") or ""
        if now == S.VERIFIED:
            obj.approve_application(admin=request.user, note=note)
        else:
            obj.reject_application(admin=request.user, note=note)


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


@admin.register(RoleApplication)
class RoleApplicationAdmin(UserAccountAdmin):
    """Screen 14's verification queue, as an admin view.

    Subclasses the account admin rather than reimplementing it, so the decision
    still routes through save_model and the approve/reject model methods — the
    audit fields are recorded exactly as before. All this changes is what is on
    screen: an approver needs the applicant, the role asked for, the evidence
    and a note, not a password widget, group pickers or permission flags.
    """

    list_display = (
        "full_name", "email", "requested_role",
        "organization", "verification_status", "documents", "created_at",
    )
    list_filter = ("verification_status", "requested_role", "organization")
    list_display_links = ("full_name", "email")
    search_fields = ("email", "full_name", "organization__name")
    ordering = ("verification_status", "created_at")

    fieldsets = (
        ("Applicant", {"fields": ("full_name", "email", "phone", "organization")}),
        (
            "Decision",
            {
                "fields": ("requested_role", "verification_status", "verification_note",
                           "verified_by_user", "verified_at"),
                "description": (
                    "Approving copies the requested role into the account. To reject, set "
                    "the status to Rejected and give a reason — the reason is required and "
                    "the role is left untouched."
                ),
            },
        ),
    )
    # The applicant's own words are evidence, not fields staff edit here.
    readonly_fields = (
        "full_name", "email", "phone", "organization", "requested_role",
        "verified_by_user", "verified_at", "created_at",
    )

    def get_queryset(self, request):
        # Only people who actually applied for something. An ordinary resident
        # has no application, so has no business in a review queue.
        return super().get_queryset(request).exclude(requested_role__isnull=True).exclude(
            requested_role=""
        )

    @admin.display(description="Documents")
    def documents(self, obj):
        docs = obj.registration_documents.all()
        if not docs:
            return format_html('<span style="color:#B45309;">none uploaded</span>')
        return format_html_join(
            " · ", '<a href="{}" target="_blank" rel="noopener">{}</a>',
            ((d.file.url, d.label or d.file.name.rsplit("/", 1)[-1]) for d in docs),
        )

    def has_add_permission(self, request):
        # Applications arrive by registering, never by being typed in here.
        return False
