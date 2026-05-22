from __future__ import annotations

from app.departments.registry import list_departments
from app.schemas.hospital_runtime import HospitalNode


SYSTEM_NODES = [
    HospitalNode(
        node_id="testing",
        node_type="system",
        name="Auxiliary Diagnostic Center",
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["start_exam", "finish_exam", "results_ready"],
        entry_conditions=["waiting_test", "waiting_test_payment", "test_payment_completed"],
        exit_conditions=["waiting_return_consultation", "results_ready"],
    ),
    HospitalNode(
        node_id="payment",
        node_type="system",
        name="Payment",
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["request_medical_payment", "pay_medical", "complete_visit"],
        entry_conditions=["waiting_payment"],
        exit_conditions=["medical_payment_completed", "completed"],
    ),
    HospitalNode(
        node_id="pharmacy",
        node_type="system",
        name="Pharmacy",
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["dispense_medication", "complete_visit"],
        entry_conditions=["waiting_pharmacy"],
        exit_conditions=["completed"],
    ),
]


def build_department_nodes() -> list[HospitalNode]:
    nodes: list[HospitalNode] = []
    for department in list_departments(include_legacy=False):
        nodes.append(
            HospitalNode(
                node_id=department["id"],
                node_type="department",
                name=department["label"],
                supports_queue=True,
                supports_consultation=True,
                supported_actions=list(department.get("supported_actions") or []),
                entry_conditions=list(department.get("entry_conditions") or []),
                exit_conditions=list(department.get("exit_conditions") or []),
            )
        )
    return nodes


def list_hospital_nodes() -> list[HospitalNode]:
    return [*build_department_nodes(), *SYSTEM_NODES]

