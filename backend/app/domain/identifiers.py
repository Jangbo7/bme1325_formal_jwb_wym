from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone


PATIENT_ID_PATTERN = re.compile(r"^P-[0-9a-f]{8}$")
ENCOUNTER_ID_PATTERN = re.compile(r"^E-[0-9]{14}-[0-9a-f]{4}$")
CN_TZ = timezone(timedelta(hours=8))


def generate_patient_id() -> str:
    return f"P-{uuid.uuid4().hex[:8]}"


def generate_encounter_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(CN_TZ)).astimezone(CN_TZ).strftime("%Y%m%d%H%M%S")
    return f"E-{timestamp}-{uuid.uuid4().hex[:4]}"


def is_valid_patient_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(PATIENT_ID_PATTERN.fullmatch(value))


def is_valid_encounter_id(value: str | None) -> bool:
    if not value:
        return False
    return bool(ENCOUNTER_ID_PATTERN.fullmatch(value))
