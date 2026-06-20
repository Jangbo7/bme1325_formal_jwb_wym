from app.agents.npc_patient.planner import NpcPlanningContext
from app.services.patient_flow_engine import FlowDecisionEngine


def test_flow_engine_maps_register_from_triaged_context():
    engine = FlowDecisionEngine()
    context = NpcPlanningContext(
        encounter_id="E-1",
        visit_state="triaged",
        patient_state="triaged",
        triage_session_state="triaged",
        internal_medicine_round1_state=None,
        internal_medicine_round2_state=None,
    )
    planned, decision = engine.decide_with_plan(assigned_department_id="internal", runner_context=context)
    assert planned.action == "register_visit"
    assert decision.next_action == "register"
    assert decision.target_node == "internal"


def test_flow_engine_uses_triage_node_before_department_assignment():
    engine = FlowDecisionEngine()
    context = NpcPlanningContext(
        encounter_id="E-UNASSIGNED",
        visit_state="triaging",
        patient_state="triaging",
        triage_session_state="collecting_initial_info",
        internal_medicine_round1_state=None,
        internal_medicine_round2_state=None,
    )
    planned, decision = engine.decide_with_plan(assigned_department_id=None, runner_context=context)
    assert planned.action == "reply_triage"
    assert decision.target_node == "triage"


def test_flow_engine_maps_return_consultation_queue_action():
    engine = FlowDecisionEngine()
    context = NpcPlanningContext(
        encounter_id="E-2",
        visit_state="results_ready",
        patient_state="in_test",
        triage_session_state="triaged",
        internal_medicine_round1_state="completed",
        internal_medicine_round2_state=None,
    )
    planned, decision = engine.decide_with_plan(assigned_department_id="internal", runner_context=context)
    assert planned.action == "trigger_encounter_event"
    assert planned.payload["event"] == "queue_second_consultation"
    assert decision.next_action == "enqueue_round2"
    assert decision.target_node == "testing"


def test_flow_engine_keeps_results_ready_on_testing_node():
    engine = FlowDecisionEngine()
    context = NpcPlanningContext(
        encounter_id="E-2B",
        visit_state="results_ready",
        patient_state="in_test",
        triage_session_state="triaged",
        internal_medicine_round1_state="completed",
        internal_medicine_round2_state="awaiting_return",
    )
    decision = engine.decide(assigned_department_id="internal", runner_context=context)
    assert decision.target_node == "testing"


def test_flow_engine_maps_outpatient_procedure_states_to_procedure_node():
    engine = FlowDecisionEngine()
    context = NpcPlanningContext(
        encounter_id="E-3",
        visit_state="waiting_outpatient_procedure",
        patient_state="in_test",
        triage_session_state="triaged",
        internal_medicine_round1_state="completed",
        internal_medicine_round2_state=None,
    )
    planned, decision = engine.decide_with_plan(assigned_department_id="surgery", runner_context=context)
    assert planned.action == "trigger_encounter_event"
    assert planned.payload["event"] == "start_outpatient_procedure"
    assert decision.next_action == "send_to_test"
    assert decision.target_node == "outpatient_procedure"
