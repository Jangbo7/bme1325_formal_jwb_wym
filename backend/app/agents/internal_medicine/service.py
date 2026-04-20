import json
from datetime import datetime, timezone
from urllib import request as urlrequest

from app.agents.internal_medicine.prompts import (
    build_consultation_system_prompt,
    build_consultation_user_prompt,
    build_final_message,
    build_follow_up_question,
    build_initial_message,
)
from app.agents.internal_medicine.rules import (
    build_missing_fields,
    derive_risk_flags,
    extract_structured_updates,
    merge_unique,
    merge_vitals,
    retrieve_relevant_internal_medicine_rules,
    rule_based_internal_medicine,
    split_symptoms,
    validate_internal_medicine_result,
)
from app.agents.internal_medicine.state import WorkingMemory
from app.agents.internal_medicine.workflow import ConsultationProgress
from app.events.types import INTERNAL_MEDICINE_CONSULTATION_COMPLETED, VISIT_STATE_CHANGED
from app.schemas.common import InternalMedicineDialogueState, PatientLifecycleState, VisitLifecycleState


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InternalMedicineService:
    def __init__(
        self,
        llm_settings: dict,
        patient_repo,
        session_repo,
        memory_repo,
        queue_repo,
        visit_repo,
        dialogue_state_machine,
        patient_state_machine,
        visit_state_machine,
        bus,
        graph,
    ):
        self.llm_settings = llm_settings
        self.patient_repo = patient_repo
        self.session_repo = session_repo
        self.memory_repo = memory_repo
        self.queue_repo = queue_repo
        self.visit_repo = visit_repo
        self.dialogue_state_machine = dialogue_state_machine
        self.patient_state_machine = patient_state_machine
        self.visit_state_machine = visit_state_machine
        self.bus = bus
        self.graph = graph

    def create_session(self, payload: dict):
        return self.graph.invoke({"mode": "create_session", "payload": payload})

    def continue_session(self, session_id: str, payload: dict):
        return self.graph.invoke({"mode": "continue_session", "payload": payload, "session_id": session_id})

    @staticmethod
    def _decode_visit_data(visit_row: dict | None) -> dict:
        if not visit_row:
            return {}
        payload = visit_row.get("data_json")
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            return {}

    def get_patient_view(self, patient_id: str):
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return None

        visit_id = patient.get("visit_id")
        visit_row = self.visit_repo.get(visit_id) if visit_id else self.visit_repo.get_active_by_patient(patient_id)
        visit_data = self._decode_visit_data(visit_row)

        session_id = visit_data.get("internal_medicine_session_id")
        if not session_id:
            latest_row = self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], "internal_medicine") if visit_row else None
            session_id = latest_row["id"] if latest_row else None
        if not session_id:
            patient_session = str(patient.get("session_id") or "")
            session_id = patient_session if patient_session.startswith("im-session-") else None

        private_memory = None
        dialogue = None
        evidence = []
        if session_id:
            private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="internal_medicine")
        if private_memory:
            dialogue = {
                "status": private_memory.get("dialogue_state", InternalMedicineDialogueState.IDLE.value),
                "assistant_message": private_memory.get("assistant_message", ""),
                "missing_fields": private_memory.get("missing_fields", []),
                "turns": self.session_repo.list_turns(session_id),
                "message_type": private_memory.get("message_type", "followup"),
            }
            evidence = private_memory.get("evidence", [])

        queue_ticket = self.queue_repo.get_active_ticket_for_patient(patient_id, visit_id=visit_row["id"] if visit_row else None)
        session_refs = {
            "triage_session_id": visit_data.get("triage_session_id"),
            "internal_medicine_session_id": session_id,
        }
        return self.patient_repo.to_view(
            patient,
            dialogue=dialogue,
            evidence=evidence,
            queue_ticket=queue_ticket,
            visit_row=visit_row,
            active_agent_type="internal_medicine",
            session_refs=session_refs,
            dialogue_source_agent="internal_medicine" if dialogue else None,
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
        if VisitLifecycleState(visit_row["state"]) != VisitLifecycleState.IN_CONSULTATION:
            raise ValueError("visit is not in consultation")
        if PatientLifecycleState(patient_row["lifecycle_state"]) != PatientLifecycleState.IN_CONSULTATION:
            raise ValueError("patient is not in consultation")
        self.session_repo.create_or_update(
            session_id,
            patient_id,
            dialogue_state.value,
            agent_type="internal_medicine",
            visit_id=visit_id,
        )
        self.patient_repo.update_patient(patient_id, session_id=session_id, visit_id=visit_id)
        self._update_visit_agent_context(visit_row, session_id, active_agent_type="internal_medicine")

    def validate_continue_session(self, session_id: str, payload: dict) -> dict:
        session_row = self.session_repo.get(session_id)
        if not session_row:
            raise ValueError("session not found")
        if session_row.get("agent_type") != "internal_medicine":
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

    def append_user_turn(self, session_id: str, patient_id: str, message: str, mode: str) -> None:
        if not message:
            return
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "user",
            message,
            now_iso(),
            metadata={"mode": mode, "agent_type": "internal_medicine"},
        )

    def prepare_context(self, payload: dict, session_id: str, dialogue_state: InternalMedicineDialogueState) -> WorkingMemory:
        patient_id = payload["patient_id"]
        patient_name = payload.get("name", patient_id)
        shared_memory = self.memory_repo.get_shared_memory(patient_id, patient_name)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="internal_medicine")
        turns = self.session_repo.list_turns(session_id)

        if payload.get("age") is not None:
            shared_memory["profile"]["age"] = payload["age"]
        if payload.get("sex"):
            shared_memory["profile"]["sex"] = payload["sex"]
        shared_memory["profile"]["name"] = patient_name
        shared_memory["profile"]["allergies"] = merge_unique(shared_memory["profile"].get("allergies"), payload.get("allergies") or [])
        if payload.get("allergies") is not None:
            shared_memory["profile"]["allergy_status"] = "known"
        shared_memory["profile"]["chronic_conditions"] = merge_unique(
            shared_memory["profile"].get("chronic_conditions"),
            payload.get("chronic_conditions") or [],
        )

        clinical = shared_memory["clinical_memory"]
        clinical["symptoms"] = merge_unique(clinical.get("symptoms"), split_symptoms(payload.get("symptoms", "")))
        clinical["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint") or payload.get("symptoms", "")
        clinical["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        clinical["vitals"] = merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

        private_memory.setdefault("message_type", "followup")
        private_memory.setdefault("missing_fields", [])
        private_memory.setdefault("assistant_message", "")
        private_memory.setdefault("evidence", [])
        private_memory.setdefault("latest_summary", {})
        private_memory.setdefault("consultation_progress", {})
        private_memory["dialogue_state"] = dialogue_state.value

        progress = ConsultationProgress.from_dict(private_memory.get("consultation_progress"))

        return WorkingMemory(
            short_term_turns=turns,
            shared_memory=shared_memory,
            private_memory=private_memory,
            consultation_progress=progress,
        )

    def apply_chat_updates(self, payload: dict, memory: WorkingMemory) -> None:
        message = (payload.get("message") or "").strip()
        if not message:
            return
        extracted = extract_structured_updates(message)
        clinical = memory.shared_memory["clinical_memory"]
        profile = memory.shared_memory["profile"]
        if extracted.get("chief_complaint") and not clinical.get("chief_complaint"):
            clinical["chief_complaint"] = extracted["chief_complaint"]
        if extracted.get("symptoms"):
            clinical["symptoms"] = merge_unique(clinical.get("symptoms"), extracted["symptoms"])
        if extracted.get("onset_time"):
            clinical["onset_time"] = extracted["onset_time"]
        if extracted.get("allergy_status") == "known":
            profile["allergy_status"] = "known"
            profile["allergies"] = extracted.get("allergies") or []
        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})
        memory.consultation_progress.patient_reply_count += 1

    def build_merged_payload(self, payload: dict, shared_memory: dict) -> dict:
        clinical = shared_memory["clinical_memory"]
        merged = dict(payload)
        merged["symptoms"] = payload.get("symptoms") or ", ".join(clinical.get("symptoms") or [])
        merged["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint")
        merged["vitals"] = merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        merged["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        merged["allergies"] = payload.get("allergies") or shared_memory["profile"].get("allergies") or []
        merged["visit_id"] = payload.get("visit_id")
        return merged

    def request_consultation_from_llm(self, payload: dict, shared_memory: dict, missing_fields: list[str]) -> dict | None:
        if not self.llm_settings.get("api_key"):
            return None
        req = urlrequest.Request(
            self.llm_settings["endpoint"],
            data=json.dumps(
                {
                    "model": self.llm_settings["model"],
                    "messages": [
                        {"role": "system", "content": [{"type": "text", "text": build_consultation_system_prompt()}]},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": build_consultation_user_prompt(shared_memory, payload.get("message", ""), missing_fields),
                                }
                            ],
                        },
                    ],
                    "temperature": 0,
                    "n": 1,
                    "stream": False,
                    "presence_penalty": 0,
                    "frequency_penalty": 0,
                }
            ).encode("utf-8"),
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.llm_settings['api_key']}",
            },
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = self.extract_text_from_response(data)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            return None

    def extract_text_from_response(self, data):
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, list):
            return " ".join([self.extract_text_from_response(item) for item in data if item]).strip()
        if not isinstance(data, dict):
            return ""
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                return " ".join(
                    [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
                ).strip()
        return ""

    def evaluate(self, merged_payload: dict, memory: WorkingMemory, mode: str) -> tuple[dict, list[dict], list[str], str, bool]:
        missing_fields = build_missing_fields(memory.shared_memory)
        rules = retrieve_relevant_internal_medicine_rules(merged_payload, top_k=3)
        evidence = [{"id": rule.get("id"), "title": rule.get("title"), "source": rule.get("source")} for rule in rules]
        fallback = rule_based_internal_medicine(merged_payload)
        progress = memory.consultation_progress

        if mode == "create_session":
            assistant_message = build_initial_message(memory.shared_memory, progress)
            return fallback, evidence, missing_fields, assistant_message, False

        llm_result = None
        if not missing_fields or progress.patient_reply_count >= 2:
            try:
                llm_result = self.request_consultation_from_llm(merged_payload, memory.shared_memory, missing_fields)
            except Exception:
                llm_result = None
            final_result = validate_internal_medicine_result(llm_result, fallback)
            assistant_message = (llm_result or {}).get("assistant_message") if isinstance(llm_result, dict) else None
            assistant_message = assistant_message or build_final_message(final_result)
            return final_result, evidence, [], assistant_message, True

        question_focus = missing_fields[0]
        progress.followup_count += 1
        progress.asked_fields_history.append(question_focus)
        assistant_message = build_follow_up_question(question_focus, memory.shared_memory)
        return fallback, evidence, missing_fields, assistant_message, False

    def persist_result(
        self,
        patient_id: str,
        session_id: str,
        payload: dict,
        memory: WorkingMemory,
        dialogue_state: InternalMedicineDialogueState,
        consultation_result: dict,
        evidence: list[dict],
        missing_fields: list[str],
        assistant_message: str,
        complete: bool,
    ):
        timestamp = now_iso()
        shared = memory.shared_memory
        private_memory = memory.private_memory
        progress = memory.consultation_progress
        progress.completed = complete

        shared["clinical_memory"]["last_department"] = consultation_result.get("department")
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["assistant_message"] = assistant_message
        private_memory["missing_fields"] = missing_fields
        private_memory["evidence"] = evidence
        private_memory["message_type"] = "final" if complete else "followup"
        private_memory["consultation_progress"] = progress.to_dict()
        private_memory["latest_summary"] = {
            "department": consultation_result.get("department"),
            "priority": consultation_result.get("priority"),
            "complete": complete,
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory, agent_type="internal_medicine")
        self.session_repo.update_state(session_id, dialogue_state.value)
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_message,
            timestamp,
            metadata={
                "agent_type": "internal_medicine",
                "message_type": "final" if complete else "followup",
                "department": consultation_result.get("department"),
                "priority": consultation_result.get("priority"),
                "diagnosis_level": consultation_result.get("diagnosis_level"),
            },
        )
        existing_patient = self.patient_repo.get(patient_id)
        self.patient_repo.update_patient(
            patient_id,
            session_id=session_id,
            visit_id=payload.get("visit_id"),
            priority=consultation_result.get("priority", existing_patient["priority"]),
        )

        visit_row = self.visit_repo.get(payload.get("visit_id")) if payload.get("visit_id") else None
        if visit_row:
            if complete:
                self._transition_visit(
                    visit_row,
                    "consultation_completed",
                    current_node="payment_wait",
                    current_department="Payment",
                    active_agent_type=None,
                    extra_data={"internal_medicine_session_id": session_id},
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
            else:
                self._update_visit_agent_context(visit_row, session_id, active_agent_type="internal_medicine")

    def build_response(self, patient_id: str, session_id: str):
        patient_view = self.get_patient_view(patient_id)
        session_row = self.session_repo.get(session_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="internal_medicine")
        dialogue = {
            "status": private_memory.get("dialogue_state", InternalMedicineDialogueState.IDLE.value),
            "assistant_message": private_memory.get("assistant_message", ""),
            "missing_fields": private_memory.get("missing_fields", []),
            "turns": self.session_repo.list_turns(session_id),
            "message_type": private_memory.get("message_type", "followup"),
        }
        return {
            "ok": True,
            "session_id": session_id,
            "visit_id": session_row.get("visit_id") if session_row else None,
            "visit_state": patient_view.visit_state.value if patient_view and patient_view.visit_state else None,
            "patient": patient_view.model_dump() if patient_view else None,
            "dialogue": dialogue,
        }

    def _update_visit_agent_context(self, visit_row: dict, session_id: str, active_agent_type: str | None) -> dict:
        data = self._get_visit_data(visit_row)
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
        current_state = VisitLifecycleState(visit_row["state"])
        next_state = self.visit_state_machine.transition(current_state, event)
        data = self._get_visit_data(visit_row)
        if extra_data:
            data.update(extra_data)
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            state=next_state.value,
            current_node=current_node if current_node is not None else visit_row.get("current_node"),
            current_department=current_department if current_department is not None else visit_row.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            data=data,
        )
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
