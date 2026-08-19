from django.contrib import admin

from .models import (
    AidPackage,
    CaseAiSuggestion,
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

    list_display = ("label", "status", "total_weight", "published_at", "published_by_user")
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


@admin.register(AidPackage)
class AidPackageAdmin(admin.ModelAdmin):
    list_display = ("name", "description")


@admin.register(CaseAiSuggestion)
class CaseAiSuggestionAdmin(admin.ModelAdmin):
    list_display = ("case", "package", "status", "reviewed_by_user", "created_at")
    list_filter = ("status",)
