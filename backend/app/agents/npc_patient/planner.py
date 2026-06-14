from __future__ import annotations

from dataclasses import dataclass, field

from app.services.disposition import OUTPATIENT_TERMINAL_VISIT_STATES


TRIGGER_EVENT_BY_VISIT_STATE = {
    "waiting_test": "request_test_payment",
    "waiting_test_payment": "pay_test",
    "test_payment_completed": "start_exam",
    "in_test": "finish_exam",
    "waiting_outpatient_procedure": "start_outpatient_procedure",
    "in_outpatient_procedure": "finish_outpatient_procedure",
    "waiting_return_consultation": "results_ready",
    "results_ready": "queue_second_consultation",
    "waiting_second_consultation": "start_second_consultation",
}


@dataclass(frozen=True)
class PlannedNpcAction:
    action: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NpcPlanningContext:
    encounter_id: str | None
    visit_state: str | None
    patient_state: str | None
    triage_session_state: str | None
    internal_medicine_round1_state: str | None
    internal_medicine_round2_state: str | None


def plan_next_action(context: NpcPlanningContext) -> PlannedNpcAction:
    visit_state = context.visit_state

    if visit_state in OUTPATIENT_TERMINAL_VISIT_STATES:
        return PlannedNpcAction("finished")

    if not context.encounter_id:
        return PlannedNpcAction("create_encounter")

    if visit_state in {None, "arrived", "triaging", "waiting_followup"}:
        if not context.triage_session_state:
            return PlannedNpcAction("create_triage_session")
        if context.triage_session_state != "triaged":
            return PlannedNpcAction("reply_triage")

    if context.triage_session_state and context.triage_session_state != "triaged":
        return PlannedNpcAction("reply_triage")

    if visit_state == "triaged":
        return PlannedNpcAction("register_visit")

    if visit_state == "registered":
        return PlannedNpcAction("progress_visit")

    if visit_state == "waiting_consultation" and context.patient_state == "called":
        return PlannedNpcAction("enter_consultation")

    if visit_state == "in_consultation":
        if not context.internal_medicine_round1_state:
            return PlannedNpcAction("create_internal_medicine_session", {"round": 1})
        if context.internal_medicine_round1_state != "completed":
            return PlannedNpcAction("reply_internal_medicine", {"round": 1})

    if visit_state in TRIGGER_EVENT_BY_VISIT_STATE:
        return PlannedNpcAction("trigger_encounter_event", {"event": TRIGGER_EVENT_BY_VISIT_STATE[visit_state]})

    if visit_state == "in_second_consultation":
        if not context.internal_medicine_round2_state:
            return PlannedNpcAction("create_internal_medicine_session", {"round": 2})
        if context.internal_medicine_round2_state != "completed":
            return PlannedNpcAction("reply_internal_medicine", {"round": 2})

    return PlannedNpcAction("idle")
