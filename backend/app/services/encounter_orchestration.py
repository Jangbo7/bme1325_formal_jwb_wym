from __future__ import annotations

import json
from datetime import datetime, timezone

from app.events.types import VISIT_STATE_CHANGED
from app.schemas.common import PatientLifecycleState
from app.schemas.orchestration import (
    AllowedTransitionView,
    StandardOutpatientState,
    StateDebugView,
    StateTransitionEvent,
    TransitionDebugResult,
)
from app.services.disposition import apply_outpatient_completion_metadata


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_STANDARD_TO_INTERNAL = {
    StandardOutpatientState.ARRIVED: "arrived",
    StandardOutpatientState.IN_TRIAGE: "triaging",
    StandardOutpatientState.TRIAGED: "triaged",
    StandardOutpatientState.IN_EMERGENCY: "in_emergency",
    StandardOutpatientState.IN_ICU_RESCUE: "in_icu_rescue",
    StandardOutpatientState.IN_REGISTRATION: "registration_pending",
    StandardOutpatientState.REGISTERED: "registered",
    StandardOutpatientState.WAITING_CALL: "waiting_consultation",
    StandardOutpatientState.IN_INITIAL_CONSULTATION: "in_consultation",
    StandardOutpatientState.TEST_ORDERED: "waiting_test",
    StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE: "waiting_outpatient_procedure",
    StandardOutpatientState.WAITING_TEST_PAYMENT: "waiting_test_payment",
    StandardOutpatientState.TEST_PAYMENT_COMPLETED: "test_payment_completed",
    StandardOutpatientState.IN_EXAM: "in_test",
    StandardOutpatientState.IN_OUTPATIENT_PROCEDURE: "in_outpatient_procedure",
    StandardOutpatientState.WAITING_TEST_RESULTS: "waiting_return_consultation",
    StandardOutpatientState.RESULTS_READY: "results_ready",
    StandardOutpatientState.WAITING_SECOND_CONSULTATION: "waiting_second_consultation",
    StandardOutpatientState.IN_SECOND_CONSULTATION: "in_second_consultation",
    StandardOutpatientState.DIAGNOSIS_FINALIZED: "diagnosis_finalized",
    StandardOutpatientState.WAITING_MEDICAL_PAYMENT: "waiting_payment",
    StandardOutpatientState.MEDICAL_PAYMENT_COMPLETED: "medical_payment_completed",
    StandardOutpatientState.DISPOSITION_PENDING: "disposition_pending",
    StandardOutpatientState.DISPOSITION_PHARMACY: "waiting_pharmacy",
    StandardOutpatientState.DISPOSITION_OUTPATIENT_TREATMENT: "disposition_outpatient_treatment",
    StandardOutpatientState.DISPOSITION_FOLLOWUP_BOOKING: "disposition_followup_booking",
    StandardOutpatientState.DISPOSITION_REFERRAL: "disposition_referral",
    StandardOutpatientState.ADMITTED: "admitted",
    StandardOutpatientState.TRANSFERRING: "transferring",
    StandardOutpatientState.COMPLETED: "completed",
    StandardOutpatientState.CANCELLED: "cancelled",
    StandardOutpatientState.ERROR: "error",
}

_INTERNAL_TO_STANDARD = {v: k for k, v in _STANDARD_TO_INTERNAL.items()}
_INTERNAL_TO_STANDARD.update(
    {
        "arrived": StandardOutpatientState.ARRIVED,
        "triaging": StandardOutpatientState.IN_TRIAGE,
        "waiting_followup": StandardOutpatientState.IN_TRIAGE,
        "triaged": StandardOutpatientState.TRIAGED,
        "in_emergency": StandardOutpatientState.IN_EMERGENCY,
        "in_icu_rescue": StandardOutpatientState.IN_ICU_RESCUE,
        "registration_pending": StandardOutpatientState.IN_REGISTRATION,
        "registered": StandardOutpatientState.REGISTERED,
        "waiting_consultation": StandardOutpatientState.WAITING_CALL,
        "in_consultation": StandardOutpatientState.IN_INITIAL_CONSULTATION,
        "waiting_test": StandardOutpatientState.TEST_ORDERED,
        "waiting_outpatient_procedure": StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE,
        "waiting_test_payment": StandardOutpatientState.WAITING_TEST_PAYMENT,
        "test_payment_completed": StandardOutpatientState.TEST_PAYMENT_COMPLETED,
        "waiting_payment": StandardOutpatientState.WAITING_MEDICAL_PAYMENT,
        "in_test": StandardOutpatientState.IN_EXAM,
        "in_outpatient_procedure": StandardOutpatientState.IN_OUTPATIENT_PROCEDURE,
        "waiting_return_consultation": StandardOutpatientState.WAITING_TEST_RESULTS,
        "results_ready": StandardOutpatientState.RESULTS_READY,
        "waiting_second_consultation": StandardOutpatientState.WAITING_SECOND_CONSULTATION,
        "in_second_consultation": StandardOutpatientState.IN_SECOND_CONSULTATION,
        "diagnosis_finalized": StandardOutpatientState.DIAGNOSIS_FINALIZED,
        "waiting_pharmacy": StandardOutpatientState.DISPOSITION_PHARMACY,
        "transferring": StandardOutpatientState.TRANSFERRING,
        "completed": StandardOutpatientState.COMPLETED,
        "cancelled": StandardOutpatientState.CANCELLED,
        "error": StandardOutpatientState.ERROR,
    }
)

_EVENT_ALIASES = {
    "triage_completed": StateTransitionEvent.TRIAGE_COMPLETE.value,
    "register_completed": StateTransitionEvent.REGISTER_COMPLETE.value,
    "queue_wait_elapsed": StateTransitionEvent.CALL_PATIENT.value,
    "start_consultation": StateTransitionEvent.START_INITIAL_CONSULTATION.value,
    "consultation_completed": StateTransitionEvent.ORDER_TESTS.value,
    "order_outpatient_procedure": StateTransitionEvent.ORDER_OUTPATIENT_PROCEDURE.value,
    "finalize_without_tests": StateTransitionEvent.FINALIZE_WITHOUT_TESTS.value,
    "ready_payment": StateTransitionEvent.REQUEST_MEDICAL_PAYMENT.value,
    "request_test_payment": StateTransitionEvent.REQUEST_TEST_PAYMENT.value,
    "pay_test": StateTransitionEvent.PAY_TEST.value,
    "start_exam": StateTransitionEvent.START_EXAM.value,
    "start_outpatient_procedure": StateTransitionEvent.START_OUTPATIENT_PROCEDURE.value,
    "finish_exam": StateTransitionEvent.FINISH_EXAM.value,
    "finish_outpatient_procedure": StateTransitionEvent.FINISH_OUTPATIENT_PROCEDURE.value,
    "results_ready": StateTransitionEvent.RESULTS_READY.value,
    "queue_second_consultation": StateTransitionEvent.QUEUE_SECOND_CONSULTATION.value,
    "start_second_consultation": StateTransitionEvent.START_SECOND_CONSULTATION.value,
    "finalize_diagnosis": StateTransitionEvent.FINALIZE_DIAGNOSIS.value,
    "request_medical_payment": StateTransitionEvent.REQUEST_MEDICAL_PAYMENT.value,
    "pay_medical": StateTransitionEvent.PAY_MEDICAL.value,
    "plan_disposition": StateTransitionEvent.PLAN_DISPOSITION.value,
    "choose_pharmacy": StateTransitionEvent.CHOOSE_PHARMACY.value,
    "dispense_medication": StateTransitionEvent.DISPENSE_MEDICATION.value,
    "choose_outpatient_treatment": StateTransitionEvent.CHOOSE_OUTPATIENT_TREATMENT.value,
    "choose_followup_booking": StateTransitionEvent.CHOOSE_FOLLOWUP_BOOKING.value,
    "choose_referral": StateTransitionEvent.CHOOSE_REFERRAL.value,
    "admit_patient": StateTransitionEvent.ADMIT_PATIENT.value,
    "complete_visit": StateTransitionEvent.COMPLETE_VISIT.value,
    "begin_triage": StateTransitionEvent.BEGIN_TRIAGE.value,
    "route_to_emergency": StateTransitionEvent.ROUTE_TO_EMERGENCY.value,
    "route_to_icu_rescue": StateTransitionEvent.ROUTE_TO_ICU_RESCUE.value,
}


def _message_for(event: str, to_state: StandardOutpatientState) -> str:
    return f"{event} -> {to_state.value}"


_GUARD_TABLE: dict[StandardOutpatientState, dict[str, StandardOutpatientState]] = {
    StandardOutpatientState.ARRIVED: {
        StateTransitionEvent.BEGIN_TRIAGE.value: StandardOutpatientState.IN_TRIAGE,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_TRIAGE: {
        StateTransitionEvent.TRIAGE_COMPLETE.value: StandardOutpatientState.TRIAGED,
        StateTransitionEvent.BEGIN_TRIAGE.value: StandardOutpatientState.IN_TRIAGE,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.TRIAGED: {
        StateTransitionEvent.ROUTE_TO_EMERGENCY.value: StandardOutpatientState.IN_EMERGENCY,
        StateTransitionEvent.ROUTE_TO_ICU_RESCUE.value: StandardOutpatientState.IN_ICU_RESCUE,
        StateTransitionEvent.BEGIN_REGISTRATION.value: StandardOutpatientState.IN_REGISTRATION,
        StateTransitionEvent.REGISTER_COMPLETE.value: StandardOutpatientState.REGISTERED,
        StateTransitionEvent.BEGIN_TRIAGE.value: StandardOutpatientState.IN_TRIAGE,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_EMERGENCY: {
        StateTransitionEvent.BEGIN_TRIAGE.value: StandardOutpatientState.IN_TRIAGE,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_ICU_RESCUE: {
        StateTransitionEvent.BEGIN_TRIAGE.value: StandardOutpatientState.IN_TRIAGE,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_REGISTRATION: {
        StateTransitionEvent.REGISTER_COMPLETE.value: StandardOutpatientState.REGISTERED,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.REGISTERED: {
        StateTransitionEvent.CALL_PATIENT.value: StandardOutpatientState.WAITING_CALL,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_CALL: {
        StateTransitionEvent.START_INITIAL_CONSULTATION.value: StandardOutpatientState.IN_INITIAL_CONSULTATION,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_INITIAL_CONSULTATION: {
        StateTransitionEvent.ORDER_TESTS.value: StandardOutpatientState.TEST_ORDERED,
        StateTransitionEvent.ORDER_OUTPATIENT_PROCEDURE.value: StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE,
        StateTransitionEvent.FINALIZE_WITHOUT_TESTS.value: StandardOutpatientState.DIAGNOSIS_FINALIZED,
        StateTransitionEvent.START_TRANSFER.value: StandardOutpatientState.TRANSFERRING,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.TEST_ORDERED: {
        StateTransitionEvent.REQUEST_TEST_PAYMENT.value: StandardOutpatientState.WAITING_TEST_PAYMENT,
        StateTransitionEvent.ORDER_OUTPATIENT_PROCEDURE.value: StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE: {
        StateTransitionEvent.START_OUTPATIENT_PROCEDURE.value: StandardOutpatientState.IN_OUTPATIENT_PROCEDURE,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_TEST_PAYMENT: {
        StateTransitionEvent.PAY_TEST.value: StandardOutpatientState.TEST_PAYMENT_COMPLETED,
        StateTransitionEvent.CANCEL.value: StandardOutpatientState.CANCELLED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.TEST_PAYMENT_COMPLETED: {
        StateTransitionEvent.START_EXAM.value: StandardOutpatientState.IN_EXAM,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_EXAM: {
        StateTransitionEvent.FINISH_EXAM.value: StandardOutpatientState.WAITING_TEST_RESULTS,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_OUTPATIENT_PROCEDURE: {
        StateTransitionEvent.ORDER_TESTS.value: StandardOutpatientState.TEST_ORDERED,
        StateTransitionEvent.FINISH_OUTPATIENT_PROCEDURE.value: StandardOutpatientState.RESULTS_READY,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_TEST_RESULTS: {
        StateTransitionEvent.RESULTS_READY.value: StandardOutpatientState.RESULTS_READY,
        StateTransitionEvent.ORDER_OUTPATIENT_PROCEDURE.value: StandardOutpatientState.WAITING_OUTPATIENT_PROCEDURE,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.RESULTS_READY: {
        StateTransitionEvent.QUEUE_SECOND_CONSULTATION.value: StandardOutpatientState.WAITING_SECOND_CONSULTATION,
        StateTransitionEvent.START_SECOND_CONSULTATION.value: StandardOutpatientState.IN_SECOND_CONSULTATION,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_SECOND_CONSULTATION: {
        StateTransitionEvent.START_SECOND_CONSULTATION.value: StandardOutpatientState.IN_SECOND_CONSULTATION,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.IN_SECOND_CONSULTATION: {
        StateTransitionEvent.FINALIZE_DIAGNOSIS.value: StandardOutpatientState.DIAGNOSIS_FINALIZED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DIAGNOSIS_FINALIZED: {
        StateTransitionEvent.REQUEST_MEDICAL_PAYMENT.value: StandardOutpatientState.WAITING_MEDICAL_PAYMENT,
        StateTransitionEvent.PLAN_DISPOSITION.value: StandardOutpatientState.DISPOSITION_PENDING,
        StateTransitionEvent.START_TRANSFER.value: StandardOutpatientState.TRANSFERRING,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.WAITING_MEDICAL_PAYMENT: {
        StateTransitionEvent.PAY_MEDICAL.value: StandardOutpatientState.MEDICAL_PAYMENT_COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.MEDICAL_PAYMENT_COMPLETED: {
        StateTransitionEvent.PLAN_DISPOSITION.value: StandardOutpatientState.DISPOSITION_PENDING,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DISPOSITION_PENDING: {
        StateTransitionEvent.CHOOSE_PHARMACY.value: StandardOutpatientState.DISPOSITION_PHARMACY,
        StateTransitionEvent.CHOOSE_OUTPATIENT_TREATMENT.value: StandardOutpatientState.DISPOSITION_OUTPATIENT_TREATMENT,
        StateTransitionEvent.CHOOSE_FOLLOWUP_BOOKING.value: StandardOutpatientState.DISPOSITION_FOLLOWUP_BOOKING,
        StateTransitionEvent.CHOOSE_REFERRAL.value: StandardOutpatientState.DISPOSITION_REFERRAL,
        StateTransitionEvent.ADMIT_PATIENT.value: StandardOutpatientState.ADMITTED,
        StateTransitionEvent.ROUTE_TO_EMERGENCY.value: StandardOutpatientState.IN_EMERGENCY,
        StateTransitionEvent.ROUTE_TO_ICU_RESCUE.value: StandardOutpatientState.IN_ICU_RESCUE,
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DISPOSITION_PHARMACY: {
        StateTransitionEvent.DISPENSE_MEDICATION.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DISPOSITION_OUTPATIENT_TREATMENT: {
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DISPOSITION_FOLLOWUP_BOOKING: {
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.DISPOSITION_REFERRAL: {
        StateTransitionEvent.START_TRANSFER.value: StandardOutpatientState.TRANSFERRING,
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.ADMITTED: {
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.TRANSFERRING: {
        StateTransitionEvent.ADMIT_PATIENT.value: StandardOutpatientState.ADMITTED,
        StateTransitionEvent.COMPLETE_VISIT.value: StandardOutpatientState.COMPLETED,
        StateTransitionEvent.MARK_ERROR.value: StandardOutpatientState.ERROR,
    },
    StandardOutpatientState.COMPLETED: {},
    StandardOutpatientState.CANCELLED: {},
    StandardOutpatientState.ERROR: {},
}


class EncounterOrchestrationService:
    def __init__(self, *, visit_repo, patient_repo, bus):
        self.visit_repo = visit_repo
        self.patient_repo = patient_repo
        self.bus = bus

    def create_or_get_encounter(self, *, patient_id: str, patient_name: str) -> dict:
        self.patient_repo.upsert_basic(patient_id, patient_name)
        visit_row = self.visit_repo.create_or_get_active(patient_id)
        self.patient_repo.update_patient(patient_id, name=patient_name, visit_id=visit_row["id"])
        self._ensure_orchestration_snapshot(visit_row, resolved_state=StandardOutpatientState.ARRIVED)
        return self.visit_repo.get(visit_row["id"]) or visit_row

    def state_debug_view(self, encounter_id: str) -> StateDebugView:
        row = self.visit_repo.get(encounter_id)
        if not row:
            raise KeyError(encounter_id)
        standard_state = self._resolve_standard_state(row)
        return StateDebugView(
            encounter_id=encounter_id,
            internal_state=row["state"],
            standard_state=standard_state,
            allowed_next=self.allowed_next(standard_state),
            updated_at=row.get("updated_at") or now_iso(),
        )

    def transition(self, encounter_id: str, event: str, *, dry_run: bool = False, context: dict | None = None) -> TransitionDebugResult:
        row = self.visit_repo.get(encounter_id)
        if not row:
            raise KeyError(encounter_id)
        from_standard = self._resolve_standard_state(row)
        normalized_event = self._normalize_event(event)
        transition_map = _GUARD_TABLE.get(from_standard, {})
        if normalized_event not in transition_map:
            raise ValueError(f"STATE_TRANSITION_INVALID: {from_standard.value} -> {normalized_event}")
        to_standard = transition_map[normalized_event]
        internal_to = _STANDARD_TO_INTERNAL[to_standard]
        internal_from = row["state"]
        next_allowed = self.allowed_next(to_standard)

        if not dry_run:
            self._commit_transition(
                row=row,
                event=normalized_event,
                to_standard=to_standard,
                internal_to=internal_to,
                context=context or {},
            )

        return TransitionDebugResult(
            encounter_id=encounter_id,
            from_state=from_standard,
            event=normalized_event,
            to_state=to_standard,
            internal_from_state=internal_from,
            internal_to_state=internal_to,
            allowed_next=next_allowed,
            dry_run=dry_run,
        )

    def reset(self, encounter_id: str, *, context: dict | None = None) -> TransitionDebugResult:
        row = self.visit_repo.get(encounter_id)
        if not row:
            raise KeyError(encounter_id)
        from_standard = self._resolve_standard_state(row)
        to_standard = StandardOutpatientState.ARRIVED
        internal_from = row["state"]
        internal_to = _STANDARD_TO_INTERNAL[to_standard]
        self._commit_transition(
            row=row,
            event="debug_reset",
            to_standard=to_standard,
            internal_to=internal_to,
            context=context or {},
        )
        return TransitionDebugResult(
            encounter_id=encounter_id,
            from_state=from_standard,
            event="debug_reset",
            to_state=to_standard,
            internal_from_state=internal_from,
            internal_to_state=internal_to,
            allowed_next=self.allowed_next(to_standard),
            dry_run=False,
        )

    def rollback(self, encounter_id: str, *, context: dict | None = None) -> TransitionDebugResult:
        row = self.visit_repo.get(encounter_id)
        if not row:
            raise KeyError(encounter_id)
        from_standard = self._resolve_standard_state(row)
        internal_from = row["state"]
        data = self._decode_data(row)
        history = data.get("orchestration_history")
        if not isinstance(history, list) or not history:
            raise ValueError("STATE_TRANSITION_INVALID: no history to rollback")

        last = history.pop()
        target_state_raw = last.get("from_state")
        if not isinstance(target_state_raw, str):
            raise ValueError("STATE_TRANSITION_INVALID: invalid rollback target")
        try:
            to_standard = StandardOutpatientState(target_state_raw)
        except Exception as exc:
            raise ValueError(f"STATE_TRANSITION_INVALID: unknown rollback target {target_state_raw}") from exc
        internal_to = _STANDARD_TO_INTERNAL[to_standard]

        data["orchestration_history"] = history
        debug_log = data.get("orchestration_debug_log")
        if not isinstance(debug_log, list):
            debug_log = []
        debug_log.append(
            {
                "at": now_iso(),
                "from_state": from_standard.value,
                "event": "debug_back",
                "to_state": to_standard.value,
                "internal_from_state": internal_from,
                "internal_to_state": internal_to,
                "context": context or {},
            }
        )
        data["orchestration_debug_log"] = debug_log
        data["orchestration_state"] = to_standard.value
        self.visit_repo.update_visit(encounter_id, state=internal_to, data=data)
        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": encounter_id,
                "patient_id": row["patient_id"],
                "state": internal_to,
                "event": "orchestration.debug_back",
                "standard_state": to_standard.value,
            },
        )
        return TransitionDebugResult(
            encounter_id=encounter_id,
            from_state=from_standard,
            event="debug_back",
            to_state=to_standard,
            internal_from_state=internal_from,
            internal_to_state=internal_to,
            allowed_next=self.allowed_next(to_standard),
            dry_run=False,
        )

    def graph(self) -> dict:
        edges = []
        for from_state, transitions in _GUARD_TABLE.items():
            for event, to_state in transitions.items():
                edges.append(
                    {
                        "from_state": from_state.value,
                        "event": event,
                        "to_state": to_state.value,
                        "message": _message_for(event, to_state),
                    }
                )
        return {
            "states": [state.value for state in StandardOutpatientState],
            "events": [event.value for event in StateTransitionEvent],
            "edges": edges,
        }

    def allowed_next(self, standard_state: StandardOutpatientState) -> list[AllowedTransitionView]:
        transitions = _GUARD_TABLE.get(standard_state, {})
        return [
            AllowedTransitionView(
                event=event,
                to_state=to_state,
                message=_message_for(event, to_state),
            )
            for event, to_state in transitions.items()
        ]

    def _resolve_standard_state(self, visit_row: dict) -> StandardOutpatientState:
        data = self._decode_data(visit_row)
        internal_state = (visit_row.get("state") or "").strip().lower()
        resolved_from_internal = _INTERNAL_TO_STANDARD.get(internal_state, StandardOutpatientState.ERROR)
        state_from_data = data.get("orchestration_state")
        if isinstance(state_from_data, str):
            try:
                resolved_from_data = StandardOutpatientState(state_from_data)
                # Heal stale snapshots produced by legacy direct state writers.
                if resolved_from_internal != StandardOutpatientState.ERROR and resolved_from_internal != resolved_from_data:
                    self._ensure_orchestration_snapshot(visit_row, resolved_state=resolved_from_internal)
                    return resolved_from_internal
                return resolved_from_data
            except Exception:
                pass
        resolved = resolved_from_internal
        self._ensure_orchestration_snapshot(visit_row, resolved_state=resolved)
        return resolved

    def _ensure_orchestration_snapshot(self, visit_row: dict, *, resolved_state: StandardOutpatientState) -> None:
        data = self._decode_data(visit_row)
        if data.get("orchestration_state") == resolved_state.value:
            return
        data["orchestration_state"] = resolved_state.value
        self.visit_repo.update_visit(visit_row["id"], data=data)

    def _commit_transition(
        self,
        *,
        row: dict,
        event: str,
        to_standard: StandardOutpatientState,
        internal_to: str,
        context: dict,
    ) -> None:
        from_standard = self._resolve_standard_state(row)
        internal_from = row["state"]
        data = self._decode_data(row)
        history = data.get("orchestration_history")
        if not isinstance(history, list):
            history = []
        history.append(
            {
                "at": now_iso(),
                "from_state": from_standard.value,
                "event": event,
                "to_state": to_standard.value,
                "internal_from_state": internal_from,
                "internal_to_state": internal_to,
                "context": context,
            }
        )
        data["orchestration_history"] = history
        data["orchestration_state"] = to_standard.value
        data = apply_outpatient_completion_metadata(
            data,
            visit_state=internal_to,
        )
        self.visit_repo.update_visit(
            row["id"],
            state=internal_to,
            data=data,
        )
        self._sync_patient_lifecycle(row["patient_id"], internal_to)
        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": row["id"],
                "patient_id": row["patient_id"],
                "state": internal_to,
                "event": f"orchestration.{event}",
                "standard_state": to_standard.value,
            },
        )

    def _sync_patient_lifecycle(self, patient_id: str, visit_state: str) -> None:
        patient_row = self.patient_repo.get(patient_id)
        if not patient_row:
            return
        if visit_state == _STANDARD_TO_INTERNAL[StandardOutpatientState.ERROR]:
            self.patient_repo.update_patient(patient_id, lifecycle_state=PatientLifecycleState.ERROR.value)
            return
        if visit_state == _STANDARD_TO_INTERNAL[StandardOutpatientState.CANCELLED]:
            self.patient_repo.update_patient(patient_id, lifecycle_state=PatientLifecycleState.CANCELLED.value)
            return
        if visit_state in {
            _STANDARD_TO_INTERNAL[StandardOutpatientState.IN_EMERGENCY],
            _STANDARD_TO_INTERNAL[StandardOutpatientState.IN_ICU_RESCUE],
            _STANDARD_TO_INTERNAL[StandardOutpatientState.DISPOSITION_REFERRAL],
            _STANDARD_TO_INTERNAL[StandardOutpatientState.ADMITTED],
            _STANDARD_TO_INTERNAL[StandardOutpatientState.TRANSFERRING],
            _STANDARD_TO_INTERNAL[StandardOutpatientState.COMPLETED],
        }:
            self.patient_repo.update_patient(patient_id, lifecycle_state=PatientLifecycleState.COMPLETED.value)

    @staticmethod
    def _decode_data(visit_row: dict) -> dict:
        payload = visit_row.get("data_json")
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            return {}

    @staticmethod
    def _normalize_event(event: str) -> str:
        key = (event or "").strip()
        if not key:
            raise ValueError("STATE_TRANSITION_INVALID: event is required")
        return _EVENT_ALIASES.get(key, key)
