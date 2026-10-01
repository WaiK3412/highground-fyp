"""Offline evaluation of the duplicate comparator on synthetic, annotated records.

Pure Python like cases/duplicates.py: it reads the fixture as plain data and
never touches the database, so no resident's information enters an experiment.

Protocol (fixed before any held-out result was seen):
- Records carry a household id; two records are duplicates exactly when they
  share it. Every pair within a split is therefore labelled.
- Families (a household's reports plus their distractors) are assigned wholly
  to "dev" or "heldout", so a paraphrase cannot appear on both sides.
- Blocking mirrors the live service: only records in the same village are
  compared, using that village's descriptions as the TF-IDF corpus. A true
  duplicate filed under another village is counted as lost to blocking.
- Thresholds are chosen on dev only with SELECTION_RULE, then frozen in
  cases/duplicates.py before the held-out split is scored.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from cases.duplicates import (
    ENGINE_VERSION,
    DuplicateInput,
    build_tfidf_corpus,
    classify_score,
    compare_cases,
)
from cases.duplicate_rules import compare_by_rules

FIXTURE_PATH = Path(__file__).parent / "evaluation" / "duplicate_pairs.json"
RESULTS_PATH = Path(__file__).parent / "evaluation" / "duplicate_results.json"

# Declared before looking at dev results. False merges close a real
# household's request, so precision is constrained and recall maximised.
SELECTION_RULE = {
    "review_flag_min_precision": 0.95,
    "match_min_precision": 0.99,
    "objective": "maximise recall subject to the precision floor",
    "tie_break": "higher threshold (fewer flags)",
    "if_infeasible": "take the highest-precision threshold (ties: higher recall) and report target_met=false",
    "grid": "0.0 to 100.0 in steps of 0.5",
}
THRESHOLD_GRID = [step / 2 for step in range(0, 201)]


@dataclass(frozen=True)
class PairOutcome:
    record_a: str
    record_b: str
    duplicate: bool
    blocked: bool
    score: float | None
    stratum: str


def load_fixture(path: Path = FIXTURE_PATH) -> dict:
    raw = path.read_bytes()
    data = json.loads(raw)
    _validate(data)
    data["_sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def _validate(data: dict) -> None:
    families = data["families"]
    ids, household_family = set(), {}
    for record in data["records"]:
        if record["id"] in ids:
            raise ValueError(f"Duplicate record id {record['id']}")
        ids.add(record["id"])
        if record["family"] not in families:
            raise ValueError(f"{record['id']} names unknown family {record['family']}")
        family = household_family.setdefault(record["household"], record["family"])
        if family != record["family"]:
            # A household split across families could leak between splits.
            raise ValueError(f"Household {record['household']} spans families")
    for key, family in families.items():
        if family["split"] not in ("dev", "heldout"):
            raise ValueError(f"Family {key} has unknown split {family['split']}")


def to_input(record: dict) -> DuplicateInput:
    return DuplicateInput(
        description_text=record.get("description") or "",
        submitter_name=record.get("submitter_name") or "",
        address=record.get("address") or "",
        phone=record.get("phone") or "",
        latitude=record.get("latitude"),
        longitude=record.get("longitude"),
        damage_category=record.get("damage_category") or "",
        needs=tuple(record.get("needs") or ()),
    )


LANGUAGE_GROUP = {"ms": "ms", "ms-dialect": "ms", "ms-en": "ms-en", "en": "en", "zh": "zh", "ta": "ta"}


def stratum(lang_a: str, lang_b: str) -> str:
    """Language pairing, so cross-language weakness is not averaged away."""
    pair = {LANGUAGE_GROUP.get(lang_a, lang_a), LANGUAGE_GROUP.get(lang_b, lang_b)}
    if "zh" in pair:
        return "chinese"
    if "ta" in pair:
        return "tamil"
    if "ms-en" in pair:
        return "code_switched"
    if pair == {"ms", "en"}:
        return "malay_english"
    if pair == {"en"}:
        return "english"
    return "malay"


def score_split(data: dict, split: str, **thresholds) -> list[PairOutcome]:
    """Score every pair of records in one split, applying village blocking."""
    families = data["families"]
    records = [r for r in data["records"] if families[r["family"]]["split"] == split]

    corpora = {}
    for record in records:
        corpora.setdefault(record["village_code"], []).append(record.get("description") or "")
    idf_by_village = {village: build_tfidf_corpus(texts) for village, texts in corpora.items()}

    outcomes = []
    for a, b in combinations(records, 2):
        duplicate = a["household"] == b["household"]
        blocked = a["village_code"] != b["village_code"]
        if blocked and not duplicate:
            # Distinct households in different villages are never compared and
            # never flagged; counting them would only inflate true negatives.
            continue
        score = None
        if not blocked:
            idf = idf_by_village[a["village_code"]]
            score = compare_cases(to_input(a), to_input(b), idf, **thresholds).score
        outcomes.append(PairOutcome(
            a["id"], b["id"], duplicate, blocked, score, stratum(a["language"], b["language"])
        ))
    return outcomes


def score_split_rules(data: dict, split: str) -> list[PairOutcome]:
    """rules-1.0 on the same pairs and blocking as score_split.

    The rules give yes/no, not a score, so a flagged pair scores 100 and an
    unflagged one 0; confusion(outcomes, 50.0) then counts them unchanged.
    """
    families = data["families"]
    records = [r for r in data["records"] if families[r["family"]]["split"] == split]
    outcomes = []
    for a, b in combinations(records, 2):
        duplicate = a["household"] == b["household"]
        blocked = a["village_code"] != b["village_code"]
        if blocked and not duplicate:
            continue
        score = None
        if not blocked:
            score = 100.0 if compare_by_rules(to_input(a), to_input(b)).needs_review else 0.0
        outcomes.append(PairOutcome(
            a["id"], b["id"], duplicate, blocked, score, stratum(a["language"], b["language"])
        ))
    return outcomes


def confusion(outcomes: list[PairOutcome], threshold: float, end_to_end: bool = False) -> dict:
    """Counts and rates for "score >= threshold" as the positive prediction.

    In-block figures judge the comparator; end-to-end figures also count
    duplicates that blocking kept apart as false negatives.
    """
    tp = fp = fn = tn = 0
    for outcome in outcomes:
        if outcome.blocked:
            if end_to_end and outcome.duplicate:
                fn += 1
            continue
        flagged = outcome.score >= threshold
        if outcome.duplicate:
            tp, fn = (tp + 1, fn) if flagged else (tp, fn + 1)
        else:
            fp, tn = (fp + 1, tn) if flagged else (fp, tn + 1)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": _r(precision), "recall": _r(recall), "f1": _r(f1),
        "flagged": tp + fp, "duplicates": tp + fn, "pairs": tp + fp + fn + tn,
    }


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def select_threshold(outcomes: list[PairOutcome], min_precision: float, floor: float = 0.0) -> dict:
    """Apply SELECTION_RULE on in-block dev pairs; ``floor`` keeps match >= possible."""
    candidates = [(t, confusion(outcomes, t)) for t in THRESHOLD_GRID if t >= floor]
    feasible = [
        (t, c) for t, c in candidates
        if c["precision"] is not None and c["precision"] >= min_precision
    ]
    if feasible:
        # Highest recall; among equal recall the higher threshold.
        threshold, stats = max(feasible, key=lambda tc: (tc[1]["recall"] or 0, tc[0]))
        return {"threshold": threshold, "target_met": True, **stats}
    scored = [(t, c) for t, c in candidates if c["precision"] is not None]
    threshold, stats = max(scored, key=lambda tc: (tc[1]["precision"], tc[1]["recall"] or 0))
    return {"threshold": threshold, "target_met": False, **stats}


def sweep_table(outcomes: list[PairOutcome], step: float = 5.0) -> list[dict]:
    """A coarse precision-recall curve for the report figure."""
    rows = []
    t = 0.0
    while t <= 100.0:
        rows.append({"threshold": t, **confusion(outcomes, t)})
        t += step
    return rows


def evaluate(outcomes: list[PairOutcome], match_threshold: float, possible_threshold: float) -> dict:
    """Metrics for review flags (possible or match) and for match alone."""
    classify_score(match_threshold, match_threshold, possible_threshold)  # validates ordering

    def block(threshold):
        section = {
            "in_block": confusion(outcomes, threshold),
            "end_to_end": confusion(outcomes, threshold, end_to_end=True),
            "by_language": {},
        }
        for name in sorted({o.stratum for o in outcomes}):
            subset = [o for o in outcomes if o.stratum == name]
            section["by_language"][name] = confusion(subset, threshold, end_to_end=True)
        return section

    return {
        "review_flags": block(possible_threshold),
        "match_only": block(match_threshold),
        "lost_to_blocking": sum(1 for o in outcomes if o.blocked and o.duplicate),
    }


def engine_settings() -> dict:
    """Everything that determines a score, recorded beside each result."""
    from cases import duplicates as engine

    return {
        "engine_version": ENGINE_VERSION,
        "m_u_probabilities": engine.M_U_PROBABILITIES,
        "bins": {
            "name": engine.NAME_BINS,
            "address": engine.ADDRESS_BINS,
            "description": engine.DESCRIPTION_BINS,
            "distance_metres": engine.DISTANCE_BINS,
            "needs": "jaccard >= 0.5 most; > 0 some; 0 none",
        },
        "normalisation": "score = 100 * clamp(sum log2(m/u) / maximum positive weight, 0, 1), rounded to 2 dp",
        "maximum_positive_weight": round(engine.MAXIMUM_POSITIVE_WEIGHT, 4),
        "match_threshold": engine.MATCH_THRESHOLD,
        "possible_threshold": engine.POSSIBLE_THRESHOLD,
    }
