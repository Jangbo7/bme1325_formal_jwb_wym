from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.domain.patient.state_machine import PatientStateMachine
from app.schemas.common import InternalMedicineDialogueState, PatientLifecycleState, TriageDialogueState, VisitLifecycleState


def test_patient_state_machine_happy_path():
    machine = PatientStateMachine()
    state = machine.transition(PatientLifecycleState.UNTRIAGED, "begin_triage")
    assert state == PatientLifecycleState.TRIAGING
    state = machine.transition(state, "followup_requested")
    assert state == PatientLifecycleState.WAITING_FOLLOWUP
    state = machine.transition(state, "resume_triage")
    assert state == PatientLifecycleState.TRIAGING


def test_patient_state_machine_allows_restart_from_in_test():
    machine = PatientStateMachine()
    state = machine.transition(PatientLifecycleState.IN_TEST, "begin_triage")
    assert state == PatientLifecycleState.TRIAGING


def test_patient_state_machine_allows_idempotent_triage_resume():
    machine = PatientStateMachine()
    state = machine.transition(PatientLifecycleState.TRIAGING, "resume_triage")
    assert state == PatientLifecycleState.TRIAGING


def test_triage_state_machine_happy_path():
    machine = TriageDialogueStateMachine()
    state = machine.transition(TriageDialogueState.IDLE, "start")
    assert state == TriageDialogueState.COLLECTING_INITIAL_INFO
    state = machine.transition(state, "evaluate")
    assert state == TriageDialogueState.EVALUATING
    state = machine.transition(state, "need_followup")
    assert state == TriageDialogueState.NEEDS_FOLLOWUP


def test_visit_state_machine_allows_restart_from_in_test():
    from app.domain.visit.state_machine import VisitStateMachine

    machine = VisitStateMachine()
    assert machine.transition(VisitLifecycleState.WAITING_TEST, "begin_triage") == VisitLifecycleState.TRIAGING
    state = machine.transition(VisitLifecycleState.IN_TEST, "finish_exam")
    assert state == VisitLifecycleState.WAITING_RETURN_CONSULTATION


def test_visit_state_machine_blocks_waiting_test_shortcut_to_payment():
    from app.domain.visit.state_machine import VisitStateMachine

    machine = VisitStateMachine()
    try:
        machine.transition(VisitLifecycleState.WAITING_TEST, "ready_payment")
        assert False, "ready_payment shortcut should be blocked in waiting_test"
    except ValueError:
        pass


def test_internal_medicine_state_machine_allows_reassessment_after_completion():
    from app.agents.internal_medicine.state_machine import InternalMedicineDialogueStateMachine

    machine = InternalMedicineDialogueStateMachine()
    state = machine.transition(InternalMedicineDialogueState.IDLE, "start")
    state = machine.transition(state, "evaluate")
    state = machine.transition(state, "complete")
    state = machine.transition(state, "plan_treatment")
    state = machine.transition(state, "approve")
    assert state == InternalMedicineDialogueState.COMPLETED
    state = machine.transition(state, "receive_reply")
    assert state == InternalMedicineDialogueState.RE_EVALUATING
