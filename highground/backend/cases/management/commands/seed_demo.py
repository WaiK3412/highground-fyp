"""Seed demo data.

Reuses the prototype's sample content (GAPS C10 item 10) so what appears on
screen matches the figures in the report — in particular the canonical case
#FRC-1042, whose score of 87 is COMPUTED by the scoring engine here, not
stored as a literal.

    python manage.py seed_demo --flush
"""

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization, UserAccount
from cases.models import CaseEventLog, CaseRecord, CaseTask, DropOffPoint
from scoring.engine import CaseScoreInput, Criterion, Rubric, score_case
from scoring.models import (
    AidPackage,
    CaseScoreComponent,
    PriorityRubricCriterion,
    PriorityRubricVersion,
)

DEMO_PASSWORD = "demo"  # short on purpose: typed live during demos

RUBRIC_V3 = [
    ("safety", "Safety & medical urgency", 25, 25,
     "none 0 · health risk 10 · medical needs disrupted 18 · urgent 25"),
    ("damage", "Damage severity & loss of shelter", 20, 20,
     "cosmetic 4 · partially unliveable 10–18 by flood depth · fully unliveable 20"),
    ("vulnerability", "Household vulnerability", 20, 20,
     "elderly +6 · child <5 +6 · disability +8 · single parent +4 (cap 20)"),
    ("needs", "Essential needs shortage", 15, 15, "+3 per category ticked (cap 15)"),
    ("access", "Location accessibility", 10, 10,
     "normal 0 · 4x4 only 5 · foot only 8 · cut off 10"),
    ("waiting", "Waiting time", 10, 10, "+2 per day (cap 10)"),
]

ORGS = [
    ("Mercy Relief Malaysia", "ngo", "03-2166 8400", "Kelantan, Terengganu"),
    ("Jabatan Kebajikan Masyarakat (Kota Bharu)", "agency", "09-748 1957", "Kota Bharu district"),
    ("Angkatan Pertahanan Awam Malaysia", "agency", "09-744 2200", "Kelantan state"),
    ("Sukarelawan Kampung Pasir Mas", "volunteer_group", "019-983 4471", "Pasir Mas"),
]

VILLAGES = [
    ("Kampung Kubang Kerian", "Jalan Hospital, Kubang Kerian", 6.1361, 102.2861),
    ("Kampung Pasir Mas", "Jalan Che Latiff, Pasir Mas", 6.0498, 102.1399),
    ("Kampung Tendong", "Jalan Tendong, Pasir Mas", 6.0912, 102.1004),
    ("Kampung Banggu", "Jalan Kuala Krai, Banggu", 5.5312, 102.2003),
    ("Kampung Manek Urai", "Jalan Manek Urai Lama", 5.4890, 102.1755),
    ("Kampung Salor", "Jalan Salor, Kota Bharu", 6.0821, 102.2645),
    ("Taman Sri Kelantan", "Jalan Sultan Yahya Petra", 6.1254, 102.2398),
    ("Kampung Chicha", "Jalan Chicha Tinggi, Tanah Merah", 5.8062, 102.1487),
]

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
        parser.add_argument(
            "--empty-log",
            action="store_true",
            help=(
                "Clear the event log after seeding, so a live demo's own actions "
                "are the only rows in the audit trail."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(1042)  # reproducible demo
        now = timezone.now()

        if options["flush"]:
            self.stdout.write("Flushing existing demo data...")
            CaseScoreComponent.objects.all().delete()
            CaseEventLog.objects.all().delete()
            CaseTask.objects.all().delete()
            CaseRecord.objects.all().delete()
            PriorityRubricCriterion.objects.all().delete()
            PriorityRubricVersion.objects.all().delete()
            AidPackage.objects.all().delete()
            DropOffPoint.objects.all().delete()
            UserAccount.objects.filter(is_superuser=False).delete()
            Organization.objects.all().delete()

        # ---------------- rubric v3.0 ----------------
        version = PriorityRubricVersion.objects.create(
            label="v3.0",
            status=PriorityRubricVersion.Status.PUBLISHED,
            medium_threshold=40,
            high_threshold=70,
            published_at=now - timedelta(days=30),
        )
        for key, name, weight, max_points, rule in RUBRIC_V3:
            PriorityRubricCriterion.objects.create(
                version=version, key=key, name=name,
                weight=weight, max_points=max_points, rule_text=rule,
            )
        self.stdout.write(self.style.SUCCESS(f"  rubric {version.label} — 6 criteria, weight 100"))

        engine_rubric = Rubric(
            label=version.label,
            criteria=tuple(
                Criterion(c.key, c.name, c.weight, c.max_points)
                for c in version.criteria.all()
            ),
            high_threshold=version.high_threshold,
            medium_threshold=version.medium_threshold,
        )

        # ---------------- organisations ----------------
        orgs = [
            Organization.objects.create(name=n, type=t, contact_no=c, service_area=a)
            for n, t, c, a in ORGS
        ]

        # ---------------- users ----------------
        resident = UserAccount.objects.create_user(
            email="resident@hg.my", full_name="Siti binti Rahman",
            password=DEMO_PASSWORD, phone="012-345 6789",
            role=UserAccount.Role.COMMUNITY_MEMBER,
        )
        officer = UserAccount.objects.create_user(
            email="officer@hg.my", full_name="Encik Zulkifli bin Hassan",
            password=DEMO_PASSWORD, phone="09-748 1957",
            role=UserAccount.Role.DISASTER_OFFICER, organization=orgs[1], is_staff=True,
        )
        volunteer = UserAccount.objects.create_user(
            email="ngo@hg.my", full_name="Aisyah Tan",
            password=DEMO_PASSWORD, phone="016-220 9931",
            role=UserAccount.Role.NGO_VOLUNTEER, organization=orgs[0],
        )
        residents = [resident] + [
            UserAccount.objects.create_user(
                email=f"r{i}@hg.my", full_name=f"Resident {i}",
                password=DEMO_PASSWORD, phone=f"01{i}-000 000{i}",
                role=UserAccount.Role.COMMUNITY_MEMBER,
            )
            for i in range(2, 8)
        ]
        self.stdout.write(self.style.SUCCESS(f"  users — {UserAccount.objects.count()} across 4 roles"))

        # ---------------- drop-off points & aid packages ----------------
        for name, addr, area in [
            ("Dewan Serbaguna Kubang Kerian", "Jalan Hospital, Kubang Kerian", "Kota Bharu"),
            ("Balai Raya Pasir Mas", "Jalan Che Latiff, Pasir Mas", "Pasir Mas"),
            ("Masjid Kampung Banggu", "Jalan Kuala Krai", "Kuala Krai"),
        ]:
            DropOffPoint.objects.create(name=name, address=addr, area=area, active=True)

        for name, desc, items in [
            ("Family cleanup kit", "For households returning to a mud-filled home.",
             "Wheelbarrow, shovels, disinfectant, heavy-duty gloves, bin bags"),
            ("Essential household restart", "Replaces the basics lost to submersion.",
             "Mattresses, blankets, cooking set, water filter, torch"),
            ("Agriculture recovery", "For smallholders who lost seed and inputs.",
             "Paddy seed, fertiliser, hand tools"),
        ]:
            AidPackage.objects.create(name=name, description=desc, items=items)

        # ---------------- the canonical case ----------------
        cases = []
        frc = self._make_case(
            reference="FRC-1042",
            submitted_by=resident,
            village="Kampung Kubang Kerian",
            address="Lot 4231, Jalan Hospital, Kubang Kerian",
            lat=6.1361, lng=102.2861,
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
        )
        cases.append(frc)

        # ---------------- the rest of the queue ----------------
        statuses = [
            CaseRecord.Status.SUBMITTED, CaseRecord.Status.SUBMITTED,
            CaseRecord.Status.NEEDS_INFO, CaseRecord.Status.VERIFIED,
            CaseRecord.Status.VERIFIED, CaseRecord.Status.CLAIMED,
            CaseRecord.Status.IN_PROGRESS, CaseRecord.Status.IN_PROGRESS,
            CaseRecord.Status.PENDING_CONFIRM, CaseRecord.Status.CLOSED,
            CaseRecord.Status.REJECTED, CaseRecord.Status.CLOSED,
        ]
        for i, status in enumerate(statuses, start=1):
            village, address, lat, lng = VILLAGES[i % len(VILLAGES)]
            claimed = status in {
                CaseRecord.Status.CLAIMED, CaseRecord.Status.IN_PROGRESS,
                CaseRecord.Status.PENDING_CONFIRM, CaseRecord.Status.CLOSED,
            }
            case = self._make_case(
                reference=f"FRC-{1043 + i}",
                submitted_by=random.choice(residents),
                village=village,
                address=f"Lot {random.randint(100, 9000)}, {address}",
                lat=lat + random.uniform(-0.01, 0.01),
                lng=lng + random.uniform(-0.01, 0.01),
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
                verified_by=officer if status != CaseRecord.Status.SUBMITTED else None,
                claimed_by=orgs[i % len(orgs)] if claimed else None,
            )
            cases.append(case)

        # ---------------- score the VERIFIED cases with the ENGINE ----------------
        # Only cases an officer has actually looked at carry a score. Screen 17
        # is explicit that a request is checked "before it is scored and
        # released to the NGO queue", and the running system now does exactly
        # that (cases/services.py). Seeding a score onto a submitted case would
        # contradict the behaviour the demo is showing.
        UNSCORED = {CaseRecord.Status.SUBMITTED, CaseRecord.Status.NEEDS_INFO}
        for case in cases:
            if case.status not in UNSCORED:
                self._score(case, engine_rubric, version, now, officer)

        # ---------------- tasks ----------------
        for case in cases:
            if case.status in {CaseRecord.Status.IN_PROGRESS, CaseRecord.Status.PENDING_CONFIRM}:
                CaseTask.objects.create(
                    case=case, lead_user=volunteer,
                    title=f"Mud clearance and disinfection — {case.village}",
                    task_type=CaseTask.TaskType.CLEANUP,
                    status=CaseTask.Status.IN_PROGRESS,
                    assigned_at=now - timedelta(days=1),
                )
                CaseEventLog.objects.create(
                    case=case, actor_user=volunteer,
                    event_type=CaseEventLog.EventType.TASK_ASSIGNED,
                    detail=f"Cleanup task assigned to {volunteer.full_name}.",
                    created_at=now - timedelta(days=1),
                )

        if options["empty_log"]:
            removed = CaseEventLog.objects.all().delete()[0]
            self.stdout.write(
                self.style.WARNING(f"  audit log cleared ({removed} rows) — demo starts empty")
            )

        scored = [c for c in cases if c.score_total is not None]
        high = sum(1 for c in scored if c.score_total >= 70)
        self.stdout.write(
            self.style.SUCCESS(
                f"  cases — {len(cases)} seeded, {len(scored)} scored, {high} high priority "
                f"({len(cases) - len(scored)} awaiting verification, so unscored)"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(f"  #FRC-1042 scored {frc.score_total} by the engine ({frc.priority_band})")
        )
        self.stdout.write(self.style.SUCCESS(f"  events — {CaseEventLog.objects.count()} audit rows"))
        self.stdout.write("")
        self.stdout.write(f"  Demo logins (password: {DEMO_PASSWORD})")
        self.stdout.write(f"    officer   {officer.email}")
        self.stdout.write(f"    ngo lead  {volunteer.email}")
        self.stdout.write(f"    resident  {resident.email}")

    # ------------------------------------------------------------------

    def _make_case(self, *, reference, submitted_by, village, address, lat, lng,
                   description, damage_category, urgency, liveability, flood_depth,
                   access_level, needs, vulns, household_size, status, created_at,
                    verified_by=None, claimed_by=None):
        case = CaseRecord.objects.create(
            reference=reference, submitted_by_user=submitted_by,
            village=village, address=address, latitude=lat, longitude=lng,
            description=description, damage_category=damage_category,
            urgency=urgency, liveability=liveability, flood_depth=flood_depth,
            access_level=access_level, needs_flags=needs, vulnerability_flags=vulns,
            household_size=household_size, status=status, created_at=created_at,
            verified_by_user=verified_by, claimed_by_org=claimed_by,
            closed_at=created_at + timedelta(days=3) if status == CaseRecord.Status.CLOSED else None,
        )
        CaseEventLog.objects.create(
            case=case, actor_user=submitted_by,
            event_type=CaseEventLog.EventType.SUBMITTED,
            detail=f"Request submitted by {submitted_by.full_name}.",
            created_at=created_at,
        )
        if verified_by:
            CaseEventLog.objects.create(
                case=case, actor_user=verified_by,
                event_type=CaseEventLog.EventType.VERIFIED,
                detail="Household details confirmed against the district register.",
                created_at=created_at + timedelta(hours=6),
            )
        if claimed_by:
            CaseEventLog.objects.create(
                case=case, actor_user=verified_by,
                event_type=CaseEventLog.EventType.CLAIMED,
                detail=f"Case claimed by {claimed_by.name}.",
                created_at=created_at + timedelta(hours=12),
            )
        return case

    def _score(self, case, engine_rubric, version, now, officer):
        """Run the pure engine, then persist its result and its reasoning."""
        result = score_case(
            CaseScoreInput(
                urgency=case.urgency,
                liveability=case.liveability,
                flood_depth=case.flood_depth,
                access_level=case.access_level,
                needs_flags=tuple(case.needs_flags),
                vulnerability_flags=tuple(case.vulnerability_flags),
                created_at=case.created_at,
            ),
            engine_rubric,
            now=now,
        )
        case.score_total = result.total
        case.rubric_version = version
        case.save(update_fields=["score_total", "rubric_version"])

        criteria = {c.key: c for c in version.criteria.all()}
        for component in result.components:
            CaseScoreComponent.objects.create(
                case=case, criterion=criteria[component.key],
                points=component.points, reason=component.reason,
            )
        CaseEventLog.objects.create(
            case=case, actor_user=officer,
            event_type=CaseEventLog.EventType.SCORE_COMPUTED,
            detail=f"Priority {result.total} ({result.band}) under rubric {version.label}.",
            created_at=case.created_at + timedelta(hours=6, minutes=1),
        )
