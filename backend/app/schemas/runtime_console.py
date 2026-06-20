from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.department_runtime import (
    DepartmentDoctorSlotRuntimeView,
    DepartmentRoomRuntimeView,
    DepartmentRuntimePatientView,
    DepartmentRuntimeSummaryView,
)


RuntimeConsoleSessionStatus = Literal["idle", "running", "paused", "draining", "stopped"]
RuntimeConsoleCommand = Literal["stop", "pause_spawn", "pause_step", "resume", "drain", "reset", "refresh"]
RuntimeConsoleEventSeverity = Literal["info", "warning", "error"]
RuntimeConsoleEventCategory = Literal["lifecycle", "spawn", "scheduling", "capacity", "llm", "validation", "stuck", "department"]
RuntimeConsoleSubjectType = Literal["system", "patient", "department"]
RuntimeConsoleMixMode = Literal["strict_ratio"]
RuntimeConsoleRunnerKind = Literal["legacy", "intelligent"]


class RuntimeConsoleDepartmentConfig(BaseModel):
    department_id: str
    department_name: str
    enabled: bool = True
    spawn_weight: float = Field(default=1.0, ge=0.0)
    allow_agent_patients: bool = False
    allow_script_patients: bool = True
    updated_at: str | None = None


class RuntimeConsoleGlobalConfig(BaseModel):
    max_active_patients: int = Field(default=20, ge=1)
    active_mix_mode: RuntimeConsoleMixMode = "strict_ratio"
    active_agent_ratio: float = Field(default=0.5, ge=0.0, le=1.0)
    fullview_step_gate_enabled: bool = False
    agent_spawn_interval_seconds: float = Field(default=4.0, ge=0.0)
    agent_step_interval_seconds: float = Field(default=2.0, ge=0.1)
    script_spawn_interval_seconds: float = Field(default=4.0, ge=0.0)
    script_step_interval_seconds: float = Field(default=2.0, ge=0.1)


class RuntimeConsoleSession(BaseModel):
    session_id: str | None = None
    status: RuntimeConsoleSessionStatus = "idle"
    running: bool = False
    spawn_paused: bool = False
    step_paused: bool = False
    drain_mode: bool = False
    mode: str = "runtime_console"
    started_at: str | None = None
    ended_at: str | None = None
    updated_at: str | None = None


class RuntimeConsoleEvent(BaseModel):
    event_id: str
    session_id: str
    occurred_at: str
    severity: RuntimeConsoleEventSeverity
    category: RuntimeConsoleEventCategory
    event_type: str
    message: str
    subject_type: RuntimeConsoleSubjectType
    subject_id: str
    department_id: str | None = None
    patient_id: str | None = None
    npc_id: str | None = None
    payload: dict = Field(default_factory=dict)


class RuntimeIssueSummary(BaseModel):
    issue_key: str
    severity: RuntimeConsoleEventSeverity
    category: RuntimeConsoleEventCategory
    subject_type: RuntimeConsoleSubjectType
    subject_id: str
    department_id: str | None = None
    patient_id: str | None = None
    npc_id: str | None = None
    latest_message: str
    occurrence_count: int = 1
    last_occurred_at: str
    current: bool = True


class RuntimeConsoleDepartmentView(BaseModel):
    department_id: str
    department_name: str
    config: RuntimeConsoleDepartmentConfig
    department_agent_enabled: bool = False
    department_capability_class: str = "script_only"
    department_gate_capacity: int | None = None
    summary: DepartmentRuntimeSummaryView
    doctor_slots: list[DepartmentDoctorSlotRuntimeView] = Field(default_factory=list)
    rooms: list[DepartmentRoomRuntimeView] = Field(default_factory=list)
    patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)
    blocked_patients: int = 0
    recent_issue_count: int = 0


class RuntimeConsoleSnapshot(BaseModel):
    session: RuntimeConsoleSession
    global_config: RuntimeConsoleGlobalConfig
    department_configs: list[RuntimeConsoleDepartmentConfig] = Field(default_factory=list)
    active_agent_target: int = 0
    active_script_target: int = 0
    active_agent_count: int = 0
    active_script_count: int = 0
    total_spawned: int = 0
    active_count: int = 0
    last_spawn_at: str | None = None
    last_tick_at: str | None = None
    last_error: str | None = None
    nodes: list[dict] = Field(default_factory=list)
    departments: list[RuntimeConsoleDepartmentView] = Field(default_factory=list)
    patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)
    current_issues: list[RuntimeIssueSummary] = Field(default_factory=list)
    recent_issues: list[RuntimeIssueSummary] = Field(default_factory=list)
    recent_events: list[RuntimeConsoleEvent] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    category_counts: dict[str, int] = Field(default_factory=dict)


class RuntimeConsoleStartRequest(BaseModel):
    global_config: RuntimeConsoleGlobalConfig = Field(default_factory=RuntimeConsoleGlobalConfig)
    department_configs: list[RuntimeConsoleDepartmentConfig] | None = None


class RuntimeConsoleCommandRequest(BaseModel):
    command: RuntimeConsoleCommand


class RuntimeConsoleGlobalConfigUpdateRequest(BaseModel):
    global_config: RuntimeConsoleGlobalConfig


class RuntimeConsoleDepartmentConfigUpdateRequest(BaseModel):
    department_configs: list[RuntimeConsoleDepartmentConfig]
