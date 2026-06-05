from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.routes._agent_debug_page import render_agent_debug_page
from app.schemas.agent_debug import AgentDebugMessageRequest, AgentDebugPreloadRequest, AgentDebugResetRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["doctor_agent_debug_controller"]


def _resolve_agent_type(agent_type: str | None) -> str:
    if not agent_type:
        raise HTTPException(status_code=422, detail="agent_type is required")
    return agent_type


@router.get("/doctor-agent-debug", include_in_schema=False)
def doctor_agent_debug_page(request: Request):
    controller = _controller(request)
    agent_options = controller.list_available_agents()
    selected_agent_type = agent_options[0]["agent_type"] if agent_options else None
    presets_by_agent = {
        agent["agent_type"]: controller.get_presets(agent["agent_type"])
        for agent in agent_options
    }
    return render_agent_debug_page(
        title="Doctor Agent Debug",
        heading="Doctor Agent Debug",
        description="Unified doctor-facing debug page. Choose the doctor agent configuration, preload a preset, then run the real consultation service path.",
        page_slug="doctor-agent-debug",
        api_base="/api/v1/doctor-agent-debug",
        presets=presets_by_agent.get(selected_agent_type or "", []),
        agent_options=agent_options,
        selected_agent_type=selected_agent_type,
        presets_by_agent=presets_by_agent,
    )


@router.post("/api/v1/doctor-agent-debug/preload")
def preload_doctor_agent_debug(body: AgentDebugPreloadRequest, request: Request):
    try:
        snapshot = _controller(request).preload(
            _resolve_agent_type(body.agent_type),
            preset_id=body.preset_id,
            payload=body.payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/doctor-agent-debug/message")
def message_doctor_agent_debug(body: AgentDebugMessageRequest, request: Request):
    try:
        snapshot = _controller(request).message(_resolve_agent_type(body.agent_type), body.message)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/doctor-agent-debug/snapshot")
def snapshot_doctor_agent_debug(request: Request, agent_type: str = Query(...)):
    try:
        snapshot = _controller(request).get_snapshot(agent_type)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/doctor-agent-debug/reset")
def reset_doctor_agent_debug(body: AgentDebugResetRequest, request: Request):
    try:
        _controller(request).reset(_resolve_agent_type(body.agent_type))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "data": None}
