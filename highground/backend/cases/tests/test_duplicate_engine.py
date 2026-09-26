"""Tests for the pure duplicate-request comparator.

Traceability — requirements covered by this file:
  FR14 Flag likely duplicate requests for officer review (report §3.7.8)

The engine imports no Django code, so these are plain unittest cases: no
database, no fixtures. Expected values are worked by hand in the comments.
"""

import math
from unittest import TestCase

from cases.duplicates import (
    MATCH_THRESHOLD,
    MAXIMUM_POSITIVE_WEIGHT,
    M_U_PROBABILITIES,
    POSSIBLE_THRESHOLD,
    DuplicateInput,
    DuplicateSignals,
    build_tfidf_corpus,
    classify_duplicate,
    classify_score,
    compare_cases,
    compare_signals,
    cosine_similarity,
    haversine_metres,
    jaro,
    jaro_winkler,
    level_weight,
    normalize_malay,
    normalize_phone,
    tfidf_vector,
    token_similarity,
    tokenize_description,
)


def case(**fields) -> DuplicateInput:
    fields.setdefault("description_text", "")
    return DuplicateInput(**fields)


class JaroWinklerTests(TestCase):
    """Reference values from Winkler (1990) and Christen (2012)."""

    def test_published_examples(self):
        self.assertAlmostEqual(jaro_winkler("MARTHA", "MARHTA"), 0.961111, places=6)
        self.assertAlmostEqual(jaro_winkler("DWAYNE", "DUANE"), 0.84, places=6)
        self.assertAlmostEqual(jaro_winkler("DIXON", "DICKSONX"), 0.813333, places=6)

    def test_is_symmetric(self):
        for a, b in [("MARTHA", "MARHTA"), ("kampung", "kampong"), ("abc", "xyzab")]:
            self.assertAlmostEqual(jaro_winkler(a, b), jaro_winkler(b, a))

    def test_empty_and_identical_strings(self):
        self.assertEqual(jaro_winkler("", ""), 0.0)
        self.assertEqual(jaro_winkler("abc", ""), 0.0)
        self.assertEqual(jaro_winkler("abc", "abc"), 1.0)
        self.assertEqual(jaro_winkler("abc", "xyz"), 0.0)

    def test_repeated_characters_match_once_each(self):
        # "aaaa" vs "aa": window = 1, so only two a's pair up.
        # jaro = (2/4 + 2/2 + 2/2) / 3 = 0.8333…
        self.assertAlmostEqual(jaro("aaaa", "aa"), 2.5 / 3)

    def test_prefix_boost_is_capped_at_four_characters(self):
        # Both pairs share jaro; only the capped prefix length differs.
        base = jaro("abcdex", "abcdey")
        self.assertAlmostEqual(jaro_winkler("abcdex", "abcdey"), base + 4 * 0.1 * (1 - base))
        base3 = jaro("abcx", "abcy")
        self.assertAlmostEqual(jaro_winkler("abcx", "abcy"), base3 + 3 * 0.1 * (1 - base3))


class NormalisationTests(TestCase):
    def test_malay_abbreviations_expand_as_whole_tokens(self):
        self.assertEqual(
            normalize_malay("Lot 88, Jln. Masjid, Kg Baru"), "lot 88 jalan masjid kampung baru"
        )
        self.assertEqual(normalize_malay("TMN Sri, Lor 3"), "taman sri lorong 3")
        # "kgs" is not the abbreviation "kg".
        self.assertEqual(normalize_malay("5 kgs rice"), "5 kgs rice")

    def test_abbreviated_and_full_addresses_agree(self):
        a = case(address="Lot 88 Jln Masjid Kg Baru")
        b = case(address="Lot 88, Jalan Masjid, Kampung Baru")
        signals = compare_signals(a, b, {})
        self.assertEqual(signals.address_similarity, 1.0)
        self.assertEqual(signals.address_numbers, "agree")

    def test_english_address_words_map_to_malay_and_order_does_not_matter(self):
        # Report §2.4.2: "Kg Baru, Jalan Masjid" vs "Kampung Baru near Masjid Road".
        a = case(address="Kg Baru, Jalan Masjid")
        b = case(address="Kampung Baru near Masjid Road")
        self.assertEqual(compare_signals(a, b, {}).address_similarity, 1.0)

    def test_neighbouring_lot_numbers_conflict_despite_similar_text(self):
        a = case(address="Lot 88, Jalan Masjid")
        b = case(address="Lot 89, Jalan Masjid")
        signals = compare_signals(a, b, {})
        self.assertEqual(signals.address_similarity, 1.0)
        self.assertEqual(signals.address_numbers, "conflict")

    def test_shorter_address_with_same_number_is_judged_by_containment(self):
        a = case(address="Lot 800, Tok Uban")
        b = case(address="Lot 800 Kampung Tok Uban, Pasir Mas")
        self.assertEqual(compare_signals(a, b, {}).address_similarity, 1.0)

    def test_containment_does_not_apply_without_agreeing_numbers(self):
        # A village-only address fits inside every address in the village.
        a = case(address="Kampung Tok Uban")
        b = case(address="Lot 455, Jalan Pasar, Kampung Tok Uban")
        self.assertLess(compare_signals(a, b, {}).address_similarity, 0.95)

    def test_number_on_only_one_address_is_missing_not_conflict(self):
        a = case(address="Lot 88, Jalan Masjid")
        b = case(address="Jalan Masjid")
        self.assertIsNone(compare_signals(a, b, {}).address_numbers)

    def test_extra_number_on_one_side_is_not_a_conflict(self):
        # "Lot 88 Jalan 5" names the same house as "Lot 88"; nothing disagrees.
        a = case(address="Lot 88, Jalan 5")
        b = case(address="Lot 88")
        self.assertIsNone(compare_signals(a, b, {}).address_numbers)

    def test_phone_formats_are_equivalent(self):
        for raw in ["012-555 0142", "+60 12-555 0142", "60125550142", "0125550142"]:
            self.assertEqual(normalize_phone(raw), "0125550142")

    def test_unusable_phone_is_none_not_a_guess(self):
        for raw in ["", "12345", "555-0142", "not a phone"]:
            self.assertIsNone(normalize_phone(raw))

    def test_name_particles_are_ignored(self):
        self.assertEqual(token_similarity(["ahmad", "ismail"], ["ahmad", "ismail"]), 1.0)
        a = case(submitter_name="Ahmad bin Ismail")
        b = case(submitter_name="Ahmad Ismail")
        self.assertEqual(compare_signals(a, b, {}).name_similarity, 1.0)

    def test_token_similarity_absorbs_typos(self):
        self.assertGreater(token_similarity(["kampung", "baru"], ["kampong", "baru"]), 0.95)


class TfidfTests(TestCase):
    def test_hand_computed_cosine(self):
        # N = 2. "banjir" is in both cases: idf = ln(3/3) + 1 = 1.
        # "rumah" and "dapur" are in one each: idf = ln(3/2) + 1 ≈ 1.405465.
        # cos = (1·1) / (1 + 1.405465²) = 1 / 2.975332 ≈ 0.336097.
        idf = build_tfidf_corpus(["banjir rumah", "banjir dapur"])
        self.assertAlmostEqual(idf["banjir"], 1.0)
        self.assertAlmostEqual(idf["rumah"], math.log(1.5) + 1)
        rare = math.log(1.5) + 1
        expected = 1 / (1 + rare**2)
        cos = cosine_similarity(tfidf_vector("banjir rumah", idf), tfidf_vector("banjir dapur", idf))
        self.assertAlmostEqual(cos, expected)
        self.assertAlmostEqual(cos, 0.336097, places=6)

    def test_document_frequency_counts_each_case_once(self):
        idf = build_tfidf_corpus(["banjir banjir banjir", "dapur"])
        self.assertAlmostEqual(idf["banjir"], math.log(3 / 2) + 1)

    def test_empty_text_is_unavailable_but_unrelated_text_is_zero(self):
        idf = build_tfidf_corpus(["banjir rumah", "dapur"])
        self.assertIsNone(cosine_similarity(tfidf_vector("", idf), tfidf_vector("banjir", idf)))
        # Only stopwords is as empty as no text.
        self.assertIsNone(cosine_similarity(tfidf_vector("dan yang", idf), tfidf_vector("banjir", idf)))
        self.assertEqual(cosine_similarity(tfidf_vector("banjir", idf), tfidf_vector("dapur", idf)), 0.0)

    def test_reordered_description_is_identical(self):
        idf = build_tfidf_corpus(["air masuk dapur rosak", "dapur rosak air masuk"])
        cos = cosine_similarity(
            tfidf_vector("air masuk dapur rosak", idf), tfidf_vector("dapur rosak air masuk", idf)
        )
        self.assertAlmostEqual(cos, 1.0)

    def test_chinese_becomes_bigrams_and_tamil_words_stay_whole(self):
        self.assertEqual(tokenize_description("水灾严重"), ["水灾", "灾严", "严重"])
        # Tamil vowel signs are combining marks; the word must not split on them.
        self.assertEqual(tokenize_description("வீட்டில் வெள்ளம்"), ["வீட்டில்", "வெள்ளம்"])


class GeographyTests(TestCase):
    def test_one_degree_of_latitude(self):
        # 2πR / 360 with R = 6 371 km.
        self.assertAlmostEqual(haversine_metres(0, 0, 1, 0), 111_194.93, places=1)

    def test_same_point_is_zero_and_symmetric(self):
        self.assertEqual(haversine_metres(6.1, 102.2, 6.1, 102.2), 0.0)
        self.assertAlmostEqual(
            haversine_metres(6.1, 102.2, 6.2, 102.3), haversine_metres(6.2, 102.3, 6.1, 102.2)
        )

    def test_distance_needs_both_complete_pins(self):
        pinned = case(latitude=6.1, longitude=102.2)
        half = case(latitude=6.1)
        self.assertIsNone(compare_signals(pinned, case(), {}).distance_metres)
        self.assertIsNone(compare_signals(pinned, half, {}).distance_metres)

    def test_distance_bins(self):
        # ~0.00027° of latitude ≈ 30 m; 0.0045° ≈ 500 m.
        near = compare_signals(case(latitude=6.1, longitude=102.2),
                               case(latitude=6.10027, longitude=102.2), {})
        result = classify_duplicate(near)
        self.assertIn("Household pins are within 50 m", [r.text for r in result.reasons])
        far = compare_signals(case(latitude=6.1, longitude=102.2),
                              case(latitude=6.1045, longitude=102.2), {})
        result = classify_duplicate(far)
        self.assertIn("Household pins are 200 m to 1 km apart", [r.text for r in result.reasons])


class EvidenceTests(TestCase):
    def test_all_missing_scores_zero_and_every_signal_is_reported_missing(self):
        result = classify_duplicate(DuplicateSignals())
        self.assertEqual(result.raw_weight, 0.0)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.classification, "non_match")
        self.assertEqual({r.effect for r in result.reasons}, {"missing"})
        self.assertEqual(len(result.reasons), len(M_U_PROBABILITIES))

    def test_missing_field_contributes_exactly_zero(self):
        with_phone_missing = classify_duplicate(DuplicateSignals(name_similarity=1.0))
        self.assertAlmostEqual(with_phone_missing.raw_weight, level_weight("name", "same"))

    def test_unusable_phone_is_neutral_like_a_missing_one(self):
        base = dict(description_text="banjir", submitter_name="Siti Aminah")
        idf = build_tfidf_corpus(["banjir"])
        blank = compare_cases(case(**base), case(**base, phone=""), idf)
        junk = compare_cases(case(**base), case(**base, phone="12345"), idf)
        self.assertEqual(blank.score, junk.score)

    def test_weights_are_log2_m_over_u(self):
        m, u = M_U_PROBABILITIES["phone"]["agree"]
        self.assertAlmostEqual(level_weight("phone", "agree"), math.log2(m / u))

    def test_score_is_bounded_and_rounded_to_two_decimals(self):
        everything = DuplicateSignals(
            name_similarity=1.0, address_similarity=1.0, address_numbers="agree", phone="agree",
            description_cosine=1.0, distance_metres=0.0, damage="agree", needs_overlap=1.0,
        )
        best = classify_duplicate(everything)
        self.assertAlmostEqual(best.raw_weight, MAXIMUM_POSITIVE_WEIGHT)
        self.assertEqual(best.score, 100.0)

        nothing = DuplicateSignals(
            name_similarity=0.0, address_similarity=0.0, address_numbers="conflict",
            phone="disagree", description_cosine=0.0, distance_metres=5000,
            damage="disagree", needs_overlap=0.0,
        )
        self.assertEqual(classify_duplicate(nothing).score, 0.0)

        partial = classify_duplicate(DuplicateSignals(phone="agree"))
        self.assertEqual(partial.score, round(partial.score, 2))
        self.assertLess(partial.score, 100)

    def test_classification_boundaries_are_inclusive(self):
        self.assertEqual(classify_score(MATCH_THRESHOLD), "match")
        self.assertEqual(classify_score(MATCH_THRESHOLD - 0.01), "possible")
        self.assertEqual(classify_score(POSSIBLE_THRESHOLD), "possible")
        self.assertEqual(classify_score(POSSIBLE_THRESHOLD - 0.01), "non_match")

    def test_thresholds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            classify_score(50, match_threshold=40, possible_threshold=60)

    def test_reasons_list_supporting_conflicting_and_missing_evidence(self):
        a = case(submitter_name="Ahmad Ismail", address="Lot 88 Jalan Masjid")
        b = case(submitter_name="Ahmad Ismail", address="Lot 89 Jalan Masjid")
        result = compare_cases(a, b, {})
        texts = {r.text: r.effect for r in result.reasons}
        self.assertEqual(texts["Submitter names match"], "supports")
        self.assertEqual(texts["Different house or lot numbers"], "against")
        self.assertEqual(texts["Phone unavailable"], "missing")
        # Missing evidence is listed last.
        self.assertEqual(result.reasons[-1].effect, "missing")


class ScenarioTests(TestCase):
    """End-to-end comparisons shaped like the report's worked examples."""

    CORPUS = [
        "Rumah dimasuki air paras pinggang, dapur rosak",
        "Air masuk rumah paras pinggang dapur rosak teruk",
        "Rumah banjir perlu bantuan makanan",
        "Bumbung bocor, tilam basah",
    ]

    def setUp(self):
        self.idf = build_tfidf_corpus(self.CORPUS)

    def test_same_household_with_abbreviations_and_phone_format_is_flagged(self):
        a = DuplicateInput(self.CORPUS[0], "Ahmad bin Ismail", "Lot 88 Jln Masjid Kg Baru",
                           "012-555 0142", damage_category="repair", needs=("food", "water"))
        b = DuplicateInput(self.CORPUS[1], "Ahmad Ismail", "Lot 88, Jalan Masjid, Kampung Baru",
                           "+60125550142", damage_category="repair", needs=("food",))
        self.assertTrue(compare_cases(a, b, self.idf).needs_review)

    def test_next_door_neighbour_is_not_flagged(self):
        a = DuplicateInput(self.CORPUS[0], "Ahmad bin Ismail", "Lot 88 Jln Masjid Kg Baru",
                           "012-555 0142", damage_category="repair", needs=("food", "water"))
        b = DuplicateInput(self.CORPUS[1], "Aminah binti Yusof", "Lot 89, Jalan Masjid, Kampung Baru",
                           "013-555 0911", damage_category="repair", needs=("food",))
        self.assertEqual(compare_cases(a, b, self.idf).classification, "non_match")

    def test_comparison_is_symmetric(self):
        a = DuplicateInput(self.CORPUS[0], "Ahmad", "Lot 88 Jln Masjid", "0125550142")
        b = DuplicateInput(self.CORPUS[1], "Ahmed", "Lot 88 Jalan Masjid", "")
        self.assertEqual(compare_cases(a, b, self.idf).score, compare_cases(b, a, self.idf).score)
