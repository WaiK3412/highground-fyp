"""Decisions on a case: officer closure and priority override, the household's
reply to a question and its decision on finished work."""

from rest_framework import serializers

from ..models import CaseRecord
from .submission import VULNERABILITY_VOCAB, _known_flags


CLOSE_OUTCOMES = {
    "household_unreachable": "Unable to contact the household",
    "confirmed_verbally": "Household confirmed by phone or in person",
    "other": "Other",
}


class CloseOnBehalfSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=list(CLOSE_OUTCOMES.items()))
    note = serializers.CharField(max_length=500)


class CompletionDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["confirm", "incomplete"])
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

    def validate(self, attrs):
        if attrs["decision"] == "incomplete" and not attrs["note"]:
            raise serializers.ValidationError({"note": ["Explain what still needs attention."]})
        return attrs


class CaseReplySerializer(serializers.Serializer):
    """What a household may change when answering the district office.

    Only the three answers the priority class reads. Address, village and pin
    stay as filed: changing them would need a fresh duplicate check.
    """

    note = serializers.CharField(max_length=1000)
    urgency = serializers.ChoiceField(choices=CaseRecord.Urgency.choices, required=False)
    access_level = serializers.ChoiceField(choices=CaseRecord.AccessLevel.choices, required=False)
    vulnerability_flags = serializers.JSONField(required=False)

    def validate_note(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Answer the district office's question.")
        return value

    def validate_vulnerability_flags(self, value):
        return _known_flags(value, VULNERABILITY_VOCAB, "vulnerability flags")


class PriorityOverrideSerializer(serializers.Serializer):
    priority_class = serializers.ChoiceField(choices=[1, 2, 3])
    reason = serializers.CharField(max_length=500)

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Say why the class should change.")
        return value
