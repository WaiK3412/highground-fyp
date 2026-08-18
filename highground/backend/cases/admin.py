"""Django admin as the case-management interface (ADR-002: admin = screens 14/19)."""

from django.contrib import admin

from scoring.models import CaseScoreComponent

from .models import (
    CaseEventLog,
    CasePhoto,
    CaseRecord,
    CaseTask,
    CommunityPledge,
    DropOffPoint,
    DuplicateCaseMatch,
)


class CaseScoreComponentInline(admin.TabularInline):
    """The explainable breakdown, shown inline on the case it belongs to."""

    model = CaseScoreComponent
    extra = 0
    readonly_fields = ("criterion", "points", "reason")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class CasePhotoInline(admin.TabularInline):
    model = CasePhoto
    extra = 0


class CaseTaskInline(admin.TabularInline):
    model = CaseTask
    extra = 0
    fields = ("title", "task_type", "status", "lead_user")


@admin.register(CaseRecord)
class CaseRecordAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "village",
        "damage_category",
        "status",
        "score_total",
        "priority_band",
        "claimed_by_org",
        "created_at",
    )
    list_filter = ("status", "damage_category", "urgency", "access_level", "liveability")
    search_fields = ("reference", "village", "address", "description")
    date_hierarchy = "created_at"
    readonly_fields = ("score_total", "priority_band")
    inlines = [CaseScoreComponentInline, CasePhotoInline, CaseTaskInline]
    fieldsets = (
        (None, {"fields": ("reference", "status", "description")}),
        (
            "Priority (computed by the scoring engine)",
            {"fields": ("score_total", "priority_band", "rubric_version")},
        ),
        (
            "Assessment — the scoring inputs",
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
        ("Location", {"fields": ("village", "address", "latitude", "longitude")}),
        (
            "People & organisations",
            {"fields": ("submitted_by_user", "verified_by_user", "claimed_by_org")},
        ),
        ("Duplicates", {"fields": ("duplicate_of_case",)}),
        ("Dates", {"fields": ("created_at", "closed_at")}),
    )

    @admin.display(description="Band", ordering="score_total")
    def priority_band(self, obj):
        return obj.priority_band


@admin.register(CaseEventLog)
class CaseEventLogAdmin(admin.ModelAdmin):
    """Append-only audit trail.

    There is no update or delete path in the codebase; the admin refuses both
    so the demo can show that the constraint is structural, not cosmetic.
    """

    list_display = ("created_at", "case", "event_type", "actor_user", "detail")
    list_filter = ("event_type",)
    search_fields = ("case__reference", "detail")
    date_hierarchy = "created_at"

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


@admin.register(DuplicateCaseMatch)
class DuplicateCaseMatchAdmin(admin.ModelAdmin):
    list_display = ("case_a", "case_b", "similarity_score", "status", "decided_by_user")
    list_filter = ("status",)


@admin.register(CommunityPledge)
class CommunityPledgeAdmin(admin.ModelAdmin):
    list_display = ("item_category", "quantity", "status", "drop_off_point", "user")
    list_filter = ("status", "drop_off_point")


@admin.register(DropOffPoint)
class DropOffPointAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "active")
    list_filter = ("active", "area")


admin.site.register(CasePhoto)

admin.site.site_header = "HighGround — flood recovery coordination"
admin.site.site_title = "HighGround admin"
admin.site.index_title = "Case management"
