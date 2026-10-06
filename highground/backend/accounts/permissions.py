"""Role-based access rules.

Report §3.5: residents see only their own cases; exact coordinates are released
to the district office and the claiming organisation only. A disaster officer
acts for one district (ADR-024): a case belongs to the district of the village
it was filed under.

The visibility rule is written as a plain queryset function so it can be tested
per role without going through HTTP.
"""

from django.db.models import Q
from rest_framework.permissions import BasePermission

from .models import UserAccount

NO_DISTRICT = "No district is assigned to your account. Ask an administrator to assign one."


def officer_district_q(user, prefix=""):
    """Cases (reached through `prefix`) filed under a village in the officer's district."""
    return Q(**{f"{prefix}location_area__parent_id": user.district_id})


def in_officer_district(user, case) -> bool:
    """Is this case filed under a village in the officer's district? (ADR-024)

    A case with no village is in no district, so no officer sees it;
    administrators do, and so do its resident and any organisation the usual
    rules allow. Villages sit directly under districts, so the village's
    parent is the district.
    """
    if user.district_id is None or case.location_area_id is None:
        return False
    return case.location_area.parent_id == user.district_id


class HasDistrictIfOfficer(BasePermission):
    """Endpoints shared by every role still refuse an officer with no district.

    Without this, such an officer would get an empty list here and a 404 there;
    the 403 and its message say what is actually wrong (ADR-024).
    """

    message = NO_DISTRICT

    def has_permission(self, request, view):
        user = request.user
        return not (
            user.is_authenticated
            and user.role == UserAccount.Role.DISASTER_OFFICER
            and user.district_id is None
        )


class IsDisasterOfficer(BasePermission):
    message = "Only district disaster officers may do this."

    def has_permission(self, request, view):
        user = request.user
        if not (user.is_authenticated and user.role == UserAccount.Role.DISASTER_OFFICER):
            return False
        if user.district_id is None:
            # Fail closed, and say why: an officer without a district has no remit.
            self.message = NO_DISTRICT
            return False
        return True


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
        user = request.user
        if not user.is_authenticated:
            return False
        if user.role == UserAccount.Role.SYSTEM_ADMIN:
            return True
        if user.role == UserAccount.Role.DISASTER_OFFICER:
            if user.district_id is None:
                self.message = NO_DISTRICT
                return False
            return True
        return (
            user.role == UserAccount.Role.NGO_VOLUNTEER
            and user.organization_id is not None
        )


def visible_cases(user, queryset):
    """Narrow a case queryset to what this user is allowed to see at all.

    community_member  -> only cases they submitted
    ngo_volunteer     -> cases available to claim, plus their org's own cases
    disaster_officer  -> cases filed under their district's villages (ADR-024)
    system_admin      -> everything
    """
    Role = UserAccount.Role

    if user.role == Role.COMMUNITY_MEMBER:
        return queryset.filter(submitted_by_user=user)

    if user.role == Role.NGO_VOLUNTEER:
        if user.organization_id is None:
            return queryset.none()
        return queryset.filter(
            Q(jobs__claimed_by_org=user.organization)
            | Q(status__in=["verified", "claimed", "in_progress", "pending_confirm"])
        ).distinct()

    if user.role == Role.DISASTER_OFFICER:
        if user.district_id is None:
            return queryset.none()
        return queryset.filter(officer_district_q(user))

    if user.role == Role.SYSTEM_ADMIN:
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

    Released to the district office (that district's officers, and admins)
    and to an organisation holding an active job on the case — not to every
    NGO browsing the queue, nor to officers of other districts.
    """
    Role = UserAccount.Role

    if user.role == Role.SYSTEM_ADMIN:
        return True
    if user.role == Role.DISASTER_OFFICER:
        return in_officer_district(user, case)
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

    if user.role == Role.SYSTEM_ADMIN:
        return True
    if user.role == Role.DISASTER_OFFICER:
        return in_officer_district(user, case)
    if user.role == Role.COMMUNITY_MEMBER:
        return case.submitted_by_user_id == user.id
    return holds_active_job(user, case)
