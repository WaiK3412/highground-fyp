"""Rubric governance and stored scores — report §2.4.1 / §3.6.

Weights live in versioned rows, not code constants, so every score is
attributable to a published rubric version and changing them is an audited act.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class PriorityRubricVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    published_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="published_rubrics",
    )
    label = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    medium_threshold = models.PositiveSmallIntegerField(default=40)
    high_threshold = models.PositiveSmallIntegerField(default=70)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "priority_rubric_version"
        ordering = ["-published_at"]

    def __str__(self):
        return f"Rubric {self.label} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.medium_threshold >= self.high_threshold:
            raise ValidationError(
                {"high_threshold": "High threshold must be above the medium threshold."}
            )

    @property
    def total_weight(self):
        return sum(c.weight for c in self.criteria.all())


class PriorityRubricCriterion(models.Model):
    """One weighted factor of a rubric version. Six of these make up v3.0.

    ``max_points`` is the top of the raw severity scale used by the point
    bands. ``weight`` is the criterion's maximum contribution after scaling.
    They are equal in v3.0, but separating them makes weight changes effective.
    """

    version = models.ForeignKey(
        PriorityRubricVersion, on_delete=models.CASCADE, related_name="criteria"
    )
    key = models.CharField(
        max_length=40,
        help_text="Stable identifier the engine matches on, e.g. 'safety'.",
    )
    name = models.CharField(max_length=100)
    weight = models.IntegerField()
    max_points = models.IntegerField()
    rule_text = models.TextField()

    class Meta:
        db_table = "priority_rubric_criterion"
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.weight})"


class CaseScoreComponent(models.Model):
    """Points and the reason behind them.

    The reason is what an officer reads in the breakdown panel; without it the
    score is a black box.
    """

    case = models.ForeignKey(
        "cases.CaseRecord", on_delete=models.CASCADE, related_name="score_components"
    )
    criterion = models.ForeignKey(
        PriorityRubricCriterion, on_delete=models.PROTECT, related_name="components"
    )
    points = models.IntegerField()
    reason = models.TextField()

    class Meta:
        db_table = "case_score_component"
        ordering = ["criterion_id"]

    def __str__(self):
        return f"{self.criterion.name}: +{self.points}"


class AidPackage(models.Model):
    """Reserved ERD table; FR12 package suggestions are withdrawn."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    items = models.TextField(blank=True)

    class Meta:
        db_table = "aid_package"

    def __str__(self):
        return self.name


class CaseAiSuggestion(models.Model):
    """Reserved ERD table; no suggestion workflow is exposed."""
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACCEPTED = "accepted", "Accepted"
        EDITED = "edited", "Edited"
        REJECTED = "rejected", "Rejected"

    case = models.ForeignKey(
        "cases.CaseRecord", on_delete=models.CASCADE, related_name="ai_suggestions"
    )
    package = models.ForeignKey(
        AidPackage, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggestions"
    )
    reviewed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_suggestions",
    )
    explanation = models.TextField()
    source_refs = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "case_ai_suggestion"

    def __str__(self):
        return f"Suggestion for {self.case.reference}"
