from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


_FORMAL_COUNTERPARTY_PATTERN = re.compile(r"^(?:[a-z0-9_]+_agent|system)$")
_SCRIPTED_COUNTERPARTY_PATTERN = re.compile(r"^scripted_[a-z0-9_]+_consultation$")


def _validate_counterparty(value: str) -> str:
    counterparty = str(value).strip()
    if _FORMAL_COUNTERPARTY_PATTERN.fullmatch(counterparty):
        return counterparty
    if _SCRIPTED_COUNTERPARTY_PATTERN.fullmatch(counterparty):
        return counterparty
    raise ValueError("counterparty must be 'system', a '*_agent', or 'scripted_{department}_consultation'")


CounterpartyType = Annotated[str, AfterValidator(_validate_counterparty)]
DialogueDirection = Literal["inbound", "outbound"]


class NpcDebugCurrentDialogue(BaseModel):
    speaker: str
    message: str
    direction: DialogueDirection


class NpcDebugTranscriptEntry(BaseModel):
    turn_id: str
    phase: str
    speaker: str
    message: str
    timestamp: str
    counterparty: CounterpartyType


class NpcDebugSnapshot(BaseModel):
    npc_id: str
    profile_id: str
    patient_id: str
    encounter_id: str | None = None
    active_session_id: str | None = None
    visit_state: str | None = None
    primary_disposition: str | None = None
    disposition: dict = Field(default_factory=dict)
    outpatient_flow_finished: bool = False
    outpatient_finished_at: str | None = None
    patient_lifecycle_state: str | None = None
    phase: str
    status: str
    current_counterparty: CounterpartyType
    current_dialogue: NpcDebugCurrentDialogue | None = None
    transcript: list[NpcDebugTranscriptEntry] = Field(default_factory=list)
    medical_record_summary: dict | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False


class NpcDebugSpawnRequest(BaseModel):
    profile_id: str
