import uuid

from fastapi import APIRouter, HTTPException, Request

from app.api.contract import require_patient_id
from app.agents.icu_doctor.schemas import CreateICUSessionRequest, ICUMessageRequest


router = APIRouter()


@router.post("/api/v1/icu-sessions")
def create_icu_session(body: CreateICUSessionRequest, request: Request):
    service = request.app.state.container["icu_doctor_service"]
    payload = body.model_dump()
    require_patient_id(payload.get("patient_id"), field="patient_id")
    payload["session_id"] = payload.get("session_id") or f"icu-session-{uuid.uuid4().hex[:8]}"
    return service.create_session(payload)


@router.post("/api/v1/icu-sessions/{session_id}/messages")
def send_icu_message(session_id: str, body: ICUMessageRequest, request: Request):
    service = request.app.state.container["icu_doctor_service"]
    session_repo = request.app.state.container["session_repo"]
    payload = body.model_dump()
    if not payload.get("patient_id"):
        session = session_repo.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        payload["patient_id"] = session["patient_id"]
    require_patient_id(payload.get("patient_id"), field="patient_id")
    return service.continue_session(session_id, payload)


@router.get("/api/v1/icu-sessions/{session_id}")
def get_icu_session(session_id: str, request: Request):
    service = request.app.state.container["icu_doctor_service"]
    session = request.app.state.container["session_repo"].get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    patient_id = session["patient_id"]
    return {
        "ok": True,
        "session_id": session_id,
        "patient": service.get_patient_view(patient_id),
        "dialogue": {
            "status": session["dialogue_state"],
            "turns": request.app.state.container["session_repo"].list_turns(session_id),
        },
    }


@router.get("/api/v1/icu-patients")
def list_icu_patients(request: Request):
    service = request.app.state.container["icu_doctor_service"]
    return {"ok": True, "patients": service.list_patient_views()}
