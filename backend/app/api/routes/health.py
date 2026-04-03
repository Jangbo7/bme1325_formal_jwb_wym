from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/api/v1/health")
def health(request: Request):
    settings = request.app.state.container["settings"]
    return {
        "ok": True,
        "mode": "rag+llm" if settings["llm_api_key"] else "rag+rules",
        "key_source": settings["mock_key_source"],
        "llm_model": settings["llm_model"],
        "llm_enabled": bool(settings["llm_api_key"]),
        "graph_runtime": "langgraph" if request.app.state.container["langgraph_available"] else "graph-fallback",
    }
