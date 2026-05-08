from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter()


@router.get("/api/v1/openemr/health")
def openemr_health(request: Request):
    client = request.app.state.container["openemr_client"]
    return client.health_check()


@router.post("/api/v1/openemr/sync/patient/{patient_id}")
def sync_openemr_patient(patient_id: str, request: Request):
    patient_repo = request.app.state.container["patient_repo"]
    if not patient_repo.get(patient_id):
        raise HTTPException(status_code=404, detail="patient not found")
    result = request.app.state.container["emr_service"].ensure_patient_synced(patient_id)
    return result.model_dump()


@router.post("/api/v1/openemr/sync/visit/{visit_id}")
def sync_openemr_visit(visit_id: str, request: Request):
    visit_repo = request.app.state.container["visit_repo"]
    if not visit_repo.get(visit_id):
        raise HTTPException(status_code=404, detail="visit not found")
    result = request.app.state.container["emr_service"].ensure_visit_encounter_synced(visit_id)
    return result.model_dump()


@router.post("/api/v1/openemr/sync/visit/{visit_id}/notes")
def sync_openemr_visit_notes(
    visit_id: str,
    request: Request,
    force: bool = Query(default=False),
):
    container = request.app.state.container
    visit = container["visit_repo"].get(visit_id)
    if not visit:
        raise HTTPException(status_code=404, detail="visit not found")
    patient_id = visit["patient_id"]
    visit_data = container["visit_repo"].to_view(visit).data
    triage_session_id = visit_data.get("triage_session_id")
    internal_session_id = visit_data.get("internal_medicine_session_id")
    service = container["emr_service"]

    triage_result = service.sync_triage_summary(
        patient_id,
        visit_id,
        session_id=triage_session_id,
        force=force,
    )
    internal_result = service.sync_internal_medicine_summary(
        patient_id,
        visit_id,
        session_id=internal_session_id,
        force=force,
    )
    test_result = service.sync_test_report(
        patient_id,
        visit_id,
        force=force,
    )

    return {
        "ok": triage_result.ok and internal_result.ok and test_result.ok,
        "triage_note": triage_result.model_dump(),
        "internal_medicine_note": internal_result.model_dump(),
        "test_report": test_result.model_dump(),
    }
