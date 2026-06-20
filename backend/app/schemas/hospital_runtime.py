from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.department_runtime import (
    DepartmentRuntimeDepartmentView,
    DepartmentRuntimePatientView,
)


class HospitalNode(BaseModel):
    node_id: str
    node_type: str
    name: str
    department_id: str | None = None
    room_type: str | None = None
    capacity: int | None = None
    supports_queue: bool
    supports_consultation: bool
    supported_actions: list[str] = Field(default_factory=list)
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)


class HospitalNodeSummary(BaseModel):
    node_id: str
    node_name: str
    node_type: str
    active_count: int
    waiting_count: int
    called_count: int
    in_consultation_count: int
    in_test_count: int
    finished_count: int
    updated_at: str


class HospitalNodeRuntimeView(BaseModel):
    node: HospitalNode
    summary: HospitalNodeSummary
    patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)


class HospitalRuntimeSnapshot(BaseModel):
    running: bool
    mode: str
    spawn_interval_seconds: float
    step_interval_seconds: float
    max_active_patients: int
    llm_probability: float | None = None
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
    blocked_attempt_count: int = 0
    currently_blocked_patients: int = 0
    department_coverage: dict[str, int] = Field(default_factory=dict)
    active_by_department: dict[str, int] = Field(default_factory=dict)
    nodes: list[HospitalNodeRuntimeView] = Field(default_factory=list)
    departments: list[DepartmentRuntimeDepartmentView] = Field(default_factory=list)
    unassigned_patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)
