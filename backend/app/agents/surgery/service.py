import json

from app.agents.department_runtime import DepartmentAgentRuntime
from app.events.types import VISIT_STATE_CHANGED


class SurgeryService(DepartmentAgentRuntime):
    def get_patient_view(self, patient_id: str):
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return None

        visit_id = patient.get("visit_id")
        visit_row = self.visit_repo.get(visit_id) if visit_id else self.visit_repo.get_active_by_patient(patient_id)
        visit_data = self._decode_visit_data(visit_row)

        session_id = visit_data.get("surgery_session_id")
        if not session_id:
            latest_row = self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], self.config.agent_type) if visit_row else None
            session_id = latest_row["id"] if latest_row else None
        if not session_id:
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
                "status": private_memory.get("dialogue_state", self.config.state_enum.IDLE.value),
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
            "surgery_session_id": session_id,
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

    def prepare_create_session(self, payload: dict, session_id: str, dialogue_state) -> None:
        patient_id = payload["patient_id"]
        visit_id = payload.get("visit_id")
        patient_row = self.patient_repo.get(patient_id)
        if not patient_row:
            raise ValueError("patient not found")
        visit_row = self.visit_repo.get(visit_id) if visit_id else None
        if not visit_row or visit_row.get("patient_id") != patient_id:
            raise ValueError("visit not found")
        if visit_row.get("state") != "in_consultation":
            raise ValueError("visit is not in consultation")
        if patient_row.get("lifecycle_state") != "in_consultation":
            raise ValueError("patient is not in consultation")

        payload["_consultation_round"] = 1
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
            raise ValueError("session is not a surgery session")
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

    def extend_dialogue_payload(self, private_memory: dict, progress) -> dict:
        return {"round": int(private_memory.get("consultation_round") or 1)}

    def after_persist_result(self, **kwargs) -> None:
        visit_row = kwargs["visit_row"]
        if not visit_row:
            return
        self._update_visit_agent_context(visit_row, kwargs["session_id"], active_agent_type=self.config.agent_type)

    def _update_visit_agent_context(self, visit_row: dict, session_id: str, active_agent_type: str | None) -> dict:
        data = self._get_visit_data(visit_row)
        data["surgery_session_id"] = session_id
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            current_node="surgery_consultation",
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

    @staticmethod
    def _get_visit_data(visit_row: dict) -> dict:
        data_json = visit_row.get("data_json")
        if not data_json:
            return {}
        try:
            return json.loads(data_json)
        except Exception:
            return {}
