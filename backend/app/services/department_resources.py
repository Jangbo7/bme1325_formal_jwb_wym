from __future__ import annotations

from dataclasses import dataclass

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
    doctor_slots: tuple[DoctorSlot, ...]
    room_nodes: tuple[RoomNode, ...]


SURGERY_RESOURCE_CONFIG = DepartmentResourceConfig(
    department_id="surgery",
    doctor_slots=(
        DoctorSlot(
            slot_id="surgery_doctor_slot_1",
            label="Surgery Doctor Slot 1",
            capacity=1,
            room_node_id="surgery_consult_room_1",
        ),
        DoctorSlot(
            slot_id="surgery_doctor_slot_2",
            label="Surgery Doctor Slot 2",
            capacity=1,
            room_node_id="surgery_consult_room_2",
        ),
    ),
    room_nodes=(
        RoomNode(
            node_id="surgery_consult_room_1",
            name="Surgery Consultation Room 1",
            room_type="consultation",
            capacity=1,
        ),
        RoomNode(
            node_id="surgery_consult_room_2",
            name="Surgery Consultation Room 2",
            room_type="consultation",
            capacity=1,
        ),
        RoomNode(
            node_id="surgery_outpatient_procedure_room",
            name="Surgery Outpatient Procedure Room",
            room_type="outpatient_procedure",
            capacity=1,
        ),
    ),
)


_RESOURCE_CONFIGS: dict[str, DepartmentResourceConfig] = {
    SURGERY_RESOURCE_CONFIG.department_id: SURGERY_RESOURCE_CONFIG,
}


def list_department_resource_configs() -> list[DepartmentResourceConfig]:
    return list(_RESOURCE_CONFIGS.values())


def get_department_resource_config(department_id: str | None) -> DepartmentResourceConfig | None:
    return _RESOURCE_CONFIGS.get(str(department_id or "").strip())


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
    if slot is None:
        return None
    return get_room_node_by_id(department_id, slot.room_node_id)


def resolve_room_for_visit_state(
    department_id: str | None,
    visit_state: str | None,
    *,
    assigned_doctor_slot_id: str | None = None,
) -> RoomNode | None:
    if str(department_id or "").strip() != "surgery":
        return None
    if visit_state in {
        VisitLifecycleState.IN_CONSULTATION.value,
        VisitLifecycleState.IN_SECOND_CONSULTATION.value,
    }:
        return resolve_consult_room_for_slot(department_id, assigned_doctor_slot_id)
    if visit_state in {
        VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
        VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
    }:
        return get_room_node_by_id(department_id, "surgery_outpatient_procedure_room")
    return None
