from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.contract import require_encounter_id


router = APIRouter()


@router.get("/api/v1/medical-records/visit/{visit_id}")
def get_medical_record_by_visit(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    medical_record_repo = request.app.state.container["medical_record_repo"]
    timeline = medical_record_repo.get_visit_timeline(visit_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="medical record not found")
    return {
        "ok": True,
        "data": timeline,
    }
