import uuid

from fastapi import APIRouter, HTTPException, Request

from app.agents.internal_medicine.schemas import CreateInternalMedicineSessionRequest, InternalMedicineMessageRequest


router = APIRouter()


@router.post("/api/v1/internal-medicine-sessions")
def create_internal_medicine_session(body: CreateInternalMedicineSessionRequest, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    payload = body.model_dump()
    payload["session_id"] = payload.get("session_id") or f"im-session-{uuid.uuid4().hex[:8]}"
    try:
        return service.create_session(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/v1/internal-medicine-sessions/{session_id}/messages")
def send_internal_medicine_message(session_id: str, body: InternalMedicineMessageRequest, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    payload = body.model_dump()
    session = request.app.state.container["session_repo"].get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if not payload.get("patient_id"):
        payload["patient_id"] = session["patient_id"]
    if not payload.get("visit_id"):
        payload["visit_id"] = session.get("visit_id")
    try:
        return service.continue_session(session_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/v1/internal-medicine-sessions/{session_id}")
def get_internal_medicine_session(session_id: str, request: Request):
    service = request.app.state.container["internal_medicine_service"]
    session = request.app.state.container["session_repo"].get(session_id)
    if not session or session.get("agent_type") != "internal_medicine":
        raise HTTPException(status_code=404, detail="session not found")
    return service.build_response(session["patient_id"], session_id)
