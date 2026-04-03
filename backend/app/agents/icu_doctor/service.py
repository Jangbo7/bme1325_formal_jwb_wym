import json
from datetime import datetime, timezone
from urllib import request as urlrequest

from app.agents.icu_doctor.prompts import (
    build_consultation_prompt,
    build_follow_up_message,
    build_initial_prompt,
    build_treatment_plan_prompt,
)
from app.agents.icu_doctor.rules import (
    build_missing_fields,
    derive_risk_flags,
    merge_unique,
    merge_vitals,
    retrieve_relevant_icu_rules,
    rule_based_icu_triage,
    split_symptoms,
    validate_icu_triage_result,
)
from app.agents.icu_doctor.state import WorkingMemory
from app.events.types import ICU_CONSULTATION_COMPLETED, PATIENT_STATE_CHANGED


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ICUDoctorService:
    def __init__(
        self,
        llm_settings: dict,
        patient_repo,
        session_repo,
        memory_repo,
        queue_repo,
        dialogue_state_machine,
        patient_state_machine,
        bus,
        graph,
    ):
        self.llm_settings = llm_settings
        self.patient_repo = patient_repo
        self.session_repo = session_repo
        self.memory_repo = memory_repo
        self.queue_repo = queue_repo
        self.dialogue_state_machine = dialogue_state_machine
        self.patient_state_machine = patient_state_machine
        self.bus = bus
        self.graph = graph

    def get_patient_view(self, patient_id: str):
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return None
        session_id = patient.get("session_id")
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id) if session_id else None
        dialogue = None
        evidence = []
        if private_memory:
            dialogue = {
                "status": private_memory.get("dialogue_state", "idle"),
                "assistant_message": private_memory.get("assistant_message", ""),
                "missing_fields": private_memory.get("missing_fields", []),
                "turns": self.session_repo.list_turns(session_id),
            }
            evidence = private_memory.get("evidence", [])
        queue_ticket = self.queue_repo.get_active_ticket_for_patient(patient_id)
        patient_view = dict(patient)
        patient_view["dialogue"] = dialogue
        patient_view["evidence"] = evidence
        patient_view["queue_ticket"] = queue_ticket
        return patient_view

    def list_patient_views(self):
        return [self.get_patient_view(row["id"]) for row in self.patient_repo.list()]

    def create_session(self, payload: dict):
        return self.graph.invoke({"mode": "create_session", "payload": payload})

    def continue_session(self, session_id: str, payload: dict):
        return self.graph.invoke({"mode": "continue_session", "payload": payload, "session_id": session_id})

    def prepare_context(self, payload: dict, session_id: str, dialogue_state) -> WorkingMemory:
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
        shared_memory["profile"]["allergies"] = merge_unique(
            shared_memory["profile"].get("allergies"), payload.get("allergies") or []
        )
        if payload.get("allergies") is not None:
            shared_memory["profile"]["allergy_status"] = "known"
        shared_memory["profile"]["chronic_conditions"] = merge_unique(
            shared_memory["profile"].get("chronic_conditions"),
            payload.get("chronic_conditions") or [],
        )

        clinical = shared_memory["clinical_memory"]
        clinical["symptoms"] = merge_unique(clinical.get("symptoms"), split_symptoms(payload.get("symptoms", "")))
        clinical["chief_complaint"] = (
            payload.get("chief_complaint") or clinical.get("chief_complaint") or payload.get("symptoms", "")
        )
        clinical["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        clinical["vitals"] = merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

        if payload.get("registration_info"):
            clinical["registration_info"] = payload["registration_info"]

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

    def apply_chat_updates(self, payload: dict, memory: WorkingMemory) -> None:
        message = (payload.get("message") or "").strip()
        if not message:
            return

        symptoms_lower = message.lower()
        if any(term in symptoms_lower for term in ["chest", "heart", "cardiac", "胸痛", "心"]):
            clinical = memory.shared_memory["clinical_memory"]
            if "chest pain" not in clinical.get("symptoms", []) and "胸痛" not in clinical.get("symptoms", []):
                clinical["symptoms"] = merge_unique(clinical.get("symptoms"), ["chest pain"])
        if any(term in symptoms_lower for term in ["breath", "dyspnea", "respiratory", "呼吸困难"]):
            clinical = memory.shared_memory["clinical_memory"]
            if "shortness of breath" not in clinical.get("symptoms", []) and "呼吸困难" not in clinical.get("symptoms", []):
                clinical["symptoms"] = merge_unique(clinical.get("symptoms"), ["shortness of breath"])
        if any(term in symptoms_lower for term in ["fever", "temperature", "发热", "高烧"]):
            clinical = memory.shared_memory["clinical_memory"]
            if "fever" not in clinical.get("symptoms", []):
                clinical["symptoms"] = merge_unique(clinical.get("symptoms"), ["fever"])
        if any(term in symptoms_lower for term in ["coma", "unconscious", "昏迷", "意识"]):
            clinical = memory.shared_memory["clinical_memory"]
            if "unconscious" not in clinical.get("symptoms", []) and "昏迷" not in clinical.get("symptoms", []):
                clinical["symptoms"] = merge_unique(clinical.get("symptoms"), ["unconscious"])

        clinical = memory.shared_memory["clinical_memory"]
        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

    def build_merged_payload(self, payload: dict, shared_memory: dict) -> dict:
        clinical = shared_memory["clinical_memory"]
        merged = dict(payload)
        merged["symptoms"] = payload.get("symptoms") or ", ".join(clinical.get("symptoms") or [])
        merged["vitals"] = merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        merged["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        merged["allergies"] = payload.get("allergies") or shared_memory["profile"].get("allergies") or []
        merged["chronic_conditions"] = (
            payload.get("chronic_conditions") or shared_memory["profile"].get("chronic_conditions") or []
        )
        merged["registration_info"] = payload.get("registration_info") or clinical.get("registration_info", {})
        return merged

    def request_icu_consultation_from_llm(
        self, payload: dict, evidence_rules: list[dict], memory_context: WorkingMemory
    ):
        if not self.llm_settings.get("api_key"):
            return None

        conversation_history = [
            {"role": turn.get("role", "user"), "content": turn.get("message", "")}
            for turn in memory_context.short_term_turns[-5:]
        ]

        if conversation_history:
            prompt = build_consultation_prompt(payload, conversation_history, evidence_rules)
        else:
            prompt = build_initial_prompt(3, payload)

        req = urlrequest.Request(
            self.llm_settings["endpoint"],
            data=json.dumps(
                {
                    "model": self.llm_settings["model"],
                    "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
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

    def evaluate(self, merged_payload: dict, memory: WorkingMemory) -> tuple[dict, list[dict], list[str], str]:
        retrieved_rules = retrieve_relevant_icu_rules(merged_payload, top_k=3)
        fallback = rule_based_icu_triage(merged_payload)
        try:
            llm_result = self.request_icu_consultation_from_llm(merged_payload, retrieved_rules, memory)
        except Exception:
            llm_result = None
        final_result = validate_icu_triage_result(llm_result, fallback)
        evidence = [{"id": rule.get("id"), "title": rule.get("title"), "source": rule.get("source")} for rule in retrieved_rules]
        missing_fields = build_missing_fields(memory.shared_memory)
        assistant_message = build_follow_up_message(missing_fields, final_result)
        return final_result, evidence, missing_fields, assistant_message

    def persist_result(
        self,
        patient_id: str,
        session_id: str,
        payload: dict,
        memory: WorkingMemory,
        dialogue_state,
        triage_result: dict,
        evidence: list[dict],
        missing_fields: list[str],
        assistant_message: str,
    ):
        timestamp = now_iso()
        shared = memory.shared_memory
        private_memory = memory.private_memory

        shared["clinical_memory"]["last_triage_level"] = triage_result.get("triage_level")
        shared["clinical_memory"]["last_urgency"] = triage_result.get("urgency")
        shared["clinical_memory"]["treatment_plan"] = triage_result.get("treatment_plan")
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["assistant_message"] = assistant_message
        private_memory["missing_fields"] = missing_fields
        private_memory["expected_field"] = missing_fields[0] if missing_fields else None
        private_memory["evidence"] = evidence
        private_memory["latest_summary"] = {
            "chief_complaint": shared["clinical_memory"].get("chief_complaint"),
            "risk_flags": shared["clinical_memory"].get("risk_flags"),
            "urgency": triage_result.get("urgency"),
            "treatment_plan": triage_result.get("treatment_plan"),
            "missing_fields": missing_fields,
            "expected_field": missing_fields[0] if missing_fields else None,
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory)
        self.memory_repo.append_icu_consultation_history(
            patient_id,
            session_id,
            {
                "time": timestamp,
                "triage_level": triage_result.get("triage_level"),
                "urgency": triage_result.get("urgency"),
                "treatment_plan": triage_result.get("treatment_plan"),
                "note": triage_result.get("note"),
                "evidence_ids": [item.get("id") for item in evidence],
            },
            timestamp,
        )
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_message or triage_result.get("note", ""),
            timestamp,
            metadata={
                "triage_level": triage_result.get("triage_level"),
                "urgency": triage_result.get("urgency"),
                "treatment_plan": triage_result.get("treatment_plan"),
            },
        )

        lifecycle_event = "icu_consultation_completed" if not missing_fields else "icu_followup_requested"
        patient_row = self.patient_repo.get(patient_id)
        current_state = self.patient_state_machine.transition(
            patient_row["lifecycle_state"] if patient_row else "untriaged", lifecycle_event
        )
        self.patient_repo.update_patient(
            patient_id,
            name=payload.get("name", patient_row["name"] if patient_row else patient_id),
            lifecycle_state=current_state.value if hasattr(current_state, 'value') else current_state,
            priority=self._urgency_to_priority(triage_result.get("urgency", "M")),
            location="ICU",
            triage_level=triage_result.get("triage_level"),
            triage_note=triage_result.get("note", ""),
            session_id=session_id,
        )
        self.session_repo.update_state(session_id, dialogue_state.value)
        self.bus.publish(
            PATIENT_STATE_CHANGED,
            {
                "patient_id": patient_id,
                "lifecycle_state": current_state.value if hasattr(current_state, 'value') else current_state,
            },
        )
        if not missing_fields:
            self.bus.publish(
                ICU_CONSULTATION_COMPLETED,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "urgency": triage_result.get("urgency"),
                    "treatment_plan": triage_result.get("treatment_plan"),
                },
            )

    def _urgency_to_priority(self, urgency: str) -> str:
        mapping = {
            "CRITICAL": "H",
            "EMERGENT": "H",
            "URGENT": "M",
            "LESS_URGENT": "M",
            "NON_URGENT": "L",
        }
        return mapping.get(urgency, "M")

    def build_response(self, patient_id: str, session_id: str):
        patient_view = self.get_patient_view(patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id)
        dialogue = {
            "status": private_memory.get("dialogue_state", "idle"),
            "assistant_message": private_memory.get("assistant_message", ""),
            "missing_fields": private_memory.get("missing_fields", []),
            "turns": self.session_repo.list_turns(session_id),
        }
        return {
            "ok": True,
            "session_id": session_id,
            "patient": patient_view,
            "dialogue": dialogue,
        }
