from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentDebugPresetSummary(BaseModel):
    preset_id: str
    agent_type: str | None = None
    department_id: str | None = None
    label: str
    payload: dict[str, Any]


class AgentDebugPreloadRequest(BaseModel):
    agent_type: str | None = None
    preset_id: str | None = None
    payload: dict[str, Any] | None = None


class AgentDebugMessageRequest(BaseModel):
    agent_type: str | None = None
    message: str


class AgentDebugResetRequest(BaseModel):
    agent_type: str | None = None


class AgentDebugTranscriptEntry(BaseModel):
    role: str
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDebugReply(BaseModel):
    role: str = "assistant"
    content: str
    timestamp: str | None = None


class AgentDebugTrace(BaseModel):
    merged_payload: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None
    user_prompt: str | None = None
    rag_query: dict[str, Any] | None = None
    rag_hits: list[dict[str, Any]] = Field(default_factory=list)
    parsed_result: dict[str, Any] = Field(default_factory=dict)
    fallback_reason: str | None = None
    llm_attempted: bool = False
    llm_succeeded: bool = False
    llm_error: str | None = None
    response_source: str | None = None
    patient_reply_source: str | None = None
    structured_result: dict[str, Any] = Field(default_factory=dict)
    patient_reply: str | None = None
    update_reason: str | None = None
    result_changed_fields: list[str] = Field(default_factory=list)
    reassessment_intent: str | None = None
    reply_rendering_mode: str | None = None
    memory_delta: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentDebugSnapshot(BaseModel):
    debug_session_id: str
    agent_type: str
    department_id: str | None = None
    agent_label: str | None = None
    patient_id: str
    visit_id: str
    session_id: str
    visit_state: str | None = None
    patient_lifecycle_state: str | None = None
    preload_summary: dict[str, Any] = Field(default_factory=dict)
    transcript: list[AgentDebugTranscriptEntry] = Field(default_factory=list)
    latest_reply: AgentDebugReply | None = None
    trace: AgentDebugTrace = Field(default_factory=AgentDebugTrace)
    medical_record_summary: dict[str, Any] | None = None
    last_error: str | None = None
