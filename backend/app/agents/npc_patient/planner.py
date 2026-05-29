from __future__ import annotations

from dataclasses import dataclass, field


TRIGGER_EVENT_BY_VISIT_STATE = {
    "waiting_test": "request_test_payment",
    "waiting_test_payment": "pay_test",
    "test_payment_completed": "start_exam",
    "in_test": "finish_exam",
    "waiting_return_consultation": "results_ready",
    "results_ready": "queue_second_consultation",
    "waiting_second_consultation": "start_second_consultation",
    "in_second_consultation": "finalize_diagnosis",
    "diagnosis_finalized": "request_medical_payment",
    "waiting_payment": "pay_medical",
    "medical_payment_completed": "plan_disposition",
    "disposition_pending": "choose_pharmacy",
    "waiting_pharmacy": "complete_visit",
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

    return PlannedNpcAction("idle")
