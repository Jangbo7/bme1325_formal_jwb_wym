import uuid

from fastapi import APIRouter, Request

from app.schemas.triage import CreateTriageSessionRequest, TriageMessageRequest


router = APIRouter()


@router.post("/api/v1/triage-sessions")
def create_triage_session(body: CreateTriageSessionRequest, request: Request):
    service = request.app.state.container["triage_service"]
    payload = body.model_dump()
    payload["session_id"] = payload.get("session_id") or f"session-{uuid.uuid4().hex[:8]}"
    return service.create_session(payload)


@router.post("/api/v1/triage-sessions/{session_id}/messages")
def send_triage_message(session_id: str, body: TriageMessageRequest, request: Request):
    service = request.app.state.container["triage_service"]
    payload = body.model_dump()
    if not payload.get("patient_id"):
        session = request.app.state.container["session_repo"].get(session_id)
        payload["patient_id"] = session["patient_id"] if session else "P-self"
    return service.continue_session(session_id, payload)
