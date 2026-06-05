from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.routes._agent_debug_page import render_agent_debug_page
from app.schemas.agent_debug import AgentDebugMessageRequest, AgentDebugPreloadRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["patient_agent_chat_debug_controller"]


@router.get("/patient-agent-chat-debug", include_in_schema=False)
def patient_agent_chat_debug_page(request: Request):
    return render_agent_debug_page(
        title="Patient Agent Chat Debug",
        heading="Patient Agent Chat Debug",
        description="Preset case card + JSON editing, then ask the patient agent one question at a time and inspect policy/prompt/RAG trace.",
        page_slug="patient-agent-chat-debug",
        api_base="/api/v1/patient-agent-chat-debug",
        presets=_controller(request).get_presets(),
    )


@router.post("/api/v1/patient-agent-chat-debug/preload")
def preload_patient_agent_chat_debug(body: AgentDebugPreloadRequest, request: Request):
    try:
        snapshot = _controller(request).preload(preset_id=body.preset_id, payload=body.payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/patient-agent-chat-debug/message")
def message_patient_agent_chat_debug(body: AgentDebugMessageRequest, request: Request):
    try:
        snapshot = _controller(request).message(body.message)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 503 if "llm" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/patient-agent-chat-debug/snapshot")
def snapshot_patient_agent_chat_debug(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/patient-agent-chat-debug/reset")
def reset_patient_agent_chat_debug(request: Request):
    _controller(request).reset()
    return {"ok": True, "data": None}
