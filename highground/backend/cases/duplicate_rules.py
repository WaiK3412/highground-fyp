"""Deterministic duplicate rules (rules-1.0), report §3.7.2 / ADR-019.

No Django imports on purpose. A pair already shares a controlled village
(the blocking step in duplicate_services); it is flagged for officer review
if ANY rule below fires. There are no weights or probabilities.

Precedent: Crisis Cleanup's production rule, read from its source
(crisiscleanup-2, app/models/legacy/legacy_site.rb):
  "Lat/Lon OR Name Metaphone OR Phone OR (Street Number AND Address Metaphone
   AND (City Metaphone OR County Metaphone OR Zip))"
Adaptations, stated in the report: the village block replaces the city/
county/zip condition, and names are compared exactly after Malay
normalisation because English Metaphone suits Malay names poorly.

The vocabularies and phone normaliser are reused from cases/duplicates.py
(the retired dup-1.1 engine), so "Jln" and "Jalan", or "+60 12…" and "012…",
compare equal here as they did there. Name and address tokenising is done
here instead, fixing three defects the 2 Oct audits reproduced (Tamil vowel
signs, "88A" vs "88 A", "12/3" vs "3/12") without changing the retired
engine's recorded evaluation.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .duplicates import (
    ADDRESS_STOPWORDS,
    ADDRESS_SYNONYMS,
    NAME_PARTICLES,
    haversine_metres,
    DuplicateInput,
    normalize_malay,
    normalize_phone,
)

RULES_VERSION = "rules-1.0"
RULE_KEYS = ("same_pin", "same_name", "same_phone", "same_house_and_address")

RULE_TEXT = {
    "same_pin": "Household pins are at the same spot (equal to 4 decimal places, about 11 m)",
    "same_name": "Same submitter name",
    "same_phone": "Same phone number",
    "same_house_and_address": "Same house or lot number and the same address",
}


@dataclass(frozen=True)
class RuleHit:
    rule: str
    text: str


@dataclass(frozen=True)
class RuleResult:
    hits: tuple[RuleHit, ...]

    @property
    def needs_review(self) -> bool:
        return bool(self.hits)


def compare_by_rules(a: DuplicateInput, b: DuplicateInput) -> RuleResult:
    """Return every rule the pair meets, in RULE_KEYS order."""
    fired = {
        "same_pin": _same_pin(a, b),
        "same_name": _same_name(a, b),
        "same_phone": _same_phone(a, b),
        "same_house_and_address": _same_house_and_address(a, b),
    }
    return RuleResult(tuple(RuleHit(key, RULE_TEXT[key]) for key in RULE_KEYS if fired[key]))


# Each rule returns False on missing data: two blanks are not evidence that
# two households are the same.


def _same_pin(a: DuplicateInput, b: DuplicateInput) -> bool:
    # `None in (...)`, not truthiness: latitude 0.0 is a real coordinate.
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return False
    return (round(a.latitude, 4), round(a.longitude, 4)) == (
        round(b.latitude, 4), round(b.longitude, 4)
    )


def name_tokens(name: str) -> list[str]:
    """Case-folded name words without Malay particles (bin, binti, a/l…).

    Keeps every letter, combining mark and digit. The regex word class drops Tamil
    vowel signs (category M), which made different names compare equal;
    Unicode UAX #29 keeps such marks with their base character.
    """
    text = unicodedata.normalize("NFKC", name or "").casefold()
    cleaned = "".join(
        ch if unicodedata.category(ch)[0] in ("L", "M", "N") or ch == "/" else " "
        for ch in text
    )
    return [tok for tok in cleaned.split() if tok not in NAME_PARTICLES]


def address_parts(address: str) -> tuple[list[str], tuple[str, ...]]:
    """Sorted address words, and the house/unit numbers in written order.

    Conservative on purpose: "12/3" stays one identifier, so it never equals
    "3/12"; a letter written apart after lot/no ("Lot 88 A") rejoins its
    number ("88a"). Word order may vary; number order may not.
    """
    text = unicodedata.normalize("NFKC", address or "").casefold()
    text = re.sub(r"\b(\d+)\s*/\s*(\d+)\b", r"\1slash\2", text)
    text = re.sub(r"\b(lot|no|nombor)\s+(\d+)\s*([a-z])\b", r"\1 \2\3", text)
    words, numbers = [], []
    for token in normalize_malay(text).split():
        token = ADDRESS_SYNONYMS.get(token, token)
        if any(ch.isdigit() for ch in token):
            numbers.append(token)
        elif token not in ADDRESS_STOPWORDS:
            words.append(token)
    return sorted(words), tuple(numbers)


def _same_name(a: DuplicateInput, b: DuplicateInput) -> bool:
    name_a, name_b = name_tokens(a.submitter_name), name_tokens(b.submitter_name)
    return bool(name_a) and name_a == name_b


def _same_phone(a: DuplicateInput, b: DuplicateInput) -> bool:
    phone_a, phone_b = normalize_phone(a.phone), normalize_phone(b.phone)
    return phone_a is not None and phone_a == phone_b


def _same_house_and_address(a: DuplicateInput, b: DuplicateInput) -> bool:
    # House numbers are compared exactly, so Lot 88 never matches Lot 89.
    words_a, numbers_a = address_parts(a.address)
    words_b, numbers_b = address_parts(b.address)
    return bool(numbers_a) and numbers_a == numbers_b and bool(words_a) and words_a == words_b


# --- What disagrees (shown to the officer; never decides a flag) ------------

CONTRADICTION_TEXT = {
    "different_name": "Different submitter names",
    "different_phone": "Different phone numbers",
    "different_house_number": "Different house or lot numbers",
}


def contradictions(a: DuplicateInput, b: DuplicateInput) -> tuple[RuleHit, ...]:
    """Fields present on both cases that disagree.

    Record linkage treats disagreement as evidence too (Fellegi & Sunter
    1969). Here it is only displayed: a relative may use another phone, so a
    disagreement does not veto a flag. Missing data is not a disagreement.
    """
    found = []
    name_a, name_b = name_tokens(a.submitter_name), name_tokens(b.submitter_name)
    if name_a and name_b and name_a != name_b:
        found.append("different_name")
    phone_a, phone_b = normalize_phone(a.phone), normalize_phone(b.phone)
    if phone_a and phone_b and phone_a != phone_b:
        found.append("different_phone")
    numbers_a, numbers_b = address_parts(a.address)[1], address_parts(b.address)[1]
    if numbers_a and numbers_b and numbers_a != numbers_b:
        found.append("different_house_number")
    return tuple(RuleHit(key, CONTRADICTION_TEXT[key]) for key in found)


def pin_distance_metres(a: DuplicateInput, b: DuplicateInput) -> int | None:
    """Distance between the two household pins, rounded to the metre."""
    if None in (a.latitude, a.longitude, b.latitude, b.longitude):
        return None
    return round(haversine_metres(a.latitude, a.longitude, b.latitude, b.longitude))
