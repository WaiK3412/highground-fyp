"""Django admin as the case-management interface (ADR-002: admin = screens 14/19)."""

from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    CaseEventLog,
    CaseJob,
    CasePhoto,
    CaseRecord,
    CaseTask,
    Donation,
    DropOffPoint,
    DuplicateCaseMatch,
    LocationArea,
    SupplyAppeal,
)


class CasePhotoInline(admin.TabularInline):
    model = CasePhoto
    extra = 0
    fields = ("stage", "caption", "uploaded_by_user", "task", "download", "uploaded_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Photo")
    def download(self, obj):
        return format_html('<a href="{}">View</a>', reverse("case-photo", kwargs={"pk": obj.pk}))


class CaseJobInline(admin.TabularInline):
    """Read-only: jobs change through the claim/complete/confirm endpoints,
    which lock, audit and notify (ADR-020)."""

    model = CaseJob
    extra = 0
    fields = ("help_type", "status", "claimed_by_org", "claimed_at", "completed_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class CaseTaskInline(admin.TabularInline):
    model = CaseTask
    extra = 0
    fields = ("title", "job", "task_type", "status", "lead_user")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class CaseRecordAdminForm(forms.ModelForm):
    """Keeps every duplicate pair inside one district (ADR-024).

    Duplicate flags are raised within one village, and duplicate events name
    both cases. Moving one case of a pair to another district would show the
    other district's officers a case they may not see, so a case with any
    duplicate history keeps its district; its village can still change within it.
    """

    class Meta:
        model = CaseRecord
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk or "location_area" not in cleaned:
            return cleaned
        new_area = cleaned["location_area"]
        with transaction.atomic():
            # Judge from locked rows, not the copy the form was opened with.
            # Lock in the duplicate service's order, villages (by id) then the
            # case: detection and decisions lock every case they pair or link,
            # so no new history can appear while the case is held, and holding
            # the new village too means the move's own foreign-key check cannot
            # queue behind a decision that is waiting for this case. Django
            # Admin runs the whole POST in one transaction, so these locks are
            # held until save_model has written the move.
            current = (
                CaseRecord.objects.filter(pk=self.instance.pk)
                .values_list("location_area_id", flat=True).first()
            )
            for area_id in sorted({current, new_area.pk if new_area else None} - {None}):
                LocationArea.objects.select_for_update().filter(pk=area_id).first()
            case = CaseRecord.objects.select_for_update().get(pk=self.instance.pk)
            if case.location_area_id != current:
                self.add_error(None, "This case was corrected by someone else just now. Reload it and try again.")
                return cleaned
            has_history = (
                DuplicateCaseMatch.objects.filter(Q(case_a=case) | Q(case_b=case)).exists()
                or case.duplicate_of_case_id
                or CaseRecord.objects.filter(duplicate_of_case=case).exists()
            )
        old = case.location_area.parent_id if case.location_area_id else None
        new = new_area.parent_id if new_area else None
        if has_history and new != old:
            self.add_error(
                "location_area",
                "This case has duplicate-review history with cases in its district, so it "
                "cannot move to another district. Choose a village in the same district.",
            )
        return cleaned


@admin.register(CaseRecord)
class CaseRecordAdmin(admin.ModelAdmin):
    form = CaseRecordAdminForm
    list_display = (
        "reference",
        "village",
        "damage_category",
        "status",
        "priority_class",
        "created_at",
    )
    list_filter = (
        "status", "priority_class", "damage_category", "urgency", "access_level", "liveability"
    )
    search_fields = ("reference", "village", "address", "description")
    date_hierarchy = "created_at"
    # Lifecycle and assessment change only through the API, which locks,
    # audits, reclassifies and notifies. The village stays editable for the
    # no-village duplicate path (scan_duplicates), and that edit is audited.
    readonly_fields = (
        "reference", "status", "description", "priority_class", "priority_reasons",
        "damage_category", "urgency", "flood_depth",
        "liveability", "access_level", "needs_flags", "vulnerability_flags",
        "household_size", "address", "latitude", "longitude", "submitted_by_user",
        "verified_by_user", "duplicate_of_case", "created_at", "closed_at",
    )
    inlines = [CaseJobInline, CasePhotoInline, CaseTaskInline]
    fieldsets = (
        (None, {"fields": ("reference", "status", "description")}),
        (
            "Priority (classes-1.0, set at verification)",
            {"fields": ("priority_class", "priority_reasons")},
        ),
        (
            "Assessment — the classification inputs",
            {
                "fields": (
                    "damage_category",
                    "urgency",
                    "flood_depth",
                    "liveability",
                    "access_level",
                    "needs_flags",
                    "vulnerability_flags",
                    "household_size",
                )
            },
        ),
        (
            "Location",
            {"fields": ("location_area", "village", "address", "latitude", "longitude")},
        ),
        (
            "People & organisations",
            {"fields": ("submitted_by_user", "verified_by_user")},
        ),
        ("Duplicates", {"fields": ("duplicate_of_case",)}),
        ("Dates", {"fields": ("created_at", "closed_at")}),
    )

    def has_add_permission(self, request):
        return False

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        # Update only the correction fields: a stale admin form must not
        # overwrite a lifecycle action committed while it was open.
        changed = [field for field in form.changed_data if field in {"location_area", "village"}]
        if change and changed:
            obj.save(update_fields=changed)
            CaseEventLog.objects.create(
                case=obj,
                actor_user=request.user,
                event_type=CaseEventLog.EventType.ADMIN_CORRECTED,
                detail=f"Corrected in admin by {request.user.full_name}: {', '.join(changed)}.",
                created_at=timezone.now(),
            )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CaseEventLog)
class CaseEventLogAdmin(admin.ModelAdmin):
    """Canonical actions appear once and cannot be edited through admin."""

    list_display = ("created_at", "case", "donation", "event_type", "actor_user", "detail")
    list_filter = ("event_type",)
    search_fields = ("case__reference", "detail")
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        # Per-recipient copies carry notification read state, not new actions.
        # Screen 19 is the audit trail, so show each canonical action once.
        return super().get_queryset(request).filter(notification_copy_of__isnull=True)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CaseTask)
class CaseTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "task_type", "status", "lead_user", "assigned_at")
    list_filter = ("status", "task_type")
    search_fields = ("title", "case__reference")

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DuplicateCaseMatch)
class DuplicateCaseMatchAdmin(admin.ModelAdmin):
    """Read-only audit view. Flags are created by detection and decided through
    /api/duplicates/, which enforces the pair rules; editing here would skip them."""

    list_display = (
        "case_a", "case_b", "method", "matched_rules", "similarity_score", "status",
        "decided_by_user", "decided_at",
    )
    list_filter = ("status", "method")
    search_fields = ("case_a__reference", "case_b__reference")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DropOffPoint)
class DropOffPointAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "active")
    list_filter = ("active", "area")


@admin.register(LocationArea)
class LocationAreaAdmin(admin.ModelAdmin):
    """Where new villages are added; states and districts come from the gazetteer.

    Codes are issued, not typed: a new village takes the next free code under
    its district, and no code is edited or deleted afterwards, because cases
    and reports refer to it. Retire a place by clearing `active`.
    """

    list_display = ("code", "name", "level", "parent", "centroid_source", "active")
    list_filter = ("level", "active", "parent")
    search_fields = ("code", "name")

    def get_fields(self, request, obj=None):
        place = ("name", "latitude", "longitude", "centroid_source", "active")
        if obj is None:
            # The add form only creates villages; the level defaults to one.
            return ("parent",) + place
        return ("code", "level", "parent") + place

    def get_readonly_fields(self, request, obj=None):
        # A village's code embeds its district, so neither can move later.
        return ("code", "level", "parent") if obj else ()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "parent":
            kwargs["queryset"] = LocationArea.objects.filter(
                level=LocationArea.Level.DISTRICT, active=True
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.level = LocationArea.Level.VILLAGE
            obj.code = LocationArea.next_village_code(obj.parent)
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CasePhoto)
class CasePhotoAdmin(admin.ModelAdmin):
    list_display = ("case", "caption", "uploaded_at", "download")
    readonly_fields = ("case", "caption", "uploaded_at", "download")
    fields = readonly_fields

    @admin.display(description="Photo")
    def download(self, obj):
        return format_html('<a href="{}">View</a>', reverse("case-photo", kwargs={"pk": obj.pk}))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.site_header = "HighGround — flood recovery coordination"
admin.site.site_title = "HighGround admin"
admin.site.index_title = "Case management"


@admin.register(SupplyAppeal)
class SupplyAppealAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "drop_off_point", "needed_until", "status")
    list_filter = ("status", "organization")
    search_fields = ("title", "items")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    """Read-only: residents record donations and NGOs confirm them in the app."""

    list_display = ("appeal", "donor_user", "items", "status", "created_at", "received_at")
    list_filter = ("status",)
    search_fields = ("appeal__title", "items", "donor_user__email")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
