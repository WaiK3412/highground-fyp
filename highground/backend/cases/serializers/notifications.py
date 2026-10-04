"""In-app notifications, worded so a recipient who lost access learns nothing."""

from rest_framework import serializers

from accounts.models import UserAccount
from accounts.permissions import may_see_private_case_details, visible_cases

from ..models import CaseRecord
from ..privacy import safe_case_text


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    case_id = serializers.IntegerField(source="case.id", read_only=True)
    event_type = serializers.CharField(read_only=True)
    event_display = serializers.CharField(source="get_event_type_display", read_only=True)
    detail = serializers.SerializerMethodField()
    read_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_detail(self, obj):
        user = self.context.get("request").user if self.context.get("request") else None
        if user is None or obj.recipient_user_id != user.pk:
            return "Case updated. Sign in to view it."
        # A recipient can lose access after a claim is released or a role is revoked.
        if not visible_cases(user, CaseRecord.objects.filter(pk=obj.case_id)).exists():
            return "Case updated. Sign in to view it."
        if user.role == UserAccount.Role.NGO_VOLUNTEER and not may_see_private_case_details(user, obj.case):
            return "Case updated. Sign in to view it."
        return safe_case_text(obj.case, user, obj.detail)
