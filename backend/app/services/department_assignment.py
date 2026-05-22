from __future__ import annotations

from app.departments.registry import resolve_department


def resolve_assigned_department_for_visit(visit_row: dict, patient_row: dict | None = None) -> dict:
    assigned_id = (visit_row.get("assigned_department_id") or "").strip()
    assigned_name = (visit_row.get("assigned_department_name") or "").strip()
    if assigned_id and assigned_name:
        return {
            "id": assigned_id,
            "label": assigned_name,
            "queue_department_id": assigned_id,
        }
    fallback_location = visit_row.get("current_department") or (patient_row or {}).get("location")
    fallback_priority = (patient_row or {}).get("priority") or "M"
    resolved = resolve_department(fallback_location, fallback_priority)
    return {
        "id": resolved["id"],
        "label": resolved["label"],
        "queue_department_id": resolved["queue_department_id"],
    }
