from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0004_caseeventlog_notification_copy_of"),
    ]

    operations = [
        migrations.AlterField(
            model_name="caseeventlog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("verified", "Verified"),
                    ("needs_info", "Needs info requested"),
                    ("rejected", "Rejected"),
                    ("score_computed", "Score computed"),
                    ("claimed", "Claimed"),
                    ("released", "Released"),
                    ("task_assigned", "Task assigned"),
                    ("task_updated", "Task updated"),
                    ("completion_requested", "Completion requested"),
                    ("escalated", "Escalated"),
                    ("closed", "Closed"),
                    ("reopened", "Reopened"),
                    ("pledge_updated", "Pledge updated"),
                    ("score_overridden", "Score overridden"),
                    ("rubric_published", "Rubric published"),
                ],
                max_length=30,
            ),
        ),
    ]
