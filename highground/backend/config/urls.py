"""URL routing.

The SPA talks to /api/; Django admin remains at /admin/ (ADR-002: admin is
screens 14/19 of the design, not a temporary stand-in).
"""

from django.contrib import admin
from django.urls import path

from accounts import api as accounts_api
from accounts import email_confirmation, password_reset, two_factor_views
from accounts.admin_site import HighGroundAdminSite
from cases import views as case_views
from cases import private_files

# The admin's own login page asks for the authenticator code as well (ADR-026).
admin.site.__class__ = HighGroundAdminSite

urlpatterns = [
    path("admin/", admin.site.urls),
    # auth — session based, no JWT (ADR-001)
    path("api/auth/csrf/", accounts_api.csrf),
    path("api/auth/register/", accounts_api.register),
    path("api/organizations/", accounts_api.organizations),
    path("api/registration-documents/<int:pk>/file/", private_files.registration_document, name="registration-document"),
    path("api/auth/login/", accounts_api.login_view),
    path("api/auth/logout/", accounts_api.logout_view),
    path("api/auth/me/", accounts_api.me),
    path("api/auth/password-reset/", password_reset.password_reset_request),
    path("api/auth/password-reset/confirm/", password_reset.password_reset_confirm),
    path("api/auth/confirm-email/", email_confirmation.confirm_email),
    path("api/auth/confirm-email/resend/", email_confirmation.resend_confirmation),
    path("api/auth/two-factor/setup/", two_factor_views.two_factor_setup),
    path("api/auth/two-factor/verify/", two_factor_views.two_factor_verify),
    path("api/auth/two-factor/", two_factor_views.two_factor_status),
    path("api/auth/two-factor/enable/", two_factor_views.two_factor_enable),
    path("api/auth/two-factor/enable/confirm/", two_factor_views.two_factor_enable_confirm),
    path("api/auth/two-factor/disable/", two_factor_views.two_factor_disable),
    # cases
    path("api/cases/", case_views.CaseListView.as_view()),
    path("api/cases/stats/", case_views.queue_stats),
    path("api/cases/map/", case_views.case_map),
    path("api/locations/", case_views.locations),
    path("api/cases/<int:pk>/", case_views.case_detail),
    path("api/case-photos/<int:pk>/file/", private_files.case_photo, name="case-photo"),
    path("api/cases/<int:pk>/verify/", case_views.verify_case),
    path("api/cases/<int:pk>/reply/", case_views.reply_to_case),
    path("api/cases/<int:pk>/priority-override/", case_views.override_priority),
    path("api/cases/<int:pk>/close/", case_views.close_on_behalf),
    path("api/cases/<int:pk>/tasks/", case_views.case_tasks),
    # Duplicate review, screen 12 — district officers only.
    path("api/duplicates/", case_views.duplicate_list),
    path("api/duplicates/<int:pk>/", case_views.duplicate_detail),
    path("api/duplicates/<int:pk>/decide/", case_views.decide_duplicate),
    # Help jobs (ADR-020): each type of help is claimed, finished and
    # confirmed on its own, so several organisations can help one household.
    path("api/jobs/unmet/", case_views.unmet_help),
    path("api/jobs/<int:pk>/claim/", case_views.claim_job),
    path("api/jobs/<int:pk>/release/", case_views.release_job),
    path("api/jobs/<int:pk>/complete/", case_views.complete_job),
    path("api/jobs/<int:pk>/confirm/", case_views.confirm_job),
    path("api/tasks/", case_views.task_board),
    path("api/tasks/<int:pk>/", case_views.update_task),
    path("api/tasks/<int:pk>/photos/", case_views.task_photos),
    # Notifications are the same event-log rows, filtered by recipient (ADR-004).
    # Screen 18 — how priority works (classes-1.0), read-only.
    path("api/priority-rules/", case_views.priority_rules),
    path("api/notifications/", case_views.notifications),
    path("api/notifications/read-all/", case_views.mark_all_notifications_read),
    path("api/notifications/<int:pk>/read/", case_views.mark_notification_read),
    # Supply appeals (ADR-021) — replaces the pledge flow.
    path("api/public/appeals/", case_views.public_appeals),
    path("api/appeals/", case_views.appeals),
    path("api/appeals/<int:pk>/", case_views.appeal_detail),
    path("api/drop-off-points/", case_views.drop_off_points),
    # Donations to appeals (ADR-025).
    path("api/appeals/<int:pk>/donations/", case_views.appeal_donations),
    path("api/donations/", case_views.my_donations),
    path("api/donations/<int:pk>/cancel/", case_views.cancel_donation),
    path("api/donations/<int:pk>/receive/", case_views.receive_donation),
]
