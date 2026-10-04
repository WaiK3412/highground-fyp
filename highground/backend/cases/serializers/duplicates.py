"""Duplicate review (officers only): flagged pairs and the two cases side by side."""

from rest_framework import serializers


class DuplicateCaseRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    reference = serializers.CharField()


# dup-1.1 flags created before 2 Oct 2026 keep the label they were given.
# Frozen thresholds of the retired dup-1.1 engine, which is no longer part of
# the app.
LEGACY_DUP11_MATCH = 65.5

LEGACY_DUP11_POSSIBLE = 35.0


def _legacy_dup11_label(score):
    if score >= LEGACY_DUP11_MATCH:
        return "match"
    if score >= LEGACY_DUP11_POSSIBLE:
        return "possible"
    return "non_match"


class DuplicateSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    # rules-1.0 flags carry matched_rules and no score; flags raised by the
    # retired dup-1.1 engine keep their score and classification.
    method = serializers.CharField()
    similarity_score = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    classification = serializers.SerializerMethodField()
    matched_rules = serializers.SerializerMethodField()
    case_a = DuplicateCaseRefSerializer()
    case_b = DuplicateCaseRefSerializer()

    def get_classification(self, obj):
        # Only dup-1.1 flags have a score to classify, with that engine's
        # frozen thresholds, exactly as it was classified when flagged.
        if obj.similarity_score is None:
            return None
        return _legacy_dup11_label(float(obj.similarity_score))

    def get_matched_rules(self, obj):
        from ..duplicate_rules import RULE_TEXT

        return [{"rule": rule, "text": RULE_TEXT.get(rule, rule)} for rule in obj.matched_rules]


class DuplicateCaseSerializer(serializers.Serializer):
    """One side of the comparison. Officers are district staff, who may see
    exact locations (B6), so coordinates are included when a pin exists."""

    id = serializers.IntegerField()
    reference = serializers.CharField()
    created_at = serializers.DateTimeField()
    status = serializers.CharField()
    status_display = serializers.CharField(source="get_status_display")
    submitter_name = serializers.CharField(source="submitted_by_user.full_name")
    submitter_phone = serializers.CharField(source="submitted_by_user.phone")
    description = serializers.CharField()
    address = serializers.CharField()
    village = serializers.CharField(source="location_area.name", default=None)
    household_size = serializers.IntegerField()
    damage_category = serializers.CharField()
    damage_category_display = serializers.CharField(source="get_damage_category_display")
    needs_flags = serializers.ListField(child=serializers.CharField())
    photo_count = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    # Each request's types of help, so the officer can see what confirming
    # would add to the older request (ADR-020).
    jobs = serializers.SerializerMethodField()

    def get_jobs(self, obj):
        return [
            {"help_type_display": job.get_help_type_display(), "status_display": job.get_status_display()}
            for job in obj.jobs.order_by("id")
        ]

    def get_photo_count(self, obj):
        return obj.photos.count()

    def get_latitude(self, obj):
        return str(obj.latitude) if obj.latitude is not None else None

    def get_longitude(self, obj):
        return str(obj.longitude) if obj.longitude is not None else None


class DuplicateDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["confirm", "dismiss"])
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True, max_length=1000)
