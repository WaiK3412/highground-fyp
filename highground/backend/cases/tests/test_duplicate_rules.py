"""Traceability: FR9 (duplicate detection) under rules-1.0 (ADR-019)."""

from django.test import SimpleTestCase

from cases.duplicate_rules import compare_by_rules
from cases.duplicates import DuplicateInput


def inp(name="", phone="", address="", lat=None, lng=None):
    return DuplicateInput(description_text="", submitter_name=name, address=address,
                          phone=phone, latitude=lat, longitude=lng)


def rules(a, b):
    return [hit.rule for hit in compare_by_rules(a, b).hits]


class RuleTests(SimpleTestCase):
    def test_same_phone_in_different_formats(self):
        self.assertEqual(rules(inp(phone="+60 12-555 0142"), inp(phone="012-555 0142")), ["same_phone"])

    def test_name_ignores_malay_particles(self):
        self.assertEqual(rules(inp(name="Ahmad bin Ismail"), inp(name="Ahmad Ismail")), ["same_name"])

    def test_same_house_and_address_after_abbreviation(self):
        self.assertEqual(
            rules(inp(address="Lot 4231, Jalan Hospital, Kubang Kerian"),
                  inp(address="Lot 4231, Jln Hospital, Kubang Kerian")),
            ["same_house_and_address"],
        )

    def test_next_door_house_does_not_match(self):
        self.assertEqual(rules(inp(address="Lot 88, Jalan Masjid"), inp(address="Lot 89, Jalan Masjid")), [])

    def test_same_pin_to_four_decimals(self):
        self.assertEqual(rules(inp(lat=6.12341, lng=102.20001), inp(lat=6.12344, lng=102.20004)), ["same_pin"])

    def test_pin_at_zero_is_present(self):
        self.assertEqual(rules(inp(lat=0.0, lng=102.2), inp(lat=0.0, lng=102.2)), ["same_pin"])

    def test_missing_data_never_matches(self):
        self.assertEqual(rules(inp(), inp()), [])
        self.assertEqual(rules(inp(phone="not a number"), inp(phone="not a number")), [])
        self.assertEqual(rules(inp(address="Lot"), inp(address="Lot")), [])
        self.assertEqual(rules(inp(lat=6.1, lng=None), inp(lat=6.1, lng=None)), [])

    def test_several_rules_can_fire_and_needs_review(self):
        result = compare_by_rules(inp(name="Siti", phone="0123456789"), inp(name="Siti", phone="0123456789"))
        self.assertEqual([h.rule for h in result.hits], ["same_name", "same_phone"])
        self.assertTrue(result.needs_review)
        self.assertTrue(all(h.text for h in result.hits))


class NormalisationDefectTests(SimpleTestCase):
    """Defects reproduced by the 2 Oct audits (docs/research/priority-and-
    duplicate-audit-2026-10-02.md, multi-organisation-and-duplicate-review-...)."""

    def test_tamil_vowel_signs_keep_names_apart(self):
        # \w dropped the combining vowel signs, so different names matched.
        self.assertEqual(rules(inp(name="கா"), inp(name="கி")), [])
        self.assertEqual(rules(inp(name="கா"), inp(name="கா")), ["same_name"])

    def test_lot_suffix_written_apart_still_matches(self):
        self.assertEqual(
            rules(inp(address="Lot 88A, Jalan Masjid"), inp(address="Lot 88 A, Jalan Masjid")),
            ["same_house_and_address"],
        )

    def test_unit_and_house_numbers_keep_their_order(self):
        self.assertEqual(rules(inp(address="12/3 Jalan Masjid"), inp(address="3/12 Jalan Masjid")), [])
        self.assertEqual(
            rules(inp(address="12/3 Jalan Masjid"), inp(address="12 / 3, Jln Masjid")),
            ["same_house_and_address"],
        )


class RulesEvaluationTests(SimpleTestCase):
    def test_heldout_counts_are_reproducible(self):
        from cases import duplicate_evaluation as ev

        data = ev.load_fixture()
        outcomes = ev.score_split_rules(data, "heldout")
        in_block = ev.confusion(outcomes, 50.0)
        end_to_end = ev.confusion(outcomes, 50.0, end_to_end=True)
        # Measured 30 Sep 2026 (docs/research/duplicate-rule-comparison-2026-09-30.md).
        self.assertEqual((in_block["tp"], in_block["fp"]), (28, 6))
        self.assertEqual(end_to_end["fn"], 3)


class ContradictionTests(SimpleTestCase):
    """Shown beside the rule hits so the officer sees what disagrees, too."""

    def test_same_account_but_different_lot_is_reported(self):
        from cases.duplicate_rules import contradictions

        a = inp(name="Ahmad", phone="0125550142", address="Lot 88 Jalan Masjid")
        b = inp(name="Ahmad", phone="0125550142", address="Lot 89 Jalan Masjid")
        self.assertEqual([c.rule for c in contradictions(a, b)], ["different_house_number"])

    def test_different_phone_and_name_are_reported(self):
        from cases.duplicate_rules import contradictions

        found = [c.rule for c in contradictions(inp(name="Siti", phone="0123456789"),
                                                  inp(name="Aminah", phone="0139876543"))]
        self.assertEqual(found, ["different_name", "different_phone"])

    def test_missing_data_is_not_a_contradiction(self):
        from cases.duplicate_rules import contradictions

        self.assertEqual(contradictions(inp(name="Siti"), inp(phone="0123456789")), ())

    def test_pin_distance_in_metres(self):
        from cases.duplicate_rules import pin_distance_metres

        self.assertIsNone(pin_distance_metres(inp(lat=6.1, lng=102.2), inp()))
        self.assertEqual(pin_distance_metres(inp(lat=6.1, lng=102.2), inp(lat=6.1, lng=102.2)), 0)
        self.assertAlmostEqual(pin_distance_metres(inp(lat=6.1, lng=102.2), inp(lat=6.101, lng=102.2)), 111, delta=1)
