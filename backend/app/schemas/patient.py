from pydantic import BaseModel, Field

from app.schemas.common import PatientLifecycleState, VisitLifecycleState


class TriageSummary(BaseModel):
    level: int | None = None
    note: str = ""


class DialogueSummary(BaseModel):
    status: str
    assistant_message: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    turns: list[dict] = Field(default_factory=list)
    question_focus: str | None = None
    message_type: str = "followup"
    recommendation_changed: bool = False
    asked_fields_history: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str | None = None
    title: str | None = None
    source: str | None = None


class QueueTicketRef(BaseModel):
    id: str
    department_id: str
    department_name: str
    number: int
    status: str


class PatientView(BaseModel):
    id: str
    name: str
    lifecycle_state: PatientLifecycleState
    state: str
    priority: str
    location: str
    updated_at: str
    session_id: str | None = None
    visit_id: str | None = None
    visit_state: VisitLifecycleState | None = None
    active_agent_type: str | None = None
    session_refs: dict = Field(default_factory=dict)
    dialogue_source_agent: str | None = None
    triage: TriageSummary = Field(default_factory=TriageSummary)
    dialogue: DialogueSummary | None = None
    triage_evidence: list[EvidenceItem] = Field(default_factory=list)
    queue_ticket: QueueTicketRef | None = None
