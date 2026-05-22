from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.schemas.common import PatientLifecycleState, VisitLifecycleState
from app.schemas.scene_snapshot import (
    SceneDialogueSnapshot,
    SceneDialogueTurn,
    SceneMedicalRecordSummary,
    SceneOtherPatientSummary,
    SceneSnapshot,
    SceneTimers,
    SceneUiFlags,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SceneSnapshotService:
    DEFAULT_PATIENT_ID = "P-self"
    QUEUE_WAIT_SECONDS = 10
    TERMINAL_PATIENT_STATES = {
        PatientLifecycleState.COMPLETED.value,
        PatientLifecycleState.CANCELLED.value,
        PatientLifecycleState.ERROR.value,
    }
    TERMINAL_VISIT_STATES = {
        VisitLifecycleState.COMPLETED.value,
        VisitLifecycleState.CANCELLED.value,
        VisitLifecycleState.ERROR.value,
    }

    def __init__(self, *, patient_repo, queue_repo, visit_repo, triage_service, medical_record_repo):
        self.patient_repo = patient_repo
        self.queue_repo = queue_repo
        self.visit_repo = visit_repo
        self.triage_service = triage_service
        self.medical_record_repo = medical_record_repo

    def get_snapshot(self, patient_id: str | None = None) -> SceneSnapshot:
        resolved_patient_id = (patient_id or self.DEFAULT_PATIENT_ID).strip() or self.DEFAULT_PATIENT_ID
        patient_view = self.triage_service.get_patient_view(resolved_patient_id)
        if not patient_view:
            raise KeyError(resolved_patient_id)

        visit_view = None
        if patient_view.visit_id:
            visit_row = self.visit_repo.get(patient_view.visit_id)
            if visit_row:
                visit_view = self.visit_repo.to_view(visit_row)

        active_dialogue = self._build_active_dialogue(patient_view)
        medical_record_summary = self._build_medical_record_summary(patient_view.visit_id)
        latest_test_report = self._build_latest_test_report(visit_view)
        timers = self._build_timers(visit_view)
        ui_flags = self._build_ui_flags(patient_view, visit_view, active_dialogue, latest_test_report, timers)
        other_patients = self._build_other_patients(resolved_patient_id)
        queues = self.queue_repo.list_views()

        snapshot = SceneSnapshot(
            generated_at=now_iso(),
            sync_token="",
            patient_id=resolved_patient_id,
            self_patient=patient_view,
            active_visit=visit_view,
            active_queue_ticket=patient_view.queue_ticket,
            active_dialogue=active_dialogue,
            medical_record_summary=medical_record_summary,
            latest_test_report=latest_test_report,
            ui_flags=ui_flags,
            timers=timers,
            other_patients=other_patients,
            queues=queues,
        )
        snapshot.sync_token = self._build_sync_token(snapshot)
        return snapshot

    def _build_active_dialogue(self, patient_view) -> SceneDialogueSnapshot | None:
        dialogue = patient_view.dialogue
        if not dialogue:
            return None

        agent_type = patient_view.dialogue_source_agent or patient_view.active_agent_type or "triage"
        session_refs = patient_view.session_refs or {}
        visit_state = patient_view.visit_state.value if patient_view and patient_view.visit_state else None
        is_second_consultation_flow = visit_state in {
            VisitLifecycleState.IN_SECOND_CONSULTATION.value,
            VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
            VisitLifecycleState.WAITING_PAYMENT.value,
            VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
            VisitLifecycleState.DISPOSITION_PENDING.value,
            VisitLifecycleState.WAITING_PHARMACY.value,
            VisitLifecycleState.DISPOSITION_OUTPATIENT_TREATMENT.value,
            VisitLifecycleState.DISPOSITION_FOLLOWUP_BOOKING.value,
            VisitLifecycleState.DISPOSITION_REFERRAL.value,
        }
        if agent_type == "internal_medicine":
            session_id = (
                session_refs.get("internal_medicine_round2_session_id")
                if is_second_consultation_flow
                else session_refs.get("internal_medicine_session_id")
            ) or patient_view.session_id
        else:
            session_id = session_refs.get("triage_session_id") or patient_view.session_id

        turns = [
            SceneDialogueTurn(
                role=str(turn.get("role") or ""),
                content=str(turn.get("content") or ""),
                timestamp=turn.get("timestamp"),
                metadata=turn.get("metadata") or {},
            )
            for turn in (dialogue.turns or [])
        ]
        return SceneDialogueSnapshot(
            agent_type=agent_type,
            session_id=session_id,
            status=dialogue.status,
            assistant_message=dialogue.assistant_message,
            missing_fields=list(dialogue.missing_fields or []),
            question_focus=dialogue.question_focus,
            message_type=dialogue.message_type,
            turns=turns,
        )

    def _build_medical_record_summary(self, visit_id: str | None) -> SceneMedicalRecordSummary | None:
        if not visit_id:
            return None
        timeline = self.medical_record_repo.get_visit_timeline(visit_id)
        if not timeline:
            return None
        summary = timeline.get("summary") or {}
        return SceneMedicalRecordSummary(
            record_id=str(summary.get("record_id") or ""),
            patient_id=str(summary.get("patient_id") or ""),
            visit_id=str(summary.get("visit_id") or ""),
            entry_count=int(summary.get("entry_count") or 0),
            latest_entry_type=summary.get("latest_entry_type"),
            latest_phase=summary.get("latest_phase"),
            updated_at=str(summary.get("updated_at") or ""),
        )

    @staticmethod
    def _build_latest_test_report(visit_view) -> dict | None:
        if not visit_view:
            return None
        report = (visit_view.data or {}).get("simulated_report")
        return report if isinstance(report, dict) else None

    def _build_ui_flags(self, patient_view, visit_view, active_dialogue, latest_test_report, timers: SceneTimers) -> SceneUiFlags:
        visit_state = visit_view.state.value if visit_view and visit_view.state else None
        patient_state = patient_view.lifecycle_state.value if patient_view and patient_view.lifecycle_state else None
        queue_status = patient_view.queue_ticket.status if patient_view and patient_view.queue_ticket else None
        active_dialogue_agent = active_dialogue.agent_type if active_dialogue else None
        can_chat_with_doctor = visit_state in {
            VisitLifecycleState.IN_CONSULTATION.value,
            VisitLifecycleState.IN_SECOND_CONSULTATION.value,
        }
        return SceneUiFlags(
            has_active_visit=visit_view is not None,
            can_submit_triage=visit_state in {None, VisitLifecycleState.ARRIVED.value},
            can_continue_triage=active_dialogue_agent == "triage",
            can_register=visit_state == VisitLifecycleState.TRIAGED.value,
            can_progress_visit=(
                visit_state == VisitLifecycleState.REGISTERED.value
                and timers.queue_wait_seconds_remaining <= 0
            ),
            ready_for_consultation=(
                patient_state == PatientLifecycleState.CALLED.value
                and visit_state == VisitLifecycleState.WAITING_CONSULTATION.value
            ),
            can_enter_consultation=(
                patient_state == PatientLifecycleState.CALLED.value
                and visit_state == VisitLifecycleState.WAITING_CONSULTATION.value
                and queue_status == "called"
            ),
            can_start_internal_medicine=can_chat_with_doctor and active_dialogue_agent != "internal_medicine",
            can_continue_internal_medicine=can_chat_with_doctor and active_dialogue_agent == "internal_medicine",
            can_view_test_report=latest_test_report is not None,
            can_ready_payment=visit_state == VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
        )

    def _build_timers(self, visit_view) -> SceneTimers:
        if not visit_view or visit_view.state != VisitLifecycleState.REGISTERED:
            return SceneTimers(queue_wait_seconds_remaining=0)

        data = visit_view.data or {}
        registered_at_text = data.get("registration_completed_at") or visit_view.updated_at
        try:
            registered_at = datetime.fromisoformat(str(registered_at_text))
        except (TypeError, ValueError):
            return SceneTimers(queue_wait_seconds_remaining=0)
        if registered_at.tzinfo is None:
            registered_at = registered_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - registered_at).total_seconds()
        remaining = max(0, int(self.QUEUE_WAIT_SECONDS - elapsed))
        return SceneTimers(queue_wait_seconds_remaining=remaining)

    def _build_other_patients(self, self_patient_id: str) -> list[SceneOtherPatientSummary]:
        rows = []
        for row in self.patient_repo.list():
            patient_id = str(row.get("id") or "")
            if patient_id == self_patient_id:
                continue
            lifecycle_state = str(row.get("lifecycle_state") or "")
            if lifecycle_state in self.TERMINAL_PATIENT_STATES:
                continue
            patient_view = self.triage_service.get_patient_view(patient_id)
            if not patient_view:
                continue
            visit_state = patient_view.visit_state.value if patient_view.visit_state else None
            if visit_state in self.TERMINAL_VISIT_STATES:
                continue
            rows.append(
                SceneOtherPatientSummary(
                    patient_id=patient_view.id,
                    name=patient_view.name,
                    state=patient_view.state,
                    lifecycle_state=patient_view.lifecycle_state.value,
                    visit_state=visit_state,
                    location=patient_view.location,
                    priority=patient_view.priority,
                    active_agent_type=patient_view.active_agent_type,
                    updated_at=patient_view.updated_at,
                )
            )
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows[:10]

    @staticmethod
    def _build_sync_token(snapshot: SceneSnapshot) -> str:
        payload = snapshot.model_dump(mode="json")
        payload["generated_at"] = ""
        payload["sync_token"] = ""
        digest = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"scene-{digest[:16]}"
