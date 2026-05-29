from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.npc_debug import CounterpartyType, NpcDebugCurrentDialogue


MultiPatientMode = Literal["legacy_template", "intelligent_agent", "department_mixed"]


class MultiPatientDebugStartRequest(BaseModel):
    mode: MultiPatientMode = "intelligent_agent"
    spawn_interval_seconds: float = 5.0
    step_interval_seconds: float = 2.0
    max_active_patients: int | None = 20


class MultiPatientDebugUpdateRequest(BaseModel):
    mode: MultiPatientMode | None = None
    spawn_interval_seconds: float | None = None
    step_interval_seconds: float | None = None
    max_active_patients: int | None = None


class MultiPatientDebugPatientSnapshot(BaseModel):
    npc_id: str
    mode: MultiPatientMode
    profile_id: str | None = None
    patient_id: str
    encounter_id: str | None = None
    visit_state: str | None = None
    patient_lifecycle_state: str | None = None
    assigned_department_id: str | None = None
    assigned_department_name: str | None = None
    phase: str
    status: str
    current_counterparty: CounterpartyType
    current_dialogue: NpcDebugCurrentDialogue | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False
    case_summary: dict | None = None
    current_node_id: str | None = None
    target_node_id: str | None = None
    next_step_at: str | None = None


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
    supervisor_mode: str = "engine_driven"
    fairness_policy: str = "oldest_due_first"
    node_capacities: dict[str, int] = Field(default_factory=dict)
    node_step_delays: dict[str, float] = Field(default_factory=dict)
    dispatch_count: int = 0
    blocked_count: int = 0
    department_coverage: dict[str, int] = Field(default_factory=dict)
    active_by_department: dict[str, int] = Field(default_factory=dict)
    patients: list[MultiPatientDebugPatientSnapshot] = Field(default_factory=list)
