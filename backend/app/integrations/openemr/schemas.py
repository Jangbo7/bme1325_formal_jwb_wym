from __future__ import annotations

from pydantic import BaseModel, Field


class OpenEMRSyncResult(BaseModel):
    ok: bool
    external_id: str | None = None
    resource_type: str
    operation: str
    raw_response: dict | None = None
    error: str | None = None
    skipped: bool = False


class OpenEMRPatientPayload(BaseModel):
    local_patient_id: str
    name: str
    sex: str | None = None
    age: int | None = None
    birth_date: str | None = None
    external_patient_id: str | None = None
    identifier_system: str = "urn:hos-sim:patient"


class OpenEMREncounterPayload(BaseModel):
    local_visit_id: str
    local_patient_id: str
    external_patient_id: str
    department: str | None = None
    status: str = "in-progress"
    class_code: str = "AMB"
    started_at: str | None = None
    external_encounter_id: str | None = None
    identifier_system: str = "urn:hos-sim:visit"


class OpenEMRNotePayload(BaseModel):
    local_visit_id: str
    local_patient_id: str
    external_patient_id: str
    external_encounter_id: str
    note_type: str
    title: str
    content: str
    created_at: str | None = None


class OpenEMRTestReportPayload(BaseModel):
    local_visit_id: str
    local_patient_id: str
    external_patient_id: str
    external_encounter_id: str
    category: str | None = None
    report_title: str
    report_content: str
    report_data: dict = Field(default_factory=dict)
    created_at: str | None = None
