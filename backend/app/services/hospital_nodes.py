from __future__ import annotations

from app.departments.registry import list_departments
from app.schemas.hospital_runtime import HospitalNode

from app.services.department_resources import get_department_gate_capacity, list_department_resource_configs


SYSTEM_NODES = [
    HospitalNode(
        node_id="triage",
        node_type="system",
        name="Triage",
        capacity=8,
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["begin_triage", "triage_completed", "followup_requested"],
        entry_conditions=["arrived", "triaging", "waiting_followup", "in_triage"],
        exit_conditions=["triaged", "in_emergency", "in_icu_rescue"],
    ),
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
        node_id="outpatient_procedure",
        node_type="system",
        name="Outpatient Procedure",
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["start_outpatient_procedure", "finish_outpatient_procedure"],
        entry_conditions=["waiting_outpatient_procedure"],
        exit_conditions=["in_outpatient_procedure", "waiting_test", "results_ready"],
    ),
    HospitalNode(
        node_id="payment",
        node_type="system",
        name="Payment",
        supports_queue=False,
        supports_consultation=False,
        supported_actions=["request_medical_payment", "pay_medical", "plan_disposition"],
        entry_conditions=["waiting_payment"],
        exit_conditions=["medical_payment_completed", "disposition_pending"],
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
                capacity=get_department_gate_capacity(department["id"]),
                supports_queue=True,
                supports_consultation=True,
                supported_actions=list(department.get("supported_actions") or []),
                entry_conditions=list(department.get("entry_conditions") or []),
                exit_conditions=list(department.get("exit_conditions") or []),
            )
        )
    return nodes


def build_room_nodes() -> list[HospitalNode]:
    nodes: list[HospitalNode] = []
    for config in list_department_resource_configs():
        for room in config.room_nodes:
            nodes.append(
                HospitalNode(
                    node_id=room.node_id,
                    node_type="room",
                    name=room.name,
                    department_id=config.department_id,
                    room_type=room.room_type,
                    capacity=room.capacity,
                    supports_queue=False,
                    supports_consultation=room.room_type == "consultation",
                    supported_actions=[],
                    entry_conditions=[],
                    exit_conditions=[],
                )
            )
    return nodes


def list_hospital_nodes() -> list[HospitalNode]:
    return [*build_department_nodes(), *build_room_nodes(), *SYSTEM_NODES]
