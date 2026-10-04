from django.contrib import admin

from .models import (
    CaseScoreComponent,
    PriorityRubricCriterion,
    PriorityRubricVersion,
)


class PriorityRubricCriterionInline(admin.TabularInline):
    """Retired rubric (classes-1.0 replaced it); kept read-only for the report."""

    model = PriorityRubricCriterion
    extra = 0
    fields = ("key", "name", "weight", "max_points", "rule_text")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PriorityRubricVersion)
class PriorityRubricVersionAdmin(admin.ModelAdmin):
    """Retired rubric (classes-1.0 replaced it); kept read-only for the report."""

    list_display = (
        "label",
        "status",
        "total_weight",
        "medium_threshold",
        "high_threshold",
        "published_at",
        "published_by_user",
    )
    list_filter = ("status",)
    inlines = [PriorityRubricCriterionInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Total weight")
    def total_weight(self, obj):
        return obj.total_weight


@admin.register(CaseScoreComponent)
class CaseScoreComponentAdmin(admin.ModelAdmin):
    """Retired rubric (classes-1.0 replaced it); kept read-only for the report."""

    list_display = ("case", "criterion", "points", "reason")
    list_filter = ("criterion__name",)
    search_fields = ("case__reference",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
