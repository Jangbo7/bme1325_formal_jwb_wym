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
