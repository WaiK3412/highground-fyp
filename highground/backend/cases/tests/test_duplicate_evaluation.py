"""Tests for the duplicate-evaluation harness (no database).

Traceability: FR14 evaluation design (report §2.4.2, §3.3.5) — dev-only
threshold selection, household-level splits, blocking losses counted.
"""

from unittest import TestCase

from cases import duplicate_evaluation as ev
from cases.duplicate_evaluation import PairOutcome


def record(rid, household, family, village="V1", language="ms", **fields):
    base = {
        "id": rid, "household": household, "family": family, "village_code": village,
        "language": language, "submitter_name": "", "phone": "", "address": "",
        "latitude": None, "longitude": None, "damage_category": "", "needs": [],
        "description": "",
    }
    base.update(fields)
    return base


def dataset(records, families):
    return {"families": families, "records": records}


class ValidationTests(TestCase):
    def test_household_spanning_families_is_rejected(self):
        data = dataset(
            [record("R1", "H1", "F1"), record("R2", "H1", "F2")],
            {"F1": {"split": "dev"}, "F2": {"split": "heldout"}},
        )
        with self.assertRaises(ValueError):
            ev._validate(data)

    def test_duplicate_ids_are_rejected(self):
        data = dataset([record("R1", "H1", "F1"), record("R1", "H2", "F1")], {"F1": {"split": "dev"}})
        with self.assertRaises(ValueError):
            ev._validate(data)


class ScoringTests(TestCase):
    def setUp(self):
        same = dict(submitter_name="Ahmad Ismail", phone="0125550142",
                    address="Lot 88 Jalan Masjid", description="dapur rosak air paras pinggang")
        self.data = dataset(
            [
                record("R1", "H1", "F1", **same),
                record("R2", "H1", "F1", **same),
                record("R3", "H1", "F1", village="V2", **same),   # filed elsewhere
                record("R4", "H2", "F1", village="V2", submitter_name="Lim Mei"),
                record("R5", "H3", "F2", **same),                  # other split
            ],
            {"F1": {"split": "dev"}, "F2": {"split": "heldout"}},
        )

    def test_splits_are_separate_and_blocking_is_counted(self):
        outcomes = ev.score_split(self.data, "dev")
        pairs = {(o.record_a, o.record_b): o for o in outcomes}
        self.assertNotIn(("R1", "R5"), pairs)             # R5 is held-out
        self.assertTrue(pairs[("R1", "R2")].duplicate)
        self.assertFalse(pairs[("R1", "R2")].blocked)
        self.assertTrue(pairs[("R1", "R3")].blocked)       # same household, other village
        self.assertIsNone(pairs[("R1", "R3")].score)
        # A distinct household in another village is never compared or counted.
        self.assertNotIn(("R1", "R4"), pairs)
        self.assertIn(("R3", "R4"), pairs)

    def test_end_to_end_counts_blocked_duplicates_as_missed(self):
        outcomes = ev.score_split(self.data, "dev")
        in_block = ev.confusion(outcomes, 0.0)
        end_to_end = ev.confusion(outcomes, 0.0, end_to_end=True)
        self.assertEqual(end_to_end["fn"] - in_block["fn"], 2)   # R1-R3, R2-R3


class MetricTests(TestCase):
    def outcomes(self, *rows):
        return [PairOutcome(f"a{i}", f"b{i}", dup, False, score, "malay")
                for i, (dup, score) in enumerate(rows)]

    def test_confusion_counts_and_rates(self):
        outs = self.outcomes((True, 80), (True, 40), (False, 60), (False, 10))
        stats = ev.confusion(outs, 50)
        self.assertEqual((stats["tp"], stats["fn"], stats["fp"], stats["tn"]), (1, 1, 1, 1))
        self.assertEqual(stats["precision"], 0.5)
        self.assertEqual(stats["recall"], 0.5)
        self.assertEqual(stats["f1"], 0.5)

    def test_no_flags_means_precision_is_undefined(self):
        stats = ev.confusion(self.outcomes((True, 10)), 50)
        self.assertIsNone(stats["precision"])
        self.assertEqual(stats["recall"], 0.0)

    def test_selection_maximises_recall_under_the_precision_floor(self):
        outs = self.outcomes((True, 90), (True, 70), (False, 60), (True, 50))
        chosen = ev.select_threshold(outs, 0.95)
        # 70.0 and everything up to 70 flags both 90 and 70 with no false
        # positive; the tie on recall goes to the higher threshold.
        self.assertEqual(chosen["threshold"], 70.0)
        self.assertTrue(chosen["target_met"])
        self.assertEqual(chosen["recall"], round(2 / 3, 4))

    def test_infeasible_target_is_reported_not_hidden(self):
        outs = self.outcomes((False, 90), (True, 80))
        chosen = ev.select_threshold(outs, 0.95)
        self.assertFalse(chosen["target_met"])

    def test_language_strata(self):
        self.assertEqual(ev.stratum("zh", "en"), "chinese")
        self.assertEqual(ev.stratum("ta", "ms"), "tamil")
        self.assertEqual(ev.stratum("ms", "en"), "malay_english")
        self.assertEqual(ev.stratum("ms-dialect", "ms"), "malay")
        self.assertEqual(ev.stratum("ms-en", "ms"), "code_switched")
