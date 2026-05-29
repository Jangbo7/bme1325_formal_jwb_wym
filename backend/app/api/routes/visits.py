from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.api.contract import require_encounter_id, require_patient_id
from app.events.types import PATIENT_STATE_CHANGED, QUEUE_TICKET_CALLED, QUEUE_TICKET_COMPLETED, QUEUE_TICKET_CREATED, VISIT_STATE_CHANGED
from app.schemas.common import PatientLifecycleState, QueueTicketKind, QueueTicketStatus, VisitLifecycleState
from app.schemas.visit import CreateVisitRequest, RegisterVisitRequest
from app.services.consultation_registry import resolve_consultation_agent_for_visit
from app.services.department_assignment import resolve_assigned_department_for_visit


router = APIRouter()

WAIT_SECONDS = 10
FIXED_QUEUE_DEPARTMENT_ID = "doctor_entry"
FIXED_QUEUE_DEPARTMENT_NAME = "Doctor Entry"
CONSULTATION_ROOM = "Consultation Room"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _get_visit_data(visit_row: dict) -> dict:
    data_json = visit_row.get("data_json")
    if not data_json:
        return {}
    try:
        import json

        return json.loads(data_json)
    except Exception:
        return {}


def _transition_visit(container: dict, visit_row: dict, event: str, *, current_node: str | None = None, current_department: str | None = None, active_agent_type: str | None = None, data: dict | None = None) -> dict:
    visit_repo = container["visit_repo"]
    bus = container["event_bus"]
    orchestration = container.get("encounter_orchestration_service")
    if orchestration is not None:
        try:
            orchestration.transition(
                visit_row["id"],
                event,
                dry_run=False,
                context={"source": "visits.route"},
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        updated_after_state = visit_repo.get(visit_row["id"]) or visit_row
        merged_data = _get_visit_data(updated_after_state)
        if data is not None:
            protected_keys = {"orchestration_state", "orchestration_history", "orchestration_debug_log"}
            for key, value in data.items():
                if key in protected_keys:
                    continue
                merged_data[key] = value
        return visit_repo.update_visit(
            visit_row["id"],
            current_node=current_node if current_node is not None else updated_after_state.get("current_node"),
            current_department=current_department if current_department is not None else updated_after_state.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else updated_after_state.get("active_agent_type"),
            data=merged_data,
        )

    next_state_value = visit_row["state"]
    visit_state_machine = container["visit_state_machine"]
    current_state = VisitLifecycleState(visit_row["state"])
    next_state = visit_state_machine.transition(current_state, event)
    next_state_value = next_state.value

    updated = visit_repo.update_visit(
        visit_row["id"],
        state=next_state_value,
        current_node=current_node if current_node is not None else visit_row.get("current_node"),
        current_department=current_department if current_department is not None else visit_row.get("current_department"),
        active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
        data=data if data is not None else _get_visit_data(visit_row),
    )
    bus.publish(
        VISIT_STATE_CHANGED,
        {
            "visit_id": updated["id"],
            "patient_id": updated["patient_id"],
            "state": updated["state"],
            "event": event,
        },
    )
    return updated


def _build_action_response(container: dict, patient_id: str, visit_row: dict) -> dict:
    triage_service = container["triage_service"]
    queue_repo = container["queue_repo"]

    patient_view = triage_service.get_patient_view(patient_id)
    queue_ticket = queue_repo.get_active_ticket_for_patient(patient_id, visit_id=visit_row["id"])
    visit_view = container["visit_repo"].to_view(visit_row).model_dump()

    ready_for_consultation = bool(
        patient_view
        and patient_view.lifecycle_state == PatientLifecycleState.CALLED
        and patient_view.visit_state == VisitLifecycleState.WAITING_CONSULTATION
    )

    return {
        "ok": True,
        "visit": visit_view,
        "patient": patient_view.model_dump() if patient_view else None,
        "queue_ticket": queue_ticket,
        "ready_for_consultation": ready_for_consultation,
        "wait_seconds": WAIT_SECONDS,
    }


@router.post("/api/v1/visits")
def create_or_get_visit(body: CreateVisitRequest, request: Request):
    container = request.app.state.container
    patient_repo = container["patient_repo"]
    visit_repo = container["visit_repo"]
    payload = body.model_dump()

    patient_id = payload["patient_id"]
    require_patient_id(patient_id, field="patient_id")
    name = payload.get("name") or "You (Player)"
    patient_repo.upsert_basic(patient_id, name)

    visit = visit_repo.create_or_get_active(patient_id)
    patient_repo.update_patient(patient_id, name=name, visit_id=visit["id"])
    return {"ok": True, "visit": visit_repo.to_view(visit).model_dump()}


@router.get("/api/v1/visits/{visit_id}")
def get_visit(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    visit_repo = request.app.state.container["visit_repo"]
    visit = visit_repo.get(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="visit not found")
    return {"visit": visit_repo.to_view(visit).model_dump()}


@router.post("/api/v1/visits/{visit_id}/register")
def register_visit(visit_id: str, body: RegisterVisitRequest, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    container = request.app.state.container
    visit_repo = container["visit_repo"]
    patient_repo = container["patient_repo"]
    queue_repo = container["queue_repo"]
    patient_state_machine = container["triage_service"].patient_state_machine
    bus = container["event_bus"]

    visit_row = visit_repo.get(visit_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="visit not found")

    patient_id = visit_row["patient_id"]
    patient_row = patient_repo.get(patient_id)
    if not patient_row:
        raise HTTPException(status_code=404, detail="patient not found")

    visit_state = VisitLifecycleState(visit_row["state"])
    if visit_state in {VisitLifecycleState.REGISTERED, VisitLifecycleState.WAITING_CONSULTATION, VisitLifecycleState.IN_CONSULTATION}:
        return _build_action_response(container, patient_id, visit_row)

    if visit_state != VisitLifecycleState.TRIAGED:
        raise HTTPException(status_code=409, detail="visit must be triaged before registration")

    profile_payload = body.model_dump()
    registration_profile = {
        "name": (profile_payload.get("name") or "You (Player)").strip() or "You (Player)",
        "sex": (profile_payload.get("sex") or "unknown").strip() or "unknown",
        "age": max(0, int(profile_payload.get("age") or 0)),
        "id_number": (profile_payload.get("id_number") or "TEMP-REG-0001").strip() or "TEMP-REG-0001",
    }

    visit_data = _get_visit_data(visit_row)
    visit_data["registration_completed_at"] = now_iso()
    visit_data["registration_profile"] = registration_profile
    assigned_department = resolve_assigned_department_for_visit(visit_row, patient_row)
    visit_row = _transition_visit(
        container,
        visit_row,
        "register_completed",
        current_node="registration_queue",
        current_department=assigned_department["label"],
        active_agent_type=None,
        data=visit_data,
    )

    ticket = queue_repo.create_ticket(
        patient_id=patient_id,
        visit_id=visit_row["id"],
        department_id=assigned_department["queue_department_id"],
        department_name=assigned_department["label"],
        queue_kind=QueueTicketKind.INITIAL_CONSULTATION.value,
    )
    bus.publish(
        QUEUE_TICKET_CREATED,
        {
            "patient_id": patient_id,
            "visit_id": visit_row["id"],
            "ticket": ticket,
        },
    )

    current_patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
    if current_patient_state == PatientLifecycleState.TRIAGED:
        next_state = patient_state_machine.transition(current_patient_state, "queue_created")
    else:
        next_state = current_patient_state
    patient_repo.update_patient(
        patient_id,
        name=registration_profile["name"],
        lifecycle_state=next_state.value,
        location=assigned_department["label"],
        visit_id=visit_row["id"],
    )
    bus.publish(
        PATIENT_STATE_CHANGED,
        {
            "patient_id": patient_id,
            "lifecycle_state": next_state.value,
        },
    )

    return _build_action_response(container, patient_id, visit_row)


@router.post("/api/v1/visits/{visit_id}/progress")
def progress_visit(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    container = request.app.state.container
    visit_repo = container["visit_repo"]
    patient_repo = container["patient_repo"]
    queue_repo = container["queue_repo"]
    patient_state_machine = container["triage_service"].patient_state_machine
    bus = container["event_bus"]

    visit_row = visit_repo.get(visit_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="visit not found")

    patient_id = visit_row["patient_id"]
    patient_row = patient_repo.get(patient_id)
    if not patient_row:
        raise HTTPException(status_code=404, detail="patient not found")

    if VisitLifecycleState(visit_row["state"]) != VisitLifecycleState.REGISTERED:
        return _build_action_response(container, patient_id, visit_row)

    visit_data = _get_visit_data(visit_row)
    registered_at = _parse_iso(visit_data.get("registration_completed_at"))
    if not registered_at:
        registered_at = _parse_iso(visit_row.get("updated_at"))

    if not registered_at:
        return _build_action_response(container, patient_id, visit_row)

    elapsed = (datetime.now(timezone.utc) - registered_at).total_seconds()
    if elapsed < WAIT_SECONDS:
        return _build_action_response(container, patient_id, visit_row)

    assigned_department = resolve_assigned_department_for_visit(visit_row, patient_row)
    ticket = queue_repo.get_active_ticket_for_patient(patient_id, visit_id=visit_id)
    if ticket and ticket.get("status") == QueueTicketStatus.WAITING.value:
        ticket = queue_repo.mark_called(ticket["id"]) or ticket
        bus.publish(
            QUEUE_TICKET_CALLED,
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "ticket": ticket,
            },
        )

    current_patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
    if current_patient_state == PatientLifecycleState.QUEUED:
        next_state = patient_state_machine.transition(current_patient_state, "ticket_called")
        patient_repo.update_patient(
            patient_id,
            lifecycle_state=next_state.value,
            location=assigned_department["label"],
            visit_id=visit_id,
        )
        bus.publish(
            PATIENT_STATE_CHANGED,
            {
                "patient_id": patient_id,
                "lifecycle_state": next_state.value,
            },
        )

    visit_row = _transition_visit(
        container,
        visit_row,
        "queue_wait_elapsed",
        current_node=f"{assigned_department['id']}_queue_gate",
        current_department=assigned_department["label"],
        active_agent_type=None,
        data=visit_data,
    )

    return _build_action_response(container, patient_id, visit_row)


@router.post("/api/v1/visits/{visit_id}/enter-consultation")
def enter_consultation(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    container = request.app.state.container
    visit_repo = container["visit_repo"]
    patient_repo = container["patient_repo"]
    queue_repo = container["queue_repo"]
    patient_state_machine = container["triage_service"].patient_state_machine
    bus = container["event_bus"]

    visit_row = visit_repo.get(visit_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="visit not found")

    patient_id = visit_row["patient_id"]
    patient_row = patient_repo.get(patient_id)
    if not patient_row:
        raise HTTPException(status_code=404, detail="patient not found")

    visit_state = VisitLifecycleState(visit_row["state"])
    if visit_state != VisitLifecycleState.WAITING_CONSULTATION:
        raise HTTPException(status_code=409, detail="visit is not ready for consultation")

    patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
    if patient_state != PatientLifecycleState.CALLED:
        raise HTTPException(status_code=409, detail="patient has not been called yet")

    ticket = queue_repo.get_active_ticket_for_patient(patient_id, visit_id=visit_id)
    if not ticket or ticket.get("status") != QueueTicketStatus.CALLED.value:
        raise HTTPException(status_code=409, detail="queue ticket is not in called status")

    next_patient_state = patient_state_machine.transition(patient_state, "start_consultation")
    assigned_department = resolve_assigned_department_for_visit(visit_row, patient_row)
    consultation_definition = resolve_consultation_agent_for_visit(visit_row, patient_row)
    patient_repo.update_patient(
        patient_id,
        lifecycle_state=next_patient_state.value,
        location=CONSULTATION_ROOM,
        visit_id=visit_id,
    )
    bus.publish(
        PATIENT_STATE_CHANGED,
        {
            "patient_id": patient_id,
            "lifecycle_state": next_patient_state.value,
        },
    )

    visit_row = _transition_visit(
        container,
        visit_row,
        "start_consultation",
        current_node=f"{assigned_department['id']}_consultation_room",
        current_department=CONSULTATION_ROOM,
        active_agent_type=consultation_definition.agent_type if consultation_definition else None,
        data=_get_visit_data(visit_row),
    )
    completed_ticket = queue_repo.mark_completed(ticket["id"])
    if completed_ticket:
        bus.publish(
            QUEUE_TICKET_COMPLETED,
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "ticket": completed_ticket,
            },
        )

    return _build_action_response(container, patient_id, visit_row)


@router.post("/api/v1/visits/{visit_id}/ready-payment")
def ready_payment(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    container = request.app.state.container
    visit_repo = container["visit_repo"]

    visit_row = visit_repo.get(visit_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="visit not found")

    visit_state = VisitLifecycleState(visit_row["state"])
    if visit_state != VisitLifecycleState.DIAGNOSIS_FINALIZED:
        raise HTTPException(status_code=409, detail="visit is not in diagnosis_finalized")

    visit_row = _transition_visit(
        container,
        visit_row,
        "request_medical_payment",
        current_node="payment_wait",
        current_department="Payment",
        active_agent_type=None,
        data=_get_visit_data(visit_row),
    )
    return {"ok": True, "visit": visit_repo.to_view(visit_row).model_dump()}


@router.get("/api/v1/visits/{visit_id}/simulated-report")
def get_simulated_report(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    visit_repo = request.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="visit not found")
    visit_data = _get_visit_data(visit_row)
    report = visit_data.get("simulated_report")
    if not isinstance(report, dict):
        raise HTTPException(status_code=404, detail="simulated report not found")
    return {
        "ok": True,
        "visit_id": visit_id,
        "visit_state": visit_row.get("state"),
        "report": report,
    }
