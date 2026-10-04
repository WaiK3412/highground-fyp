"""Backfill duplicate checks, one village at a time.

    manage.py scan_duplicates [--dry-run] [--location-code CODE]

Every unordered pair of live cases in a village is compared once with rules-1.0.
Existing flags keep their matched rules or legacy score and status, including
officer decisions, so a rescan never reopens a dismissed pair. Villages are
independent: one failing leaves the others' results in place, and the command
exits non-zero. Output is counts only, never household details.

--dry-run writes nothing: no flags, no events, no pending or completed state.

Cases with no controlled village (legacy free-text records) are never
compared, so they stay "duplicate check pending" and cannot be verified. To
release one, an officer sets its village in the admin case form, then runs
`scan_duplicates --location-code <village code>`.
"""

from django.core.management.base import BaseCommand, CommandError

from cases.duplicate_services import scan_duplicate_area
from cases.models import CaseRecord, LocationArea


class Command(BaseCommand):
    help = "Compare live cases within each village and flag possible duplicates."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report counts; write nothing.")
        parser.add_argument("--location-code", help="Scan one village by its code.")

    def handle(self, *args, dry_run=False, location_code=None, **options):
        villages = LocationArea.objects.filter(level=LocationArea.Level.VILLAGE)
        if location_code:
            # Retired villages stay scannable: their historical cases still exist.
            villages = villages.filter(code=location_code)
            if not villages.exists():
                raise CommandError(f"{location_code} is not a village code.")
        else:
            villages = villages.filter(cases__isnull=False).distinct()

        totals = {"villages": 0, "examined": 0, "created": 0, "existing": 0, "failed": 0}
        for village in villages.order_by("pk"):
            try:
                result = scan_duplicate_area(village.pk, dry_run=dry_run)
            except Exception as exc:  # noqa: BLE001 — record and continue with other villages
                totals["failed"] += 1
                self.stderr.write(f"{village.code}: failed ({type(exc).__name__})")
                continue
            totals["villages"] += 1
            totals["examined"] += result.examined
            totals["created"] += result.created
            totals["existing"] += result.existing

        # Cases with no controlled village cannot be blocked into a comparison
        # set; they stay "check pending" until given one.
        skipped = CaseRecord.objects.filter(location_area__isnull=True).count()
        verb = "would flag" if dry_run else "flagged"
        self.stdout.write(
            f"{'[dry run] ' if dry_run else ''}{totals['villages']} villages scanned, "
            f"{totals['examined']} pairs compared, {verb} {totals['created']}, "
            f"{totals['existing']} already recorded, {skipped} cases skipped "
            f"(no controlled village), {totals['failed']} villages failed."
        )
        if totals["failed"]:
            raise CommandError(f"{totals['failed']} village scan(s) failed.")
