import json
from datetime import datetime, timezone
from urllib import request as urlrequest

from app.agents.triage.prompts import (
    build_fallback_follow_up_message,
    build_final_message,
    build_follow_up_system_prompt,
    build_follow_up_user_prompt,
)
from app.agents.triage.rules import (
    derive_risk_flags,
    extract_structured_updates,
    merge_unique,
    merge_vitals,
    prioritize_missing_fields,
    retrieve_relevant_rules,
    rule_based_triage,
    split_symptoms,
    validate_triage_result,
)
from app.agents.triage.schemas import WorkingMemory
from app.domain.patient.state_machine import PatientStateMachine
from app.events.types import PATIENT_STATE_CHANGED, TRIAGE_COMPLETED, VISIT_STATE_CHANGED
from app.schemas.common import PatientLifecycleState, TriageDialogueState, VisitLifecycleState


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TriageService:
    def __init__(
        self,
        llm_settings: dict,
        patient_repo,
        session_repo,
        memory_repo,
        queue_repo,
        visit_repo,
        dialogue_state_machine,
        patient_state_machine: PatientStateMachine,
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

    def ensure_visit_for_payload(self, payload: dict) -> dict:
        patient_id = payload["patient_id"]
        requested_visit_id = payload.get("visit_id")

        visit_row = None
        if requested_visit_id:
            candidate = self.visit_repo.get(requested_visit_id)
            if candidate and candidate.get("patient_id") == patient_id:
                visit_row = candidate

        if not visit_row:
            visit_row = self.visit_repo.create_or_get_active(patient_id)

        payload["visit_id"] = visit_row["id"]
        self.patient_repo.update_patient(patient_id, visit_id=visit_row["id"])
        return visit_row

    def transition_visit_state(
        self,
        visit_id: str | None,
        event: str,
        *,
        current_node: str | None = None,
        current_department: str | None = None,
        active_agent_type: str | None = None,
    ) -> dict | None:
        if not visit_id:
            return None
        visit_row = self.visit_repo.get(visit_id)
        if not visit_row:
            return None

        current_state = VisitLifecycleState(visit_row["state"])
        next_state = self.visit_state_machine.transition(current_state, event)

        updated = self.visit_repo.update_visit(
            visit_id,
            state=next_state.value,
            current_node=current_node if current_node is not None else visit_row.get("current_node"),
            current_department=current_department if current_department is not None else visit_row.get("current_department"),
            active_agent_type=active_agent_type,
            data=visit_row.get("data_json") and json.loads(visit_row["data_json"]) or {},
        )
        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": visit_id,
                "patient_id": visit_row["patient_id"],
                "state": next_state.value,
                "event": event,
            },
        )
        return updated

    def get_patient_view(self, patient_id: str):
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return None

        session_id = patient.get("session_id")
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id) if session_id else None
        dialogue = None
        evidence = []
        if private_memory and session_id:
            dialogue = {
                "status": private_memory.get("dialogue_state", TriageDialogueState.IDLE.value),
                "assistant_message": private_memory.get("assistant_message", ""),
                "missing_fields": private_memory.get("missing_fields", []),
                "turns": self.session_repo.list_turns(session_id),
                "question_focus": private_memory.get("last_question_focus"),
                "message_type": private_memory.get("message_type", "followup"),
                "recommendation_changed": private_memory.get("recommendation_changed", False),
                "asked_fields_history": private_memory.get("asked_fields_history", []),
            }
            evidence = private_memory.get("evidence", [])

        visit_id = patient.get("visit_id")
        visit_row = self.visit_repo.get(visit_id) if visit_id else self.visit_repo.get_active_by_patient(patient_id)
        if visit_row and patient.get("visit_id") != visit_row["id"]:
            self.patient_repo.update_patient(patient_id, visit_id=visit_row["id"])
            patient = self.patient_repo.get(patient_id)

        queue_ticket = self.queue_repo.get_active_ticket_for_patient(
            patient_id,
            visit_id=visit_row["id"] if visit_row else None,
        )
        return self.patient_repo.to_view(patient, dialogue=dialogue, evidence=evidence, queue_ticket=queue_ticket, visit_row=visit_row)

    def list_patient_views(self):
        return [self.get_patient_view(row["id"]) for row in self.patient_repo.list()]

    def create_session(self, payload: dict):
        return self.graph.invoke({"mode": "create_session", "payload": payload})

    def continue_session(self, session_id: str, payload: dict):
        session_row = self.session_repo.get(session_id)
        if session_row and session_row.get("dialogue_state") == TriageDialogueState.TRIAGED.value:
            patient_id = payload.get("patient_id") or session_row["patient_id"]
            return self.build_response(patient_id, session_id)
        return self.graph.invoke({"mode": "continue_session", "payload": payload, "session_id": session_id})

    def prepare_context(self, payload: dict, session_id: str, dialogue_state: TriageDialogueState) -> WorkingMemory:
        patient_id = payload["patient_id"]
        patient_name = payload.get("name", patient_id)
        shared_memory = self.memory_repo.get_shared_memory(patient_id, patient_name)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id)
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

        private_memory.setdefault("asked_fields_history", [])
        private_memory.setdefault("last_question_focus", None)
        private_memory.setdefault("last_question_text", "")
        private_memory.setdefault("last_question_style", None)
        private_memory.setdefault("recommendation_snapshot", None)
        private_memory.setdefault("recommendation_changed", False)
        private_memory.setdefault("message_type", "followup")
        private_memory.setdefault("latest_extraction", {})
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["latest_summary"] = {
            "chief_complaint": clinical.get("chief_complaint"),
            "risk_flags": clinical.get("risk_flags"),
        }
        return WorkingMemory(
            short_term_turns=turns,
            shared_memory=shared_memory,
            private_memory=private_memory,
        )

    def apply_chat_updates(self, payload: dict, memory: WorkingMemory) -> dict:
        message = (payload.get("message") or "").strip()
        expected_fields = memory.private_memory.get("missing_fields") or []
        extracted = extract_structured_updates(message, target_fields=expected_fields)
        clinical = memory.shared_memory["clinical_memory"]
        profile = memory.shared_memory["profile"]
        if extracted["symptoms"]:
            clinical["symptoms"] = merge_unique(clinical.get("symptoms"), extracted["symptoms"])
            if not clinical.get("chief_complaint"):
                clinical["chief_complaint"] = extracted["symptoms"][0]
        if extracted["onset_time"]:
            clinical["onset_time"] = extracted["onset_time"]
        if extracted["pain_score"] is not None:
            clinical["vitals"] = merge_vitals(clinical.get("vitals") or {}, {"pain_score": extracted["pain_score"]})
        if extracted["temp_c"] is not None:
            clinical["vitals"] = merge_vitals(clinical.get("vitals") or {}, {"temp_c": extracted["temp_c"]})
        if extracted["allergies"] is not None:
            profile["allergies"] = extracted["allergies"]
        if extracted.get("allergy_status") == "known":
            profile["allergy_status"] = "known"
        elif extracted.get("allergy_status") == "uncertain" and profile.get("allergy_status") != "known":
            profile["allergy_status"] = "uncertain"
        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})
        memory.private_memory["latest_extraction"] = {
            "extracted_fields": extracted.get("extracted_fields", []),
            "confidence_by_field": extracted.get("confidence_by_field", {}),
            "unresolved_targets": extracted.get("unresolved_targets", []),
        }
        return extracted

    def build_merged_payload(self, payload: dict, shared_memory: dict) -> dict:
        clinical = shared_memory["clinical_memory"]
        merged = dict(payload)
        merged["symptoms"] = payload.get("symptoms") or ", ".join(clinical.get("symptoms") or [])
        merged["vitals"] = merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        merged["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        merged["allergies"] = payload.get("allergies") or shared_memory["profile"].get("allergies") or []
        merged["chronic_conditions"] = payload.get("chronic_conditions") or shared_memory["profile"].get("chronic_conditions") or []
        merged["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint")
        return merged

    def request_llm_json(self, messages: list[dict]):
        if not self.llm_settings["api_key"]:
            return None
        req = urlrequest.Request(
            self.llm_settings["endpoint"],
            data=json.dumps(
                {
                    "model": self.llm_settings["model"],
                    "messages": messages,
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
            raise

    def request_triage_from_llm(self, payload: dict, evidence_rules: list[dict], memory_context: WorkingMemory):
        prompt = (
            "You are a hospital triage nurse assistant. "
            "Use the retrieved triage knowledge as supporting evidence, and consider both short-term conversation memory and long-term patient memory. "
            "Return strict JSON only with keys: triage_level (integer 1-5), priority (H/M/L), department (string), note (string). "
            "Patient data: "
            + json.dumps(payload, ensure_ascii=False)
            + " Short-term memory: "
            + json.dumps({"turns": memory_context.short_term_turns}, ensure_ascii=False)
            + " Long-term memory: "
            + json.dumps(memory_context.shared_memory, ensure_ascii=False)
            + " Agent-private memory: "
            + json.dumps(memory_context.private_memory, ensure_ascii=False)
            + " Retrieved rules: "
            + json.dumps(evidence_rules, ensure_ascii=False)
        )
        return self.request_llm_json([{"role": "user", "content": [{"type": "text", "text": prompt}]}])

    def request_followup_from_llm(
        self,
        *,
        triage_result: dict,
        missing_fields: list[str],
        memory: WorkingMemory,
        recommendation_changed: bool,
    ) -> dict | None:
        if not missing_fields:
            return None
        prompt_messages = [
            {"role": "system", "content": [{"type": "text", "text": build_follow_up_system_prompt()}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": build_follow_up_user_prompt(
                            triage_result=triage_result,
                            missing_fields=missing_fields,
                            patient_summary=memory.shared_memory,
                            turns=memory.short_term_turns,
                            risk_flags=memory.shared_memory["clinical_memory"].get("risk_flags") or [],
                            last_question_focus=memory.private_memory.get("last_question_focus"),
                            last_question_text=memory.private_memory.get("last_question_text"),
                            asked_fields_history=memory.private_memory.get("asked_fields_history") or [],
                            recommendation_changed=recommendation_changed,
                        ),
                    }
                ],
            },
        ]
        result = self.request_llm_json(prompt_messages)
        if not isinstance(result, dict):
            return None
        question_focus = result.get("question_focus")
        if question_focus not in missing_fields:
            return None
        assistant_message = (result.get("assistant_message") or "").strip()
        if not assistant_message:
            return None
        style_tag = result.get("style_tag") or "followup"
        if style_tag not in {"followup", "final_recommendation"}:
            return None
        if assistant_message.count("\n") > 1 or len(assistant_message) > 90:
            return None
        lowered = assistant_message.lower()
        if not recommendation_changed:
            repeated_tokens = [
                (triage_result.get("department") or "").lower(),
                f"priority {str(triage_result.get('priority') or '').lower()}",
                "recommendation",
                "department",
                "\u5efa\u8bae",
                "\u6025\u8bca",
                "\u6025\u8a3a",
                "\u79d1\u5ba4",
                "\u8bc4\u4f30",
            ]
            if any(token and token in lowered for token in repeated_tokens):
                return None
        last_question_text = (memory.private_memory.get("last_question_text") or "").strip()
        if last_question_text and assistant_message == last_question_text:
            return None
        message_type = "final" if style_tag == "final_recommendation" else "followup"
        return {
            "assistant_message": assistant_message,
            "question_focus": question_focus,
            "mention_recommendation": bool(result.get("mention_recommendation", False) and recommendation_changed),
            "style_tag": style_tag,
            "message_type": message_type,
        }

    @staticmethod
    def extract_text_from_response(data):
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, list):
            return " ".join([TriageService.extract_text_from_response(item) for item in data if item]).strip()
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

    @staticmethod
    def recommendation_snapshot(triage_result: dict) -> dict:
        return {
            "department": triage_result.get("department"),
            "priority": triage_result.get("priority"),
            "triage_level": triage_result.get("triage_level"),
        }

    def generate_dialogue_payload(self, triage_result: dict, missing_fields: list[str], memory: WorkingMemory) -> dict:
        previous_snapshot = memory.private_memory.get("recommendation_snapshot")
        current_snapshot = self.recommendation_snapshot(triage_result)
        recommendation_changed = previous_snapshot != current_snapshot
        risk_flags = memory.shared_memory["clinical_memory"].get("risk_flags") or []

        if not missing_fields:
            return {
                "assistant_message": build_final_message(triage_result),
                "question_focus": None,
                "mention_recommendation": True,
                "style_tag": "final_recommendation",
                "message_type": "final",
                "recommendation_changed": recommendation_changed,
            }

        llm_followup = None
        try:
            llm_followup = self.request_followup_from_llm(
                triage_result=triage_result,
                missing_fields=missing_fields,
                memory=memory,
                recommendation_changed=recommendation_changed,
            )
        except Exception:
            llm_followup = None

        payload = llm_followup or build_fallback_follow_up_message(
            missing_fields=missing_fields,
            triage_result=triage_result,
            risk_flags=risk_flags,
            last_question_focus=memory.private_memory.get("last_question_focus"),
            asked_fields_history=memory.private_memory.get("asked_fields_history") or [],
            recommendation_changed=recommendation_changed,
        )
        payload["recommendation_changed"] = recommendation_changed
        return payload

    def evaluate(self, merged_payload: dict, memory: WorkingMemory) -> tuple[dict, list[dict], list[str], dict]:
        retrieved_rules = retrieve_relevant_rules(merged_payload, top_k=3)
        fallback = rule_based_triage(merged_payload)
        try:
            llm_result = self.request_triage_from_llm(merged_payload, retrieved_rules, memory)
        except Exception:
            llm_result = None
        final_result = validate_triage_result(llm_result, fallback)
        evidence = [{"id": rule.get("id"), "title": rule.get("title"), "source": rule.get("source")} for rule in retrieved_rules]
        missing_fields = prioritize_missing_fields(memory.shared_memory, memory.private_memory)
        assistant_payload = self.generate_dialogue_payload(final_result, missing_fields, memory)
        return final_result, evidence, missing_fields, assistant_payload

    def persist_result(
        self,
        patient_id: str,
        session_id: str,
        payload: dict,
        memory: WorkingMemory,
        dialogue_state: TriageDialogueState,
        triage_result: dict,
        evidence: list[dict],
        missing_fields: list[str],
        assistant_payload: dict,
    ):
        timestamp = now_iso()
        shared = memory.shared_memory
        private_memory = memory.private_memory
        shared["clinical_memory"]["last_department"] = triage_result.get("department")
        shared["clinical_memory"]["last_triage_level"] = triage_result.get("triage_level")
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["assistant_message"] = assistant_payload.get("assistant_message", "")
        private_memory["missing_fields"] = missing_fields
        private_memory["expected_field"] = missing_fields[0] if missing_fields else None
        private_memory["evidence"] = evidence
        private_memory["message_type"] = assistant_payload.get("message_type", "followup")
        private_memory["recommendation_changed"] = assistant_payload.get("recommendation_changed", False)
        private_memory["last_question_focus"] = assistant_payload.get("question_focus")
        private_memory["last_question_text"] = assistant_payload.get("assistant_message", "")
        private_memory["last_question_style"] = assistant_payload.get("style_tag")
        if assistant_payload.get("question_focus"):
            private_memory["asked_fields_history"] = (private_memory.get("asked_fields_history") or []) + [assistant_payload.get("question_focus")]
        private_memory["recommendation_snapshot"] = self.recommendation_snapshot(triage_result)
        private_memory["latest_summary"] = {
            "chief_complaint": shared["clinical_memory"].get("chief_complaint"),
            "risk_flags": shared["clinical_memory"].get("risk_flags"),
            "missing_fields": missing_fields,
            "expected_field": missing_fields[0] if missing_fields else None,
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory)
        self.memory_repo.append_triage_history(
            patient_id,
            session_id,
            {
                "time": timestamp,
                "triage_level": triage_result.get("triage_level"),
                "priority": triage_result.get("priority"),
                "department": triage_result.get("department"),
                "note": triage_result.get("note"),
                "evidence_ids": [item.get("id") for item in evidence],
            },
            timestamp,
        )
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_payload.get("assistant_message") or triage_result.get("note", ""),
            timestamp,
            metadata={
                "triage_level": triage_result.get("triage_level"),
                "department": triage_result.get("department"),
                "priority": triage_result.get("priority"),
                "question_focus": assistant_payload.get("question_focus"),
                "message_type": assistant_payload.get("message_type", "followup"),
                "recommendation_changed": assistant_payload.get("recommendation_changed", False),
                "mention_recommendation": assistant_payload.get("mention_recommendation", False),
                "style_tag": assistant_payload.get("style_tag", "followup"),
            },
        )
        lifecycle_event = "followup_requested" if missing_fields else "triage_completed"
        patient_row = self.patient_repo.get(patient_id)
        current_state = PatientLifecycleState(patient_row["lifecycle_state"])
        next_state = self.patient_state_machine.transition(current_state, lifecycle_event)

        visit_id = payload.get("visit_id") or patient_row.get("visit_id")
        self.patient_repo.update_patient(
            patient_id,
            name=payload.get("name", patient_row["name"]),
            lifecycle_state=next_state.value,
            priority=triage_result.get("priority", "M"),
            location=triage_result.get("department", patient_row["location"]),
            triage_level=triage_result.get("triage_level"),
            triage_note=triage_result.get("note", ""),
            session_id=session_id,
            visit_id=visit_id,
        )
        self.session_repo.update_state(session_id, dialogue_state.value)

        visit_event = "followup_requested" if missing_fields else "triage_completed"
        visit_state_row = self.transition_visit_state(
            visit_id,
            visit_event,
            current_node="triage" if missing_fields else "triage_done",
            current_department=triage_result.get("department"),
            active_agent_type="triage" if missing_fields else None,
        )
        if visit_state_row:
            self.patient_repo.update_patient(patient_id, visit_id=visit_state_row["id"])

        self.bus.publish(
            PATIENT_STATE_CHANGED,
            {
                "patient_id": patient_id,
                "lifecycle_state": next_state.value,
            },
        )
        if not missing_fields:
            self.bus.publish(
                TRIAGE_COMPLETED,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "visit_id": visit_id,
                    "department": triage_result.get("department"),
                    "priority": triage_result.get("priority"),
                },
            )

    def build_response(self, patient_id: str, session_id: str):
        patient_view = self.get_patient_view(patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id)
        dialogue = {
            "status": private_memory.get("dialogue_state", TriageDialogueState.IDLE.value),
            "assistant_message": private_memory.get("assistant_message", ""),
            "missing_fields": private_memory.get("missing_fields", []),
            "turns": self.session_repo.list_turns(session_id),
            "question_focus": private_memory.get("last_question_focus"),
            "message_type": private_memory.get("message_type", "followup"),
            "recommendation_changed": private_memory.get("recommendation_changed", False),
            "asked_fields_history": private_memory.get("asked_fields_history", []),
        }
        return {
            "ok": True,
            "session_id": session_id,
            "visit_id": patient_view.visit_id if patient_view else None,
            "visit_state": patient_view.visit_state.value if patient_view and patient_view.visit_state else None,
            "patient": patient_view.model_dump() if patient_view else None,
            "dialogue": dialogue,
        }

