"""Role-based access rules.

Report §3.5: residents see only their own cases; exact coordinates are released
to the district office and the claiming organisation only.

The visibility rule is written as a plain queryset function so it can be tested
per role without going through HTTP.
"""

from rest_framework.permissions import BasePermission

from .models import UserAccount


class IsDisasterOfficer(BasePermission):
    message = "Only district disaster officers may do this."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserAccount.Role.DISASTER_OFFICER
        )


class IsNgoVolunteer(BasePermission):
    message = "Only members of a responding organisation may do this."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserAccount.Role.NGO_VOLUNTEER
            and request.user.organization_id is not None
        )


class IsCommunityMember(BasePermission):
    message = "Only the resident who submitted the case may do this."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserAccount.Role.COMMUNITY_MEMBER
        )


class IsCoordinator(BasePermission):
    """Officer, administrator, or an NGO responder attached to an organisation."""

    message = "Only authorised coordinators may view this resource."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.role in {
            UserAccount.Role.DISASTER_OFFICER,
            UserAccount.Role.SYSTEM_ADMIN,
        }:
            return True
        return (
            request.user.role == UserAccount.Role.NGO_VOLUNTEER
            and request.user.organization_id is not None
        )


def visible_cases(user, queryset):
    """Narrow a case queryset to what this user is allowed to see at all.

    community_member  -> only cases they submitted
    ngo_volunteer     -> cases available to claim, plus their org's own cases
    disaster_officer  -> everything in their remit
    system_admin      -> everything
    """
    Role = UserAccount.Role

    if user.role == Role.COMMUNITY_MEMBER:
        return queryset.filter(submitted_by_user=user)

    if user.role == Role.NGO_VOLUNTEER:
        from django.db.models import Q

        if user.organization_id is None:
            return queryset.none()
        return queryset.filter(
            Q(jobs__claimed_by_org=user.organization)
            | Q(status__in=["verified", "claimed", "in_progress", "pending_confirm"])
        ).distinct()

    if user.role in {Role.DISASTER_OFFICER, Role.SYSTEM_ADMIN}:
        return queryset
    return queryset.none()


def holds_active_job(user, case) -> bool:
    """Is the user's organisation doing work on this case right now?

    True while one of its jobs is claimed, in progress or awaiting the
    resident's confirmation (ADR-020). Once its work is done, access ends,
    even if other organisations' jobs on the case are still open. Reads
    case.jobs.all(), so a prefetched list (the map, the queue) costs no query.
    """
    if user.role != UserAccount.Role.NGO_VOLUNTEER or user.organization_id is None:
        return False
    from cases.models import CaseJob

    return any(
        job.claimed_by_org_id == user.organization_id and job.status in CaseJob.ACTIVE
        for job in case.jobs.all()
    )


def may_see_exact_location(user, case) -> bool:
    """Exact coordinates are restricted; everyone else gets village-level only.

    Released to the district office (officers, admins) and to an organisation
    holding an active job on the case — not to every NGO browsing the queue.
    Known limit: officers are not yet tied to a district, so every officer
    sees every district (stated in the report).
    """
    Role = UserAccount.Role

    if user.role in {Role.DISASTER_OFFICER, Role.SYSTEM_ADMIN}:
        return True
    if user.role == Role.NGO_VOLUNTEER:
        return holds_active_job(user, case)
    if user.role == Role.COMMUNITY_MEMBER:
        return case.submitted_by_user_id == user.id
    return False


def may_see_private_case_details(user, case) -> bool:
    """Keep household evidence behind ownership or operational responsibility.

    NGOs need a village-level queue summary to decide whether they can help,
    but descriptions, photos, vulnerability flags and the operational history
    are released only while their organisation holds an active job on it.
    """
    Role = UserAccount.Role

    if user.role in {Role.DISASTER_OFFICER, Role.SYSTEM_ADMIN}:
        return True
    if user.role == Role.COMMUNITY_MEMBER:
        return case.submitted_by_user_id == user.id
    return holds_active_job(user, case)
