from dataclasses import dataclass, field

from app.agents.internal_medicine.workflow import ConsultationProgress
from app.schemas.common import InternalMedicineDialogueState


@dataclass
class InternalMedicineGraphState:
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
    complete: bool = False
    dialogue_state: InternalMedicineDialogueState = InternalMedicineDialogueState.IDLE


@dataclass
class WorkingMemory:
    short_term_turns: list[dict] = field(default_factory=list)
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
    consultation_progress: ConsultationProgress = field(default_factory=ConsultationProgress)
