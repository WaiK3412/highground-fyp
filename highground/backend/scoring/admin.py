from django.contrib import admin

from .models import (
    CaseScoreComponent,
    PriorityRubricCriterion,
    PriorityRubricVersion,
)


class PriorityRubricCriterionInline(admin.TabularInline):
    model = PriorityRubricCriterion
    extra = 0
    fields = ("key", "name", "weight", "max_points", "rule_text")


@admin.register(PriorityRubricVersion)
class PriorityRubricVersionAdmin(admin.ModelAdmin):
    """Rubric weights are governed data, not code constants."""

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

    @admin.display(description="Total weight")
    def total_weight(self, obj):
        return obj.total_weight


@admin.register(CaseScoreComponent)
class CaseScoreComponentAdmin(admin.ModelAdmin):
    list_display = ("case", "criterion", "points", "reason")
    list_filter = ("criterion__name",)
    search_fields = ("case__reference",)
