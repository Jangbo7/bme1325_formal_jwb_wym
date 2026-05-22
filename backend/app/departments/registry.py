from app.departments.emergency import DEPARTMENT as EMERGENCY
from app.departments.fever import DEPARTMENT as FEVER
from app.departments.internal import DEPARTMENT as INTERNAL
from app.departments.obgyn import DEPARTMENT as OBGYN
from app.departments.pediatrics import DEPARTMENT as PEDIATRICS
from app.departments.ophthalmology import DEPARTMENT as OPHTHALMOLOGY
from app.departments.ent import DEPARTMENT as ENT
from app.departments.dentistry import DEPARTMENT as DENTISTRY
from app.departments.dermatology import DEPARTMENT as DERMATOLOGY
from app.departments.psychiatry import DEPARTMENT as PSYCHIATRY
from app.departments.rehabilitation import DEPARTMENT as REHABILITATION
from app.departments.pain import DEPARTMENT as PAIN
from app.departments.surgery import DEPARTMENT as SURGERY


DEFAULT_ENTRY_CONDITIONS = [
    "triaged_and_registered",
    "called_for_consultation",
    "return_consultation_queued",
]

DEFAULT_EXIT_CONDITIONS = [
    "sent_to_test",
    "waiting_second_consultation",
    "waiting_payment",
    "completed",
    "cancelled",
    "transferred_out",
]

DEFAULT_SUPPORTED_ACTIONS = [
    "accept_initial_queue",
    "accept_return_queue",
    "start_consultation",
    "resume_consultation",
    "complete_consultation",
]

DEFAULT_QUEUE_POLICY = {
    "supports_initial_queue": True,
    "supports_return_queue": True,
    "queue_model": "dual_kind_shared_department",
}


def _build_catalog_entry(raw: dict) -> dict:
    department_id = raw["id"]
    name = raw["label"]
    return {
        # New formal fields
        "department_id": department_id,
        "name": name,
        "queue_department_id": raw["queue_department_id"],
        "entry_conditions": list(raw.get("entry_conditions") or DEFAULT_ENTRY_CONDITIONS),
        "exit_conditions": list(raw.get("exit_conditions") or DEFAULT_EXIT_CONDITIONS),
        "supported_actions": list(raw.get("supported_actions") or DEFAULT_SUPPORTED_ACTIONS),
        "queue_policy": dict(raw.get("queue_policy") or DEFAULT_QUEUE_POLICY),
        # Backward-compatible fields
        "id": department_id,
        "label": name,
        "follow_up_priority": list(raw.get("follow_up_priority") or []),
    }


FORMAL_DEPARTMENTS = [
    _build_catalog_entry(INTERNAL),
    _build_catalog_entry(SURGERY),
    _build_catalog_entry(OBGYN),
    _build_catalog_entry(PEDIATRICS),
    _build_catalog_entry(OPHTHALMOLOGY),
    _build_catalog_entry(ENT),
    _build_catalog_entry(DENTISTRY),
    _build_catalog_entry(DERMATOLOGY),
    _build_catalog_entry(PSYCHIATRY),
    _build_catalog_entry(REHABILITATION),
    _build_catalog_entry(PAIN),
]

LEGACY_DEPARTMENTS = [
    _build_catalog_entry(EMERGENCY),
    _build_catalog_entry(FEVER),
]

DEPARTMENTS = {
    department["id"]: department for department in [*FORMAL_DEPARTMENTS, *LEGACY_DEPARTMENTS]
}
DEPARTMENTS_BY_LABEL = {
    str(department["label"]).lower(): department for department in [*FORMAL_DEPARTMENTS, *LEGACY_DEPARTMENTS]
}


def list_departments(*, include_legacy: bool = True) -> list[dict]:
    selected = [*FORMAL_DEPARTMENTS]
    if include_legacy:
        selected.extend(LEGACY_DEPARTMENTS)
    return [dict(department) for department in selected]


def resolve_department(location: str | None, priority: str = "M") -> dict:
    normalized = (location or "").strip().lower()
    if normalized in DEPARTMENTS:
        return DEPARTMENTS[normalized]
    if normalized in DEPARTMENTS_BY_LABEL:
        return DEPARTMENTS_BY_LABEL[normalized]
    return map_department_from_triage(location or "", priority)


def map_department_from_triage(location: str, priority: str) -> dict:
    normalized = (location or "").lower()
    if "emergency" in normalized or priority == "H":
        return _build_catalog_entry(EMERGENCY)
    if "fever" in normalized:
        return _build_catalog_entry(FEVER)
    if "obgyn" in normalized or "obstetric" in normalized or "gynec" in normalized or "pregnan" in normalized:
        return _build_catalog_entry(OBGYN)
    if "surgery" in normalized:
        return _build_catalog_entry(SURGERY)
    if "ophtha" in normalized or "eye" in normalized or "vision" in normalized:
        return _build_catalog_entry(OPHTHALMOLOGY)
    if "otolaryngology" in normalized or "ent" in normalized or "ear" in normalized or "nose" in normalized or "throat" in normalized:
        return _build_catalog_entry(ENT)
    if "dent" in normalized or "oral" in normalized:
        return _build_catalog_entry(DENTISTRY)
    if "dermat" in normalized or "skin" in normalized:
        return _build_catalog_entry(DERMATOLOGY)
    if "psychi" in normalized or "mental" in normalized or "anxiety" in normalized or "depress" in normalized:
        return _build_catalog_entry(PSYCHIATRY)
    if "rehab" in normalized:
        return _build_catalog_entry(REHABILITATION)
    if "pain" in normalized:
        return _build_catalog_entry(PAIN)
    if "pediatrics" in normalized or "pediatric" in normalized or "children" in normalized:
        return _build_catalog_entry(PEDIATRICS)
    return _build_catalog_entry(INTERNAL)
