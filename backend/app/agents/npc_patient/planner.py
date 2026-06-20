from __future__ import annotations

from dataclasses import dataclass, field

from app.services.disposition import should_stop_outpatient_automation


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
    "waiting_payment": "pay_medical",
    "medical_payment_completed": "plan_disposition",
    "waiting_pharmacy": "dispense_medication",
    "disposition_outpatient_treatment": "complete_visit",
    "disposition_followup_booking": "complete_visit",
}


@dataclass(frozen=True)
class PlannedNpcAction:
    action: str
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NpcPlanningContext:
    encounter_id: str | None
    visit_state: str | None
    visit_data: dict = field(default_factory=dict)
    patient_state: str | None = None
    triage_session_state: str | None = None
    internal_medicine_round1_state: str | None = None
    internal_medicine_round2_state: str | None = None


def plan_next_action(context: NpcPlanningContext) -> PlannedNpcAction:
    visit_state = context.visit_state


    if should_stop_outpatient_automation(visit_state, context.visit_data):
        return PlannedNpcAction("finished")
    if visit_state in {"cancelled", "error"}:
        return PlannedNpcAction("halted")


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

    if visit_state == "disposition_pending":
        event = _disposition_event_for_context(context)
        if event:
            return PlannedNpcAction("trigger_encounter_event", {"event": event})

    if visit_state == "in_second_consultation":
        if not context.internal_medicine_round2_state:
            return PlannedNpcAction("create_internal_medicine_session", {"round": 2})
        if context.internal_medicine_round2_state != "completed":
            return PlannedNpcAction("reply_internal_medicine", {"round": 2})


    return PlannedNpcAction("idle")


def _disposition_event_for_context(context: NpcPlanningContext) -> str | None:
    disposition = dict(context.visit_data.get("disposition") or {})
    category = str(disposition.get("category") or "").strip()
    if not category:
        return None
    if context.visit_data.get("needs_pharmacy") is True:
        return "choose_pharmacy"
    if category == "followup_booking":
        return "choose_followup_booking"
    if category == "outpatient_treatment":
        return "choose_outpatient_treatment"
    if category == "specialty_referral":
        return "choose_referral"
    if category == "inpatient_admission":
        return "admit_patient"
    if category == "emergency_escalation":
        return "route_to_emergency"
    if category == "icu_rescue":
        return "route_to_icu_rescue"
    return None
