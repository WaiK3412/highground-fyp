"""Deterministic presentation redaction; no database or web dependencies.

Known names and addresses must be supplied by the caller. Free-text pattern
matching alone cannot identify every person or address, so access policy must
still decide whether a whole field is safe to release.
"""

import re


PHONE = re.compile(r"(?<!\w)(?:\+?60|0)[\s.-]?1[0-9](?:[\s.-]?[0-9]){7,8}(?!\w)")
IC = re.compile(r"(?<!\d)\d{6}[\s-]?\d{2}[\s-]?\d{4}(?!\d)")
COORDINATES = re.compile(r"(?<!\d)-?\d{1,3}\.\d{4,}\s*[,;/]\s*-?\d{1,3}\.\d{4,}(?!\d)")


def redact_personal_data(text, *, names=(), phones=(), addresses=(), coordinates=()):
    """Mask known identifiers and recognisable Malaysian identifiers in prose."""
    if not text:
        return text
    result = str(text)
    for values, label in (
        (addresses, "address"),
        (names, "name"),
        (phones, "phone"),
        (coordinates, "location"),
    ):
        for value in sorted((str(v).strip() for v in values if v), key=len, reverse=True):
            if value:
                result = re.sub(re.escape(value), f"[redacted {label}]", result, flags=re.IGNORECASE)
    result = IC.sub("[redacted IC]", result)
    result = PHONE.sub("[redacted phone]", result)
    return COORDINATES.sub("[redacted location]", result)
