"""Shared pure normalisation, inputs and geography for duplicate rules (ADR-019)."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass


# --- Normalisation ----------------------------------------------------------

# Whole-token expansions only, so "kg" becomes "kampung" but "kgs" is untouched.
# Sources: common Malaysian postal/informal abbreviations (report §2.4.2).
MALAY_ABBREVIATIONS = {
    "kg": "kampung",
    "kpg": "kampung",
    "jln": "jalan",
    "tmn": "taman",
    "lrg": "lorong",
    "lor": "lorong",
    "sg": "sungai",
    "bkt": "bukit",
    "spg": "simpang",
    "pkn": "pekan",
    "sek": "sekolah",
    "msjd": "masjid",
}


# English address words residents mix with Malay ones ("Masjid Road" versus
# "Jalan Masjid"). Mapping them onto one vocabulary lets code-switched
# addresses agree; word order is handled by the token-level comparison.
ADDRESS_SYNONYMS = {
    "road": "jalan",
    "rd": "jalan",
    "street": "jalan",
    "lane": "lorong",
    "village": "kampung",
    "mosque": "masjid",
    "river": "sungai",
    "hill": "bukit",
    "school": "sekolah",
    "junction": "simpang",
    "town": "pekan",
}


# Words that locate a house without identifying it; they would otherwise make
# every address in a village look alike.
ADDRESS_STOPWORDS = frozenset(
    {"lot", "no", "nombor", "number", "house", "rumah", "unit", "blok", "block",
     "near", "dekat", "depan", "belakang", "sebelah", "opposite", "behind",
     "off", "the", "di", "at"}
)


# Malay patronymic particles: "Ahmad bin Ismail" and "Ahmad Ismail" name the
# same person.
NAME_PARTICLES = frozenset({"bin", "binti", "bte", "bt", "a/l", "a/p", "al", "ap"})


def _is_word_char(ch: str) -> bool:
    # Letters, combining marks and digits. Marks matter: Tamil vowel signs are
    # category M, and splitting on them would break every Tamil word apart.
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def normalize_malay(text: str) -> str:
    """Fold case and punctuation, then expand Malay abbreviations.

    NFKC makes full-width and compatibility characters comparable; casefold is
    Unicode-aware lower-casing. Numbers are kept because they identify houses.
    """
    text = unicodedata.normalize("NFKC", text or "").casefold()
    cleaned = "".join(ch if _is_word_char(ch) else " " for ch in text)
    return " ".join(MALAY_ABBREVIATIONS.get(tok, tok) for tok in cleaned.split())


def normalize_phone(raw: str) -> str | None:
    """Return a Malaysian number in national form (0XXXXXXXXX), or None.

    "+60 12-555 0142", "60125550142" and "012-555 0142" all become
    "0125550142". A value that cannot be a Malaysian number is unusable rather
    than guessed at, so it supplies no evidence.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("60"):
        digits = "0" + digits[2:]
    if not digits.startswith("0") or not 9 <= len(digits) <= 11:
        return None
    return digits


# --- Geography --------------------------------------------------------------
EARTH_RADIUS_METRES = 6_371_000


def haversine_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two household pins, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_METRES * math.asin(min(1.0, math.sqrt(h)))


# --- Inputs and signals -----------------------------------------------------
@dataclass(frozen=True)
class DuplicateInput:
    """What the comparator may see of one case.

    Coordinates are the household's own pin only. A village centroid must
    never be passed here: every case in a village shares it, so it would make
    all neighbours look co-located.
    """

    description_text: str
    submitter_name: str = ""
    address: str = ""
    phone: str = ""
    latitude: float | None = None
    longitude: float | None = None
    damage_category: str = ""
    needs: tuple[str, ...] = ()
