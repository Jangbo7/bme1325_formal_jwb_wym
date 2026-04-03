from pydantic import BaseModel, Field

from app.schemas.patient import DialogueSummary, PatientView


class VitalsPayload(BaseModel):
    temp_c: float | None = None
    heart_rate: int | None = None
    systolic_bp: int | None = None
    diastolic_bp: int | None = None
    pain_score: int | None = None


class CreateTriageSessionRequest(BaseModel):
    patient_id: str = "P-self"
    session_id: str | None = None
    name: str = "You (Player)"
    age: int | None = None
    sex: str | None = None
    chief_complaint: str | None = None
    symptoms: str = ""
    onset_time: str | None = None
    vitals: VitalsPayload = Field(default_factory=VitalsPayload)
    allergies: list[str] = Field(default_factory=list)
    chronic_conditions: list[str] = Field(default_factory=list)
    location: str | None = None
    floor: int | None = None


class TriageMessageRequest(BaseModel):
    patient_id: str | None = None
    name: str | None = None
    message: str


class TriageSessionResponse(BaseModel):
    ok: bool = True
    session_id: str
    patient: PatientView
    dialogue: DialogueSummary
