"""URL routing.

The SPA talks to /api/; Django admin remains at /admin/ (ADR-002: admin is
screens 14/19 of the design, not a temporary stand-in).
"""

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
    path("api/cases/<int:pk>/verify/", cases_api.verify_case),
]
