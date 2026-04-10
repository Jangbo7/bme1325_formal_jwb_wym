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
        "register_completed": VisitLifecycleState.REGISTERED,
        "begin_triage": VisitLifecycleState.TRIAGING,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_CONSULTATION: {
        "start_consultation": VisitLifecycleState.IN_CONSULTATION,
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.IN_CONSULTATION: {
        "complete_visit": VisitLifecycleState.COMPLETED,
        "mark_error": VisitLifecycleState.ERROR,
    },
    VisitLifecycleState.WAITING_PAYMENT: {"mark_error": VisitLifecycleState.ERROR},
    VisitLifecycleState.WAITING_TEST: {"mark_error": VisitLifecycleState.ERROR},
    VisitLifecycleState.IN_TEST: {"mark_error": VisitLifecycleState.ERROR},
    VisitLifecycleState.WAITING_RETURN_CONSULTATION: {"mark_error": VisitLifecycleState.ERROR},
    VisitLifecycleState.WAITING_PHARMACY: {"mark_error": VisitLifecycleState.ERROR},
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
