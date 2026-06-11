from __future__ import annotations

from dataclasses import dataclass

from app.departments.registry import list_departments
from app.schemas.common import VisitLifecycleState


@dataclass(frozen=True, slots=True)
class DoctorSlot:
    slot_id: str
    label: str
    capacity: int
    room_node_id: str


@dataclass(frozen=True, slots=True)
class RoomNode:
    node_id: str
    name: str
    room_type: str
    capacity: int


@dataclass(frozen=True, slots=True)
class DepartmentResourceConfig:
    department_id: str
    department_gate_capacity: int
    doctor_slots: tuple[DoctorSlot, ...]
    room_nodes: tuple[RoomNode, ...]


CONSULTATION_VISIT_STATES = {
    VisitLifecycleState.IN_CONSULTATION.value,
    VisitLifecycleState.IN_SECOND_CONSULTATION.value,
}

SURGERY_PROCEDURE_VISIT_STATES = {
    VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
    VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
}


def _doctor_slot(department_id: str, department_name: str, index: int) -> DoctorSlot:
    return DoctorSlot(
        slot_id=f"{department_id}_doctor_slot_{index}",
        label=f"{department_name} Doctor Slot {index}",
        capacity=1,
        room_node_id=f"{department_id}_consult_room_{index}",
    )


def _consult_room(department_id: str, department_name: str, index: int) -> RoomNode:
    return RoomNode(
        node_id=f"{department_id}_consult_room_{index}",
        name=f"{department_name} Consultation Room {index}",
        room_type="consultation",
        capacity=1,
    )


def _build_resource_config(department_id: str, department_name: str) -> DepartmentResourceConfig:
    if department_id == "internal":
        consult_count = 2
        gate_capacity = 2
    elif department_id == "surgery":
        consult_count = 2
        gate_capacity = 2
    else:
        consult_count = 1
        gate_capacity = 1

    doctor_slots = tuple(
        _doctor_slot(department_id, department_name, index)
        for index in range(1, consult_count + 1)
    )
    room_nodes = tuple(
        _consult_room(department_id, department_name, index)
        for index in range(1, consult_count + 1)
    )
    if department_id == "surgery":
        room_nodes = (
            *room_nodes,
            RoomNode(
                node_id="surgery_outpatient_procedure_room",
                name="Surgery Outpatient Procedure Room",
                room_type="outpatient_procedure",
                capacity=1,
            ),
        )
    return DepartmentResourceConfig(
        department_id=department_id,
        department_gate_capacity=gate_capacity,
        doctor_slots=doctor_slots,
        room_nodes=room_nodes,
    )


_RESOURCE_CONFIGS: dict[str, DepartmentResourceConfig] = {
    department["id"]: _build_resource_config(department["id"], department["label"])
    for department in list_departments(include_legacy=False)
}


def list_department_resource_configs() -> list[DepartmentResourceConfig]:
    return list(_RESOURCE_CONFIGS.values())


def get_department_resource_config(department_id: str | None) -> DepartmentResourceConfig | None:
    return _RESOURCE_CONFIGS.get(str(department_id or "").strip())


def get_department_gate_capacity(department_id: str | None) -> int | None:
    config = get_department_resource_config(department_id)
    if config is None:
        return None
    return config.department_gate_capacity


def get_doctor_slot_by_id(department_id: str | None, slot_id: str | None) -> DoctorSlot | None:
    config = get_department_resource_config(department_id)
    if config is None:
        return None
    for slot in config.doctor_slots:
        if slot.slot_id == slot_id:
            return slot
    return None


def get_room_node_by_id(department_id: str | None, node_id: str | None) -> RoomNode | None:
    config = get_department_resource_config(department_id)
    if config is None:
        return None
    for room in config.room_nodes:
        if room.node_id == node_id:
            return room
    return None


def stable_doctor_slot_for_patient(department_id: str | None, patient_id: str | None) -> DoctorSlot | None:
    config = get_department_resource_config(department_id)
    if config is None or not config.doctor_slots:
        return None
    identity = str(patient_id or "")
    index = sum(ord(char) for char in identity) % len(config.doctor_slots)
    return config.doctor_slots[index]


def resolve_consult_room_for_slot(department_id: str | None, slot_id: str | None) -> RoomNode | None:
    slot = get_doctor_slot_by_id(department_id, slot_id)
    if slot is not None:
        return get_room_node_by_id(department_id, slot.room_node_id)
    config = get_department_resource_config(department_id)
    if config is None:
        return None
    consult_rooms = [room for room in config.room_nodes if room.room_type == "consultation"]
    if len(consult_rooms) == 1:
        return consult_rooms[0]
    return None


def resolve_room_for_visit_state(
    department_id: str | None,
    visit_state: str | None,
    *,
    assigned_doctor_slot_id: str | None = None,
) -> RoomNode | None:
    normalized_department_id = str(department_id or "").strip()
    if visit_state in CONSULTATION_VISIT_STATES:
        return resolve_consult_room_for_slot(normalized_department_id, assigned_doctor_slot_id)
    if normalized_department_id == "surgery" and visit_state in SURGERY_PROCEDURE_VISIT_STATES:
        return get_room_node_by_id(normalized_department_id, "surgery_outpatient_procedure_room")
    return None
