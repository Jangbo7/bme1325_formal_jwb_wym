from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.npc_debug import CounterpartyType, NpcDebugCurrentDialogue


MultiPatientMode = Literal["legacy_template", "intelligent_agent"]


class MultiPatientDebugStartRequest(BaseModel):
    mode: MultiPatientMode = "intelligent_agent"
    spawn_interval_seconds: float = 5.0
    step_interval_seconds: float = 2.0
    max_active_patients: int = 10


class MultiPatientDebugPatientSnapshot(BaseModel):
    npc_id: str
    mode: MultiPatientMode
    profile_id: str | None = None
    patient_id: str
    encounter_id: str | None = None
    visit_state: str | None = None
    patient_lifecycle_state: str | None = None
    phase: str
    status: str
    current_counterparty: CounterpartyType
    current_dialogue: NpcDebugCurrentDialogue | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False
    case_summary: dict | None = None


class MultiPatientDebugSnapshot(BaseModel):
    running: bool
    mode: MultiPatientMode
    spawn_interval_seconds: float
    step_interval_seconds: float
    max_active_patients: int
    total_spawned: int
    active_count: int
    last_spawn_at: str | None = None
    last_tick_at: str | None = None
    last_error: str | None = None
    patients: list[MultiPatientDebugPatientSnapshot] = Field(default_factory=list)
