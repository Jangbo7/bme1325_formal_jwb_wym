from pydantic import BaseModel, Field

from app.schemas.common import VisitLifecycleState


class CreateVisitRequest(BaseModel):
    patient_id: str = "P-self"
    name: str | None = None


class VisitView(BaseModel):
    id: str
    patient_id: str
    state: VisitLifecycleState
    current_node: str | None = None
    current_department: str | None = None
    active_agent_type: str | None = None
    data: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class VisitResponse(BaseModel):
    ok: bool = True
    visit: VisitView
