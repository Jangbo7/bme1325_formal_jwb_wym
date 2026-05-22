from __future__ import annotations

from pydantic import BaseModel, Field


class DepartmentQueuePolicy(BaseModel):
    supports_initial_queue: bool = True
    supports_return_queue: bool = True
    queue_model: str = "dual_kind_shared_department"


class DepartmentCatalogEntry(BaseModel):
    department_id: str
    name: str
    queue_department_id: str
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)
    queue_policy: DepartmentQueuePolicy = Field(default_factory=DepartmentQueuePolicy)
    # Backward-compatible fields
    id: str
    label: str
    follow_up_priority: list[str] = Field(default_factory=list)
