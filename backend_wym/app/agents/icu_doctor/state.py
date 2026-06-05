from dataclasses import dataclass, field

from app.schemas.common import ICUDoctorDialogueState


@dataclass
class ICUTriageDecision:
    triage_level: int
    urgency: str
    treatment_plan: str
    note: str


@dataclass
class ICUDoctorGraphState:
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
    assistant_message: str = ""
    dialogue_state: ICUDoctorDialogueState = ICUDoctorDialogueState.IDLE


@dataclass
class WorkingMemory:
    short_term_turns: list[dict] = field(default_factory=list)
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
