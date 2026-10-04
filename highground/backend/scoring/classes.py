"""Literature-informed priority classes (classes-1.0).

The sources below inform which circumstances count; the exact class
boundaries are this project's interpretation of them (ADR-018), not rules the
sources prescribe. ESI, for example, is clinical emergency triage, not a
flood-recovery tool.

No Django imports on purpose: the rules take plain values. There are no weights or
points: a case belongs to the first class whose condition it meets, and the
queue orders a class by submission time (first come, first served).

Sources (verbatim quotes in docs/research/case-ranking-msni-2026-09-30.md):
- Class 1: ESI Handbook v5 levels 1-2 (life-saving or time-sensitive
  treatment); Sphere Health, essential concepts ("interrupted medicine supply
  can disrupt ongoing treatment"); Sphere NCD standard 2.6.
- Class 2: Sphere "Understanding vulnerabilities and capacities" (age,
  disability; children, older people); Core Humanitarian Standard key action
  1.2 (hard-to-reach locations, persons with disabilities, older people,
  female-headed households).
"""

from __future__ import annotations

from dataclasses import dataclass

CLASS_RULES_VERSION = "classes-1.0"

# "Health-critical" rather than "life-threatening": emergencies go to 999
# first (the form says so). Class 1 is ongoing health needs the flood has
# put at risk, such as interrupted medicine or dialysis access.
CLASS_LABELS = {1: "Health-critical", 2: "At risk", 3: "Standard"}

HEALTH_CRITICAL_URGENCY = {
    "urgent": "urgent medical attention needed",
    "medical_disrupted": "medical care disrupted",
}
AT_RISK_FLAGS = {
    "elderly": "older person in the household",
    "child_under_5": "child under 5 in the household",
    "disability": "person with a disability or medical needs in the household",
    # CHS 1.2 names female-headed households; single parent is the nearest
    # field the form collects. Stated as an interpretation in the report.
    "single_parent": "single-parent household",
}
HARD_TO_REACH_ACCESS = {
    "four_wd": "reachable by 4x4 only",
    "foot": "reachable on foot only",
    "cut_off": "cut off",
}

RULES = [
    {
        "priority_class": 1,
        "label": CLASS_LABELS[1],
        "rule": "Urgency is 'someone needs urgent medical attention' or 'medical needs disrupted'.",
        "sources": [
            "Emergency Severity Index Handbook v5 (levels 1-2)",
            "Sphere Handbook 2018, Health: essential concepts; NCD standard 2.6",
        ],
    },
    {
        "priority_class": 2,
        "label": CLASS_LABELS[2],
        "rule": "An older person, child under 5, person with a disability or medical needs, "
                "or single parent in the household, or the home is hard to reach "
                "(4x4 only, on foot only, cut off).",
        "sources": [
            "Sphere Handbook 2018: Understanding vulnerabilities and capacities",
            "Core Humanitarian Standard, key action 1.2",
        ],
    },
    {
        "priority_class": 3,
        "label": CLASS_LABELS[3],
        "rule": "Every other verified case.",
        "sources": [],
    },
]


@dataclass(frozen=True)
class ClassInput:
    """The non-identifying fields classification depends on."""

    urgency: str
    access_level: str | None
    vulnerability_flags: tuple[str, ...]


@dataclass(frozen=True)
class PriorityClassResult:
    priority_class: int
    label: str
    reasons: tuple[str, ...]


def classify(case: ClassInput) -> PriorityClassResult:
    """Return the first class the case qualifies for, with its reasons."""
    if case.urgency in HEALTH_CRITICAL_URGENCY:
        reasons = [f"Health-critical: {HEALTH_CRITICAL_URGENCY[case.urgency]}"]
        reasons += _at_risk_reasons(case)  # shown for context; class is already decided
        return PriorityClassResult(1, CLASS_LABELS[1], tuple(reasons))

    reasons = _at_risk_reasons(case)
    if reasons:
        return PriorityClassResult(2, CLASS_LABELS[2], tuple(reasons))

    return PriorityClassResult(
        3, CLASS_LABELS[3], ("No health-critical or at-risk condition recorded",)
    )


def _at_risk_reasons(case: ClassInput) -> list[str]:
    reasons = [
        f"At risk: {AT_RISK_FLAGS[flag]}"
        for flag in case.vulnerability_flags
        if flag in AT_RISK_FLAGS
    ]
    if case.access_level in HARD_TO_REACH_ACCESS:
        reasons.append(f"Hard to reach: {HARD_TO_REACH_ACCESS[case.access_level]}")
    return reasons
