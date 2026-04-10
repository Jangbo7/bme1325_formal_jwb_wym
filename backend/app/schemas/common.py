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


class QueueTicketStatus(str, Enum):
    WAITING = "waiting"
    CALLED = "called"
    COMPLETED = "completed"


class PriorityLevel(str, Enum):
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"


class VisitLifecycleState(str, Enum):
    ARRIVED = "arrived"
    REGISTRATION_PENDING = "registration_pending"
    REGISTERED = "registered"
    TRIAGING = "triaging"
    WAITING_FOLLOWUP = "waiting_followup"
    TRIAGED = "triaged"
    WAITING_CONSULTATION = "waiting_consultation"
    IN_CONSULTATION = "in_consultation"
    WAITING_PAYMENT = "waiting_payment"
    WAITING_TEST = "waiting_test"
    IN_TEST = "in_test"
    WAITING_RETURN_CONSULTATION = "waiting_return_consultation"
    WAITING_PHARMACY = "waiting_pharmacy"
    COMPLETED = "completed"
    ERROR = "error"
