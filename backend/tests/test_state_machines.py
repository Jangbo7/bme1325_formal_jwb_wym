from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.domain.patient.state_machine import PatientStateMachine
from app.schemas.common import PatientLifecycleState, TriageDialogueState


def test_patient_state_machine_happy_path():
    machine = PatientStateMachine()
    state = machine.transition(PatientLifecycleState.UNTRIAGED, "begin_triage")
    assert state == PatientLifecycleState.TRIAGING
    state = machine.transition(state, "followup_requested")
    assert state == PatientLifecycleState.WAITING_FOLLOWUP
    state = machine.transition(state, "resume_triage")
    assert state == PatientLifecycleState.TRIAGING


def test_triage_state_machine_happy_path():
    machine = TriageDialogueStateMachine()
    state = machine.transition(TriageDialogueState.IDLE, "start")
    assert state == TriageDialogueState.COLLECTING_INITIAL_INFO
    state = machine.transition(state, "evaluate")
    assert state == TriageDialogueState.EVALUATING
    state = machine.transition(state, "need_followup")
    assert state == TriageDialogueState.NEEDS_FOLLOWUP
