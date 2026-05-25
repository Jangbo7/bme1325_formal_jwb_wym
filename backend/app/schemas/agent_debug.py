from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentDebugType = Literal["triage", "internal_medicine", "patient_agent"]


class AgentDebugPresetSummary(BaseModel):
    preset_id: str
    label: str
    payload: dict[str, Any]


class AgentDebugPreloadRequest(BaseModel):
    preset_id: str | None = None
    payload: dict[str, Any] | None = None


class AgentDebugMessageRequest(BaseModel):
    message: str


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
    memory_delta: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentDebugSnapshot(BaseModel):
    debug_session_id: str
    agent_type: AgentDebugType
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
