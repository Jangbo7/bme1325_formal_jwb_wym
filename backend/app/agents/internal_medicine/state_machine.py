from app.schemas.common import InternalMedicineDialogueState


INTERNAL_MEDICINE_TRANSITIONS = {
    InternalMedicineDialogueState.IDLE: {"start": InternalMedicineDialogueState.COLLECTING_INFO},
    InternalMedicineDialogueState.COLLECTING_INFO: {
        "evaluate": InternalMedicineDialogueState.EVALUATING,
        "need_followup": InternalMedicineDialogueState.NEEDS_FOLLOWUP,
    },
    InternalMedicineDialogueState.EVALUATING: {
        "complete": InternalMedicineDialogueState.DIAGNOSIS_COMPLETE,
        "need_followup": InternalMedicineDialogueState.NEEDS_FOLLOWUP,
        "fail": InternalMedicineDialogueState.FAILED,
    },
    InternalMedicineDialogueState.NEEDS_FOLLOWUP: {"wait_for_reply": InternalMedicineDialogueState.AWAITING_PATIENT_REPLY},
    InternalMedicineDialogueState.AWAITING_PATIENT_REPLY: {
        "receive_reply": InternalMedicineDialogueState.RE_EVALUATING,
        "fail": InternalMedicineDialogueState.FAILED,
    },
    InternalMedicineDialogueState.RE_EVALUATING: {
        "complete": InternalMedicineDialogueState.DIAGNOSIS_COMPLETE,
        "need_followup": InternalMedicineDialogueState.NEEDS_FOLLOWUP,
        "receive_reply": InternalMedicineDialogueState.RE_EVALUATING,
        "fail": InternalMedicineDialogueState.FAILED,
    },
    InternalMedicineDialogueState.DIAGNOSIS_COMPLETE: {
        "plan_treatment": InternalMedicineDialogueState.TREATMENT_PLANNING,
        "receive_reply": InternalMedicineDialogueState.RE_EVALUATING,
    },
    InternalMedicineDialogueState.TREATMENT_PLANNING: {"approve": InternalMedicineDialogueState.COMPLETED},
    InternalMedicineDialogueState.COMPLETED: {},
    InternalMedicineDialogueState.FAILED: {},
}


class InternalMedicineDialogueStateMachine:
    def transition(self, current: InternalMedicineDialogueState, event: str) -> InternalMedicineDialogueState:
        next_state = INTERNAL_MEDICINE_TRANSITIONS.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid internal medicine transition: {current} -> {event}")
        return next_state
