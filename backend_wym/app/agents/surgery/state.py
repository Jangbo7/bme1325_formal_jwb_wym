from dataclasses import dataclass, field
from enum import Enum

from app.agents.surgery.workflow import ConsultationProgress


class SurgeryDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING_INFO = "collecting_info"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING_PATIENT_REPLY = "awaiting_patient_reply"
    RE_EVALUATING = "re_evaluating"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    TREATMENT_PLANNING = "treatment_planning"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SurgeryGraphState:
    payload: dict
    patient_row: dict | None = None
    session_row: dict | None = None
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)
    merged_payload: dict = field(default_factory=dict)
    final_result: dict | None = None
    evidence: list[dict] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    assistant_message: dict = field(default_factory=dict)
    complete: bool = False
    dialogue_state: SurgeryDialogueState = SurgeryDialogueState.IDLE


@dataclass
class WorkingMemory:
    short_term_turns: list[dict] = field(default_factory=list)
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
    consultation_progress: ConsultationProgress = field(default_factory=ConsultationProgress)
