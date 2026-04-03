from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/api/v1/patients")
def list_patients(request: Request):
    service = request.app.state.container["triage_service"]
    return {"patients": [patient.model_dump() for patient in service.list_patient_views() if patient]}


@router.get("/api/v1/patients/{patient_id}")
def get_patient(patient_id: str, request: Request):
    service = request.app.state.container["triage_service"]
    patient = service.get_patient_view(patient_id)
    return {"patient": patient.model_dump() if patient else None}
