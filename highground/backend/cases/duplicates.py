"""Pure, explainable duplicate-request comparison (report §2.4.2, §3.7.8) — RETIRED.

The app now flags pairs with cases/duplicate_rules.py (rules-1.0, ADR-019),
which reuses the normalisers below. The weighted comparator (dup-1.1) and its
tests are kept, unused, as the evaluated alternative in the report.

No Django imports on purpose: two cases and their village's description corpus
arrive as plain values, so every rule here can be unit-tested and hand-checked.

The comparator follows the Fellegi-Sunter record-linkage pattern. Each signal
(name, address, phone, description, ...) is observed at one agreement level,
and that level contributes log2(m / u) evidence, where

    m = how often duplicates show this level, and
    u = how often different households in the same village show it.

The m/u values below are hand-set assumptions for a village block, not
probabilities learned or validated from field data. A missing field
contributes exactly zero, so absent data never counts for or against a match.

The summed evidence is scaled to a 0-100 *evidence index* using a fixed,
engine-wide maximum. It is not a probability. Both "match" and "possible"
send the pair to an officer; nothing here closes or merges a case.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

ENGINE_VERSION = "dup-1.1"

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

DESCRIPTION_STOPWORDS = frozenset(
    {"dan", "di", "yang", "ke", "dari", "untuk", "ini", "itu", "ada", "dengan",
     "kami", "saya", "the", "and", "a", "an", "of", "to", "in", "is", "are",
     "was", "we", "our", "my", "i", "it", "on", "for", "with", "at"}
)


def _is_word_char(ch: str) -> bool:
    # Letters, combining marks and digits. Marks matter: Tamil vowel signs are
    # category M, and splitting on them would break every Tamil word apart.
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF


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


def _name_tokens(name: str) -> list[str]:
    text = unicodedata.normalize("NFKC", name or "").casefold()
    text = re.sub(r"\ba/([lp])\b", r"a/\1", text)
    tokens = re.split(r"[^\w/]+", text)
    return [tok for tok in tokens if tok and tok not in NAME_PARTICLES]


def _address_parts(address: str) -> tuple[list[str], frozenset[str]]:
    """Split an address into comparable words and house/lot numbers.

    Numbers are compared exactly and separately: "Lot 88" and "Lot 89" are
    one keystroke apart for Jaro-Winkler, yet they are different houses.
    """
    words, numbers = [], set()
    for tok in normalize_malay(address).split():
        tok = ADDRESS_SYNONYMS.get(tok, tok)
        if any(ch.isdigit() for ch in tok):
            numbers.add(tok)
        elif tok not in ADDRESS_STOPWORDS:
            words.append(tok)
    return words, frozenset(numbers)


# --- String similarity ------------------------------------------------------

JARO_WINKLER_PREFIX_CAP = 4
JARO_WINKLER_SCALING = 0.1


def jaro(s1: str, s2: str) -> float:
    """Jaro similarity (Jaro 1989): shared characters and transpositions."""
    if s1 == s2:
        return 1.0 if s1 else 0.0
    if not s1 or not s2:
        return 0.0

    window = max(max(len(s1), len(s2)) // 2 - 1, 0)
    s1_matched = [False] * len(s1)
    s2_matched = [False] * len(s2)
    matches = 0
    for i, ch in enumerate(s1):
        low, high = max(0, i - window), min(i + window + 1, len(s2))
        for j in range(low, high):
            if not s2_matched[j] and s2[j] == ch:
                s1_matched[i] = s2_matched[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0

    s2_in_order = [s2[j] for j in range(len(s2)) if s2_matched[j]]
    s1_in_order = [s1[i] for i in range(len(s1)) if s1_matched[i]]
    half_transpositions = sum(a != b for a, b in zip(s1_in_order, s2_in_order))
    t = half_transpositions / 2
    return (matches / len(s1) + matches / len(s2) + (matches - t) / matches) / 3


def jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler (Winkler 1990) with the standard 0.1 boost per shared
    prefix character, capped at four characters.

    The boost is applied whatever the Jaro value (no 0.7 boost threshold), the
    common textbook convention; e.g. MARTHA/MARHTA = 0.961111.
    """
    base = jaro(s1, s2)
    prefix = 0
    for a, b in zip(s1[:JARO_WINKLER_PREFIX_CAP], s2[:JARO_WINKLER_PREFIX_CAP]):
        if a != b:
            break
        prefix += 1
    return base + prefix * JARO_WINKLER_SCALING * (1 - base)


def token_similarity(tokens_a: list[str], tokens_b: list[str]) -> float | None:
    """Symmetric Monge-Elkan: each word's best Jaro-Winkler partner, averaged.

    Comparing word by word tolerates reordering ("Kampung Baru Jalan Masjid"
    versus "Jalan Masjid Kampung Baru") while Jaro-Winkler still absorbs typos
    inside each word (Christen 2012, ch. 5). Averaging both directions keeps
    the measure symmetric.
    """
    if not tokens_a or not tokens_b:
        return None

    def directed(xs, ys):
        return sum(max(jaro_winkler(x, y) for y in ys) for x in xs) / len(xs)

    return (directed(tokens_a, tokens_b) + directed(tokens_b, tokens_a)) / 2


def contained_similarity(shorter: list[str], longer: list[str]) -> float:
    """One-directional Monge-Elkan: how well every word of ``shorter`` finds a
    close partner in ``longer``. Used only when house numbers already agree."""
    if not shorter or not longer:
        return 0.0
    return sum(max(jaro_winkler(x, y) for y in longer) for x in shorter) / len(shorter)


# --- Description TF-IDF -----------------------------------------------------


def tokenize_description(text: str) -> list[str]:
    """Deterministic, Unicode-aware word tokens for TF-IDF.

    Chinese is written without spaces, so each run of Han characters becomes
    overlapping character bigrams, a crude but common substitute for a word
    segmenter. Tamil and Malay split on spaces. Cross-language pairs share
    few tokens, so their description evidence is weak by design; the
    structured signals carry those pairs.
    """
    tokens = []
    for word in normalize_malay(text).split():
        if word in DESCRIPTION_STOPWORDS:
            continue
        # A mixed word such as "banjir水灾" splits into its Han and non-Han runs.
        for run in HAN_RUN.findall(word):
            tokens.extend(_han_bigrams(run) if _is_cjk(run[0]) else [run])
    return tokens


HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\u3400-\u4dbf\u4e00-\u9fff]+")


def _han_bigrams(run: str) -> list[str]:
    if len(run) == 1:
        return [run]
    return [run[i:i + 2] for i in range(len(run) - 1)]


def build_tfidf_corpus(descriptions: list[str]) -> dict[str, float]:
    """Smoothed inverse document frequency for one village's descriptions.

    idf(t) = ln((1 + N) / (1 + df(t))) + 1, the smoothed form used by
    scikit-learn: it is never zero and never divides by zero. Each case counts
    once towards df, however often it repeats a word.
    """
    n = len(descriptions)
    df = Counter()
    for text in descriptions:
        df.update(set(tokenize_description(text)))
    return {term: math.log((1 + n) / (1 + count)) + 1 for term, count in df.items()}


def tfidf_vector(text: str, idf: dict[str, float]) -> dict[str, float]:
    """Raw term counts weighted by idf. A term missing from the corpus gets
    the maximum idf, as if it appeared in no other case."""
    unseen = max(idf.values(), default=1.0)
    counts = Counter(tokenize_description(text))
    return {term: count * idf.get(term, unseen) for term, count in counts.items()}


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float | None:
    """Cosine of two sparse vectors; None when either has no terms."""
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return None
    dot = sum(value * vec_b.get(term, 0.0) for term, value in vec_a.items())
    return dot / (norm_a * norm_b)


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


@dataclass(frozen=True)
class DuplicateSignals:
    """Observed comparisons for one pair. None means "unavailable"."""

    name_similarity: float | None = None
    address_similarity: float | None = None
    address_numbers: str | None = None       # "agree" | "conflict" | None
    phone: str | None = None                 # "agree" | "disagree" | None
    description_cosine: float | None = None
    distance_metres: float | None = None
    damage: str | None = None                # "agree" | "disagree" | None
    needs_overlap: float | None = None       # Jaccard index


def compare_signals(
    a: DuplicateInput, b: DuplicateInput, idf: dict[str, float]
) -> DuplicateSignals:
    """Measure every signal for a pair; ``idf`` comes from the village block."""
    words_a, numbers_a = _address_parts(a.address)
    words_b, numbers_b = _address_parts(b.address)
    if numbers_a and numbers_b:
        # Any number on one side without a partner on the other means the
        # addresses name different houses (Lot 88 vs Lot 89). A number present
        # on only one address is merely missing detail.
        address_numbers = "agree" if numbers_a == numbers_b else (
            "conflict" if numbers_a - numbers_b and numbers_b - numbers_a else None
        )
    else:
        address_numbers = None

    address_similarity = token_similarity(words_a, words_b)
    if address_numbers == "agree" and address_similarity is not None:
        # With the same house number, a shorter address is usually the longer
        # one with parts left out ("Lot 800, Tok Uban" versus "Lot 800 Kampung
        # Tok Uban, Pasir Mas"). Omission is not disagreement, so the shorter
        # address is judged by how well it fits inside the longer one.
        shorter, longer = sorted((words_a, words_b), key=len)
        address_similarity = max(address_similarity, contained_similarity(shorter, longer))

    phone_a, phone_b = normalize_phone(a.phone), normalize_phone(b.phone)
    phone = None
    if phone_a and phone_b:
        phone = "agree" if phone_a == phone_b else "disagree"

    distance = None
    if None not in (a.latitude, a.longitude, b.latitude, b.longitude):
        distance = haversine_metres(a.latitude, a.longitude, b.latitude, b.longitude)

    damage = None
    if a.damage_category and b.damage_category:
        damage = "agree" if a.damage_category == b.damage_category else "disagree"

    needs_overlap = None
    needs_a, needs_b = set(a.needs), set(b.needs)
    if needs_a and needs_b:
        needs_overlap = len(needs_a & needs_b) / len(needs_a | needs_b)

    return DuplicateSignals(
        name_similarity=token_similarity(_name_tokens(a.submitter_name), _name_tokens(b.submitter_name)),
        address_similarity=address_similarity,
        address_numbers=address_numbers,
        phone=phone,
        description_cosine=cosine_similarity(
            tfidf_vector(a.description_text, idf), tfidf_vector(b.description_text, idf)
        ),
        distance_metres=distance,
        damage=damage,
        needs_overlap=needs_overlap,
    )


# --- Fellegi-Sunter evidence ------------------------------------------------

# (m, u) per agreement level: m = share of duplicate pairs in a village block
# at this level, u = share of different-household pairs at it. Hand-set from
# reasoning about flood requests, not fitted to data:
# - a relative may file for a household, so different names and phones are
#   only mild evidence against (m stays well above zero);
# - most requests in a flood report the same damage, so damage agreement is
#   weak evidence (u is high);
# - exact phones, house numbers and household pins rarely coincide by chance
#   (u is low), so they are strong evidence.
# dup-1.1 revised four assumptions after inspecting development-split misses
# only (the held-out split had not been scored); see duplicate_results.json:
# - name "different" m 0.20 -> 0.35: relatives filing is common, not rare;
# - description "different" m 0.15 -> 0.35: a relative or a different language
#   describes the same damage in different words;
# - distance "within_50m" u 0.01 -> 0.08: kampung neighbours are 20-40 m apart
#   and phone GPS is only accurate to tens of metres;
# - containment for addresses with agreeing house numbers (compare_signals).
M_U_PROBABILITIES = {
    "name": {"same": (0.60, 0.02), "similar": (0.20, 0.08), "different": (0.35, 0.90)},
    "address": {"same": (0.65, 0.05), "similar": (0.25, 0.15), "different": (0.10, 0.80)},
    "address_numbers": {"agree": (0.70, 0.02), "conflict": (0.03, 0.60)},
    "phone": {"agree": (0.55, 0.01), "disagree": (0.45, 0.99)},
    "description": {"similar": (0.50, 0.03), "related": (0.35, 0.17), "different": (0.35, 0.80)},
    "distance": {"within_50m": (0.70, 0.08), "within_200m": (0.20, 0.05),
                 "within_1km": (0.07, 0.20), "further": (0.03, 0.74)},
    "damage": {"agree": (0.90, 0.35), "disagree": (0.10, 0.65)},
    "needs": {"most": (0.70, 0.30), "some": (0.20, 0.30), "none": (0.10, 0.40)},
}

# Lower edges of each graded bin, checked from the top down.
NAME_BINS = ((0.95, "same"), (0.85, "similar"), (0.0, "different"))
ADDRESS_BINS = ((0.95, "same"), (0.85, "similar"), (0.0, "different"))
DESCRIPTION_BINS = ((0.60, "similar"), (0.30, "related"), (0.0, "different"))
DISTANCE_BINS = ((50, "within_50m"), (200, "within_200m"), (1000, "within_1km"))


def level_weight(signal: str, level: str) -> float:
    m, u = M_U_PROBABILITIES[signal][level]
    return math.log2(m / u)


# The largest possible total: every signal at its most favourable level. A
# fixed denominator means missing fields lower the score instead of being
# averaged away; a pair supported only by one field cannot reach 100.
MAXIMUM_POSITIVE_WEIGHT = sum(
    max(level_weight(signal, level) for level in levels)
    for signal, levels in M_U_PROBABILITIES.items()
)

# Evidence-index thresholds (0-100). Both send the pair to an officer.
# Frozen from the development split before held-out evaluation; see
# cases/evaluation/duplicate_results.json.
MATCH_THRESHOLD = 65.5
POSSIBLE_THRESHOLD = 35.0


@dataclass(frozen=True)
class Reason:
    signal: str
    effect: str           # "supports" | "against" | "neutral" | "missing"
    weight: float
    text: str


@dataclass
class DuplicateResult:
    raw_weight: float
    score: float
    classification: str   # "match" | "possible" | "non_match"
    reasons: list[Reason] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.classification != "non_match"


def _bin(value: float, bins) -> str:
    for lower, level in bins:
        if value >= lower:
            return level
    return bins[-1][1]


SIGNAL_TEXT = {
    ("name", "same"): "Submitter names match",
    ("name", "similar"): "Submitter names are similar",
    ("name", "different"): "Different submitter names (a relative may have filed)",
    ("address", "same"): "Addresses match after normalisation",
    ("address", "similar"): "Address spelling is similar",
    ("address", "different"): "Addresses differ",
    ("address_numbers", "agree"): "Same house or lot number",
    ("address_numbers", "conflict"): "Different house or lot numbers",
    ("phone", "agree"): "Same phone number",
    ("phone", "disagree"): "Different phone numbers (a relative may have filed)",
    ("description", "similar"): "Descriptions use many of the same distinctive words",
    ("description", "related"): "Descriptions share some distinctive words",
    ("description", "different"): "Descriptions share few distinctive words",
    ("distance", "within_50m"): "Household pins are within 50 m",
    ("distance", "within_200m"): "Household pins are within 200 m",
    ("distance", "within_1km"): "Household pins are 200 m to 1 km apart",
    ("distance", "further"): "Household pins are more than 1 km apart",
    ("damage", "agree"): "Same damage category",
    ("damage", "disagree"): "Different damage categories",
    ("needs", "most"): "Most requested needs overlap",
    ("needs", "some"): "Some requested needs overlap",
    ("needs", "none"): "No requested needs in common",
}

MISSING_TEXT = {
    "name": "Name unavailable",
    "address": "Address unavailable",
    "address_numbers": "House number missing on one or both requests",
    "phone": "Phone unavailable",
    "description": "Description unavailable",
    "distance": "Household pin unavailable",
    "damage": "Damage category unavailable",
    "needs": "Needs unavailable on one or both requests",
}


def _needs_level(overlap: float | None) -> str | None:
    if overlap is None:
        return None
    if overlap >= 0.5:
        return "most"
    return "some" if overlap > 0 else "none"


def signal_levels(signals: DuplicateSignals) -> dict[str, str | None]:
    """Map each measured value onto its agreement level (None = missing)."""
    distance = None
    if signals.distance_metres is not None:
        distance = next(
            (level for edge, level in DISTANCE_BINS if signals.distance_metres <= edge),
            "further",
        )
    return {
        "name": None if signals.name_similarity is None else _bin(signals.name_similarity, NAME_BINS),
        "address": None if signals.address_similarity is None
        else _bin(signals.address_similarity, ADDRESS_BINS),
        "address_numbers": signals.address_numbers,
        "phone": signals.phone,
        "description": None if signals.description_cosine is None
        else _bin(signals.description_cosine, DESCRIPTION_BINS),
        "distance": distance,
        "damage": signals.damage,
        "needs": _needs_level(signals.needs_overlap),
    }


def classify_score(
    score: float,
    match_threshold: float = MATCH_THRESHOLD,
    possible_threshold: float = POSSIBLE_THRESHOLD,
) -> str:
    if possible_threshold > match_threshold:
        raise ValueError("The possible threshold must not exceed the match threshold.")
    if score >= match_threshold:
        return "match"
    if score >= possible_threshold:
        return "possible"
    return "non_match"


def classify_duplicate(
    signals: DuplicateSignals,
    match_threshold: float = MATCH_THRESHOLD,
    possible_threshold: float = POSSIBLE_THRESHOLD,
) -> DuplicateResult:
    """Sum log2(m/u) evidence, scale it to 0-100 and explain each part."""
    reasons = []
    total = 0.0
    for signal, level in signal_levels(signals).items():
        if level is None:
            reasons.append(Reason(signal, "missing", 0.0, MISSING_TEXT[signal]))
            continue
        weight = level_weight(signal, level)
        total += weight
        effect = "supports" if weight > 0 else "against" if weight < 0 else "neutral"
        reasons.append(Reason(signal, effect, round(weight, 2), SIGNAL_TEXT[(signal, level)]))

    # Stored with two decimals, so classify the rounded value: a case shown to
    # an officer as 45.00 must be classified exactly as 45.00 is.
    score = round(100 * min(max(total / MAXIMUM_POSITIVE_WEIGHT, 0.0), 1.0), 2)
    reasons.sort(key=lambda r: (r.effect == "missing", -abs(r.weight)))
    return DuplicateResult(
        raw_weight=total,
        score=score,
        classification=classify_score(score, match_threshold, possible_threshold),
        reasons=reasons,
    )


def compare_cases(
    a: DuplicateInput, b: DuplicateInput, idf: dict[str, float], **thresholds
) -> DuplicateResult:
    """Convenience: measure signals and classify in one call."""
    return classify_duplicate(compare_signals(a, b, idf), **thresholds)
