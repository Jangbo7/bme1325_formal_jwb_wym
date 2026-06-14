from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.npc_debug import CounterpartyType, NpcDebugCurrentDialogue, NpcDebugTranscriptEntry


PatientAgentMode = Literal["intelligent_agent"]


class PatientAgentDebugSnapshot(BaseModel):
    npc_id: str
    mode: PatientAgentMode = "intelligent_agent"
    patient_id: str
    encounter_id: str | None = None
    active_session_id: str | None = None
    visit_state: str | None = None
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
    patient_lifecycle_state: str | None = None
    phase: str
    status: str
    case_summary: dict | None = None
    case_generation_status: str | None = None
    policy_state: dict | None = None
    current_counterparty: CounterpartyType
    current_dialogue: NpcDebugCurrentDialogue | None = None
    transcript: list[NpcDebugTranscriptEntry] = Field(default_factory=list)
    medical_record_summary: dict | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False


class PatientAgentDebugSpawnRequest(BaseModel):
    seed: str | None = None
