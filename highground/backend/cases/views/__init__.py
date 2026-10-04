"""Explicit case endpoint exports for config.urls."""

from .cases import (
    CaseListView,
    case_detail,
    queue_stats,
    case_map,
    locations,
)
from .verification import (
    verify_case,
    reply_to_case,
    override_priority,
    close_on_behalf,
)
from .jobs import (
    claim_job,
    release_job,
    complete_job,
    confirm_job,
    unmet_help,
)
from .tasks import (
    task_board,
    case_tasks,
    update_task,
    task_photos,
)
from .duplicates import (
    duplicate_list,
    duplicate_detail,
    decide_duplicate,
)
from .notifications import (
    notifications,
    mark_notification_read,
    mark_all_notifications_read,
    priority_rules,
)
from .appeals import (
    appeals,
    appeal_detail,
    drop_off_points,
)

__all__ = [
    "CaseListView",
    "case_detail",
    "queue_stats",
    "case_map",
    "locations",
    "verify_case",
    "reply_to_case",
    "override_priority",
    "close_on_behalf",
    "claim_job",
    "release_job",
    "complete_job",
    "confirm_job",
    "unmet_help",
    "task_board",
    "case_tasks",
    "update_task",
    "task_photos",
    "duplicate_list",
    "duplicate_detail",
    "decide_duplicate",
    "notifications",
    "mark_notification_read",
    "mark_all_notifications_read",
    "priority_rules",
    "appeals",
    "appeal_detail",
    "drop_off_points",
]
