from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.api.contract import require_encounter_id, require_patient_id
from app.events.types import ENCOUNTER_OPENED, ENCOUNTER_TRANSFERRED
from app.schemas.encounter import CreateEncounterRequest, EncounterView, TransferCommand
from app.schemas.orchestration import EncounterEventRequest, TransitionDebugRequest


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
        current_node=visit_view.current_node,
        current_department=visit_view.current_department,
        active_agent_type=visit_view.active_agent_type,
        data=visit_view.data,
        created_at=visit_view.created_at,
        updated_at=visit_view.updated_at,
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
    visit_row = visit_repo.get(encounter_id)
    if not visit_row:
        raise HTTPException(status_code=404, detail="ENCOUNTER_NOT_FOUND")
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
