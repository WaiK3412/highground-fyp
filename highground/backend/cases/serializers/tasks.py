"""The NGO task board: tasks, the jobs they belong to, and task photos."""

from rest_framework import serializers

from ..models import CaseEventLog, CasePhoto, CaseTask
from ..privacy import safe_case_text
from .cases import CaseJobSerializer, CaseTaskSummarySerializer
from .submission import ALLOWED_PHOTO_TYPES, MAX_PHOTO_BYTES, MAX_PHOTOS


class CaseTaskBoardSerializer(CaseTaskSummarySerializer):
    safety_note = serializers.SerializerMethodField()
    job_id = serializers.IntegerField(source="job.id", default=None, read_only=True)
    job_status = serializers.CharField(source="job.status", default=None, read_only=True)
    job_help_type_display = serializers.CharField(
        source="job.get_help_type_display", default=None, read_only=True
    )
    case_id = serializers.IntegerField(source="case.id", read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    case_village = serializers.CharField(source="case.village", read_only=True)
    case_priority_class = serializers.IntegerField(source="case.priority_class", read_only=True)
    case_priority_label = serializers.CharField(
        source="case.get_priority_class_display", read_only=True, default=None
    )
    case_status = serializers.CharField(source="case.status", read_only=True)
    case_status_display = serializers.CharField(
        source="case.get_status_display", read_only=True
    )
    lead = serializers.SerializerMethodField()
    updates = serializers.SerializerMethodField()
    safety_acknowledgement = serializers.SerializerMethodField()

    class Meta(CaseTaskSummarySerializer.Meta):
        fields = CaseTaskSummarySerializer.Meta.fields + [
            "job_id",
            "job_status",
            "job_help_type_display",
            "case_id",
            "case_reference",
            "case_village",
            "case_priority_class",
            "case_priority_label",
            "case_status",
            "case_status_display",
            "lead",
            "updates",
            "safety_note",
            "safety_acknowledgement",
        ]

    def get_lead(self, obj):
        if obj.lead_user_id is None:
            return None
        return {"id": obj.lead_user_id, "full_name": obj.lead_user.full_name}

    def get_safety_note(self, obj):
        request = self.context.get("request")
        return safe_case_text(obj.case, request.user if request else None, obj.safety_note)

    def get_safety_acknowledgement(self, obj):
        if not obj.safety_note or not obj.lead_user_id or not obj.assigned_at:
            return None
        acknowledgements = [
            event for event in obj.events.all()
            if event.notification_copy_of_id is None
            and event.event_type == CaseEventLog.EventType.SAFETY_ACKNOWLEDGED
            and event.actor_user_id == obj.lead_user_id
            and event.created_at >= obj.assigned_at
        ]
        if not acknowledgements:
            return None
        latest = max(acknowledgements, key=lambda event: (event.created_at, event.pk))
        return {"by": latest.actor_user.full_name, "at": latest.created_at}

    def get_updates(self, obj):
        rows = [
            event
            for event in obj.events.all()
            if event.notification_copy_of_id is None
            and event.event_type == CaseEventLog.EventType.TASK_UPDATED
        ]
        rows.sort(key=lambda event: event.created_at)
        return [
            {
                "detail": safe_case_text(
                    obj.case,
                    self.context["request"].user if self.context.get("request") else None,
                    event.detail,
                ),
                "actor": event.actor_user.full_name if event.actor_user else None,
                "created_at": event.created_at,
            }
            for event in rows[-5:]
        ]


class BoardJobSerializer(CaseJobSerializer):
    """A job on the organisation's own board, with the case it belongs to."""

    case_id = serializers.IntegerField(source="case.id", read_only=True)
    case_reference = serializers.CharField(source="case.reference", read_only=True)
    case_village = serializers.CharField(source="case.village", read_only=True)
    case_priority_class = serializers.IntegerField(source="case.priority_class", read_only=True)
    case_priority_label = serializers.CharField(
        source="case.get_priority_class_display", read_only=True, default=None
    )
    task_count = serializers.SerializerMethodField()
    tasks_done = serializers.SerializerMethodField()

    class Meta(CaseJobSerializer.Meta):
        fields = CaseJobSerializer.Meta.fields + [
            "case_id", "case_reference", "case_village", "case_priority_class",
            "case_priority_label", "task_count", "tasks_done",
        ]

    def get_task_count(self, obj):
        return len(obj.tasks.all())

    def get_tasks_done(self, obj):
        return sum(1 for task in obj.tasks.all() if task.status == CaseTask.Status.DONE)


class CaseTaskCreateSerializer(serializers.Serializer):
    job_id = serializers.IntegerField()
    title = serializers.CharField(max_length=150)
    task_type = serializers.ChoiceField(choices=CaseTask.TaskType.choices)
    lead_user_id = serializers.IntegerField(required=False, allow_null=True)
    safety_note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the task a title.")
        return value

    def validate_safety_note(self, value):
        return value.strip()


class CaseTaskUpdateSerializer(serializers.Serializer):
    lead_user_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=CaseTask.Status.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    safety_acknowledged = serializers.BooleanField(required=False)


class TaskPhotoUploadSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=[CasePhoto.Stage.BEFORE, CasePhoto.Stage.AFTER])
    photos = serializers.ListField(
        child=serializers.FileField(), min_length=1, max_length=MAX_PHOTOS, write_only=True,
    )
    caption = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate_photos(self, uploads):
        from ..upload_validation import has_expected_signature

        for upload in uploads:
            if upload.size > MAX_PHOTO_BYTES:
                raise serializers.ValidationError(f"{upload.name} is larger than 5 MB.")
            if upload.content_type not in ALLOWED_PHOTO_TYPES or not has_expected_signature(upload):
                raise serializers.ValidationError(f"{upload.name} must be a JPEG, PNG or WebP image.")
        return uploads
