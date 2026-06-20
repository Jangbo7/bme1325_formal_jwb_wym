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
    response_mode: str | None = None
    judgment_changed: bool = False
    judgment_action: str | None = None
    answer_source: str | None = None
    llm_response_kind: str | None = None
    recommendation_changed: bool = False
    asked_fields_history: list[str] = Field(default_factory=list)
    final_result: dict = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    id: str | None = None
    title: str | None = None
    source: str | None = None


class QueueTicketRef(BaseModel):
    id: str
    department_id: str
    department_name: str
    queue_kind: str
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
    encounter_id: str | None = None
    visit_state: VisitLifecycleState | None = None
    primary_disposition: str | None = None
    disposition: dict = Field(default_factory=dict)
    outpatient_flow_finished: bool = False
    outpatient_finished_at: str | None = None
    rare_event_profile: dict = Field(default_factory=dict)
    rare_event_triggered_by: str | None = None
    rare_event_type: str | None = None
    rare_event_seed: str | None = None
    report_acuity_level: str | None = None
    report_cross_specialty_clues: list[dict] = Field(default_factory=list)
    recommended_department: str | None = None
    recommended_department_reason: str | None = None
    requires_new_registration: bool = False
    carry_forward_summary: dict = Field(default_factory=dict)
    active_agent_type: str | None = None
    session_refs: dict = Field(default_factory=dict)
    dialogue_source_agent: str | None = None
    triage: TriageSummary = Field(default_factory=TriageSummary)
    dialogue: DialogueSummary | None = None
    triage_evidence: list[EvidenceItem] = Field(default_factory=list)
    queue_ticket: QueueTicketRef | None = None
