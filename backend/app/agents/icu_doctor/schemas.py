from pydantic import BaseModel, Field


class VitalsPayload(BaseModel):
    temp_c: float | None = None
    heart_rate: int | None = None
    systolic_bp: int | None = None
    diastolic_bp: int | None = None
    pain_score: int | None = None
    spo2: float | None = None
    respiratory_rate: int | None = None


class CreateICUSessionRequest(BaseModel):
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
    registration_info: dict = Field(default_factory=dict)
    location: str | None = None
    floor: int | None = None


class ICUMessageRequest(BaseModel):
    patient_id: str | None = None
    name: str | None = None
    message: str


class ICUSessionResponse(BaseModel):
    ok: bool = True
    session_id: str
    patient: dict
    dialogue: dict
