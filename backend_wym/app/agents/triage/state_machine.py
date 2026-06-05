from app.schemas.common import TriageDialogueState


TRIAGE_TRANSITIONS = {
    TriageDialogueState.IDLE: {"start": TriageDialogueState.COLLECTING_INITIAL_INFO},
    TriageDialogueState.COLLECTING_INITIAL_INFO: {"evaluate": TriageDialogueState.EVALUATING},
    TriageDialogueState.EVALUATING: {
        "need_followup": TriageDialogueState.NEEDS_FOLLOWUP,
        "complete": TriageDialogueState.TRIAGED,
        "fail": TriageDialogueState.FAILED,
    },
    TriageDialogueState.NEEDS_FOLLOWUP: {"wait_for_reply": TriageDialogueState.AWAITING_PATIENT_REPLY},
    TriageDialogueState.AWAITING_PATIENT_REPLY: {
        "receive_reply": TriageDialogueState.RE_EVALUATING,
        "fail": TriageDialogueState.FAILED,
    },
    TriageDialogueState.RE_EVALUATING: {
        "need_followup": TriageDialogueState.NEEDS_FOLLOWUP,
        "complete": TriageDialogueState.TRIAGED,
        "fail": TriageDialogueState.FAILED,
    },
    TriageDialogueState.TRIAGED: {},
    TriageDialogueState.FAILED: {},
}


class TriageDialogueStateMachine:
    def transition(self, current: TriageDialogueState, event: str) -> TriageDialogueState:
        next_state = TRIAGE_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid triage transition: {current} -> {event}")
        return next_state
