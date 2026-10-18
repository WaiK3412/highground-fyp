"""NGO supply appeals and the drop-off points they name (ADR-021)."""

from django.utils import timezone
from rest_framework import serializers

from ..models import DropOffPoint, SupplyAppeal


class DropOffPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = DropOffPoint
        fields = ["id", "name", "address", "area"]


class SupplyAppealSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="organization.name", read_only=True)
    organization_contact = serializers.CharField(
        source="organization.contact_no", read_only=True
    )
    drop_off_point = DropOffPointSerializer(read_only=True)
    drop_off_point_id = serializers.PrimaryKeyRelatedField(
        source="drop_off_point",
        queryset=DropOffPoint.objects.filter(active=True),
        write_only=True,
        error_messages={"does_not_exist": "Choose an active drop-off point."},
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SupplyAppeal
        fields = [
            "id", "title", "items", "needed_until", "status", "status_display",
            "organization", "organization_contact", "drop_off_point", "drop_off_point_id",
            "created_at", "closed_at",
        ]
        read_only_fields = ["status", "created_at", "closed_at"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the appeal a short title.")
        return value

    def validate_items(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("List the items you need.")
        if len(value) > 1000:
            raise serializers.ValidationError("Keep the list under 1,000 characters.")
        return value

    def validate_needed_until(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("That date has already passed.")
        return value


class PublicAppealSerializer(serializers.ModelSerializer):
    """What a visitor who is not signed in sees: the need and where to bring it (ADR-025)."""

    organization = serializers.CharField(source="organization.name", read_only=True)
    organization_contact = serializers.CharField(source="organization.contact_no", read_only=True)
    drop_off_point = DropOffPointSerializer(read_only=True)

    class Meta:
        model = SupplyAppeal
        fields = [
            "id", "title", "items", "needed_until",
            "organization", "organization_contact", "drop_off_point",
        ]
