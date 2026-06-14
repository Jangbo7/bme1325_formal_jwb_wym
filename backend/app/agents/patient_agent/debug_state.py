from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.npc_debug import NpcDebugCurrentDialogue, NpcDebugTranscriptEntry
from app.schemas.patient_agent_debug import PatientAgentDebugSnapshot


@dataclass
class PatientAgentDebugState:
    npc_id: str
    patient_id: str
    encounter_id: str | None = None
    active_session_id: str | None = None
    visit_state: str | None = None
    primary_disposition: str | None = None
    disposition: dict = field(default_factory=dict)
    outpatient_flow_finished: bool = False
    outpatient_finished_at: str | None = None
    rare_event_profile: dict = field(default_factory=dict)
    rare_event_triggered_by: str | None = None
    rare_event_type: str | None = None
    rare_event_seed: str | None = None
    report_acuity_level: str | None = None
    report_cross_specialty_clues: list[dict] = field(default_factory=list)
    recommended_department: str | None = None
    recommended_department_reason: str | None = None
    requires_new_registration: bool = False
    carry_forward_summary: dict = field(default_factory=dict)
    patient_lifecycle_state: str | None = None
    phase: str = "spawned"
    status: str = "idle"
    mode: str = "intelligent_agent"
    case_summary: dict | None = None
    case_generation_status: str | None = None
    policy_state: dict | None = None
    current_counterparty: str = "system"
    current_dialogue: NpcDebugCurrentDialogue | None = None
    transcript: list[NpcDebugTranscriptEntry] = field(default_factory=list)
    medical_record_summary: dict | None = None
    last_action: str | None = None
    last_error: str | None = None
    step_count: int = 0
    finished: bool = False
    case_id: str | None = None
    session_turn_offsets: dict[str, int] = field(default_factory=dict)

    def clear_dialogue(self) -> None:
        self.current_counterparty = "system"
        self.current_dialogue = None

    def append_transcript(
        self,
        *,
        phase: str,
        speaker: str,
        message: str,
        timestamp: str,
        counterparty: str,
        direction: str,
    ) -> None:
        turn_id = f"turn-{len(self.transcript) + 1:04d}"
        entry = NpcDebugTranscriptEntry(
            turn_id=turn_id,
            phase=phase,
            speaker=speaker,
            message=message,
            timestamp=timestamp,
            counterparty=counterparty,
        )
        self.transcript.append(entry)
        self.current_counterparty = counterparty
        self.current_dialogue = NpcDebugCurrentDialogue(
            speaker=speaker,
            message=message,
            direction=direction,
        )

    def to_snapshot(self) -> PatientAgentDebugSnapshot:
        return PatientAgentDebugSnapshot(
            npc_id=self.npc_id,
            mode="intelligent_agent",
            patient_id=self.patient_id,
            encounter_id=self.encounter_id,
            active_session_id=self.active_session_id,
            visit_state=self.visit_state,
            primary_disposition=self.primary_disposition,
            disposition=dict(self.disposition),
            outpatient_flow_finished=self.outpatient_flow_finished,
            outpatient_finished_at=self.outpatient_finished_at,
            rare_event_profile=dict(self.rare_event_profile),
            rare_event_triggered_by=self.rare_event_triggered_by,
            rare_event_type=self.rare_event_type,
            rare_event_seed=self.rare_event_seed,
            report_acuity_level=self.report_acuity_level,
            report_cross_specialty_clues=list(self.report_cross_specialty_clues),
            recommended_department=self.recommended_department,
            recommended_department_reason=self.recommended_department_reason,
            requires_new_registration=self.requires_new_registration,
            carry_forward_summary=dict(self.carry_forward_summary),
            patient_lifecycle_state=self.patient_lifecycle_state,
            phase=self.phase,
            status=self.status,
            case_summary=self.case_summary,
            case_generation_status=self.case_generation_status,
            policy_state=self.policy_state,
            current_counterparty=self.current_counterparty,
            current_dialogue=self.current_dialogue,
            transcript=list(self.transcript),
            medical_record_summary=self.medical_record_summary,
            last_action=self.last_action,
            last_error=self.last_error,
            step_count=self.step_count,
            finished=self.finished,
        )
