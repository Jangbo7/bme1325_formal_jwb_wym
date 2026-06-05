from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CounterpartyType = Literal["triage_agent", "internal_medicine_agent", "surgery_agent", "system"]
DialogueDirection = Literal["inbound", "outbound"]


class NpcDebugCurrentDialogue(BaseModel):
    speaker: str
    message: str
    direction: DialogueDirection


class NpcDebugTranscriptEntry(BaseModel):
    turn_id: str
    phase: str
    speaker: str
    message: str
    timestamp: str
    counterparty: CounterpartyType


class NpcDebugSnapshot(BaseModel):
    npc_id: str
    profile_id: str
    patient_id: str
    encounter_id: str | None = None
    active_session_id: str | None = None
    visit_state: str | None = None
    patient_lifecycle_state: str | None = None
    phase: str
    status: str
    current_counterparty: CounterpartyType
    current_dialogue: NpcDebugCurrentDialogue | None = None
    transcript: list[NpcDebugTranscriptEntry] = Field(default_factory=list)
    medical_record_summary: dict | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False


class NpcDebugSpawnRequest(BaseModel):
    profile_id: str
