"""FR9: shared normalisation and household-pin geography (report §3.7.8)."""


from unittest import TestCase

from cases.normalise import haversine_metres, normalize_malay, normalize_phone


class NormalisationTests(TestCase):
    def test_malay_abbreviations_expand_as_whole_tokens(self):
        self.assertEqual(
            normalize_malay("Lot 88, Jln. Masjid, Kg Baru"), "lot 88 jalan masjid kampung baru"
        )
        self.assertEqual(normalize_malay("TMN Sri, Lor 3"), "taman sri lorong 3")
        # "kgs" is not the abbreviation "kg".
        self.assertEqual(normalize_malay("5 kgs rice"), "5 kgs rice")

    def test_phone_formats_are_equivalent(self):
        for raw in ["012-555 0142", "+60 12-555 0142", "60125550142", "0125550142"]:
            self.assertEqual(normalize_phone(raw), "0125550142")

    def test_unusable_phone_is_none_not_a_guess(self):
        for raw in ["", "12345", "555-0142", "not a phone"]:
            self.assertIsNone(normalize_phone(raw))


class GeographyTests(TestCase):
    def test_one_degree_of_latitude(self):
        # 2πR / 360 with R = 6 371 km.
        self.assertAlmostEqual(haversine_metres(0, 0, 1, 0), 111_194.93, places=1)

    def test_same_point_is_zero_and_symmetric(self):
        self.assertEqual(haversine_metres(6.1, 102.2, 6.1, 102.2), 0.0)
        self.assertAlmostEqual(
            haversine_metres(6.1, 102.2, 6.2, 102.3), haversine_metres(6.2, 102.3, 6.1, 102.2)
        )
