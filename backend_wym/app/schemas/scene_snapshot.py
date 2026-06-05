from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.patient import PatientView, QueueTicketRef
from app.schemas.queue import QueueView
from app.schemas.visit import VisitView


class SceneDialogueTurn(BaseModel):
    role: str
    content: str
    timestamp: str | None = None
    metadata: dict = Field(default_factory=dict)


class SceneDialogueSnapshot(BaseModel):
    agent_type: str
    session_id: str | None = None
    status: str
    assistant_message: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    question_focus: str | None = None
    message_type: str = "followup"
    turns: list[SceneDialogueTurn] = Field(default_factory=list)


class SceneMedicalRecordSummary(BaseModel):
    record_id: str
    patient_id: str
    visit_id: str
    entry_count: int
    latest_entry_type: str | None = None
    latest_phase: str | None = None
    updated_at: str


class SceneUiFlags(BaseModel):
    has_active_visit: bool = False
    can_submit_triage: bool = False
    can_continue_triage: bool = False
    can_register: bool = False
    can_progress_visit: bool = False
    ready_for_consultation: bool = False
    can_enter_consultation: bool = False
    consultation_agent_type: str | None = None
    can_start_consultation: bool = False
    can_continue_consultation: bool = False
    can_start_internal_medicine: bool = False
    can_continue_internal_medicine: bool = False
    can_view_test_report: bool = False
    can_ready_payment: bool = False


class SceneTimers(BaseModel):
    queue_wait_seconds_remaining: int = 0


class SceneOtherPatientSummary(BaseModel):
    patient_id: str
    name: str
    state: str
    lifecycle_state: str
    visit_state: str | None = None
    location: str
    priority: str
    active_agent_type: str | None = None
    updated_at: str


class SceneSnapshot(BaseModel):
    generated_at: str
    sync_token: str
    patient_id: str
    self_patient: PatientView | None = None
    active_visit: VisitView | None = None
    active_queue_ticket: QueueTicketRef | None = None
    active_dialogue: SceneDialogueSnapshot | None = None
    medical_record_summary: SceneMedicalRecordSummary | None = None
    latest_test_report: dict | None = None
    ui_flags: SceneUiFlags = Field(default_factory=SceneUiFlags)
    timers: SceneTimers = Field(default_factory=SceneTimers)
    other_patients: list[SceneOtherPatientSummary] = Field(default_factory=list)
    queues: list[QueueView] = Field(default_factory=list)
