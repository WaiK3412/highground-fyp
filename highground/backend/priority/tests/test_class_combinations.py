"""Traceability: FR10 (case prioritisation), classes-1.0 (ADR-018).

Checks every combination of the answers that classification reads, against
an expected class worked out separately from the rule text in the report
(Section 5.8.1), not from classify().
The answer lists come from the request form's own choices, so a new choice
is included automatically.
"""

from itertools import chain, combinations, product

from django.test import SimpleTestCase

from cases.models import CaseRecord
from cases.serializers.submission import VULNERABILITY_VOCAB
from priority.classes import ClassInput, classify

URGENCIES = [value for value, _ in CaseRecord.Urgency.choices]
ACCESS_LEVELS = [value for value, _ in CaseRecord.AccessLevel.choices] + [None]
FLAGS = sorted(VULNERABILITY_VOCAB)
FLAG_SETS = list(chain.from_iterable(combinations(FLAGS, size) for size in range(len(FLAGS) + 1)))

# The rule text, written out again by hand.
MEDICAL_URGENCIES = {"urgent", "medical_disrupted"}
HARD_TO_REACH = {"four_wd", "foot", "cut_off"}


def expected_class(urgency, access, flags):
    if urgency in MEDICAL_URGENCIES:
        return 1
    if flags or access in HARD_TO_REACH:
        return 2
    return 3


class EveryCombinationTests(SimpleTestCase):
    def test_the_input_space_is_the_one_the_report_describes(self):
        # 4 urgency levels x (4 access levels + missing) x 16 sets of household flags.
        self.assertEqual((len(URGENCIES), len(ACCESS_LEVELS), len(FLAG_SETS)), (4, 5, 16))

    def test_every_combination_gets_the_expected_class_and_reasons(self):
        checked = 0
        for urgency, access, flags in product(URGENCIES, ACCESS_LEVELS, FLAG_SETS):
            with self.subTest(urgency=urgency, access=access, flags=flags):
                result = classify(ClassInput(urgency, access, flags))
                expected = expected_class(urgency, access, flags)
                self.assertEqual(result.priority_class, expected)

                # Every at-risk circumstance is named, whatever the class.
                at_risk = len(flags) + (access in HARD_TO_REACH)
                if expected == 1:
                    self.assertTrue(result.reasons[0].startswith("Health-critical"))
                    self.assertEqual(len(result.reasons), 1 + at_risk)
                elif expected == 2:
                    self.assertEqual(len(result.reasons), at_risk)
                else:
                    self.assertEqual(result.reasons, ("No health-critical or at-risk condition recorded",))
            checked += 1
        self.assertEqual(checked, 320)
