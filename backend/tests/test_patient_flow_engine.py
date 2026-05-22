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
