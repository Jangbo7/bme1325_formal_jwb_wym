from enum import Enum


class PatientLifecycleState(str, Enum):
    UNTRIAGED = "untriaged"
    TRIAGING = "triaging"
    WAITING_FOLLOWUP = "waiting_followup"
    TRIAGED = "triaged"
    QUEUED = "queued"
    CALLED = "called"
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class TriageDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING_INITIAL_INFO = "collecting_initial_info"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING_PATIENT_REPLY = "awaiting_patient_reply"
    RE_EVALUATING = "re_evaluating"
    TRIAGED = "triaged"
    FAILED = "failed"


class InternalMedicineDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING_INFO = "collecting_info"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING_PATIENT_REPLY = "awaiting_patient_reply"
    RE_EVALUATING = "re_evaluating"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    TREATMENT_PLANNING = "treatment_planning"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueTicketStatus(str, Enum):
    WAITING = "waiting"
    CALLED = "called"
    COMPLETED = "completed"


class PriorityLevel(str, Enum):
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"


class ICUDoctorDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING_INFO = "collecting_info"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING_PATIENT_REPLY = "awaiting_patient_reply"
    RE_EVALUATING = "re_evaluating"
    TREATMENT_PLANNING = "treatment_planning"
    TREATMENT_APPROVED = "treatment_approved"
    TREATMENT_REJECTED = "treatment_rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class InternalMedicineDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING_INFO = "collecting_info"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING_PATIENT_REPLY = "awaiting_patient_reply"
    RE_EVALUATING = "re_evaluating"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    TREATMENT_PLANNING = "treatment_planning"
    COMPLETED = "completed"
    FAILED = "failed"
