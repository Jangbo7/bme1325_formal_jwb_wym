from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


@router.get("/api/v1/scene-snapshot")
def get_scene_snapshot(request: Request, patient_id: str | None = None):
    service = request.app.state.container["scene_snapshot_service"]
    try:
        snapshot = service.get_snapshot(patient_id=patient_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="patient not found") from exc
    return {"ok": True, "data": snapshot.model_dump(mode="json")}
