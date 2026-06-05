from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.api.contract import require_encounter_id, require_patient_id
from app.events.types import ENCOUNTER_OPENED, ENCOUNTER_TRANSFERRED, PATIENT_STATE_CHANGED, QUEUE_TICKET_CALLED, QUEUE_TICKET_COMPLETED, QUEUE_TICKET_CREATED
from app.schemas.common import QueueTicketKind, QueueTicketStatus
from app.schemas.encounter import CreateEncounterRequest, EncounterView, TransferCommand
from app.schemas.common import PatientLifecycleState
from app.schemas.orchestration import EncounterEventRequest, TransitionDebugRequest, TransitionDebugResult
from app.services.department_assignment import resolve_assigned_department_for_visit


router = APIRouter()

TRANSFER_BLOCKED_STATES = {"arrived", "error", "completed", "cancelled"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_data(visit_row: dict) -> dict:
    payload = visit_row.get("data_json")
    if not payload:
        return {}
    try:
        import json

        return json.loads(payload)
    except Exception:
        return {}


def _to_encounter_view(visit_repo, visit_row: dict) -> EncounterView:
    visit_view = visit_repo.to_view(visit_row)
    return EncounterView(
        encounter_id=visit_view.id,
        patient_id=visit_view.patient_id,
        state=visit_view.state.value.upper(),
        assigned_department_id=visit_view.assigned_department_id,
        assigned_department_name=visit_view.assigned_department_name,
        current_node=visit_view.current_node,
        current_department=visit_view.current_department,
        active_agent_type=visit_view.active_agent_type,
        data=visit_view.data,
        created_at=visit_view.created_at,
        updated_at=visit_view.updated_at,
    )


def _build_transition_result(orchestration, before_row: dict, after_row: dict, event: str) -> TransitionDebugResult:
    from_state = orchestration._resolve_standard_state(before_row)  # noqa: SLF001
    to_state = orchestration._resolve_standard_state(after_row)  # noqa: SLF001
    return TransitionDebugResult(
        encounter_id=after_row["id"],
        from_state=from_state,
        event=event,
        to_state=to_state,
        internal_from_state=before_row["state"],
        internal_to_state=after_row["state"],
        allowed_next=orchestration.allowed_next(to_state),
        dry_run=False,
    )


@router.post("/api/v1/encounters")
def create_encounter(body: CreateEncounterRequest, request: Request):
    container = request.app.state.container
    orchestration = container["encounter_orchestration_service"]
    visit_repo = container["visit_repo"]
    bus = container["event_bus"]

    payload = body.model_dump()
    patient_id = payload.get("patient_id")
    require_patient_id(patient_id, field="patient_id")

    patient_name = payload.get("name") or "Patient"
    encounter = orchestration.create_or_get_encounter(
        patient_id=patient_id,
        patient_name=patient_name,
    )
    bus.publish(
        ENCOUNTER_OPENED,
        {
            "patient_id": patient_id,
            "encounter_id": encounter["id"],
            "state": encounter["state"],
            "department": encounter.get("current_department"),
        },
    )
    return {"ok": True, "encounter": _to_encounter_view(visit_repo, encounter).model_dump()}


@router.get("/api/v1/encounters/{encounter_id}")
def get_encounter(encounter_id: str, request: Request):
    require_encounter_id(encounter_id, field="encounter_id")
    visit_repo = request.app.state.container["visit_repo"]
    visit = visit_repo.get(encounter_id)
    if not visit:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND")
    return {"ok": True, "encounter": _to_encounter_view(visit_repo, visit).model_dump()}


@router.post("/api/v1/encounters/{encounter_id}/events")
def trigger_encounter_event(encounter_id: str, body: EncounterEventRequest, request: Request):
    require_encounter_id(encounter_id, field="encounter_id")
    container = request.app.state.container
    orchestration = container["encounter_orchestration_service"]
    visit_repo = container["visit_repo"]
    patient_repo = container["patient_repo"]
    queue_repo = container["queue_repo"]
    outpatient_procedure_service = container.get("outpatient_procedure_service")
    patient_state_machine = container["triage_service"].patient_state_machine
    bus = container["event_bus"]
    visit_row = visit_repo.get(encounter_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND")
    special_handled = False
    transition = None
    updated = None
    visit_data = _decode_data(visit_row)
    requirements = visit_data.get("pre_round2_requirements") if isinstance(visit_data.get("pre_round2_requirements"), dict) else {}
    if outpatient_procedure_service is not None and body.event in {"start_outpatient_procedure", "finish_outpatient_procedure"}:
        if body.event == "start_outpatient_procedure":
            updated = outpatient_procedure_service.start_outpatient_procedure(
                visit_row,
                active_agent_type=visit_row.get("active_agent_type"),
            )
            transition = _build_transition_result(orchestration, visit_row, updated, "start_outpatient_procedure")
        else:
            updated = outpatient_procedure_service.finish_outpatient_procedure(
                visit_row,
                active_agent_type=visit_row.get("active_agent_type"),
            )
            effective_event = "order_tests" if updated.get("state") == "waiting_test" else "finish_outpatient_procedure"
            transition = _build_transition_result(orchestration, visit_row, updated, effective_event)
        special_handled = True
    elif (
        outpatient_procedure_service is not None
        and body.event == "results_ready"
        and requirements.get("outpatient_procedure_required")
    ):
        updated = outpatient_procedure_service.mark_tests_completed(
            visit_row,
            active_agent_type=visit_row.get("active_agent_type"),
        )
        effective_event = "order_outpatient_procedure" if updated.get("state") == "waiting_outpatient_procedure" else "results_ready"
        transition = _build_transition_result(orchestration, visit_row, updated, effective_event)
        special_handled = True

    if not special_handled:
        try:
            transition = orchestration.transition(
                encounter_id,
                body.event,
                context=body.context,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        updated = visit_repo.get(encounter_id)
        if not updated:
            raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND")
    patient_row = patient_repo.get(updated["patient_id"])
    assigned_department = resolve_assigned_department_for_visit(updated, patient_row)
    updated = visit_repo.update_visit(
        encounter_id,
        assigned_department_id=assigned_department["id"],
        assigned_department_name=assigned_department["label"],
    )
    if body.event == "queue_second_consultation":
        ticket = queue_repo.create_ticket(
            patient_id=updated["patient_id"],
            visit_id=updated["id"],
            department_id=assigned_department["queue_department_id"],
            department_name=assigned_department["label"],
            queue_kind=QueueTicketKind.RETURN_CONSULTATION.value,
        )
        bus.publish(
            QUEUE_TICKET_CREATED,
            {
                "patient_id": updated["patient_id"],
                "visit_id": updated["id"],
                "ticket": ticket,
            },
        )
    if body.event == "start_second_consultation":
        ticket = queue_repo.get_active_ticket_for_patient(
            updated["patient_id"],
            visit_id=updated["id"],
            queue_kind=QueueTicketKind.RETURN_CONSULTATION.value,
        )
        if not ticket:
            raise HTTPException(status_code=409, detail="return consultation ticket not found")
        if ticket.get("status") == QueueTicketStatus.WAITING.value:
            ticket = queue_repo.mark_called(ticket["id"]) or ticket
            bus.publish(
                QUEUE_TICKET_CALLED,
                {
                    "patient_id": updated["patient_id"],
                    "visit_id": updated["id"],
                    "ticket": ticket,
                },
            )
        if ticket.get("status") != QueueTicketStatus.CALLED.value:
            raise HTTPException(status_code=409, detail="return consultation ticket is not callable")
        if patient_row:
            current_patient_state = patient_row.get("lifecycle_state")
            try:
                next_patient_state = patient_state_machine.transition(
                    PatientLifecycleState(current_patient_state),
                    "start_second_consultation",
                )
            except Exception:
                next_patient_state = None
            if next_patient_state is not None:
                patient_repo.update_patient(
                    updated["patient_id"],
                    lifecycle_state=next_patient_state.value,
                    location="Consultation",
                    visit_id=updated["id"],
                )
                bus.publish(
                    PATIENT_STATE_CHANGED,
                    {
                        "patient_id": updated["patient_id"],
                        "lifecycle_state": next_patient_state.value,
                    },
                )
        completed_ticket = queue_repo.mark_completed(ticket["id"])
        if completed_ticket:
            bus.publish(
                QUEUE_TICKET_COMPLETED,
                {
                    "patient_id": updated["patient_id"],
                    "visit_id": updated["id"],
                    "ticket": completed_ticket,
                },
            )
    return {
        "ok": True,
        "encounter": _to_encounter_view(visit_repo, updated).model_dump(),
        "transition": transition.model_dump(),
    }


@router.post("/api/v1/encounters/{encounter_id}/transfer")
def transfer_encounter(encounter_id: str, body: TransferCommand, request: Request):
    require_encounter_id(encounter_id, field="encounter_id")

    container = request.app.state.container
    visit_repo = container["visit_repo"]
    bus = container["event_bus"]
    orchestration = container["encounter_orchestration_service"]

    visit = visit_repo.get(encounter_id)
    if not visit:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND")

    state = (visit.get("state") or "").lower()
    if state in TRANSFER_BLOCKED_STATES:
        raise HTTPException(status_code=409, detail="STATE_TRANSITION_INVALID")

    transfer = body.model_dump()
    data = _decode_data(visit)
    history = data.get("transfer_history")
    if not isinstance(history, list):
        history = []

    transfer_record = {
        "at": now_iso(),
        "from_group": transfer["from_group"],
        "to_group": transfer["to_group"],
        "reason": transfer["reason"],
        "ctas_level": transfer.get("ctas_level"),
        "summary": transfer.get("summary") or {},
        "requested_resources": transfer.get("requested_resources") or {},
        "status": "accepted",
    }
    history.append(transfer_record)
    data["transfer_history"] = history
    data["latest_transfer"] = transfer_record

    try:
        orchestration.transition(
            encounter_id,
            "start_transfer",
            context={"from_group": transfer["from_group"], "to_group": transfer["to_group"], "reason": transfer["reason"]},
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated = visit_repo.update_visit(
        encounter_id,
        data=data,
        current_node="transfer",
        current_department=transfer["to_group"],
        active_agent_type=None,
    )

    bus.publish(
        ENCOUNTER_TRANSFERRED,
        {
            "patient_id": updated["patient_id"],
            "encounter_id": encounter_id,
            "from_group": transfer["from_group"],
            "to_group": transfer["to_group"],
            "reason": transfer["reason"],
            "ctas_level": transfer.get("ctas_level"),
            "status": "accepted",
        },
    )

    return {
        "ok": True,
        "data": {
            "transfer_id": f"TRF-{encounter_id}",
            "status": "accepted",
            "encounter": _to_encounter_view(visit_repo, updated).model_dump(),
        },
    }


def _require_state_debug_enabled(container: dict) -> None:
    if not container.get("settings", {}).get("state_debug_enabled", False):
        raise HTTPException(status_code=404, detail="STATE_DEBUG_DISABLED")


@router.get("/api/v1/encounters/{encounter_id}/state-debug")
def get_state_debug(encounter_id: str, request: Request):
    container = request.app.state.container
    _require_state_debug_enabled(container)
    require_encounter_id(encounter_id, field="encounter_id")
    orchestration = container["encounter_orchestration_service"]
    try:
        view = orchestration.state_debug_view(encounter_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND") from exc
    return {"ok": True, "data": view.model_dump()}


@router.post("/api/v1/encounters/{encounter_id}/state-debug/transition")
def transition_state_debug(encounter_id: str, body: TransitionDebugRequest, request: Request):
    container = request.app.state.container
    _require_state_debug_enabled(container)
    require_encounter_id(encounter_id, field="encounter_id")
    if body.dry_run and not container.get("settings", {}).get("state_debug_allow_force", False):
        # dry-run does not mutate; always allowed. Keep flag reserved but harmless for now.
        pass
    orchestration = container["encounter_orchestration_service"]
    try:
        result = orchestration.transition(
            encounter_id,
            body.event,
            dry_run=body.dry_run,
            context=body.context,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "data": result.model_dump()}


@router.post("/api/v1/encounters/{encounter_id}/state-debug/reset")
def reset_state_debug(encounter_id: str, request: Request):
    container = request.app.state.container
    _require_state_debug_enabled(container)
    require_encounter_id(encounter_id, field="encounter_id")
    orchestration = container["encounter_orchestration_service"]
    try:
        result = orchestration.reset(
            encounter_id,
            context={"source": "state_debug_api"},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND") from exc
    return {"ok": True, "data": result.model_dump()}


@router.post("/api/v1/encounters/{encounter_id}/state-debug/back")
def rollback_state_debug(encounter_id: str, request: Request):
    container = request.app.state.container
    _require_state_debug_enabled(container)
    require_encounter_id(encounter_id, field="encounter_id")
    orchestration = container["encounter_orchestration_service"]
    try:
        result = orchestration.rollback(
            encounter_id,
            context={"source": "state_debug_api"},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "data": result.model_dump()}


@router.get("/api/v1/state-machine/graph")
def get_state_machine_graph(request: Request):
    container = request.app.state.container
    _require_state_debug_enabled(container)
    orchestration = container["encounter_orchestration_service"]
    return {"ok": True, "data": orchestration.graph()}
