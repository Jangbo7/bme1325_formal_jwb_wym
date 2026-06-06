from __future__ import annotations

from app.schemas.multi_patient_debug import MultiPatientMode
from app.services.department_capabilities import is_script_only_department


LOCKED_SCRIPT_ONLY_MODES: set[MultiPatientMode] = {
    "legacy_template",
    "legacy_probabilistic_llm",
    "department_mixed",
}


def should_lock_department_for_debug(*, mode: MultiPatientMode, department_id: str | None) -> bool:
    return mode in LOCKED_SCRIPT_ONLY_MODES and is_script_only_department(department_id)


def resolve_locked_debug_department(visit_row: dict | None) -> dict[str, str] | None:
    if not visit_row:
        return None
    visit_data = visit_row.get("data_json")
    try:
        import json

        payload = json.loads(visit_data) if visit_data else {}
    except Exception:
        payload = {}
    if not payload.get("debug_department_locked_by_mode"):
        return None
    department_id = str(payload.get("debug_spawn_department_id") or "").strip()
    department_name = str(payload.get("debug_spawn_department_name") or "").strip()
    if not department_id or not department_name:
        return None
    return {"id": department_id, "label": department_name}
