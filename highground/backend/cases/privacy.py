"""Presentation policy for case prose; storage and duplicate evidence stay intact."""

from .redaction import redact_personal_data


def safe_case_text(case, user, text):
    if user and user.role in {"disaster_officer", "system_admin"}:
        return text
    owner = case.submitted_by_user
    return redact_personal_data(
        text,
        names=(owner.full_name,) if owner else (),
        phones=(owner.phone,) if owner else (),
        addresses=(case.address,),
        coordinates=(
            f"{case.latitude}, {case.longitude}"
            if case.latitude is not None and case.longitude is not None else "",
        ),
    )
