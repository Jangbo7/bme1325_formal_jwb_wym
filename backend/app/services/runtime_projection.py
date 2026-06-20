from __future__ import annotations

from app.schemas.common import DepartmentFlowStatus, VisitLifecycleState
from app.services.department_resources import get_department_resource_config


TRIAGE_VISIT_STATES = {
    VisitLifecycleState.ARRIVED.value,
    VisitLifecycleState.TRIAGING.value,
    VisitLifecycleState.IN_TRIAGE.value,
    VisitLifecycleState.WAITING_FOLLOWUP.value,
    VisitLifecycleState.TRIAGED.value,
}

PAYMENT_VISIT_STATES = {
    VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
    VisitLifecycleState.WAITING_PAYMENT.value,
    VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
}

FINISHED_VISIT_STATES = {
    VisitLifecycleState.IN_EMERGENCY.value,
    VisitLifecycleState.IN_ICU_RESCUE.value,
    VisitLifecycleState.DISPOSITION_REFERRAL.value,
    VisitLifecycleState.ADMITTED.value,
    VisitLifecycleState.TRANSFERRING.value,
    VisitLifecycleState.COMPLETED.value,
}

ROUND1_PHASES = {"internal_medicine_round1", "consultation_round1"}
ROUND2_PHASES = {"internal_medicine_round2", "consultation_round2"}

SYSTEM_RESOURCE_NAMES = {
    "triage": "Triage",
    "testing": "Testing",
    "payment": "Payment",
    "pharmacy": "Pharmacy",
}


def derive_runtime_projection(
    *,
    assigned_department_id: str | None,
    assigned_department_name: str | None,
    assigned_doctor_slot_id: str | None,
    assigned_doctor_slot_name: str | None,
    current_node_id: str | None,
    current_room_node_id: str | None,
    current_room_name: str | None,
    room_type: str | None,
    target_node_id: str | None,
    visit_state: str | None,
    patient_lifecycle_state: str | None,
    department_status: str | None,
    department_round: str | None,
    phase: str | None,
    status: str | None,
    finished: bool,
    last_error: str | None,
) -> dict[str, object]:
    consultation_round = derive_consultation_round(
        department_round=department_round,
        department_status=department_status,
        visit_state=visit_state,
        phase=phase,
    )
    display_stage = derive_display_stage(
        assigned_department_id=assigned_department_id,
        visit_state=visit_state,
        patient_lifecycle_state=patient_lifecycle_state,
        department_status=department_status,
        finished=finished,
    )
    dispatch_state = derive_dispatch_state(
        display_stage=display_stage,
        status=status,
        finished=finished,
        last_error=last_error,
    )
    target_resource = classify_resource(
        node_id=target_node_id,
        assigned_department_id=assigned_department_id,
        assigned_department_name=assigned_department_name,
        current_room_node_id=current_room_node_id,
        current_room_name=current_room_name,
        room_type=room_type,
    )
    blocking = build_blocking_view(
        dispatch_state=dispatch_state,
        target_resource=target_resource,
        last_error=last_error,
    )
    return {
        "display_stage": display_stage,
        "dispatch_state": dispatch_state,
        "consultation_round": consultation_round,
        "blocking": blocking,
        "resource_assignment": {
            "department_id": assigned_department_id,
            "department_name": assigned_department_name,
            "department_gate_id": assigned_department_id if assigned_department_id not in {None, "unassigned"} else None,
            "department_gate_name": (
                f"{assigned_department_name} Gate"
                if assigned_department_id not in {None, "unassigned"} and assigned_department_name
                else None
            ),
            "doctor_slot_id": assigned_doctor_slot_id,
            "doctor_slot_name": assigned_doctor_slot_name,
            "consultation_room_id": current_room_node_id,
            "consultation_room_name": current_room_name,
            "consultation_room_type": room_type,
            "current_node_id": current_node_id,
            "target_node_id": target_node_id,
            "target_resource_kind": target_resource["resource_kind"],
        },
    }


def derive_display_stage(
    *,
    assigned_department_id: str | None,
    visit_state: str | None,
    patient_lifecycle_state: str | None,
    department_status: str | None,
    finished: bool,
) -> str:
    if finished:
        return "finished"
    if visit_state in {VisitLifecycleState.ERROR.value, VisitLifecycleState.CANCELLED.value}:
        return "error"
    if visit_state in PAYMENT_VISIT_STATES:
        return "payment"
    if visit_state == VisitLifecycleState.WAITING_PHARMACY.value:
        return "pharmacy"
    if visit_state in FINISHED_VISIT_STATES:
        return "finished"
    if visit_state in {
        VisitLifecycleState.WAITING_TEST.value,
        VisitLifecycleState.WAITING_TEST_PAYMENT.value,
        VisitLifecycleState.TEST_PAYMENT_COMPLETED.value,
        VisitLifecycleState.IN_TEST.value,
        VisitLifecycleState.WAITING_RETURN_CONSULTATION.value,
        VisitLifecycleState.RESULTS_READY.value,
    }:
        return "testing"
    if visit_state in {
        VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
        VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
    }:
        return "procedure"
    if department_status == DepartmentFlowStatus.ASSIGNED_PENDING_REGISTRATION.value:
        return "pending_registration"
    if department_status in {
        DepartmentFlowStatus.WAITING_QUEUE_ROUND1.value,
        DepartmentFlowStatus.WAITING_QUEUE_ROUND2.value,
    }:
        return "waiting_call"
    if department_status in {
        DepartmentFlowStatus.CALLED_ROUND1.value,
        DepartmentFlowStatus.CALLED_ROUND2.value,
    }:
        return "called"
    if department_status in {
        DepartmentFlowStatus.IN_CONSULTATION_ROUND1.value,
        DepartmentFlowStatus.IN_CONSULTATION_ROUND2.value,
    }:
        return "consultation"
    if department_status == DepartmentFlowStatus.FINISHED.value:
        return "finished"
    if visit_state in TRIAGE_VISIT_STATES:
        if department_status == DepartmentFlowStatus.ASSIGNED_PENDING_REGISTRATION.value:
            return "pending_registration"
        return "triage"
    if assigned_department_id in {None, "unassigned"}:
        if patient_lifecycle_state in {"triaging", "arrived"}:
            return "triage"
        return "unassigned"
    if visit_state in {
        VisitLifecycleState.REGISTERED.value,
        VisitLifecycleState.WAITING_CONSULTATION.value,
        VisitLifecycleState.WAITING_SECOND_CONSULTATION.value,
    }:
        return "waiting_call"
    if visit_state in {
        VisitLifecycleState.IN_CONSULTATION.value,
        VisitLifecycleState.IN_SECOND_CONSULTATION.value,
    }:
        return "consultation"
    return "department_flow"


def derive_dispatch_state(
    *,
    display_stage: str,
    status: str | None,
    finished: bool,
    last_error: str | None,
) -> str:
    normalized_error = (last_error or "").lower()
    if finished or display_stage == "finished":
        return "finished"
    if display_stage == "error" or status == "error":
        return "error"
    if status == "waiting_capacity" or normalized_error.startswith("node capacity reached:"):
        return "blocked_capacity"
    if status == "waiting_fullview":
        return "waiting_fullview"
    if status == "blocked":
        return "blocked_guard"
    return "ready"


def derive_consultation_round(
    *,
    department_round: str | None,
    department_status: str | None,
    visit_state: str | None,
    phase: str | None,
) -> int | None:
    if department_round == "round1":
        return 1
    if department_round == "round2":
        return 2
    if department_status in {
        DepartmentFlowStatus.WAITING_QUEUE_ROUND1.value,
        DepartmentFlowStatus.CALLED_ROUND1.value,
        DepartmentFlowStatus.IN_CONSULTATION_ROUND1.value,
    }:
        return 1
    if department_status in {
        DepartmentFlowStatus.WAITING_QUEUE_ROUND2.value,
        DepartmentFlowStatus.CALLED_ROUND2.value,
        DepartmentFlowStatus.IN_CONSULTATION_ROUND2.value,
    }:
        return 2
    if phase in ROUND1_PHASES:
        return 1
    if phase in ROUND2_PHASES:
        return 2
    if visit_state in {
        VisitLifecycleState.REGISTERED.value,
        VisitLifecycleState.WAITING_CONSULTATION.value,
        VisitLifecycleState.IN_CONSULTATION.value,
    }:
        return 1
    if visit_state in {
        VisitLifecycleState.WAITING_SECOND_CONSULTATION.value,
        VisitLifecycleState.IN_SECOND_CONSULTATION.value,
    }:
        return 2
    return None


def build_blocking_view(
    *,
    dispatch_state: str,
    target_resource: dict[str, str | None],
    last_error: str | None,
) -> dict[str, str | None] | None:
    if dispatch_state not in {"blocked_capacity", "blocked_guard", "waiting_fullview", "error"}:
        return None
    if dispatch_state == "blocked_capacity":
        kind = "capacity"
    elif dispatch_state == "blocked_guard":
        kind = "guard"
    elif dispatch_state == "waiting_fullview":
        kind = "fullview"
    else:
        kind = "error"
    return {
        "kind": kind,
        "resource_kind": target_resource["resource_kind"],
        "resource_id": target_resource["resource_id"],
        "resource_name": target_resource["resource_name"],
        "message": last_error,
    }


def classify_resource(
    *,
    node_id: str | None,
    assigned_department_id: str | None,
    assigned_department_name: str | None,
    current_room_node_id: str | None,
    current_room_name: str | None,
    room_type: str | None,
) -> dict[str, str | None]:
    if not node_id:
        return {
            "resource_kind": None,
            "resource_id": None,
            "resource_name": None,
        }
    if assigned_department_id not in {None, "unassigned"} and node_id == assigned_department_id:
        return {
            "resource_kind": "department_gate",
            "resource_id": node_id,
            "resource_name": f"{assigned_department_name or assigned_department_id} Gate",
        }
    if current_room_node_id and node_id == current_room_node_id:
        return {
            "resource_kind": normalize_room_resource_kind(room_type),
            "resource_id": node_id,
            "resource_name": current_room_name or node_id,
        }
    if node_id in SYSTEM_RESOURCE_NAMES:
        return {
            "resource_kind": node_id,
            "resource_id": node_id,
            "resource_name": SYSTEM_RESOURCE_NAMES[node_id],
        }
    config = get_department_resource_config(assigned_department_id) if assigned_department_id not in {None, "unassigned"} else None
    if config is not None:
        for room in config.room_nodes:
            if room.node_id == node_id:
                return {
                    "resource_kind": normalize_room_resource_kind(room.room_type),
                    "resource_id": room.node_id,
                    "resource_name": room.name,
                }
    return {
        "resource_kind": "node",
        "resource_id": node_id,
        "resource_name": node_id,
    }


def normalize_room_resource_kind(room_type: str | None) -> str:
    if room_type == "consultation":
        return "consultation_room"
    if room_type == "outpatient_procedure":
        return "outpatient_procedure"
    if room_type:
        return room_type
    return "room"
