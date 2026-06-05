from __future__ import annotations

from pydantic import BaseModel, Field


class FlowDecision(BaseModel):
    next_action: str
    target_node: str | None = None
    reason: str = ""
    guard_result: str = "ok"
    payload: dict = Field(default_factory=dict)


class FlowExecutionResult(BaseModel):
    ok: bool
    action: str
    target_node: str | None = None
    error: str | None = None


class PatientFlowSnapshot(BaseModel):
    patient_id: str
    visit_id: str | None = None
    visit_state: str | None = None
    patient_lifecycle_state: str | None = None
    current_node_id: str | None = None
    target_node_id: str | None = None
    last_transition_action: str | None = None
