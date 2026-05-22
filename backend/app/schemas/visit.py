from pydantic import BaseModel, Field

from app.schemas.common import VisitLifecycleState


class CreateVisitRequest(BaseModel):
    patient_id: str
    name: str | None = None


class RegisterVisitRequest(BaseModel):
    name: str = "You (Player)"
    sex: str = "unknown"
    age: int = 30
    id_number: str = "TEMP-REG-0001"


class VisitView(BaseModel):
    id: str
    encounter_id: str | None = None
    patient_id: str
    state: VisitLifecycleState
    assigned_department_id: str | None = None
    assigned_department_name: str | None = None
    current_node: str | None = None
    current_department: str | None = None
    active_agent_type: str | None = None
    data: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class VisitResponse(BaseModel):
    ok: bool = True
    visit: VisitView
