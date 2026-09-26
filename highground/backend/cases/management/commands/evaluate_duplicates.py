"""Evaluate the duplicate comparator on the synthetic annotated fixture.

    manage.py evaluate_duplicates --split dev --sweep --write
    manage.py evaluate_duplicates --split heldout --write

Dev: sweeps thresholds under the pre-declared selection rule and records the
chosen values. They are then copied into cases/duplicates.py by hand (the
freeze). Held-out: scores with the frozen engine constants only, and refuses
to record results if those constants differ from the dev selection.

Reads only cases/evaluation/duplicate_pairs.json; never the database.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from cases import duplicate_evaluation as ev
from cases import duplicates as engine


class Command(BaseCommand):
    help = "Evaluate duplicate detection on synthetic fixtures (no live data)."

    def add_arguments(self, parser):
        parser.add_argument("--split", choices=["dev", "heldout"], required=True)
        parser.add_argument("--sweep", action="store_true",
                            help="Dev only: select thresholds with the declared rule.")
        parser.add_argument("--write", action="store_true",
                            help="Record this run in cases/evaluation/duplicate_results.json.")

    def handle(self, *args, split, sweep, write, **options):
        if sweep and split != "dev":
            raise CommandError("Thresholds may only be swept on the dev split.")

        data = ev.load_fixture()
        outcomes = ev.score_split(data, split)
        results = _read_results()

        if sweep:
            possible = ev.select_threshold(outcomes, ev.SELECTION_RULE["review_flag_min_precision"])
            match = ev.select_threshold(
                outcomes, ev.SELECTION_RULE["match_min_precision"], floor=possible["threshold"]
            )
            section = {
                "selection_rule": ev.SELECTION_RULE,
                "selected": {"possible": possible, "match": match},
                "sweep": ev.sweep_table(outcomes),
                "metrics_at_selected": ev.evaluate(outcomes, match["threshold"], possible["threshold"]),
            }
            self.stdout.write(
                f"Selected possible >= {possible['threshold']} "
                f"(precision {possible['precision']}, recall {possible['recall']}, "
                f"target met: {possible['target_met']})"
            )
            self.stdout.write(
                f"Selected match >= {match['threshold']} "
                f"(precision {match['precision']}, recall {match['recall']}, "
                f"target met: {match['target_met']})"
            )
            frozen = (engine.MATCH_THRESHOLD, engine.POSSIBLE_THRESHOLD)
            if frozen != (match["threshold"], possible["threshold"]):
                self.stdout.write(self.style.WARNING(
                    f"Engine constants {frozen} differ from this selection; "
                    "update cases/duplicates.py before the held-out run."
                ))
        else:
            if split == "heldout":
                selected = results.get("dev", {}).get("selected")
                frozen = (engine.MATCH_THRESHOLD, engine.POSSIBLE_THRESHOLD)
                if not selected or frozen != (selected["match"]["threshold"],
                                              selected["possible"]["threshold"]):
                    raise CommandError(
                        "Held-out evaluation needs thresholds selected on dev and frozen in "
                        "cases/duplicates.py. Run --split dev --sweep --write first."
                    )
            section = {"metrics": ev.evaluate(
                outcomes, engine.MATCH_THRESHOLD, engine.POSSIBLE_THRESHOLD
            )}
            metrics = section["metrics"]
            for label in ("review_flags", "match_only"):
                stats = metrics[label]["end_to_end"]
                self.stdout.write(
                    f"{label}: precision {stats['precision']}, recall {stats['recall']}, "
                    f"F1 {stats['f1']} (tp {stats['tp']}, fp {stats['fp']}, fn {stats['fn']})"
                )

        section.update({
            "fixture_sha256": data["_sha256"],
            "records": sum(
                1 for r in data["records"] if data["families"][r["family"]]["split"] == split
            ),
            "engine": ev.engine_settings(),
            "command": f"manage.py evaluate_duplicates --split {split}"
                       + (" --sweep" if sweep else "") + " --write",
        })
        if write:
            results["note"] = (
                "Synthetic fixture results. Not field validation; non-Malay and dialect "
                "examples still need native-speaker review."
            )
            results[split] = section
            ev.RESULTS_PATH.write_text(
                json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.stdout.write(f"Recorded in {ev.RESULTS_PATH.name}")


def _read_results() -> dict:
    if ev.RESULTS_PATH.exists():
        return json.loads(ev.RESULTS_PATH.read_text(encoding="utf-8"))
    return {}
