from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class StandardOutpatientState(str, Enum):
    ARRIVED = "ARRIVED"
    IN_TRIAGE = "IN_TRIAGE"
    TRIAGED = "TRIAGED"
    IN_EMERGENCY = "IN_EMERGENCY"
    IN_ICU_RESCUE = "IN_ICU_RESCUE"
    IN_REGISTRATION = "IN_REGISTRATION"
    REGISTERED = "REGISTERED"
    WAITING_CALL = "WAITING_CALL"
    IN_INITIAL_CONSULTATION = "IN_INITIAL_CONSULTATION"
    TEST_ORDERED = "TEST_ORDERED"
    WAITING_OUTPATIENT_PROCEDURE = "WAITING_OUTPATIENT_PROCEDURE"
    WAITING_TEST_PAYMENT = "WAITING_TEST_PAYMENT"
    TEST_PAYMENT_COMPLETED = "TEST_PAYMENT_COMPLETED"
    IN_EXAM = "IN_EXAM"
    IN_OUTPATIENT_PROCEDURE = "IN_OUTPATIENT_PROCEDURE"
    WAITING_TEST_RESULTS = "WAITING_TEST_RESULTS"
    RESULTS_READY = "RESULTS_READY"
    WAITING_SECOND_CONSULTATION = "WAITING_SECOND_CONSULTATION"
    IN_SECOND_CONSULTATION = "IN_SECOND_CONSULTATION"
    DIAGNOSIS_FINALIZED = "DIAGNOSIS_FINALIZED"
    WAITING_MEDICAL_PAYMENT = "WAITING_MEDICAL_PAYMENT"
    MEDICAL_PAYMENT_COMPLETED = "MEDICAL_PAYMENT_COMPLETED"
    DISPOSITION_PENDING = "DISPOSITION_PENDING"
    DISPOSITION_PHARMACY = "DISPOSITION_PHARMACY"
    DISPOSITION_OUTPATIENT_TREATMENT = "DISPOSITION_OUTPATIENT_TREATMENT"
    DISPOSITION_FOLLOWUP_BOOKING = "DISPOSITION_FOLLOWUP_BOOKING"
    DISPOSITION_REFERRAL = "DISPOSITION_REFERRAL"
    ADMITTED = "ADMITTED"
    TRANSFERRING = "TRANSFERRING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class StateTransitionEvent(str, Enum):
    BEGIN_TRIAGE = "begin_triage"
    TRIAGE_COMPLETE = "triage_complete"
    ROUTE_TO_EMERGENCY = "route_to_emergency"
    ROUTE_TO_ICU_RESCUE = "route_to_icu_rescue"
    BEGIN_REGISTRATION = "begin_registration"
    REGISTER_COMPLETE = "register_complete"
    CALL_PATIENT = "call_patient"
    START_INITIAL_CONSULTATION = "start_initial_consultation"
    ORDER_TESTS = "order_tests"
    ORDER_OUTPATIENT_PROCEDURE = "order_outpatient_procedure"
    FINALIZE_WITHOUT_TESTS = "finalize_without_tests"
    REQUEST_TEST_PAYMENT = "request_test_payment"
    PAY_TEST = "pay_test"
    START_EXAM = "start_exam"
    START_OUTPATIENT_PROCEDURE = "start_outpatient_procedure"
    FINISH_EXAM = "finish_exam"
    FINISH_OUTPATIENT_PROCEDURE = "finish_outpatient_procedure"
    RESULTS_READY = "results_ready"
    QUEUE_SECOND_CONSULTATION = "queue_second_consultation"
    START_SECOND_CONSULTATION = "start_second_consultation"
    FINALIZE_DIAGNOSIS = "finalize_diagnosis"
    REQUEST_MEDICAL_PAYMENT = "request_medical_payment"
    PAY_MEDICAL = "pay_medical"
    PLAN_DISPOSITION = "plan_disposition"
    CHOOSE_PHARMACY = "choose_pharmacy"
    DISPENSE_MEDICATION = "dispense_medication"
    CHOOSE_OUTPATIENT_TREATMENT = "choose_outpatient_treatment"
    CHOOSE_FOLLOWUP_BOOKING = "choose_followup_booking"
    CHOOSE_REFERRAL = "choose_referral"
    ADMIT_PATIENT = "admit_patient"
    START_TRANSFER = "start_transfer"
    COMPLETE_VISIT = "complete_visit"
    CANCEL = "cancel"
    MARK_ERROR = "mark_error"


class AllowedTransitionView(BaseModel):
    event: str
    to_state: StandardOutpatientState
    message: str


class StateDebugView(BaseModel):
    encounter_id: str
    internal_state: str
    standard_state: StandardOutpatientState
    allowed_next: list[AllowedTransitionView] = Field(default_factory=list)
    updated_at: str


class TransitionDebugRequest(BaseModel):
    event: str
    dry_run: bool = False
    context: dict = Field(default_factory=dict)


class EncounterEventRequest(BaseModel):
    event: str
    context: dict = Field(default_factory=dict)


class TransitionDebugResult(BaseModel):
    ok: bool = True
    encounter_id: str
    from_state: StandardOutpatientState
    event: str
    to_state: StandardOutpatientState
    internal_from_state: str
    internal_to_state: str
    allowed_next: list[AllowedTransitionView] = Field(default_factory=list)
    dry_run: bool = False
