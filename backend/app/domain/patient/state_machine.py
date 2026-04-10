from app.schemas.common import PatientLifecycleState


PATIENT_TRANSITIONS = {
    PatientLifecycleState.UNTRIAGED: {
        "begin_triage": PatientLifecycleState.TRIAGING,
        "start_internal_medicine": PatientLifecycleState.IN_CONSULTATION,
    },
    PatientLifecycleState.TRIAGING: {
        "begin_triage": PatientLifecycleState.TRIAGING,
        "followup_requested": PatientLifecycleState.WAITING_FOLLOWUP,
        "triage_completed": PatientLifecycleState.TRIAGED,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.WAITING_FOLLOWUP: {
        "begin_triage": PatientLifecycleState.TRIAGING,
        "resume_triage": PatientLifecycleState.TRIAGING,
        "triage_completed": PatientLifecycleState.TRIAGED,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.TRIAGED: {
        "begin_triage": PatientLifecycleState.TRIAGING,
        "queue_created": PatientLifecycleState.QUEUED,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.QUEUED: {
        "begin_triage": PatientLifecycleState.TRIAGING,
        "ticket_called": PatientLifecycleState.CALLED,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.CALLED: {
        "start_consultation": PatientLifecycleState.IN_CONSULTATION,
        "start_icu_consultation": PatientLifecycleState.IN_CONSULTATION,
        "start_internal_medicine": PatientLifecycleState.IN_CONSULTATION,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.IN_CONSULTATION: {
        "finish": PatientLifecycleState.COMPLETED,
        "icu_consultation_completed": PatientLifecycleState.COMPLETED,
        "internal_medicine_completed": PatientLifecycleState.COMPLETED,
        "icu_followup_requested": PatientLifecycleState.WAITING_FOLLOWUP,
        "internal_medicine_followup_requested": PatientLifecycleState.WAITING_FOLLOWUP,
        "mark_error": PatientLifecycleState.ERROR,
    },
    PatientLifecycleState.COMPLETED: {"begin_triage": PatientLifecycleState.TRIAGING},
    PatientLifecycleState.CANCELLED: {"begin_triage": PatientLifecycleState.TRIAGING},
    PatientLifecycleState.ERROR: {"begin_triage": PatientLifecycleState.TRIAGING},
}


DISPLAY_STATE_LABELS = {
    PatientLifecycleState.UNTRIAGED: "Untriaged",
    PatientLifecycleState.TRIAGING: "Triaging",
    PatientLifecycleState.WAITING_FOLLOWUP: "Waiting Follow-up",
    PatientLifecycleState.TRIAGED: "Triaged",
    PatientLifecycleState.QUEUED: "Queued",
    PatientLifecycleState.CALLED: "Called",
    PatientLifecycleState.IN_CONSULTATION: "In Consultation",
    PatientLifecycleState.COMPLETED: "Completed",
    PatientLifecycleState.CANCELLED: "Cancelled",
    PatientLifecycleState.ERROR: "Error",
}


class PatientStateMachine:
    def transition(self, current: PatientLifecycleState, event: str) -> PatientLifecycleState:
        next_state = PATIENT_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid patient transition: {current} -> {event}")
        return next_state

    def label_for(self, state: PatientLifecycleState) -> str:
        return DISPLAY_STATE_LABELS[state]
