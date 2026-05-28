from app.agents.surgery.state import SurgeryDialogueState


SURGERY_TRANSITIONS = {
    SurgeryDialogueState.IDLE: {"start": SurgeryDialogueState.COLLECTING_INFO},
    SurgeryDialogueState.COLLECTING_INFO: {
        "evaluate": SurgeryDialogueState.EVALUATING,
        "need_followup": SurgeryDialogueState.NEEDS_FOLLOWUP,
    },
    SurgeryDialogueState.EVALUATING: {
        "complete": SurgeryDialogueState.DIAGNOSIS_COMPLETE,
        "need_followup": SurgeryDialogueState.NEEDS_FOLLOWUP,
        "fail": SurgeryDialogueState.FAILED,
    },
    SurgeryDialogueState.NEEDS_FOLLOWUP: {"wait_for_reply": SurgeryDialogueState.AWAITING_PATIENT_REPLY},
    SurgeryDialogueState.AWAITING_PATIENT_REPLY: {
        "receive_reply": SurgeryDialogueState.RE_EVALUATING,
        "fail": SurgeryDialogueState.FAILED,
    },
    SurgeryDialogueState.RE_EVALUATING: {
        "complete": SurgeryDialogueState.DIAGNOSIS_COMPLETE,
        "need_followup": SurgeryDialogueState.NEEDS_FOLLOWUP,
        "receive_reply": SurgeryDialogueState.RE_EVALUATING,
        "fail": SurgeryDialogueState.FAILED,
    },
    SurgeryDialogueState.DIAGNOSIS_COMPLETE: {
        "plan_treatment": SurgeryDialogueState.TREATMENT_PLANNING,
        "receive_reply": SurgeryDialogueState.RE_EVALUATING,
    },
    SurgeryDialogueState.TREATMENT_PLANNING: {"approve": SurgeryDialogueState.COMPLETED},
    SurgeryDialogueState.COMPLETED: {"receive_reply": SurgeryDialogueState.RE_EVALUATING},
    SurgeryDialogueState.FAILED: {},
}


class SurgeryDialogueStateMachine:
    def transition(self, current: SurgeryDialogueState, event: str) -> SurgeryDialogueState:
        next_state = SURGERY_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid surgery transition: {current} -> {event}")
        return next_state
