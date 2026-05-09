from __future__ import annotations

from pydantic import BaseModel, Field


class CreateEncounterRequest(BaseModel):
    patient_id: str
    name: str | None = None


class TransferCommand(BaseModel):
    from_group: str
    to_group: str
    reason: str
    ctas_level: str | None = None
    summary: dict = Field(default_factory=dict)
    requested_resources: dict = Field(default_factory=dict)


class EncounterView(BaseModel):
    encounter_id: str
    patient_id: str
    state: str
    current_node: str | None = None
    current_department: str | None = None
    active_agent_type: str | None = None
    data: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
