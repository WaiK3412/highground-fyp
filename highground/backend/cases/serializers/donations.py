"""Donations to supply appeals (ADR-025)."""

from rest_framework import serializers

from ..models import Donation, SupplyAppeal


class DonationAppealSerializer(serializers.ModelSerializer):
    """Just enough of the appeal for a donor to know where the items go."""

    organization = serializers.CharField(source="organization.name", read_only=True)
    drop_off_point = serializers.CharField(source="drop_off_point.name", read_only=True)

    class Meta:
        model = SupplyAppeal
        fields = ["id", "title", "organization", "drop_off_point"]


class DonationSerializer(serializers.ModelSerializer):
    """What the donor sees; carries no contact details."""

    appeal = DonationAppealSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    received_by = serializers.CharField(
        source="received_by_user.full_name", read_only=True, default=None
    )

    class Meta:
        model = Donation
        fields = [
            "id", "appeal", "items", "status", "status_display",
            "created_at", "received_at", "received_by", "cancelled_at",
        ]
        read_only_fields = ["status", "created_at", "received_at", "cancelled_at"]

    def validate_items(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Say what you are bringing.")
        return value


class OrgDonationSerializer(DonationSerializer):
    """What the appeal's own organisation sees: who is bringing it, and how to reach them."""

    donor_name = serializers.CharField(source="donor_user.full_name", read_only=True)
    donor_phone = serializers.CharField(source="donor_user.phone", read_only=True)

    class Meta(DonationSerializer.Meta):
        fields = DonationSerializer.Meta.fields + ["donor_name", "donor_phone"]
