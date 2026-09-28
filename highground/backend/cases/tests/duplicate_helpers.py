"""Shared world for the duplicate-workflow tests (not a test module itself).

Villages are created here rather than taken from the gazetteer migration, so
the same helpers work in TransactionTestCase, which empties the database.
"""

from datetime import timedelta

from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseRecord, LocationArea

PASSWORD = "Recovery2026"

SAME_HOUSEHOLD = dict(
    address="Lot 88, Jalan Masjid, Kampung Sireh",
    description="Air masuk rumah paras pinggang, dapur rosak dan tilam basah.",
    damage_category=CaseRecord.DamageCategory.REPAIR,
    needs_flags=["food", "water"],
)


def make_area(code="TST-V001", name="Kampung Sireh"):
    # Submission only accepts villages under an active district.
    district, _ = LocationArea.objects.get_or_create(
        code="TST-D01", defaults={"name": "Daerah Ujian", "level": LocationArea.Level.DISTRICT},
    )
    return LocationArea.objects.create(
        code=code, name=name, level=LocationArea.Level.VILLAGE, parent=district,
        latitude=6.1, longitude=102.2,
    )


def make_user(email, name="Ahmad bin Ismail", phone="012-555 0142", role=None, organization=None):
    return UserAccount.objects.create_user(
        email=email, full_name=name, password=PASSWORD, phone=phone,
        role=role or UserAccount.Role.COMMUNITY_MEMBER, organization=organization,
    )


def make_case(submitter, area, *, reference, minutes_ago=60, status=CaseRecord.Status.SUBMITTED, **fields):
    values = dict(SAME_HOUSEHOLD)
    values.update(fields)
    return CaseRecord.objects.create(
        reference=reference, submitted_by_user=submitter,
        location_area=area, village=area.name if area else "Kg. Lama",
        status=status, created_at=timezone.now() - timedelta(minutes=minutes_ago),
        **values,
    )


class DuplicateWorld:
    """Mixin: two reports of one household (flagged) and a different one."""

    def build_world(self):
        self.area = make_area()
        self.other_area = make_area("TST-V002", "Kampung Pulau Rusa")
        self.org = Organization.objects.create(
            name="Mercy Relief", type=Organization.Type.NGO, contact_no="03-1", service_area="Kelantan",
        )
        self.other_org = Organization.objects.create(
            name="Persatuan Belia", type=Organization.Type.VOLUNTEER_GROUP,
            contact_no="03-2", service_area="Pasir Mas",
        )
        self.resident = make_user("ahmad@example.my")
        self.relative = make_user("ahmad2@example.my", name="Ahmad Ismail", phone="+60125550142")
        self.neighbour = make_user("aminah@example.my", name="Aminah binti Yusof", phone="013-555 0911")
        self.officer = make_user(
            "officer@example.my", name="Encik Zulkifli", phone="09-748 1957",
            role=UserAccount.Role.DISASTER_OFFICER,
        )
        self.admin_user = make_user(
            "admin@example.my", name="Admin", phone="", role=UserAccount.Role.SYSTEM_ADMIN,
        )
        self.ngo = make_user(
            "ngo@example.my", name="Aisyah Tan", phone="016-220 9931",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.org,
        )
        self.other_ngo = make_user(
            "belia@example.my", name="Belia Lead", phone="",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=self.other_org,
        )

    def older_and_newer(self):
        older = make_case(self.resident, self.area, reference="FRC-5001", minutes_ago=120)
        newer = make_case(self.relative, self.area, reference="FRC-5002", minutes_ago=10)
        return older, newer


def event_types(case):
    return list(
        CaseEventLog.objects.filter(case=case).order_by("pk").values_list("event_type", flat=True)
    )
