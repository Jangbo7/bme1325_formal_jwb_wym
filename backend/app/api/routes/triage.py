import uuid

from fastapi import APIRouter, HTTPException, Request

from app.schemas.triage import CreateTriageSessionRequest, TriageMessageRequest


router = APIRouter()


@router.post("/api/v1/triage-sessions")
def create_triage_session(body: CreateTriageSessionRequest, request: Request):
    service = request.app.state.container["triage_service"]
    payload = body.model_dump()
    payload["session_id"] = payload.get("session_id") or f"session-{uuid.uuid4().hex[:8]}"
    try:
        return service.create_session(payload)
    except Exception as e:
        print(f"Error creating triage session: {e}")
        raise


@router.post("/api/v1/triage-sessions/{session_id}/messages")
def send_triage_message(session_id: str, body: TriageMessageRequest, request: Request):
    service = request.app.state.container["triage_service"]
    session_repo = request.app.state.container["session_repo"]
    payload = body.model_dump()
    session = session_repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="triage session not found")

    if not payload.get("patient_id"):
        payload["patient_id"] = session["patient_id"]
    if not payload.get("visit_id"):
        payload["visit_id"] = session.get("visit_id")

    try:
        return service.continue_session(session_id, payload)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
