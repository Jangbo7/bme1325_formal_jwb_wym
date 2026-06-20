from pydantic import ValidationError
import pytest

from app.schemas.multi_patient_debug import MultiPatientDebugPatientSnapshot
from app.schemas.npc_debug import NpcDebugSnapshot, NpcDebugTranscriptEntry
from app.schemas.patient_agent_debug import PatientAgentDebugSnapshot


def test_shared_debug_schemas_accept_scripted_consultation_counterparties():
    npc_entry = NpcDebugTranscriptEntry(
        turn_id="turn-0001",
        phase="consultation_round1",
        speaker="scripted_pain_consultation",
        message="Please describe your pain history.",
        timestamp="2026-06-15T00:00:00Z",
        counterparty="scripted_pain_consultation",
    )
    npc_snapshot = NpcDebugSnapshot(
        npc_id="NPC-DEBUG-001",
        profile_id="pain_chronic_back_pain",
        patient_id="P-001",
        phase="consultation_round1",
        status="awaiting_patient_reply",
        current_counterparty="scripted_pain_consultation",
        transcript=[npc_entry],
    )
    patient_snapshot = PatientAgentDebugSnapshot(
        npc_id="PATIENT-AGENT-DEBUG-001",
        patient_id="P-002",
        phase="consultation_round1",
        status="awaiting_patient_reply",
        current_counterparty="scripted_rehabilitation_consultation",
        transcript=[
            NpcDebugTranscriptEntry(
                turn_id="turn-0002",
                phase="consultation_round1",
                speaker="scripted_rehabilitation_consultation",
                message="Tell me how your recovery changed this week.",
                timestamp="2026-06-15T00:01:00Z",
                counterparty="scripted_rehabilitation_consultation",
            )
        ],
    )
    multi_patient_snapshot = MultiPatientDebugPatientSnapshot(
        npc_id="NPC-003",
        mode="department_mixed",
        execution_runner_kind="legacy",
        patient_id="P-003",
        phase="consultation_round1",
        status="awaiting_patient_reply",
        current_counterparty="scripted_dentistry_consultation",
    )

    assert npc_snapshot.current_counterparty == "scripted_pain_consultation"
    assert patient_snapshot.current_counterparty == "scripted_rehabilitation_consultation"
    assert multi_patient_snapshot.current_counterparty == "scripted_dentistry_consultation"


def test_shared_debug_schemas_reject_invalid_counterparty_values():
    with pytest.raises(ValidationError):
        NpcDebugTranscriptEntry(
            turn_id="turn-0001",
            phase="triage",
            speaker="unknown",
            message="invalid",
            timestamp="2026-06-15T00:00:00Z",
            counterparty="scripted_pain",
        )
