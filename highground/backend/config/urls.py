"""URL routing.

The SPA talks to /api/; Django admin remains at /admin/ (ADR-002: admin is
screens 14/19 of the design, not a temporary stand-in).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from accounts import api as accounts_api
from cases import api as cases_api

urlpatterns = [
    path("admin/", admin.site.urls),
    # auth — session based, no JWT (ADR-001)
    path("api/auth/csrf/", accounts_api.csrf),
    path("api/auth/register/", accounts_api.register),
    path("api/organizations/", accounts_api.organizations),
    path("api/auth/login/", accounts_api.login_view),
    path("api/auth/logout/", accounts_api.logout_view),
    path("api/auth/me/", accounts_api.me),
    # cases
    path("api/cases/", cases_api.CaseListView.as_view()),
    path("api/cases/stats/", cases_api.queue_stats),
    path("api/cases/<int:pk>/", cases_api.case_detail),
    path("api/cases/<int:pk>/claim/", cases_api.claim_case),
    path("api/cases/<int:pk>/release/", cases_api.release_case),
    path("api/cases/<int:pk>/verify/", cases_api.verify_case),
    path("api/cases/<int:pk>/tasks/", cases_api.case_tasks),
    path("api/cases/<int:pk>/complete/", cases_api.complete_case),
    path("api/cases/<int:pk>/confirm/", cases_api.confirm_case),
    path("api/tasks/", cases_api.task_board),
    path("api/tasks/<int:pk>/", cases_api.update_task),
    # Notifications are the same event-log rows, filtered by recipient (ADR-004).
    # Screen 18 — how scoring works, read-only.
    path("api/rubric/", cases_api.rubric),
    path("api/notifications/", cases_api.notifications),
    path("api/notifications/read-all/", cases_api.mark_all_notifications_read),
    path("api/notifications/<int:pk>/read/", cases_api.mark_notification_read),
]

# runserver serves STATIC by itself but never MEDIA, so uploaded registration
# documents 404 without this line. DEBUG-only on purpose: in production the
# web server serves MEDIA_ROOT, and this helper refuses to run anyway.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
