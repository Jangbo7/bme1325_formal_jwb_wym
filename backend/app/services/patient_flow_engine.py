from __future__ import annotations

from dataclasses import dataclass

from app.agents.npc_patient.planner import PlannedNpcAction, plan_next_action
from app.schemas.common import QueueTicketKind, QueueTicketStatus, VisitLifecycleState
from app.schemas.patient_flow import FlowDecision, FlowExecutionResult


@dataclass
class FlowEngineContext:
    assigned_department_id: str | None
    visit_state: str | None
    patient_state: str | None
    planned_action: PlannedNpcAction


def _target_node_for_state(visit_state: str | None, assigned_department_id: str | None) -> str | None:
    department_id = assigned_department_id or "triage"
    if visit_state in {
        VisitLifecycleState.ARRIVED.value,
        VisitLifecycleState.TRIAGING.value,
        VisitLifecycleState.WAITING_FOLLOWUP.value,
        VisitLifecycleState.IN_TRIAGE.value,
    }:
        return "triage"
    if visit_state in {
        VisitLifecycleState.TRIAGED.value,
        VisitLifecycleState.REGISTERED.value,
        VisitLifecycleState.WAITING_CONSULTATION.value,
        VisitLifecycleState.IN_CONSULTATION.value,
        VisitLifecycleState.WAITING_SECOND_CONSULTATION.value,
        VisitLifecycleState.IN_SECOND_CONSULTATION.value,
    }:
        return department_id
    if visit_state in {
        VisitLifecycleState.WAITING_TEST.value,
        VisitLifecycleState.WAITING_TEST_PAYMENT.value,
        VisitLifecycleState.TEST_PAYMENT_COMPLETED.value,
        VisitLifecycleState.IN_TEST.value,
        VisitLifecycleState.WAITING_RETURN_CONSULTATION.value,
        VisitLifecycleState.RESULTS_READY.value,
    }:
        return "testing"
    if visit_state in {
        VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
        VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
    }:
        return "outpatient_procedure"
    if visit_state in {
        VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
        VisitLifecycleState.WAITING_PAYMENT.value,
        VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
        VisitLifecycleState.DISPOSITION_PENDING.value,
    }:
        return "payment"
    if visit_state == VisitLifecycleState.WAITING_PHARMACY.value:
        return "pharmacy"
    return department_id


class FlowDecisionEngine:
    """Single source of truth for next-step decision in auto multi-patient mode."""

    def decide(self, *, assigned_department_id: str | None, runner_context) -> FlowDecision:
        planned = plan_next_action(runner_context)
        context = FlowEngineContext(
            assigned_department_id=assigned_department_id,
            visit_state=runner_context.visit_state,
            patient_state=runner_context.patient_state,
            planned_action=planned,
        )
        return self._to_decision(context)

    def decide_with_plan(self, *, assigned_department_id: str | None, runner_context) -> tuple[PlannedNpcAction, FlowDecision]:
        planned = plan_next_action(runner_context)
        context = FlowEngineContext(
            assigned_department_id=assigned_department_id,
            visit_state=runner_context.visit_state,
            patient_state=runner_context.patient_state,
            planned_action=planned,
        )
        return planned, self._to_decision(context)

    def _to_decision(self, context: FlowEngineContext) -> FlowDecision:
        planned = context.planned_action
        visit_state = context.visit_state
        target_node = _target_node_for_state(visit_state, context.assigned_department_id)
        if planned.action == "finished":

            return FlowDecision(next_action="complete_visit", target_node=target_node, reason="outpatient flow finished")
        if planned.action == "halted":
            return FlowDecision(next_action="idle", target_node=target_node, reason="automation stopped")

        if planned.action == "idle":
            return FlowDecision(next_action="idle", target_node=target_node, reason="no legal step")
        if planned.action == "register_visit":
            return FlowDecision(next_action="register", target_node=context.assigned_department_id, reason="triage completed")
        if planned.action == "progress_visit":
            return FlowDecision(next_action="call_round1", target_node=context.assigned_department_id, reason="registration ready")
        if planned.action == "enter_consultation":
            return FlowDecision(next_action="enter_round1_consult", target_node=context.assigned_department_id, reason="ticket called")
        if planned.action == "create_internal_medicine_session":
            round_number = int((planned.payload or {}).get("round") or 1)
            next_action = "enter_round2_consult" if round_number == 2 else "enter_round1_consult"
            return FlowDecision(next_action=next_action, target_node=context.assigned_department_id, reason="consultation session creation", payload=planned.payload)
        if planned.action == "reply_internal_medicine":
            round_number = int((planned.payload or {}).get("round") or 1)
            next_action = "enter_round2_consult" if round_number == 2 else "enter_round1_consult"
            return FlowDecision(next_action=next_action, target_node=context.assigned_department_id, reason="consultation dialogue turn", payload=planned.payload)
        if planned.action == "create_triage_session":
            return FlowDecision(next_action="enqueue_round1", target_node=target_node, reason="create triage session")
        if planned.action == "reply_triage":
            return FlowDecision(next_action="enqueue_round1", target_node=target_node, reason="triage follow-up turn")
        if planned.action == "create_encounter":
            return FlowDecision(next_action="register", target_node=target_node, reason="encounter bootstrap")
        if planned.action == "trigger_encounter_event":
            event = (planned.payload or {}).get("event")
            if event == "queue_second_consultation":
                return FlowDecision(next_action="enqueue_round2", target_node="testing", reason=event, payload=planned.payload)
            if event == "start_second_consultation":
                return FlowDecision(next_action="enter_round2_consult", target_node=context.assigned_department_id, reason=event, payload=planned.payload)
            if event in {"request_test_payment", "pay_test", "start_exam", "finish_exam", "results_ready"}:
                return FlowDecision(next_action="send_to_test", target_node="testing", reason=event, payload=planned.payload)
            if event in {"start_outpatient_procedure", "finish_outpatient_procedure"}:
                return FlowDecision(next_action="send_to_test", target_node="outpatient_procedure", reason=event, payload=planned.payload)

            if event in {"pay_medical", "plan_disposition"}:
                return FlowDecision(next_action="send_to_payment", target_node="payment", reason=event, payload=planned.payload)
            if event in {"choose_pharmacy", "dispense_medication"}:
                return FlowDecision(next_action="send_to_pharmacy", target_node="pharmacy", reason=event, payload=planned.payload)
            if event == "complete_visit":
                return FlowDecision(next_action="complete_visit", target_node=target_node, reason=event, payload=planned.payload)
            if event in {
                "choose_outpatient_treatment",
                "choose_followup_booking",
                "choose_referral",
                "admit_patient",
                "route_to_emergency",
                "route_to_icu_rescue",
            }:
                return FlowDecision(next_action="transition_visit", target_node=target_node, reason=event, payload=planned.payload)

            return FlowDecision(next_action="idle", target_node=target_node, reason=f"unsupported event {event}", guard_result="blocked", payload=planned.payload)
        return FlowDecision(next_action="error", target_node=target_node, reason=f"unsupported planned action {planned.action}", guard_result="blocked")


class FlowExecutor:
    """Execute already-decided action by delegating to existing runner primitives."""

    def execute_legacy(self, *, runner, state, profile, planned: PlannedNpcAction, decision: FlowDecision, force_offline_llm: bool = False) -> FlowExecutionResult:
        if not self._guard_passed(decision, state, planned, runner, profile=profile):
            return FlowExecutionResult(ok=False, action=decision.next_action, target_node=decision.target_node, error=decision.reason)
        runner.execute_planned_action(state, profile, planned, force_offline_llm=force_offline_llm)
        return FlowExecutionResult(ok=True, action=decision.next_action, target_node=decision.target_node)

    def execute_intelligent(self, *, runner, state, planned: PlannedNpcAction, decision: FlowDecision) -> FlowExecutionResult:
        if not self._guard_passed(decision, state, planned, runner):
            return FlowExecutionResult(ok=False, action=decision.next_action, target_node=decision.target_node, error=decision.reason)
        runner.execute_planned_action(state, planned)
        return FlowExecutionResult(ok=True, action=decision.next_action, target_node=decision.target_node)

    def _guard_passed(self, decision: FlowDecision, state, planned: PlannedNpcAction, runner, profile=None) -> bool:
        if decision.guard_result != "ok":
            return False
        if planned.action == "enter_consultation":
            visit_row = runner._require_visit_row(state)  # noqa: SLF001
            ticket = runner.queue_repo.get_active_ticket_for_patient(state.patient_id, visit_id=visit_row["id"])
            if not ticket or ticket.get("status") != QueueTicketStatus.CALLED.value:
                return False
        if planned.action == "trigger_encounter_event":
            event = (planned.payload or {}).get("event")
            if event == "start_second_consultation":
                visit_row = runner._require_visit_row(state)  # noqa: SLF001
                ticket = runner.queue_repo.get_active_ticket_for_patient(
                    state.patient_id,
                    visit_id=visit_row["id"],
                    queue_kind=QueueTicketKind.RETURN_CONSULTATION.value,
                )
                if not ticket:
                    return False
        return True
