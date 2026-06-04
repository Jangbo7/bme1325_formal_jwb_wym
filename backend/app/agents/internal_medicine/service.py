import json

from app.agents.department_runtime import DepartmentAgentRuntime
from app.agents.test_simulator.service import TestSimulationAgent
from app.events.types import (
    INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
    TEST_REPORT_GENERATED,
    TEST_ZONE_ASSIGNED,
    VISIT_STATE_CHANGED,
)
from app.schemas.common import InternalMedicineDialogueState, PatientLifecycleState, VisitLifecycleState


PRIMARY_TEST_ZONE_LABELS = {
    "medical_imaging": "医学影像检查",
    "medical_laboratory": "医学实验室检验",
}


class InternalMedicineService(DepartmentAgentRuntime):
    def __init__(self, *args, test_simulator=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_simulator = test_simulator or TestSimulationAgent()

    def get_patient_view(self, patient_id: str):
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return None

        visit_id = patient.get("visit_id")
        visit_row = self.visit_repo.get(visit_id) if visit_id else self.visit_repo.get_active_by_patient(patient_id)
        visit_data = self._decode_visit_data(visit_row)

        visit_state_text = (visit_row.get("state") or "") if visit_row else ""
        is_second_consultation_flow = visit_state_text in {
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
        session_id = visit_data.get("internal_medicine_round2_session_id") if is_second_consultation_flow else None
        if not session_id and not is_second_consultation_flow:
            session_id = visit_data.get("internal_medicine_session_id")
        if not session_id and not is_second_consultation_flow:
            latest_row = self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], self.config.agent_type) if visit_row else None
            session_id = latest_row["id"] if latest_row else None
        if not session_id and not is_second_consultation_flow:
            patient_session = str(patient.get("session_id") or "")
            session_id = patient_session if patient_session.startswith(self.config.session_prefix) else None

        private_memory = None
        dialogue = None
        evidence = []
        if session_id:
            private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=self.config.agent_type)
        if private_memory:
            progress = self._get_progress(private_memory)
            dialogue = {
                "status": private_memory.get("dialogue_state", InternalMedicineDialogueState.IDLE.value),
                "assistant_message": private_memory.get("assistant_message", ""),
                "missing_fields": private_memory.get("missing_fields", []),
                "turns": self.session_repo.list_turns(session_id),
                "message_type": private_memory.get("message_type", "followup"),
                "question_focus": progress.last_question_focus,
                "asked_fields_history": progress.asked_fields_history,
                "final_result": private_memory.get("final_result", {}),
            }
            evidence = private_memory.get("evidence", [])

        queue_ticket = self.queue_repo.get_active_ticket_for_patient(patient_id, visit_id=visit_row["id"] if visit_row else None)
        session_refs = {
            "triage_session_id": visit_data.get("triage_session_id"),
            "internal_medicine_session_id": visit_data.get("internal_medicine_session_id") or session_id,
            "internal_medicine_round2_session_id": visit_data.get("internal_medicine_round2_session_id"),
        }
        return self.patient_repo.to_view(
            patient,
            dialogue=dialogue,
            evidence=evidence,
            queue_ticket=queue_ticket,
            visit_row=visit_row,
            active_agent_type=self.config.agent_type,
            session_refs=session_refs,
            dialogue_source_agent=self.config.agent_type if dialogue else None,
        )

    def list_patient_views(self):
        return [self.get_patient_view(row["id"]) for row in self.patient_repo.list()]

    def prepare_create_session(self, payload: dict, session_id: str, dialogue_state: InternalMedicineDialogueState) -> None:
        patient_id = payload["patient_id"]
        visit_id = payload.get("visit_id")
        patient_row = self.patient_repo.get(patient_id)
        if not patient_row:
            raise ValueError("patient not found")
        visit_row = self.visit_repo.get(visit_id) if visit_id else None
        if not visit_row or visit_row.get("patient_id") != patient_id:
            raise ValueError("visit not found")
        visit_state = VisitLifecycleState(visit_row["state"])
        if visit_state == VisitLifecycleState.IN_CONSULTATION:
            consultation_round = 1
        elif visit_state == VisitLifecycleState.IN_SECOND_CONSULTATION:
            consultation_round = 2
        else:
            raise ValueError("visit is not in consultation")
        patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
        if consultation_round == 1 and patient_state != PatientLifecycleState.IN_CONSULTATION:
            raise ValueError("patient is not in consultation")
        if consultation_round == 2 and patient_state not in {PatientLifecycleState.IN_CONSULTATION, PatientLifecycleState.IN_TEST}:
            raise ValueError("patient is not ready for second consultation")
        payload["_consultation_round"] = consultation_round
        self.session_repo.create_or_update(
            session_id,
            patient_id,
            dialogue_state.value,
            agent_type=self.config.agent_type,
            visit_id=visit_id,
        )
        self.patient_repo.update_patient(patient_id, session_id=session_id, visit_id=visit_id)
        self._update_visit_agent_context(visit_row, session_id, active_agent_type=self.config.agent_type)

    def validate_continue_session(self, session_id: str, payload: dict) -> dict:
        session_row = self.session_repo.get(session_id)
        if not session_row:
            raise ValueError("session not found")
        if session_row.get("agent_type") != self.config.agent_type:
            raise ValueError("session is not an internal medicine session")
        payload["visit_id"] = payload.get("visit_id") or session_row.get("visit_id")
        patient_id = payload.get("patient_id") or session_row.get("patient_id")
        payload["patient_id"] = patient_id
        if patient_id != session_row.get("patient_id"):
            raise ValueError("patient does not match session")
        visit_row = self.visit_repo.get(payload["visit_id"]) if payload.get("visit_id") else None
        if not visit_row or visit_row.get("patient_id") != patient_id:
            raise ValueError("visit does not match session")
        return session_row

    def configure_private_memory_defaults(self, private_memory: dict, payload: dict) -> None:
        private_memory.setdefault("message_type", "followup")
        private_memory.setdefault("missing_fields", [])
        private_memory.setdefault("assistant_message", "")
        private_memory.setdefault("evidence", [])
        private_memory.setdefault("latest_extraction", {})
        private_memory.setdefault("latest_summary", {})
        private_memory.setdefault(self.config.progress_memory_key, {})
        private_memory.setdefault("final_result", {})
        private_memory.setdefault("consultation_round", int(payload.get("_consultation_round") or 1))

    def load_historical_records_template(self, *, patient_id: str, visit_id: str) -> dict:
        return self._build_historical_records_template(patient_id=patient_id, visit_id=visit_id)

    def build_assistant_turn_metadata(self, consultation_result: dict, message_type: str, progress, private_memory: dict) -> dict:
        return {
            "agent_type": self.config.agent_type,
            "message_type": message_type,
            "department": consultation_result.get("department"),
            "priority": consultation_result.get("priority"),
            "diagnosis_level": consultation_result.get("diagnosis_level"),
            "test_category": consultation_result.get("test_category"),
            "test_required": consultation_result.get("test_required", True),
            "question_focus": progress.last_question_focus,
            "round": int(private_memory.get("consultation_round") or 1),
        }

    def resolve_patient_transition(
        self,
        *,
        existing_patient: dict | None,
        consultation_result: dict,
        complete: bool,
        was_completed: bool,
        private_memory: dict,
    ):
        if not complete or was_completed or not existing_patient:
            return None, None
        consultation_round = int(private_memory.get("consultation_round") or 1)
        current_patient_state = PatientLifecycleState(existing_patient["lifecycle_state"])
        if consultation_round == 1:
            return self.patient_state_machine.transition(current_patient_state, "internal_medicine_completed"), "Auxiliary Diagnostic Center"
        return self.patient_state_machine.transition(current_patient_state, "finish"), "Payment"

    def after_persist_result(self, **kwargs) -> None:
        patient_id = kwargs["patient_id"]
        session_id = kwargs["session_id"]
        payload = kwargs["payload"]
        memory = kwargs["memory"]
        consultation_result = kwargs["consultation_result"]
        assistant_message = kwargs["assistant_message"]
        complete = kwargs["complete"]
        was_completed = kwargs["was_completed"]
        visit_row = kwargs["visit_row"]
        timestamp = kwargs["timestamp"]

        consultation_round = int(memory.private_memory.get("consultation_round") or 1)
        visit_id = payload.get("visit_id")
        if complete and not was_completed and consultation_round == 1:
            self._append_medical_record_entry(
                patient_id=patient_id,
                visit_id=visit_id,
                phase="internal_medicine_round1",
                entry_type="initial_consult_note",
                title="Initial Internal Medicine Assessment",
                content_text=(
                    f"department={consultation_result.get('department')}; "
                    f"priority={consultation_result.get('priority')}; "
                    f"diagnosis_level={consultation_result.get('diagnosis_level')}"
                ),
                content={
                    "department": consultation_result.get("department"),
                    "priority": consultation_result.get("priority"),
                    "diagnosis_level": consultation_result.get("diagnosis_level"),
                    "impression": consultation_result.get("impression"),
                    "differentials": consultation_result.get("differentials", []),
                    "test_required": consultation_result.get("test_required", True),
                    "test_category": consultation_result.get("test_category"),
                    "assistant_message": assistant_message,
                },
            )

        if not visit_row:
            return

        if consultation_round == 1 and complete and not was_completed:
            visit_data = self._get_visit_data(visit_row)
            simulation_report = self.test_simulator.generate_report(consultation_result, memory.shared_memory)
            assigned_category = simulation_report["category_code"]
            assigned_zone_label = PRIMARY_TEST_ZONE_LABELS.get(assigned_category, "辅助检查")
            existing_diagnostic_session = visit_data.get("diagnostic_session")
            existing_diagnostic_session = existing_diagnostic_session if isinstance(existing_diagnostic_session, dict) else {}
            diagnostic_session = {
                "id": existing_diagnostic_session.get("id") or f"diag-session-{visit_row['id']}",
                "type": "auxiliary_diagnostic_center",
                "primary_category": assigned_category,
                "primary_category_label": assigned_zone_label,
                "window_code": simulation_report.get("window_code"),
                "window_label": simulation_report.get("window_label"),
                "recommended_items": simulation_report.get("test_items", []),
                "status": "report_generated",
                "created_at": existing_diagnostic_session.get("created_at") or timestamp,
                "generated_at": simulation_report.get("generated_at", timestamp),
                "source_session_id": session_id,
                "report": simulation_report,
            }
            self._transition_visit(
                visit_row,
                "consultation_completed",
                current_node="diagnostic_wait",
                current_department="Auxiliary Diagnostic Center",
                active_agent_type=None,
                extra_data={
                    "internal_medicine_session_id": session_id,
                    "internal_medicine_round": consultation_round,
                    "diagnostic_session": diagnostic_session,
                    "test_required": True,
                    "test_category": assigned_category,
                    "test_category_label": assigned_zone_label,
                    "test_items": simulation_report.get("test_items", []),
                    "simulated_report": simulation_report,
                },
            )
            self.bus.publish(
                TEST_ZONE_ASSIGNED,
                {
                    "patient_id": patient_id,
                    "visit_id": visit_row["id"],
                    "session_id": session_id,
                    "test_category": assigned_category,
                    "window_label": simulation_report.get("window_label"),
                },
            )
            self.bus.publish(
                TEST_REPORT_GENERATED,
                {
                    "patient_id": patient_id,
                    "visit_id": visit_row["id"],
                    "session_id": session_id,
                    "test_category": assigned_category,
                    "report_summary": simulation_report.get("report_summary", {}),
                },
            )
            self._append_medical_record_entry(
                patient_id=patient_id,
                visit_id=visit_row["id"],
                phase="testing",
                entry_type="test_result_note",
                title="Auxiliary Test Report",
                content_text=(
                    f"category={assigned_category}; "
                    f"window={simulation_report.get('window_label')}; "
                    f"summary={simulation_report.get('report_summary')}"
                ),
                content={
                    "test_category": assigned_category,
                    "window_code": simulation_report.get("window_code"),
                    "window_label": simulation_report.get("window_label"),
                    "test_items": simulation_report.get("test_items", []),
                    "report_summary": simulation_report.get("report_summary", {}),
                    "generated_at": simulation_report.get("generated_at", timestamp),
                },
            )
            self.bus.publish(
                INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "visit_id": visit_row["id"],
                    "department": consultation_result.get("department"),
                    "priority": consultation_result.get("priority"),
                },
            )
        elif consultation_round == 2 and complete and not was_completed:
            visit_data = self._get_visit_data(visit_row)
            visit_data["internal_medicine_round2_session_id"] = session_id
            visit_data["internal_medicine_round2_summary"] = {
                "assistant_message": assistant_message,
                "department": consultation_result.get("department"),
                "priority": consultation_result.get("priority"),
                "diagnosis_level": consultation_result.get("diagnosis_level"),
                "updated_at": timestamp,
            }
            finalized_visit = self._transition_visit(
                visit_row,
                "finalize_diagnosis",
                current_node="diagnosis_finalized",
                current_department="Consultation",
                active_agent_type=self.config.agent_type,
                extra_data=visit_data,
            )
            self._transition_visit(
                finalized_visit,
                "request_medical_payment",
                current_node="payment_wait",
                current_department="Payment",
                active_agent_type=None,
                extra_data=self._get_visit_data(finalized_visit),
            )
            self._append_medical_record_entry(
                patient_id=patient_id,
                visit_id=visit_row["id"],
                phase="internal_medicine_round2",
                entry_type="second_consult_note",
                title="Second Consultation And Plan",
                content_text=(
                    f"department={consultation_result.get('department')}; "
                    f"priority={consultation_result.get('priority')}; "
                    f"diagnosis_level={consultation_result.get('diagnosis_level')}; "
                    "status=waiting_payment"
                ),
                content={
                    "department": consultation_result.get("department"),
                    "priority": consultation_result.get("priority"),
                    "diagnosis_level": consultation_result.get("diagnosis_level"),
                    "final_diagnosis": consultation_result.get("final_diagnosis"),
                    "plan": consultation_result.get("plan"),
                    "prescriptions": consultation_result.get("prescriptions", []),
                    "prescription_plan": consultation_result.get("prescription_plan", []),
                    "clinical_impression": consultation_result.get("clinical_impression"),
                    "final_assessment_summary": consultation_result.get("final_assessment_summary"),
                    "primary_disposition": consultation_result.get("primary_disposition"),
                    "medication_recommendation": consultation_result.get("medication_recommendation"),
                    "admission_recommendation": consultation_result.get("admission_recommendation"),
                    "procedure_recommendation": consultation_result.get("procedure_recommendation"),
                    "followup_recommendation": consultation_result.get("followup_recommendation"),
                    "return_precautions": consultation_result.get("return_precautions", []),
                    "patient_facing_plan": consultation_result.get("patient_facing_plan"),
                    "assistant_message": assistant_message,
                    "visit_state_after_consult": "waiting_payment",
                },
            )
            self.bus.publish(
                INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "visit_id": visit_row["id"],
                    "department": consultation_result.get("department"),
                    "priority": consultation_result.get("priority"),
                },
            )
        elif not complete:
            self._update_visit_agent_context(visit_row, session_id, active_agent_type=self.config.agent_type)

    def extend_dialogue_payload(self, private_memory: dict, progress) -> dict:
        return {"round": int(private_memory.get("consultation_round") or 1)}

    def _build_historical_records_template(self, *, patient_id: str, visit_id: str) -> dict:
        if not self.medical_record_repo or not visit_id:
            return {"current_visit": None, "previous_visits": [], "clinician_note": ""}

        def compact_timeline(timeline: dict | None) -> dict | None:
            if not timeline:
                return None
            summary = dict(timeline.get("summary") or {})
            entries = list(timeline.get("entries") or [])
            highlights = []
            for entry in entries[-4:]:
                highlights.append(
                    {
                        "phase": entry.get("phase"),
                        "entry_type": entry.get("entry_type"),
                        "title": entry.get("title"),
                        "content_text": entry.get("content_text"),
                        "created_at": entry.get("created_at"),
                    }
                )
            return {
                "summary": summary,
                "highlights": highlights,
            }

        current_timeline = compact_timeline(self.medical_record_repo.get_visit_timeline(visit_id))
        previous_visits: list[dict] = []
        for previous_visit_id in self.medical_record_repo.list_recent_visit_ids_by_patient(
            patient_id,
            exclude_visit_id=visit_id,
            limit=2,
        ):
            previous_timeline = compact_timeline(self.medical_record_repo.get_visit_timeline(previous_visit_id))
            if previous_timeline:
                previous_visits.append(previous_timeline)

        current_summary = (current_timeline or {}).get("summary") or {}
        previous_labels = []
        for timeline in previous_visits:
            summary = timeline.get("summary") or {}
            previous_labels.append(f"{summary.get('visit_id')}({summary.get('entry_count', 0)} entries)")
        clinician_note = (
            f"current_visit={current_summary.get('visit_id') or visit_id}, "
            f"current_entries={current_summary.get('entry_count', 0)}, "
            f"previous_visits={', '.join(previous_labels) if previous_labels else 'none'}"
        )
        return {
            "current_visit": current_timeline,
            "previous_visits": previous_visits,
            "clinician_note": clinician_note,
        }

    def _append_medical_record_entry(
        self,
        *,
        patient_id: str,
        visit_id: str | None,
        phase: str,
        entry_type: str,
        title: str,
        content_text: str,
        content: dict,
    ) -> None:
        if not self.medical_record_repo or not visit_id:
            return
        self.medical_record_repo.append_entry(
            patient_id=patient_id,
            visit_id=visit_id,
            phase=phase,
            entry_type=entry_type,
            actor="internal_medicine_agent",
            title=title,
            content_text=content_text,
            content=content,
        )

    def _update_visit_agent_context(self, visit_row: dict, session_id: str, active_agent_type: str | None) -> dict:
        data = self._get_visit_data(visit_row)
        visit_state = VisitLifecycleState(visit_row["state"])
        if visit_state == VisitLifecycleState.IN_SECOND_CONSULTATION:
            data["internal_medicine_round2_session_id"] = session_id
        else:
            data["internal_medicine_session_id"] = session_id
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            current_node="internal_medicine_consultation",
            current_department="Consultation",
            active_agent_type=active_agent_type,
            data=data,
        )
        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": updated["id"],
                "patient_id": updated["patient_id"],
                "state": updated["state"],
                "event": "agent_context_updated",
            },
        )
        return updated

    def _transition_visit(
        self,
        visit_row: dict,
        event: str,
        *,
        current_node: str | None = None,
        current_department: str | None = None,
        active_agent_type: str | None = None,
        extra_data: dict | None = None,
    ) -> dict:
        if self.encounter_orchestration_service is not None:
            transition = self.encounter_orchestration_service.transition(
                visit_row["id"],
                event,
                context={"source": "internal_medicine_service"},
            )
            next_state_value = transition.internal_to_state
            base_row = self.visit_repo.get(visit_row["id"]) or visit_row
        else:
            current_state = VisitLifecycleState(visit_row["state"])
            next_state = self.visit_state_machine.transition(current_state, event)
            next_state_value = next_state.value
            base_row = visit_row
        data = self._get_visit_data(base_row)
        if extra_data:
            protected_keys = {"orchestration_state", "orchestration_history", "orchestration_debug_log"}
            for key, value in extra_data.items():
                if key not in protected_keys:
                    data[key] = value
        refreshed = self.visit_repo.get(visit_row["id"]) or base_row
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            state=next_state_value,
            current_node=current_node if current_node is not None else refreshed.get("current_node"),
            current_department=current_department if current_department is not None else refreshed.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else refreshed.get("active_agent_type"),
            data=data,
        )
        if self.encounter_orchestration_service is None:
            self.bus.publish(
                VISIT_STATE_CHANGED,
                {
                    "visit_id": updated["id"],
                    "patient_id": updated["patient_id"],
                    "state": updated["state"],
                    "event": event,
                },
            )
        return updated

    @staticmethod
    def _get_visit_data(visit_row: dict) -> dict:
        data_json = visit_row.get("data_json")
        if not data_json:
            return {}
        try:
            return json.loads(data_json)
        except Exception:
            return {}
