from app.departments.emergency import DEPARTMENT as EMERGENCY
from app.departments.fever import DEPARTMENT as FEVER
from app.departments.internal import DEPARTMENT as INTERNAL
from app.departments.pediatrics import DEPARTMENT as PEDIATRICS
from app.departments.surgery import DEPARTMENT as SURGERY


DEPARTMENTS = {
    INTERNAL["id"]: INTERNAL,
    SURGERY["id"]: SURGERY,
    PEDIATRICS["id"]: PEDIATRICS,
    EMERGENCY["id"]: EMERGENCY,
    FEVER["id"]: FEVER,
}


def map_department_from_triage(location: str, priority: str) -> dict:
    normalized = (location or "").lower()
    if "emergency" in normalized or priority == "H":
        return EMERGENCY
    if "fever" in normalized:
        return FEVER
    if "surgery" in normalized:
        return SURGERY
    if "pediatrics" in normalized:
        return PEDIATRICS
    return INTERNAL
