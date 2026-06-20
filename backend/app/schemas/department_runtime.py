from __future__ import annotations

from pydantic import BaseModel, Field


class RuntimeBlockingView(BaseModel):
    kind: str
    resource_kind: str | None = None
    resource_id: str | None = None
    resource_name: str | None = None
    message: str | None = None


class RuntimeResourceAssignmentView(BaseModel):
    department_id: str | None = None
    department_name: str | None = None
    department_gate_id: str | None = None
    department_gate_name: str | None = None
    doctor_slot_id: str | None = None
    doctor_slot_name: str | None = None
    consultation_room_id: str | None = None
    consultation_room_name: str | None = None
    consultation_room_type: str | None = None
    current_node_id: str | None = None
    target_node_id: str | None = None
    target_resource_kind: str | None = None


class DepartmentPatientState(BaseModel):
    patient_id: str
    visit_id: str
    assigned_department_id: str
    assigned_department_name: str
    execution_runner_kind: str | None = None
    patient_source: str | None = None
    generation_hint_department_id: str | None = None
    generation_hint_department_name: str | None = None
    phase: str | None = None
    status: str | None = None
    step_count: int = 0
    department_agent_enabled: bool = False
    department_capability_class: str | None = None
    assigned_doctor_slot_id: str | None = None
    assigned_doctor_slot_name: str | None = None
    queue_kind: str | None = None
    department_status: str
    department_round: str = "none"
    # Backward-compatible alias field used by existing debug views
    department_flow_status: str | None = None
    queue_ticket_id: str | None = None
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
    active_agent_type: str | None = None
    current_node: str | None = None
    current_node_id: str | None = None
    current_room_node_id: str | None = None
    current_room_name: str | None = None
    room_type: str | None = None
    target_node_id: str | None = None
    display_stage: str | None = None
    dispatch_state: str | None = None
    consultation_round: int | None = None
    blocking: RuntimeBlockingView | None = None
    resource_assignment: RuntimeResourceAssignmentView | None = None
    latest_consultation_response_source: str | None = None
    latest_consultation_llm_error: str | None = None
    last_transition_action: str | None = None
    transition_version: str | None = None
    current_counterparty: str | None = None
    current_dialogue: dict | None = None
    current_dialogue_preview: str | None = None
    last_error: str | None = None
    entered_department_at: str | None = None
    updated_at: str
    source_of_truth_version: str | None = None
    finished_at: str | None = None
    npc_id: str | None = None
    last_action: str | None = None
    finished: bool = False


class DepartmentRuntimeState(BaseModel):
    department_id: str
    department_name: str
    active_count: int
    pending_registration_count: int
    waiting_round1_count: int
    waiting_round2_count: int
    called_round1_count: int
    called_round2_count: int
    in_consultation_round1_count: int
    in_consultation_round2_count: int
    # Backward-compatible aggregate counters
    waiting_count: int
    called_count: int
    in_consultation_count: int
    in_test_count: int
    finished_count: int
    updated_at: str


class DepartmentRuntimePatientView(DepartmentPatientState):
    pass


class DepartmentRuntimeSummaryView(DepartmentRuntimeState):
    pass


class DepartmentDoctorSlotRuntimeView(BaseModel):
    slot_id: str
    label: str
    capacity: int
    active_count: int
    patient_ids: list[str] = Field(default_factory=list)


class DepartmentRoomRuntimeView(BaseModel):
    node_id: str
    name: str
    room_type: str
    capacity: int
    active_count: int
    patient_ids: list[str] = Field(default_factory=list)


class DepartmentRuntimeDepartmentView(BaseModel):
    department_id: str
    department_name: str
    department_agent_enabled: bool = False
    department_capability_class: str = "script_only"
    department_gate_capacity: int | None = None
    summary: DepartmentRuntimeSummaryView
    doctor_slots: list[DepartmentDoctorSlotRuntimeView] = Field(default_factory=list)
    rooms: list[DepartmentRoomRuntimeView] = Field(default_factory=list)
    patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)


class DepartmentRuntimeSnapshot(BaseModel):
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
    currently_blocked_patients: int = 0
    formal_departments: list[dict] = Field(default_factory=list)
    departments: list[DepartmentRuntimeDepartmentView] = Field(default_factory=list)
    unassigned_patients: list[DepartmentRuntimePatientView] = Field(default_factory=list)
