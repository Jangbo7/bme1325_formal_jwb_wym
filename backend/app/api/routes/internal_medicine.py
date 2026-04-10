import uuid

from fastapi import APIRouter, Request

from app.agents.internal_medicine.schemas import (
    CreateInternalMedicineSessionRequest,
    InternalMedicineMessageRequest,
)


router = APIRouter()


@router.post("/api/v1/internal-medicine-sessions")
def create_internal_medicine_session(body: CreateInternalMedicineSessionRequest, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    payload = body.model_dump()
    payload["session_id"] = payload.get("session_id") or f"im-session-{uuid.uuid4().hex[:8]}"
    return service.create_session(payload)


@router.post("/api/v1/internal-medicine-sessions/{session_id}/messages")
def send_internal_medicine_message(session_id: str, body: InternalMedicineMessageRequest, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    payload = body.model_dump()
    if not payload.get("patient_id"):
        session = request.app.state.container["session_repo"].get(session_id)
        payload["patient_id"] = session["patient_id"] if session else "P-self"
    return service.continue_session(session_id, payload)


@router.get("/api/v1/internal-medicine-sessions/{session_id}")
def get_internal_medicine_session(session_id: str, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    session = request.app.state.container["session_repo"].get(session_id)
    if not session:
        return {"ok": False, "error": "Session not found"}
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


@router.get("/api/v1/internal-medicine-patients")
def list_internal_medicine_patients(request: Request):
    service = request.app.state.container["internal_medicine_service"]
    return {"ok": True, "patients": service.list_patient_views()}
