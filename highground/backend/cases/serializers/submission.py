"""What a household may send in a new request (FR3), and its upload limits."""

import json
import math
from decimal import Decimal

from rest_framework import serializers

from ..models import CaseRecord, LocationArea
from ..normalise import haversine_metres


# Same limits as registration documents (accounts/api.py) — a household on a
# phone connection should not be asked to upload more than this.
MAX_PHOTOS = 5

MAX_PHOTO_BYTES = 5 * 1024 * 1024

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


# Unknown flags must not reach the priority class rules or the reasons
# shown to households, so both vocabularies are closed.
VULNERABILITY_VOCAB = {"elderly", "child_under_5", "disability", "single_parent"}

NEEDS_VOCAB = {"food", "water", "hygiene", "bedding", "medicine", "baby_supplies"}


def _known_flags(values, vocabulary, field):
    # A multipart submission (one carrying photos) cannot hold a real list, so
    # the client sends the flags as a JSON string. Accept either shape.
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except ValueError:
            raise serializers.ValidationError("Expected a list.")
    if not isinstance(values, list):
        raise serializers.ValidationError("Expected a list.")
    unknown = sorted({str(v) for v in values} - vocabulary)
    if unknown:
        raise serializers.ValidationError(f"Unrecognised {field}: {', '.join(unknown)}.")
    # De-duplicated: a repeated flag would otherwise be listed twice as a reason.
    return sorted(set(values))


class CaseCreateSerializer(serializers.ModelSerializer):
    """What a household may put in a new case (FR3).

    The field list IS the security boundary, and it is deliberately short.
    Everything a resident must not control — status, priority_class,
    verified_by_user, jobs and who claims them, rubric_version, reference,
    submitted_by_user — is simply absent, so DRF drops it instead of trusting
    it. Posting priority_class=1 is not an error; it is ignored.

    Same rule as ADR-012 registration: the request records what you want, the
    server decides what you get.
    """

    # A code from /api/locations/, not free text: a household cannot file
    # under a retired or invented place, and every case lands on the map.
    location_code = serializers.SlugRelatedField(
        source="location_area",
        slug_field="code",
        queryset=LocationArea.objects.filter(
            level=LocationArea.Level.VILLAGE, active=True, parent__active=True
        ),
        write_only=True,
        error_messages={
            "required": "Choose your village.",
            "null": "Choose your village.",
            "does_not_exist": "Choose a village from the list.",
        },
    )
    # The household's own pin (screen 05a). Optional: the village is the
    # required location, so a map that fails to load never blocks a request.
    latitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-90, max_value=90
    )
    longitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-180, max_value=180
    )
    # Other types of help besides the main one (damage_category). Each type
    # becomes its own job that a different organisation can claim (ADR-020).
    also_need = serializers.JSONField(required=False, write_only=True)

    class Meta:
        model = CaseRecord
        fields = [
            "also_need",
            "location_code",
            "latitude",
            "longitude",
            "address",
            "household_size",
            "damage_category",
            "description",
            "flood_depth",
            "liveability",
            "access_level",
            "urgency",
            "vulnerability_flags",
            "needs_flags",
        ]

    def validate_household_size(self, value):
        if value < 1:
            raise serializers.ValidationError("A household has at least one person.")
        return value

    def validate_description(self, value):
        if not value.strip():
            raise serializers.ValidationError("Describe the damage and what you need.")
        return value.strip()

    def validate_vulnerability_flags(self, value):
        return _known_flags(value, VULNERABILITY_VOCAB, "vulnerability flags")

    def validate_needs_flags(self, value):
        return _known_flags(value, NEEDS_VOCAB, "needs flags")

    def validate_also_need(self, value):
        return _known_flags(value, set(CaseRecord.DamageCategory.values), "types of help")

    def validate(self, attrs):
        # The name as filed stays on the case, so it still reads the same if
        # the area is later renamed or retired.
        attrs["village"] = attrs["location_area"].name
        attrs.update(self._pin(attrs))
        return attrs

    def _pin(self, attrs):
        """Both coordinates or neither, and near the village chosen.

        The distance check catches a pin dropped on the wrong village or a
        mis-tap far away; it cannot prove the pin is on the right house, which
        is still the officer's check at verification.
        """
        latitude, longitude = attrs.pop("latitude", None), attrs.pop("longitude", None)
        if latitude is None and longitude is None:
            return {}
        if latitude is None or longitude is None:
            raise serializers.ValidationError(
                {"latitude": ["Send both latitude and longitude, or neither."]}
            )
        # DRF's range check lets NaN through (every comparison with NaN is
        # false), and a NaN distance would pass the limit below too.
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise serializers.ValidationError({"latitude": ["The pin is not a valid position."]})
        village = attrs["location_area"]
        distance = haversine_metres(
            latitude, longitude, float(village.latitude), float(village.longitude)
        )
        if distance > MAX_PIN_DISTANCE_METRES:
            raise serializers.ValidationError(
                {"latitude": [
                    f"Your pin is {distance / 1000:.1f} km from the centre of {village.name}. "
                    "Check the village you chose, or move the pin to your home."
                ]}
            )
        # The columns hold six decimal places (about 0.1 m), finer than any
        # phone fix, so rounding loses nothing real.
        return {
            "latitude": Decimal(f"{latitude:.6f}"),
            "longitude": Decimal(f"{longitude:.6f}"),
        }


# How far a household pin may sit from its village's centre point. Village
# centres are approximate (many from OpenStreetMap) and rural kampung spread
# along roads and rivers for kilometres, so the limit is generous: it rejects
# a pin in the wrong district, not a pin at the edge of the right village.
MAX_PIN_DISTANCE_METRES = 5_000
