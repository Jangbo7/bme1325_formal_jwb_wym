from app.schemas.common import ICUDoctorDialogueState


ICU_DOCTOR_TRANSITIONS = {
    ICUDoctorDialogueState.IDLE: {"start": ICUDoctorDialogueState.COLLECTING_INFO},
    ICUDoctorDialogueState.COLLECTING_INFO: {
        "evaluate": ICUDoctorDialogueState.EVALUATING,
        "need_followup": ICUDoctorDialogueState.NEEDS_FOLLOWUP,
    },
    ICUDoctorDialogueState.EVALUATING: {
        "complete": ICUDoctorDialogueState.TREATMENT_PLANNING,
        "need_followup": ICUDoctorDialogueState.NEEDS_FOLLOWUP,
        "fail": ICUDoctorDialogueState.FAILED,
    },
    ICUDoctorDialogueState.NEEDS_FOLLOWUP: {"wait_for_reply": ICUDoctorDialogueState.AWAITING_PATIENT_REPLY},
    ICUDoctorDialogueState.AWAITING_PATIENT_REPLY: {
        "receive_reply": ICUDoctorDialogueState.RE_EVALUATING,
        "fail": ICUDoctorDialogueState.FAILED,
    },
    ICUDoctorDialogueState.RE_EVALUATING: {
        "complete": ICUDoctorDialogueState.TREATMENT_PLANNING,
        "need_followup": ICUDoctorDialogueState.NEEDS_FOLLOWUP,
        "fail": ICUDoctorDialogueState.FAILED,
    },
    ICUDoctorDialogueState.TREATMENT_PLANNING: {
        "approve": ICUDoctorDialogueState.TREATMENT_APPROVED,
        "reject": ICUDoctorDialogueState.TREATMENT_REJECTED,
    },
    ICUDoctorDialogueState.TREATMENT_APPROVED: {"finish": ICUDoctorDialogueState.COMPLETED},
    ICUDoctorDialogueState.TREATMENT_REJECTED: {"modify": ICUDoctorDialogueState.TREATMENT_PLANNING},
    ICUDoctorDialogueState.COMPLETED: {},
    ICUDoctorDialogueState.FAILED: {},
}


class ICUDoctorDialogueStateMachine:
    def transition(self, current: ICUDoctorDialogueState, event: str) -> ICUDoctorDialogueState:
        next_state = ICU_DOCTOR_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid ICU doctor transition: {current} -> {event}")
        return next_state
