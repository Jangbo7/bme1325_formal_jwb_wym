from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.routes._agent_debug_page import render_agent_debug_page
from app.schemas.agent_debug import AgentDebugMessageRequest, AgentDebugPreloadRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["ent_agent_debug_controller"]


@router.get("/ent-agent-debug", include_in_schema=False)
def ent_agent_debug_page(request: Request):
    return render_agent_debug_page(
        title="ENT Agent Debug",
        heading="ENT Agent Debug",
        description="Prototype ENT agent with dedicated RAG and single-turn debug chat.",
        page_slug="ent-agent-debug",
        api_base="/api/v1/ent-agent-debug",
        presets=_controller(request).get_presets(),
    )


@router.post("/api/v1/ent-agent-debug/preload")
def preload_ent_agent_debug(body: AgentDebugPreloadRequest, request: Request):
    try:
        snapshot = _controller(request).preload(preset_id=body.preset_id, payload=body.payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/ent-agent-debug/message")
def message_ent_agent_debug(body: AgentDebugMessageRequest, request: Request):
    try:
        snapshot = _controller(request).message(body.message)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/ent-agent-debug/snapshot")
def snapshot_ent_agent_debug(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/ent-agent-debug/reset")
def reset_ent_agent_debug(request: Request):
    _controller(request).reset()
    return {"ok": True, "data": None}
