from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.domain.patient.state_machine import PatientStateMachine
from app.domain.visit.state_machine import VisitStateMachine
from app.schemas.common import PatientLifecycleState, TriageDialogueState, VisitLifecycleState


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


def test_visit_state_machine_happy_path():
    machine = VisitStateMachine()
    state = machine.transition(VisitLifecycleState.ARRIVED, "begin_triage")
    assert state == VisitLifecycleState.TRIAGING
    state = machine.transition(state, "followup_requested")
    assert state == VisitLifecycleState.WAITING_FOLLOWUP
    state = machine.transition(state, "resume_triage")
    assert state == VisitLifecycleState.TRIAGING
    state = machine.transition(state, "triage_completed")
    assert state == VisitLifecycleState.TRIAGED
    state = machine.transition(state, "register_completed")
    assert state == VisitLifecycleState.REGISTERED
    state = machine.transition(state, "queue_wait_elapsed")
    assert state == VisitLifecycleState.WAITING_CONSULTATION
    state = machine.transition(state, "start_consultation")
    assert state == VisitLifecycleState.IN_CONSULTATION


def test_visit_state_machine_invalid_transition_raises():
    machine = VisitStateMachine()
    try:
        machine.transition(VisitLifecycleState.ARRIVED, "complete_visit")
    except ValueError as exc:
        assert "invalid visit transition" in str(exc)
    else:
        raise AssertionError("expected ValueError")
