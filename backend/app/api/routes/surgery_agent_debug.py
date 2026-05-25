from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.routes._agent_debug_page import render_agent_debug_page
from app.schemas.agent_debug import AgentDebugMessageRequest, AgentDebugPreloadRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["surgery_agent_debug_controller"]


@router.get("/surgery-agent-debug", include_in_schema=False)
def surgery_agent_debug_page(request: Request):
    return render_agent_debug_page(
        title="Surgery Agent Debug",
        heading="Surgery Agent Debug",
        description="Prototype specialty surgery agent with dedicated outpatient RAG and single-turn debug chat.",
        page_slug="surgery-agent-debug",
        api_base="/api/v1/surgery-agent-debug",
        presets=_controller(request).get_presets(),
    )


@router.post("/api/v1/surgery-agent-debug/preload")
def preload_surgery_agent_debug(body: AgentDebugPreloadRequest, request: Request):
    try:
        snapshot = _controller(request).preload(preset_id=body.preset_id, payload=body.payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/surgery-agent-debug/message")
def message_surgery_agent_debug(body: AgentDebugMessageRequest, request: Request):
    try:
        snapshot = _controller(request).message(body.message)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/surgery-agent-debug/snapshot")
def snapshot_surgery_agent_debug(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/surgery-agent-debug/reset")
def reset_surgery_agent_debug(request: Request):
    _controller(request).reset()
    return {"ok": True, "data": None}
