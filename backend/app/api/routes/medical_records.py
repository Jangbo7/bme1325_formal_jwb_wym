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


@router.get("/api/v1/medical-records/visit/{visit_id}/card")
def get_medical_record_card_by_visit(visit_id: str, request: Request):
    require_encounter_id(visit_id, field="visit_id")
    visit_repo = request.app.state.container["visit_repo"]
    medical_record_card_service = request.app.state.container["medical_record_card_service"]
    visit_row = visit_repo.get(visit_id)
    if visit_row is None:
        raise HTTPException(status_code=404, detail="visit not found")
    card = medical_record_card_service.get_card_for_visit(visit_id)
    return {
        "ok": True,
        "data": card,
    }
