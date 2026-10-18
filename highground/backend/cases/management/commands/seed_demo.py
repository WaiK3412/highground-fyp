"""GAPS C10 item 10: match report/prototype content; compute FRC-1042's class via cases.services.

    python manage.py seed_demo --flush
"""

import base64
import random
import os

from datetime import timedelta

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import Organization, UserAccount
from accounts.two_factor import STAFF_ROLES
from cases.services import classify_case_record
from cases.models import (
    CaseEventLog, CaseJob, CasePhoto, CaseRecord, CaseTask, Donation, DropOffPoint, LocationArea, SupplyAppeal, demo_audit_reset,
)

DEMO_PASSWORD = "demo"  # short on purpose: typed live during demos

ORGS = [
    ("Mercy Relief Malaysia", "ngo", "03-2166 8400", "Kelantan, Terengganu"),
    ("Jabatan Kebajikan Masyarakat (Kota Bharu)", "agency", "09-748 1957", "Kota Bharu district"),
    ("Angkatan Pertahanan Awam Malaysia", "agency", "09-744 2200", "Kelantan state"),
    ("Sukarelawan Kampung Pasir Mas", "volunteer_group", "019-983 4471", "Pasir Mas"),
]

# Use controlled villages (migration 0008) to match live submissions; streets are demo text.
DEMO_STREETS = {
    "MY0304-V001": "Jalan Hospital, Kubang Kerian",
    "MY0304-V002": "Jalan Salor, Kota Bharu",
    "MY0304-V003": "Jalan Banggu, Kota Bharu",
    "MY0304-V004": "Jalan Pengkalan Chepa, Kota Bharu",
    "MY0304-V005": "Jalan Kadok, Ketereh",
    "MY0307-V001": "Jalan Tendong, Pasir Mas",
    "MY0307-V002": "Jalan Rantau Panjang, Pasir Mas",
    "MY0307-V003": "Jalan Meranti, Pasir Mas",
    "MY0307-V004": "Jalan Kangkong, Pasir Mas",
    "MY0307-V005": "Jalan Che Latiff, Pasir Mas",
    "MY0307-V006": "Jalan Gual Periok, Pasir Mas",
    "MY0307-V007": "Jalan Bunut Susu, Pasir Mas",
}


def near(area, dlat, dlng):
    """Offset a village centre with invented demo coordinates, never a real house."""
    return (
        area.latitude + Decimal(str(round(dlat, 6))),
        area.longitude + Decimal(str(round(dlng, 6))),
    )

DESCRIPTIONS = [
    "Water reached the ceiling of the kitchen; all lower cabinets and the fridge are destroyed.",
    "Mud has filled the ground floor to knee height. Elderly parents cannot clear it themselves.",
    "Roof sheeting torn off during the storm surge; two rooms are open to the rain.",
    "Paddy plot fully submerged for six days; seed stock and fertiliser stores lost.",
    "Septic backflow through the bathroom; the family are staying with neighbours.",
    "Perimeter wall collapsed onto the access lane, blocking vehicles into the row of houses.",
    "All bedding, clothes and school uniforms soaked; no dry storage left in the house.",
    "Well contaminated by floodwater — the household has no safe drinking supply.",
]

NEEDS = ["water", "food", "bedding", "hygiene", "medicine", "baby_supplies"]
VULNS = ["elderly", "child_under_5", "disability", "single_parent"]


class Command(BaseCommand):
    help = "Seed realistic demo data for the Phase 1 supervisor demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete existing demo data first so the command is re-runnable.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_demo creates accounts with a known password; it only runs "
                "in development (DJANGO_DEBUG=1)."
            )
        random.seed(1042)  # reproducible demo
        now = timezone.now()

        if options["flush"]:
            self._flush()
        orgs, responding = self._make_organisations()
        resident, officer, volunteer, volunteer2, residents, lead_for = self._make_users(orgs)
        self._enrol_demo_authenticators()
        self._make_drop_off_points_and_appeal(orgs, volunteer, resident, residents[0])
        villages = self._starter_villages()
        cases, frc, kubang_kerian = self._make_canonical_case(resident, officer, now)
        self._make_queue_cases(cases, villages, residents, officer, responding, orgs, now)
        self._classify(cases, officer)
        self._make_tasks(lead_for, officer, now)
        self._make_duplicate_case(cases, kubang_kerian, now)
        self._print_case_summary(cases, frc)
        flagged = self._scan_duplicates()
        self._print_summary(flagged, resident, officer, volunteer, volunteer2)

    def _flush(self):
        self.stdout.write("Flushing existing demo data...")
        with demo_audit_reset():
            # Per-recipient copies protect their original event, events protect the
            # donations they record, and donations their appeal: delete in that order.
            CaseEventLog.objects.filter(notification_copy_of__isnull=False).delete()
            CaseEventLog.objects.all().delete()
            Donation.objects.all().delete()
            SupplyAppeal.objects.all().delete()
            # Evidence protects its task/uploader; an explicit reset removes it first.
            CasePhoto.objects.all().delete()
            CaseTask.objects.all().delete()
            CaseRecord.objects.all().delete()
            DropOffPoint.objects.all().delete()
            UserAccount.objects.filter(is_superuser=False).delete()
            Organization.objects.all().delete()

    def _make_organisations(self):
        orgs = [
            Organization.objects.create(name=n, type=t, contact_no=c, service_area=a)
            for n, t, c, a in ORGS
        ]
        # Agencies have no demo responders, so only responding organisations can claim movable work.
        responding = [org for org in orgs if org.type != Organization.Type.AGENCY]

        return orgs, responding

    def _make_users(self, orgs):
        # DEMO_*_EMAIL enables real demo inboxes; EMAIL_SKIP_DOMAINS skips fallback placeholders.
        resident = UserAccount.objects.create_user(
            email=os.environ.get("DEMO_RESIDENT_EMAIL") or "resident@hg.my", full_name="Siti binti Rahman",
            password=DEMO_PASSWORD, phone="012-345 6789",
            role=UserAccount.Role.COMMUNITY_MEMBER,
        )
        # ADR-024: each officer acts for one district, so the demo has one per
        # seeded district; logging in as each shows the other district's cases hidden.
        kota_bharu = LocationArea.objects.get(code="MY0304")
        pasir_mas = LocationArea.objects.get(code="MY0307")
        officer = UserAccount.objects.create_user(
            email=os.environ.get("DEMO_OFFICER_EMAIL") or "officer@hg.my", full_name="Encik Zulkifli bin Hassan",
            password=DEMO_PASSWORD, phone="09-748 1957",
            role=UserAccount.Role.DISASTER_OFFICER, organization=orgs[1], is_staff=True,
            district=kota_bharu,
        )
        officer2 = UserAccount.objects.create_user(
            email="officer2@hg.my", full_name="Puan Noraini binti Ismail",
            password=DEMO_PASSWORD, phone="09-790 2210",
            role=UserAccount.Role.DISASTER_OFFICER, district=pasir_mas,
        )
        self.officers_by_district = {kota_bharu.pk: officer, pasir_mas.pk: officer2}
        volunteer = UserAccount.objects.create_user(
            email="ngo@hg.my", full_name="Aisyah Tan",
            password=DEMO_PASSWORD, phone="016-220 9931",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=orgs[0],
        )
        # ADR-020: demonstrate two NGOs taking separate jobs on one household request.
        volunteer2 = UserAccount.objects.create_user(
            email="ngo2@hg.my", full_name="Hafiz bin Omar",
            password=DEMO_PASSWORD, phone="019-983 4471",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=orgs[3],
        )
        lead_for = {orgs[0].pk: volunteer, orgs[3].pk: volunteer2}
        residents = [resident] + [
            UserAccount.objects.create_user(
                email=f"r{i}@hg.my", full_name=f"Resident {i}",
                password=DEMO_PASSWORD, phone=f"01{i}-000 000{i}",
                role=UserAccount.Role.COMMUNITY_MEMBER,
            )
            for i in range(2, 8)
        ]
        self.stdout.write(self.style.SUCCESS(f"  users — {UserAccount.objects.count()} across 3 seeded roles"))

        return resident, officer, volunteer, volunteer2, residents, lead_for

    def _enrol_demo_authenticators(self):
        """Give every demo staff account the same authenticator secret (ADR-026).

        With DEMO_TOTP_SECRET set in .env, one entry in an authenticator app signs
        in as any demo officer or NGO responder, and survives re-seeding. Without
        it, each demo staff member sets up an app at first sign-in.
        """
        secret = os.environ.get("DEMO_TOTP_SECRET", "").strip().lower()
        if not secret:
            return
        try:
            key = bytes.fromhex(secret)
        except ValueError:
            key = b""
        if len(key) != 20:
            raise CommandError("DEMO_TOTP_SECRET must be 40 hexadecimal characters.")
        for user in UserAccount.objects.filter(role__in=STAFF_ROLES):
            TOTPDevice.objects.create(user=user, name="Demo authenticator", key=secret, confirmed=True)
        setup_key = base64.b32encode(key).decode().rstrip("=")
        self.stdout.write(f"  demo staff authenticator — add this setup key to your app once: {setup_key}")

    def _make_drop_off_points_and_appeal(self, orgs, volunteer, resident, neighbour):
        points = [
            DropOffPoint.objects.create(name=name, address=addr, area=area, active=True)
            for name, addr, area in [
                ("Dewan Serbaguna Kubang Kerian", "Jalan Hospital, Kubang Kerian", "Kota Bharu"),
                ("Balai Raya Pasir Mas", "Jalan Che Latiff, Pasir Mas", "Pasir Mas"),
                ("Masjid Kampung Banggu", "Jalan Kuala Krai", "Kuala Krai"),
            ]
        ]
        appeal = SupplyAppeal.objects.create(
            organization=orgs[0],
            created_by_user=volunteer,
            drop_off_point=points[1],
            title="Cleaning supplies for Pasir Mas households",
            items="Mops, buckets, bleach, rubber boots, heavy-duty rubbish bags",
            needed_until=timezone.localdate() + timedelta(days=10),
        )
        # One donation of each kind, so the demo shows both states (ADR-025).
        Donation.objects.create(appeal=appeal, donor_user=resident, items="2 mops and 3 buckets")
        Donation.objects.create(
            appeal=appeal, donor_user=neighbour, items="Box of heavy-duty rubbish bags",
            status=Donation.Status.RECEIVED, received_at=timezone.now(), received_by_user=volunteer,
        )

    def _starter_villages(self):
        villages = list(
            LocationArea.objects.filter(
                level=LocationArea.Level.VILLAGE, active=True, code__in=DEMO_STREETS
            ).order_by("code")
        )
        if not villages:
            raise CommandError("No starter villages found — run `manage.py migrate` first.")

        return villages

    def _make_canonical_case(self, resident, officer, now):
        cases = []
        kubang_kerian = LocationArea.objects.get(code="MY0304-V001")
        lat, lng = near(kubang_kerian, 0.004, 0.002)
        frc = self._make_case(
            reference="FRC-1042",
            submitted_by=resident,
            area=kubang_kerian,
            address="Lot 4231, Jalan Hospital, Kubang Kerian",
            lat=lat, lng=lng,
            description=(
                "Floodwater reached waist height indoors and has not fully receded. "
                "The medicine store for two elderly parents was destroyed and the access "
                "lane is currently cut off to all vehicles."
            ),
            damage_category=CaseRecord.DamageCategory.ESSENTIAL_ITEMS,
            urgency=CaseRecord.Urgency.MEDICAL_DISRUPTED,
            liveability=CaseRecord.Liveability.PARTIAL,
            flood_depth=CaseRecord.FloodDepth.WAIST,
            access_level=CaseRecord.AccessLevel.CUT_OFF,
            needs=["water", "food", "bedding", "hygiene", "medicine"],
            vulns=["elderly", "child_under_5", "disability"],
            household_size=5,
            status=CaseRecord.Status.VERIFIED,
            created_at=now - timedelta(days=4),
            verified_by=officer,
            extra_jobs=[(CaseRecord.DamageCategory.CLEANUP, None), (CaseRecord.DamageCategory.REPAIR, None)],
        )
        cases.append(frc)

        return cases, frc, kubang_kerian

    def _officer_for(self, area, default):
        """The seeded officer of the district this village is in (ADR-024)."""
        return self.officers_by_district.get(area.parent_id, default) if area else default

    def _make_queue_cases(self, cases, villages, residents, officer, responding, orgs, now):
        statuses = [
            CaseRecord.Status.SUBMITTED, CaseRecord.Status.SUBMITTED,
            CaseRecord.Status.NEEDS_INFO, CaseRecord.Status.VERIFIED,
            CaseRecord.Status.VERIFIED, CaseRecord.Status.CLAIMED,
            CaseRecord.Status.IN_PROGRESS, CaseRecord.Status.IN_PROGRESS,
            CaseRecord.Status.PENDING_CONFIRM, CaseRecord.Status.CLOSED,
            CaseRecord.Status.REJECTED, CaseRecord.Status.CLOSED,
        ]
        for i, status in enumerate(statuses, start=1):
            area = villages[i % len(villages)]
            lat, lng = near(area, random.uniform(-0.01, 0.01), random.uniform(-0.01, 0.01))
            claimed = status in {
                CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS,
                CaseRecord.Status.PENDING_CONFIRM, CaseRecord.Status.CLOSED,
            }
            case = self._make_case(
                reference=f"FRC-{1043 + i}",
                submitted_by=random.choice(residents),
                area=area,
                address=f"Lot {random.randint(100, 9000)}, {DEMO_STREETS[area.code]}",
                lat=lat,
                lng=lng,
                description=DESCRIPTIONS[i % len(DESCRIPTIONS)],
                damage_category=random.choice(list(CaseRecord.DamageCategory.values)),
                urgency=random.choice(list(CaseRecord.Urgency.values)),
                liveability=random.choice(list(CaseRecord.Liveability.values)),
                flood_depth=random.choice(list(CaseRecord.FloodDepth.values)),
                access_level=random.choice(list(CaseRecord.AccessLevel.values)),
                needs=random.sample(NEEDS, random.randint(0, 5)),
                vulns=random.sample(VULNS, random.randint(0, 3)),
                household_size=random.randint(1, 8),
                status=status,
                created_at=now - timedelta(days=random.randint(0, 9), hours=random.randint(0, 20)),
                verified_by=self._officer_for(area, officer) if status != CaseRecord.Status.SUBMITTED else None,
                claimed_by=responding[i % len(responding)] if claimed else None,
                # Show two NGOs and unclaimed help on one case for the unmet-help report.
                extra_jobs=(
                    [(CaseRecord.DamageCategory.REPAIR, orgs[0]), (CaseRecord.DamageCategory.AGRICULTURE, None)]
                    if i == 7 else []
                ),
            )
            cases.append(case)

    def _classify(self, cases, officer):
        # Match screen 17/cases.services: submitted, needs-info and rejected cases have no class; verify_case clears rejected classes.
        UNCLASSIFIED = {
            CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO, CaseRecord.Status.REJECTED,
        }
        for case in cases:
            if case.status not in UNCLASSIFIED:
                # Classify through the verify service just after verification so the timeline stays ordered.
                classify_case_record(
                    case, self._officer_for(case.location_area, officer),
                    at=case.created_at + timedelta(hours=6, minutes=1),
                )

    def _make_tasks(self, lead_for, officer, now):
        for job in CaseJob.objects.filter(
            status__in=[CaseJob.Status.IN_PROGRESS, CaseJob.Status.PENDING_CONFIRM]
        ).select_related("case"):
            lead = lead_for.get(job.claimed_by_org_id)
            done = job.status == CaseJob.Status.PENDING_CONFIRM
            CaseTask.objects.create(
                case=job.case, job=job, lead_user=lead,
                title=f"{job.get_help_type_display()} work — {job.case.village}",
                task_type=CaseTask.TaskType.REPAIR if job.help_type == "repair" else CaseTask.TaskType.CLEANUP,
                status=CaseTask.Status.DONE if done else (CaseTask.Status.IN_PROGRESS if lead else CaseTask.Status.OPEN),
                assigned_at=now - timedelta(days=1) if lead else None,
                completed_at=now - timedelta(hours=3) if done else None,
            )
            CaseEventLog.objects.create(
                case=job.case, actor_user=lead or self._officer_for(job.case.location_area, officer),
                event_type=CaseEventLog.EventType.TASK_ASSIGNED,
                detail=f"{job.get_help_type_display()} task created by {job.claimed_by_org.name}.",
                created_at=now - timedelta(days=1),
            )

    def _make_duplicate_case(self, cases, kubang_kerian, now):
        # rules-1.0: lot 4231 and Jln -> Jalan identify a relative's Malay report despite different names, phones, nearby pins and descriptions.
        relative = UserAccount.objects.create_user(
            email="relative@hg.my", full_name="Nurul binti Rahman",
            password=DEMO_PASSWORD, phone="013-778 2140",
            role=UserAccount.Role.COMMUNITY_MEMBER,
        )
        lat, lng = near(kubang_kerian, 0.0042, 0.0021)
        cases.append(self._make_case(
            reference="FRC-1056",
            submitted_by=relative,
            area=kubang_kerian,
            address="Lot 4231, Jln Hospital, Kubang Kerian",
            lat=lat, lng=lng,
            description=(
                "Rumah ibu bapa saya dinaiki air paras pinggang dan belum surut. "
                "Ubat-ubatan mereka rosak dan jalan masuk terputus."
            ),
            damage_category=CaseRecord.DamageCategory.ESSENTIAL_ITEMS,
            urgency=CaseRecord.Urgency.MEDICAL_DISRUPTED,
            liveability=CaseRecord.Liveability.PARTIAL,
            flood_depth=CaseRecord.FloodDepth.WAIST,
            access_level=CaseRecord.AccessLevel.CUT_OFF,
            needs=["water", "food", "bedding", "medicine"],
            vulns=["elderly"],
            household_size=5,
            status=CaseRecord.Status.SUBMITTED,
            created_at=now - timedelta(days=3),
        ))

    def _print_case_summary(self, cases, frc):
        classified = [c for c in cases if c.priority_class is not None]
        health_critical = sum(1 for c in classified if c.priority_class == 1)
        self.stdout.write(
            self.style.SUCCESS(
                f"  cases — {len(cases)} seeded, {len(classified)} classified, "
                f"{health_critical} health-critical "
                f"({len(cases) - len(classified)} unverified or rejected, so unclassified)"
            )
        )
        frc.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"  #FRC-1042 classified as priority class {frc.priority_class} "
                f"({frc.get_priority_class_display()})"
            )
        )

    def _scan_duplicates(self):
        # Scan seeded villages because bypassing submission leaves duplicate checks pending and blocks officer verification.
        from cases.duplicate_services import scan_duplicate_area

        flagged = 0
        for area_id in sorted(
            set(CaseRecord.objects.exclude(location_area=None).values_list("location_area_id", flat=True))
        ):
            flagged += scan_duplicate_area(area_id).created

        return flagged

    def _print_summary(self, flagged, resident, officer, volunteer, volunteer2):
        self.stdout.write(self.style.SUCCESS(f"  duplicate check — {flagged} possible duplicates flagged"))
        self.stdout.write(self.style.SUCCESS(f"  events — {CaseEventLog.objects.count()} audit rows"))
        self.stdout.write("")
        self.stdout.write("  Demo logins (credentials are defined in seed_demo.py)")
        for district_officer in self.officers_by_district.values():
            self.stdout.write(f"    officer   {district_officer.email} ({district_officer.district.name})")
        self.stdout.write(f"    ngo lead  {volunteer.email} ({volunteer.organization.name})")
        self.stdout.write(f"    ngo lead  {volunteer2.email} ({volunteer2.organization.name})")
        self.stdout.write(f"    resident  {resident.email}")

    def _make_case(self, *, reference, submitted_by, area, address, lat, lng,
                   description, damage_category, urgency, liveability, flood_depth,
                   access_level, needs, vulns, household_size, status, created_at,
                    verified_by=None, claimed_by=None, extra_jobs=()):
        case = CaseRecord.objects.create(
            reference=reference, submitted_by_user=submitted_by,
            location_area=area, village=area.name,
            address=address, latitude=lat, longitude=lng,
            description=description, damage_category=damage_category,
            urgency=urgency, liveability=liveability, flood_depth=flood_depth,
            access_level=access_level, needs_flags=needs, vulnerability_flags=vulns,
            household_size=household_size, status=status, created_at=created_at,
            verified_by_user=verified_by,
            closed_at=created_at + timedelta(days=3) if status == CaseRecord.Status.CLOSED else None,
        )
        # Create the primary job in case state; extras are open or in progress with the given organisation.
        main_status = {
            CaseRecord.Status.CLAIMED: CaseJob.Status.CLAIMED,
            CaseRecord.Status.IN_PROGRESS: CaseJob.Status.IN_PROGRESS,
            CaseRecord.Status.PENDING_CONFIRM: CaseJob.Status.PENDING_CONFIRM,
            CaseRecord.Status.CLOSED: CaseJob.Status.DONE,
        }.get(status, CaseJob.Status.OPEN) if claimed_by else CaseJob.Status.OPEN
        CaseJob.objects.create(
            case=case, help_type=damage_category, status=main_status, claimed_by_org=claimed_by,
            claimed_at=created_at + timedelta(hours=12) if claimed_by else None,
            completed_at=(
                case.closed_at if main_status == CaseJob.Status.DONE
                # Give awaiting-household jobs a past completion time for the officer's waiting count.
                else min(timezone.now(), max(created_at + timedelta(hours=18), timezone.now() - timedelta(days=2)))
                if main_status == CaseJob.Status.PENDING_CONFIRM else None
            ),
        )
        for help_type, org in extra_jobs:
            if help_type == damage_category:
                continue  # already the main job
            CaseJob.objects.create(
                case=case, help_type=help_type, claimed_by_org=org,
                status=CaseJob.Status.IN_PROGRESS if org else CaseJob.Status.OPEN,
                claimed_at=created_at + timedelta(hours=14) if org else None,
            )
        CaseEventLog.objects.create(
            case=case, actor_user=submitted_by,
            event_type=CaseEventLog.EventType.SUBMITTED,
            detail=f"Request submitted by {submitted_by.full_name}.",
            created_at=created_at,
        )
        if verified_by:
            # Mirror officer audit decisions so needs-info replies quote the actual question.
            event_type, detail = {
                CaseRecord.Status.NEEDS_INFO: (
                    CaseEventLog.EventType.NEEDS_INFO,
                    "Please confirm whether anyone in the household needs regular "
                    "medical treatment, and whether the road to your house is open.",
                ),
                CaseRecord.Status.REJECTED: (
                    CaseEventLog.EventType.REJECTED,
                    "This address is outside the flood-affected area recorded for "
                    "this event. Contact the district office if this is wrong.",
                ),
            }.get(status, (
                CaseEventLog.EventType.VERIFIED,
                "Household details confirmed against the district register.",
            ))
            CaseEventLog.objects.create(
                case=case, actor_user=verified_by, event_type=event_type, detail=detail,
                created_at=created_at + timedelta(hours=6),
            )
        for job in case.jobs.exclude(claimed_by_org=None):
            CaseEventLog.objects.create(
                case=case, actor_user=verified_by,
                event_type=CaseEventLog.EventType.CLAIMED,
                detail=f"{job.get_help_type_display()} claimed by {job.claimed_by_org.name}.",
                created_at=job.claimed_at,
            )
        return case
