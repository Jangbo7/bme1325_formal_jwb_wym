from app.schemas.common import VisitLifecycleState


VISIT_TRANSITIONS = {
    VisitLifecycleState.ARRIVED: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.REGISTRATION_PENDING: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.REGISTERED: {
        "queue_wait_elapsed": VisitLifecycleState.WAITING_CONSULTATION,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.TRIAGING: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "resume_triage": VisitLifecycleState.TRIAGING,
        "followup_requested": VisitLifecycleState.WAITING_FOLLOWUP,
        "triage_completed": VisitLifecycleState.TRIAGED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_FOLLOWUP: {
        "resume_triage": VisitLifecycleState.TRIAGING,
        "begin_triage": VisitLifecycleState.TRIAGING,
        "followup_requested": VisitLifecycleState.WAITING_FOLLOWUP,
        "triage_completed": VisitLifecycleState.TRIAGED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.TRIAGED: {
        "triage_completed": VisitLifecycleState.TRIAGED,
        "route_to_emergency": VisitLifecycleState.IN_EMERGENCY,
        "route_to_icu_rescue": VisitLifecycleState.IN_ICU_RESCUE,
        "register_completed": VisitLifecycleState.REGISTERED,
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_EMERGENCY: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_ICU_RESCUE: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_CONSULTATION: {
        "start_consultation": VisitLifecycleState.IN_CONSULTATION,
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_CONSULTATION: {
        "consultation_completed": VisitLifecycleState.WAITING_TEST,
        "order_outpatient_procedure": VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE,
        "finalize_without_tests": VisitLifecycleState.DIAGNOSIS_FINALIZED,
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_PAYMENT: {
        "pay_medical": VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_TEST: {
        "begin_triage": VisitLifecycleState.TRIAGING,
        "request_test_payment": VisitLifecycleState.WAITING_TEST_PAYMENT,
        "results_ready": VisitLifecycleState.RESULTS_READY,
        "order_outpatient_procedure": VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE: {
        "start_outpatient_procedure": VisitLifecycleState.IN_OUTPATIENT_PROCEDURE,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_TEST_PAYMENT: {
        "pay_test": VisitLifecycleState.TEST_PAYMENT_COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.TEST_PAYMENT_COMPLETED: {
        "start_exam": VisitLifecycleState.IN_TEST,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_TEST: {
        "finish_exam": VisitLifecycleState.WAITING_RETURN_CONSULTATION,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_OUTPATIENT_PROCEDURE: {
        "finish_outpatient_procedure": VisitLifecycleState.RESULTS_READY,
        "order_tests": VisitLifecycleState.WAITING_TEST,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_RETURN_CONSULTATION: {
        "results_ready": VisitLifecycleState.RESULTS_READY,
        "order_outpatient_procedure": VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.RESULTS_READY: {
        "queue_second_consultation": VisitLifecycleState.WAITING_SECOND_CONSULTATION,
        "start_second_consultation": VisitLifecycleState.IN_SECOND_CONSULTATION,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_SECOND_CONSULTATION: {
        "start_second_consultation": VisitLifecycleState.IN_SECOND_CONSULTATION,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_SECOND_CONSULTATION: {
        "finalize_diagnosis": VisitLifecycleState.DIAGNOSIS_FINALIZED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.DIAGNOSIS_FINALIZED: {
        "request_medical_payment": VisitLifecycleState.WAITING_PAYMENT,
        "plan_disposition": VisitLifecycleState.DISPOSITION_PENDING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED: {
        "plan_disposition": VisitLifecycleState.DISPOSITION_PENDING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.DISPOSITION_PENDING: {
        "choose_pharmacy": VisitLifecycleState.WAITING_PHARMACY,
        "choose_outpatient_treatment": VisitLifecycleState.DISPOSITION_OUTPATIENT_TREATMENT,
        "choose_followup_booking": VisitLifecycleState.DISPOSITION_FOLLOWUP_BOOKING,
        "choose_referral": VisitLifecycleState.DISPOSITION_REFERRAL,
        "admit_patient": VisitLifecycleState.ADMITTED,
        "route_to_emergency": VisitLifecycleState.IN_EMERGENCY,
        "route_to_icu_rescue": VisitLifecycleState.IN_ICU_RESCUE,
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.DISPOSITION_OUTPATIENT_TREATMENT: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.DISPOSITION_FOLLOWUP_BOOKING: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.DISPOSITION_REFERRAL: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.ADMITTED: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_PHARMACY: {
        "dispense_medication": VisitLifecycleState.COMPLETED,
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.TRANSFERRING: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.COMPLETED: {},
    VisitLifecycleState.ERROR: {
        "begin_triage": VisitLifecycleState.TRIAGING,
    },
}


class VisitStateMachine:
    def transition(self, current: VisitLifecycleState, event: str) -> VisitLifecycleState:
        next_state = VISIT_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid visit transition: {current} -> {event}")
        return next_state
