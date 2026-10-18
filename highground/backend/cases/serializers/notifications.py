"""In-app notifications, worded so a recipient who lost access learns nothing."""

from rest_framework import serializers

from accounts.models import UserAccount
from accounts.permissions import may_see_private_case_details, visible_cases

from ..models import CaseEventLog, CaseRecord
from ..notifications import application_headline, donation_headline
from ..privacy import safe_case_text


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    # A row is about a case, a donation (ADR-025) or the recipient's account (ADR-027).
    case_reference = serializers.CharField(source="case.reference", read_only=True, default=None)
    case_id = serializers.IntegerField(read_only=True)
    donation_id = serializers.IntegerField(read_only=True)
    appeal_id = serializers.IntegerField(source="donation.appeal_id", read_only=True, default=None)
    event_type = serializers.CharField(read_only=True)
    event_display = serializers.CharField(source="get_event_type_display", read_only=True)
    detail = serializers.SerializerMethodField()
    read_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_detail(self, obj):
        user = self.context.get("request").user if self.context.get("request") else None
        if obj.donation_id:
            return self._donation_detail(obj, user)
        if obj.event_type in CaseEventLog.ACCOUNT_EVENTS:
            return self._account_detail(obj, user)
        if user is None or obj.recipient_user_id != user.pk:
            return "Case updated. Sign in to view it."
        # A recipient can lose access after a claim is released or a role is revoked.
        if not visible_cases(user, CaseRecord.objects.filter(pk=obj.case_id)).exists():
            return "Case updated. Sign in to view it."
        if user.role == UserAccount.Role.NGO_VOLUNTEER and not may_see_private_case_details(user, obj.case):
            return "Case updated. Sign in to view it."
        return safe_case_text(obj.case, user, obj.detail)

    def _account_detail(self, obj, user):
        if user is None or obj.recipient_user_id != user.pk:
            return "Account updated. Sign in to view it."
        text = application_headline(user, obj.event_type)
        return f"{text}. Reason: {obj.detail}" if obj.detail else f"{text}."

    def _donation_detail(self, obj, user):
        donation = obj.donation
        still_concerned = user is not None and obj.recipient_user_id == user.pk and (
            donation.donor_user_id == user.pk
            or (
                user.role == UserAccount.Role.NGO_VOLUNTEER
                and user.organization_id == donation.appeal.organization_id
            )
        )
        if not still_concerned:
            # Moved organisation or lost the role: no donor details any more.
            return "Donation updated. Sign in to view it."
        return f"{donation_headline(donation, obj.event_type)}: {donation.items}"
