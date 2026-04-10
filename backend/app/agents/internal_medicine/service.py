import json
from datetime import datetime, timezone
from urllib import request as urlrequest

from app.agents.internal_medicine.prompts import (
    build_consultation_prompt,
    build_diagnosis_prompt,
    build_follow_up_message,
    build_initial_prompt,
    build_progress_follow_up,
    build_step_aware_prompt,
    build_treatment_plan_prompt,
)
from app.agents.internal_medicine.rules import (
    build_missing_fields,
    derive_risk_flags,
    merge_unique,
    merge_vitals,
    retrieve_relevant_internal_medicine_rules,
    rule_based_internal_medicine,
    split_symptoms,
    validate_internal_medicine_result,
)
from app.agents.internal_medicine.state import WorkingMemory
from app.agents.internal_medicine.workflow import (
    ConsultationProgress,
    ConsultationStep,
)
from app.events.types import INTERNAL_MEDICINE_CONSULTATION_COMPLETED, PATIENT_STATE_CHANGED


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

    def _determine_severity_level(self, payload: dict, clinical: dict) -> int:
        symptoms_text = " ".join(clinical.get("symptoms", [])).lower()
        chief_complaint = (clinical.get("chief_complaint") or "").lower()
        text = symptoms_text + " " + chief_complaint

        MODERATE_KEYWORDS = [
            "fracture", "broken", "骨折",
            "hand foot mouth", "手足口",
            "infection", "感染", "发热", "高烧",
            "pneumonia", "肺炎",
            "appendicitis", "阑尾炎",
            "gallbladder", "胆囊",
            "kidney stone", "肾结石",
            "stroke", "中风",
            "heart attack", "心脏病",
            "severe", "严重",
            "blood", "血", "bleeding",
            "x-ray", "xray", "拍片",
            "test", "检验", "检查",
        ]

        for keyword in MODERATE_KEYWORDS:
            if keyword.lower() in text:
                return 2

        risk_flags = clinical.get("risk_flags", [])
        if any(flag in risk_flags for flag in ["fever", "infection_alert", "cardiac_alert", "neurological_alert"]):
            return 2

        if clinical.get("vitals"):
            vitals = clinical.get("vitals", {})
            if vitals.get("temp_c") and vitals["temp_c"] >= 38.5:
                return 2
            if vitals.get("systolic_bp") and (vitals["systolic_bp"] >= 160 or vitals["systolic_bp"] <= 80):
                return 2

        return 1

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

        progress_data = private_memory.get("consultation_progress")
        if progress_data:
            consultation_progress = ConsultationProgress.from_dict(progress_data)
        else:
            severity = self._determine_severity_level(payload, clinical)
            consultation_progress = ConsultationProgress(
                current_step=ConsultationStep.CHIEF_COMPLAINT,
                severity_level=severity,
            )

        return WorkingMemory(
            short_term_turns=turns,
            shared_memory=shared_memory,
            private_memory=private_memory,
            consultation_progress=consultation_progress,
        )

    def apply_chat_updates(self, payload: dict, memory: WorkingMemory) -> None:
        message = (payload.get("message") or "").strip()
        if not message:
            return

        symptoms_lower = message.lower()
        symptom_keywords = {
            "headache": ["headache", "头疼", "头痛"],
            "cough": ["cough", "咳嗽"],
            "fever": ["fever", "发热", "发烧"],
            "fatigue": ["fatigue", "tiredness", "疲劳", "累"],
            "nausea": ["nausea", "恶心", "vomiting", "呕吐"],
        }

        clinical = memory.shared_memory["clinical_memory"]
        for symptom_key, keywords in symptom_keywords.items():
            if any(term in symptoms_lower for term in keywords):
                if symptom_key not in clinical.get("symptoms", []) and symptom_key.title() not in clinical.get("symptoms", []):
                    clinical["symptoms"] = merge_unique(clinical.get("symptoms"), [symptom_key.title()])

        clinical["risk_flags"] = derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

        from app.agents.internal_medicine.workflow import (
            CONSULTATION_STEPS,
            ConsultationStep,
            detect_medication_feedback,
            detect_test_completion,
            should_advance_step,
        )
        progress = memory.consultation_progress

        if progress.current_step == ConsultationStep.MEDICATION_FEEDBACK:
            feedback = detect_medication_feedback(message)
            if feedback:
                progress.advance("medication_feedback", feedback)
                if feedback == "ok":
                    next_step = progress.get_next_step()
                    if next_step:
                        progress.current_step = next_step
                else:
                    progress.current_step = ConsultationStep.ADJUST_MEDICATION
                    adjustment = {"original": "initial", "feedback": feedback, "action": "adjust"}
                    progress.medication_adjustments.append(adjustment)
                    next_step = progress.get_next_step()
                    if next_step:
                        progress.current_step = next_step
                return

        if progress.current_step == ConsultationStep.TESTS_PENDING:
            if detect_test_completion(message):
                progress.advance("tests_completed", "yes")
                next_step = progress.get_next_step()
                if next_step:
                    progress.current_step = next_step
                return

        if should_advance_step(progress, message):
            required_field = None
            for s in CONSULTATION_STEPS:
                if s["step"] == progress.current_step:
                    required_field = s.get("required_field")
                    break
            if required_field and not progress.is_complete():
                progress.advance(required_field, message)
                next_step = progress.get_next_step()
                if next_step:
                    progress.current_step = next_step

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

    def request_consultation_from_llm(
        self, payload: dict, evidence_rules: list[dict], memory_context: WorkingMemory
    ):
        if not self.llm_settings.get("api_key"):
            return None

        conversation_history = [
            {"role": turn.get("role", "user"), "content": turn.get("message", "")}
            for turn in memory_context.short_term_turns[-5:]
        ]

        if conversation_history:
            prompt = build_step_aware_prompt(
                payload,
                conversation_history,
                evidence_rules,
                memory_context.consultation_progress,
            )
        else:
            prompt = build_diagnosis_prompt(payload, evidence_rules)

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
            return {"note": text, "diagnosis_level": 1, "priority": "M", "department": "General Medicine"}

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
        retrieved_rules = retrieve_relevant_internal_medicine_rules(merged_payload, top_k=3)
        fallback = rule_based_internal_medicine(merged_payload)
        llm_text_response = None
        try:
            llm_result = self.request_consultation_from_llm(merged_payload, retrieved_rules, memory)
            if llm_result and isinstance(llm_result, dict):
                llm_text_response = llm_result.get("note") or llm_result.get("diagnosis", "")
        except Exception:
            llm_result = None

        final_result = validate_internal_medicine_result(llm_result, fallback)
        evidence = [{"id": rule.get("id"), "title": rule.get("title"), "source": rule.get("source")} for rule in retrieved_rules]
        missing_fields = build_missing_fields(memory.shared_memory)

        if llm_text_response:
            assistant_message = llm_text_response
        elif final_result.get("note"):
            assistant_message = final_result["note"]
        elif memory.short_term_turns:
            assistant_message = build_progress_follow_up(memory.consultation_progress, final_result)
        else:
            assistant_message = build_follow_up_message(missing_fields, final_result)

        return final_result, evidence, missing_fields, assistant_message

    def persist_result(
        self,
        patient_id: str,
        session_id: str,
        payload: dict,
        memory: WorkingMemory,
        dialogue_state,
        consultation_result: dict,
        evidence: list[dict],
        missing_fields: list[str],
        assistant_message: str,
    ):
        timestamp = now_iso()
        shared = memory.shared_memory
        private_memory = memory.private_memory

        shared["clinical_memory"]["last_department"] = consultation_result.get("department")
        shared["clinical_memory"]["last_diagnosis_level"] = consultation_result.get("diagnosis_level")
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["assistant_message"] = assistant_message
        private_memory["missing_fields"] = missing_fields
        private_memory["expected_field"] = missing_fields[0] if missing_fields else None
        private_memory["evidence"] = evidence
        private_memory["consultation_progress"] = memory.consultation_progress.to_dict()
        private_memory["latest_summary"] = {
            "chief_complaint": shared["clinical_memory"].get("chief_complaint"),
            "risk_flags": shared["clinical_memory"].get("risk_flags"),
            "diagnosis_level": consultation_result.get("diagnosis_level"),
            "department": consultation_result.get("department"),
            "missing_fields": missing_fields,
            "expected_field": missing_fields[0] if missing_fields else None,
            "severity_level": memory.consultation_progress.severity_level,
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory)
        self.memory_repo.append_internal_medicine_history(
            patient_id,
            session_id,
            {
                "time": timestamp,
                "diagnosis_level": consultation_result.get("diagnosis_level"),
                "priority": consultation_result.get("priority"),
                "department": consultation_result.get("department"),
                "note": consultation_result.get("note"),
                "evidence_ids": [item.get("id") for item in evidence],
            },
            timestamp,
        )
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_message or consultation_result.get("note", ""),
            timestamp,
            metadata={
                "diagnosis_level": consultation_result.get("diagnosis_level"),
                "department": consultation_result.get("department"),
            },
        )

        lifecycle_event = "internal_medicine_completed" if not missing_fields else "internal_medicine_followup_requested"
        patient_row = self.patient_repo.get(patient_id)
        if patient_row:
            current_lifecycle = patient_row["lifecycle_state"]
            if current_lifecycle not in ("completed", "cancelled", "error"):
                current_state = self.patient_state_machine.transition(current_lifecycle, lifecycle_event)
                self.patient_repo.update_patient(
                    patient_id,
                    name=payload.get("name", patient_row["name"]),
                    lifecycle_state=current_state.value,
                    priority=consultation_result.get("priority", "M"),
                    location=consultation_result.get("department", "General Medicine"),
                    session_id=session_id,
                )
                self.session_repo.update_state(session_id, dialogue_state.value)
                self.bus.publish(
                    PATIENT_STATE_CHANGED,
                    {
                        "patient_id": patient_id,
                        "lifecycle_state": current_state.value,
                    },
                )
                if not missing_fields:
                    self.bus.publish(
                        INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
                        {
                            "patient_id": patient_id,
                            "session_id": session_id,
                            "department": consultation_result.get("department"),
                            "priority": consultation_result.get("priority"),
                        },
                    )

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
