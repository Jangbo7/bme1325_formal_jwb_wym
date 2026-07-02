import json
import inspect
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib import request as urlrequest

from app.agents.clinical_policy import ClinicalPolicyRuntime, ClinicalPolicyValidatorResult
from app.llm_retry import DEFAULT_LLM_RETRIES, call_with_llm_retries
from app.agents.department_runtime.chart_view import build_doctor_chart_view
from app.agents.department_runtime.config import DepartmentAgentConfig
from app.agents.department_runtime.replies import (
    ANSWER_ONLY,
    ANSWER_WITH_GUIDANCE,
    REASSESS_REQUIRED,
    infer_answer_mode_from_message,
    infer_reassessment_intent,
    infer_reply_rendering_mode,
    default_patient_reply_from_result,
    infer_result_changed_fields,
    infer_update_reason,
    reassessment_intent_from_answer_mode,
    select_patient_reply_style,
)
from app.events.types import PATIENT_STATE_CHANGED


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DepartmentAgentRuntime:
    def __init__(
        self,
        *,
        config: DepartmentAgentConfig,
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
        encounter_orchestration_service=None,
        medical_record_repo=None,
        medical_record_card_service=None,
    ):
        self.config = config
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
        self.encounter_orchestration_service = encounter_orchestration_service
        self.medical_record_repo = medical_record_repo
        self.medical_record_card_service = medical_record_card_service
        self.policy_runtime = ClinicalPolicyRuntime()
        self._policy_registry = None

    def create_session(self, payload: dict):
        return self.graph.invoke({"mode": "create_session", "payload": payload})

    def continue_session(self, session_id: str, payload: dict):
        return self.graph.invoke({"mode": "continue_session", "payload": payload, "session_id": session_id})

    def continue_system_session(self, session_id: str, payload: dict):
        return self.graph.invoke({"mode": "system_continue", "payload": payload, "session_id": session_id})

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

    def _get_progress(self, private_memory: dict):
        return self.config.progress_from_dict(private_memory.get(self.config.progress_memory_key))

    def sync_progress_to_private_memory(self, memory) -> None:
        memory.private_memory[self.config.progress_memory_key] = memory.consultation_progress.to_dict()

    @staticmethod
    def _call_with_supported_kwargs(func, *args, **kwargs):
        if func is None:
            return None
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return func(*args, **kwargs)

        if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
            return func(*args, **kwargs)

        filtered_kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return func(*args, **filtered_kwargs)

    def get_policy_registry(self):
        if self.config.policy_registry_loader is None:
            return None
        if self._policy_registry is None:
            self._policy_registry = self.config.policy_registry_loader()
        return self._policy_registry

    def resolve_policy_runtime_context(self, payload: dict, merged_payload: dict, memory, mode: str):
        registry = self.get_policy_registry()
        if registry is None or self.config.policy_phase_selector is None:
            return None
        progress = memory.consultation_progress
        phase = self._call_with_supported_kwargs(
            self.config.policy_phase_selector,
            payload,
            memory.shared_memory,
            memory.private_memory,
            progress,
            mode,
            merged_payload=merged_payload,
        )
        if not phase:
            return None
        match_result = registry.find(
            agent_scope=self.config.policy_agent_scope or self.config.agent_type,
            department_scope=self.config.policy_department_scope or self.config.route_slug.replace("-", "_"),
            phase=phase,
            context={
                "message": payload.get("message", ""),
                "chief_complaint": merged_payload.get("chief_complaint"),
                "symptoms": merged_payload.get("symptoms"),
                "risk_flags": (memory.shared_memory.get("clinical_memory") or {}).get("risk_flags", []),
                "patient": {
                    "patient_id": payload.get("patient_id"),
                    "age": payload.get("age"),
                    "sex": payload.get("sex"),
                },
                "visit": {
                    "visit_id": payload.get("visit_id"),
                    "consultation_round": int(memory.private_memory.get("consultation_round") or 1),
                },
            },
        )
        runtime_context = self.policy_runtime.build_runtime_context(match_result)
        if runtime_context.primary_card is None:
            return None
        return runtime_context

    def build_working_memory_from_state(self, bundle: dict, state):
        memory = bundle.get("memory")
        if memory is not None:
            return memory
        return self.config.working_memory_cls(
            short_term_turns=state.turns,
            shared_memory=state.shared_memory,
            private_memory=state.private_memory,
            consultation_progress=self._get_progress(state.private_memory),
        )

    def build_graph_state(
        self,
        *,
        payload: dict,
        patient_row: dict | None,
        session_row: dict | None,
        shared_memory: dict,
        private_memory: dict,
        turns: list[dict],
        merged_payload: dict,
        dialogue_state,
    ):
        return self.config.graph_state_cls(
            payload=payload,
            patient_row=patient_row,
            session_row=session_row,
            shared_memory=shared_memory,
            private_memory=private_memory,
            turns=turns,
            merged_payload=merged_payload,
            dialogue_state=dialogue_state,
        )

    def append_user_turn(self, session_id: str, patient_id: str, message: str, mode: str) -> None:
        if not message:
            return
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "user",
            message,
            now_iso(),
            metadata={"mode": mode, "agent_type": self.config.agent_type},
        )

    def prepare_context(self, payload: dict, session_id: str, dialogue_state):
        patient_id = payload["patient_id"]
        patient_name = payload.get("name", patient_id)
        shared_memory = self._ensure_shared_memory_shape(
            self.memory_repo.get_shared_memory(patient_id, patient_name),
            patient_name,
        )
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=self.config.agent_type)
        turns = self.session_repo.list_turns(session_id)
        visit_row = self.visit_repo.get(payload.get("visit_id")) if payload.get("visit_id") and self.visit_repo is not None else None
        visit_data = self._decode_visit_data(visit_row)

        self.configure_private_memory_defaults(private_memory, payload)
        consultation_round = self._normalize_consultation_round(
            private_memory.get("consultation_round") or payload.get("_consultation_round") or payload.get("consultation_round")
        )
        consultation_context = self._build_consultation_context(
            consultation_round=consultation_round,
            visit_data=visit_data,
            private_memory=private_memory,
        )
        if consultation_context.get("doctor_memory_policy") == "chart_only" and not private_memory.get("doctor_memory_reset_applied"):
            shared_memory = self._reset_shared_memory_for_receiving_doctor(shared_memory, patient_name)
            private_memory["doctor_memory_reset_applied"] = True
        private_memory["consultation_context"] = consultation_context

        if payload.get("age") is not None:
            shared_memory["profile"]["age"] = payload["age"]
        if payload.get("sex"):
            shared_memory["profile"]["sex"] = payload["sex"]
        shared_memory["profile"]["name"] = patient_name
        shared_memory["profile"]["allergies"] = self.config.merge_unique(
            shared_memory["profile"].get("allergies"),
            payload.get("allergies") or [],
        )
        if payload.get("allergies") is not None:
            shared_memory["profile"]["allergy_status"] = "known"
        shared_memory["profile"]["chronic_conditions"] = self.config.merge_unique(
            shared_memory["profile"].get("chronic_conditions"),
            payload.get("chronic_conditions") or [],
        )
        if payload.get("chronic_conditions"):
            shared_memory["profile"]["chronic_conditions_status"] = "known"

        clinical = shared_memory["clinical_memory"]
        clinical["symptoms"] = self.config.merge_unique(
            clinical.get("symptoms"),
            self.config.split_symptoms(payload.get("symptoms", "")),
        )
        clinical["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint") or payload.get("symptoms", "")
        clinical["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        clinical["vitals"] = self.config.merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        clinical["risk_flags"] = self.config.derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

        private_memory["force_offline_llm"] = bool(payload.get("_force_offline_llm") or private_memory.get("force_offline_llm"))
        private_memory["dialogue_state"] = dialogue_state.value
        if payload.get("visit_id"):
            private_memory["chart_view"] = build_doctor_chart_view(
                medical_record_repo=self.medical_record_repo,
                patient_id=patient_id,
                visit_id=str(payload.get("visit_id") or ""),
                visit_data=visit_data,
            )
        if payload.get("debug_read_historical_records") or (
            consultation_round >= 2 and consultation_context.get("doctor_memory_policy") != "chart_only"
        ):
            template = self.load_historical_records_template(
                patient_id=patient_id,
                visit_id=str(payload.get("visit_id") or ""),
            )
            private_memory["historical_records_template"] = template
            private_memory["historical_records_note"] = template.get("clinician_note") or ""
        else:
            private_memory.pop("historical_records_template", None)
            private_memory.pop("historical_records_note", None)

        self.after_prepare_context(payload, shared_memory, private_memory)
        progress = self._get_progress(private_memory)

        return self.config.working_memory_cls(
            short_term_turns=turns,
            shared_memory=shared_memory,
            private_memory=private_memory,
            consultation_progress=progress,
        )

    def apply_chat_updates(self, payload: dict, memory) -> None:
        message = (payload.get("message") or "").strip()
        if not message:
            return
        extracted = self.config.extract_structured_updates(message)
        clinical = memory.shared_memory["clinical_memory"]
        profile = memory.shared_memory["profile"]
        if extracted.get("chief_complaint") and not clinical.get("chief_complaint"):
            clinical["chief_complaint"] = extracted["chief_complaint"]
        if extracted.get("symptoms"):
            clinical["symptoms"] = self.config.merge_unique(clinical.get("symptoms"), extracted["symptoms"])
        if extracted.get("onset_time"):
            clinical["onset_time"] = extracted["onset_time"]
        if extracted.get("allergy_status") == "known":
            profile["allergy_status"] = "known"
            profile["allergies"] = extracted.get("allergies") or []
        elif extracted.get("allergy_status") == "uncertain" and profile.get("allergy_status") != "known":
            profile["allergy_status"] = "uncertain"
        if extracted.get("chronic_conditions_status") == "known":
            profile["chronic_conditions_status"] = "known"
            profile["chronic_conditions"] = self.config.merge_unique([], extracted.get("chronic_conditions") or [])
        elif extracted.get("chronic_conditions_status") == "uncertain" and profile.get("chronic_conditions_status") != "known":
            profile["chronic_conditions_status"] = "uncertain"
        clinical["risk_flags"] = self.config.derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})
        memory.private_memory["latest_extraction"] = extracted
        memory.consultation_progress.patient_reply_count += 1
        memory.consultation_progress.last_extracted_fields = extracted.get("extracted_fields", [])

    def build_merged_payload(self, payload: dict, shared_memory: dict, private_memory: dict | None = None) -> dict:
        clinical = shared_memory["clinical_memory"]
        merged = {key: value for key, value in dict(payload).items() if not str(key).startswith("_")}
        merged["consultation_round"] = self._normalize_consultation_round(
            (private_memory or {}).get("consultation_round") or payload.get("consultation_round") or payload.get("_consultation_round")
        )
        consultation_context = dict((private_memory or {}).get("consultation_context") or {})
        doctor_memory_policy = str(consultation_context.get("doctor_memory_policy") or "")
        merged["symptoms"] = payload.get("symptoms") or ", ".join(clinical.get("symptoms") or [])
        merged["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint")
        merged["vitals"] = self.config.merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        merged["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        merged["allergies"] = payload.get("allergies") or shared_memory["profile"].get("allergies") or []
        merged["chronic_conditions"] = shared_memory["profile"].get("chronic_conditions") or []
        merged["chronic_conditions_status"] = shared_memory["profile"].get("chronic_conditions_status") or "unknown"
        merged["visit_id"] = payload.get("visit_id")
        if consultation_context:
            merged["consultation_context"] = consultation_context
        if private_memory and isinstance(private_memory.get("chart_view"), dict):
            merged["chart_view"] = private_memory.get("chart_view")

        visit_id = payload.get("visit_id")
        if visit_id and self.visit_repo is not None:
            visit_row = self.visit_repo.get(visit_id)
            visit_data = self._decode_visit_data(visit_row) if visit_row else {}
            simulated_report = visit_data.get("simulated_report")
            diagnostic_session = visit_data.get("diagnostic_session")
            if isinstance(simulated_report, dict):
                merged["simulated_report"] = simulated_report
            if isinstance(diagnostic_session, dict) and doctor_memory_policy != "chart_only":
                merged["diagnostic_session"] = diagnostic_session
            outpatient_procedure_plan = visit_data.get("outpatient_procedure_plan")
            outpatient_procedure_summary = visit_data.get("outpatient_procedure_summary")
            if isinstance(outpatient_procedure_plan, dict):
                merged["outpatient_procedure_plan"] = outpatient_procedure_plan
            if isinstance(outpatient_procedure_summary, dict):
                merged["outpatient_procedure_summary"] = outpatient_procedure_summary
                merged["procedure_completed"] = bool(outpatient_procedure_summary.get("completed"))
            if merged["consultation_round"] >= 2 and doctor_memory_policy != "chart_only":
                previous_round_summary = self._extract_previous_round_summary(visit_data)
                if isinstance(previous_round_summary, dict):
                    merged["previous_round_summary"] = previous_round_summary
        if private_memory and doctor_memory_policy != "chart_only" and isinstance(private_memory.get("historical_records_template"), dict):
            merged["historical_records_template"] = private_memory.get("historical_records_template")
        if private_memory and isinstance(private_memory.get("physical_exam"), dict):
            merged["physical_exam"] = private_memory.get("physical_exam")
        self.extend_merged_payload(merged, payload, shared_memory, private_memory or {})
        return merged

    def build_consultation_llm_messages(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        historical_records_template: dict | None = None,
        previous_final_result: dict | None = None,
        post_final_reassessment: bool = False,
        policy_runtime_context=None,
    ) -> list[dict]:
        consultation_round = self._normalize_consultation_round(payload.get("consultation_round"))
        policy_prompt_context = policy_runtime_context.prompt_policy_context if policy_runtime_context else ""
        if policy_prompt_context and self.config.policy_prompt_adapter is not None:
            policy_prompt_context = self._call_with_supported_kwargs(
                self.config.policy_prompt_adapter,
                policy_runtime_context,
                policy_prompt_context,
                prompt_kind="llm",
                payload=payload,
                missing_fields=missing_fields,
            )
        policy_prompt_context = self._augment_prompt_context_for_handoff(
            policy_prompt_context,
            payload,
        )
        prompt_shared_memory = self._build_prompt_shared_memory(shared_memory, payload)
        return [
            {
                "role": "system",
                "content": self._call_with_supported_kwargs(
                    self.config.build_system_prompt,
                    policy_prompt_context=policy_prompt_context,
                    policy_runtime_context=policy_runtime_context,
                    consultation_round=consultation_round,
                ),
            },
            {
                "role": "user",
                "content": self._call_with_supported_kwargs(
                    self.config.build_user_prompt,
                    prompt_shared_memory,
                    payload.get("message", ""),
                    missing_fields,
                    payload=payload,
                    historical_records_template=historical_records_template,
                    previous_final_result=previous_final_result,
                    post_final_reassessment=post_final_reassessment,
                    policy_prompt_context=policy_prompt_context,
                    policy_runtime_context=policy_runtime_context,
                    consultation_round=consultation_round,
                ),
            },
        ]

    def request_consultation_from_llm(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        historical_records_template: dict | None = None,
        previous_final_result: dict | None = None,
        post_final_reassessment: bool = False,
        policy_runtime_context=None,
    ) -> dict | None:
        if payload.get("_force_offline_llm"):
            return None
        if not self.llm_settings.get("api_key"):
            return None
        messages = self.build_consultation_llm_messages(
            payload,
            shared_memory,
            missing_fields,
            historical_records_template=historical_records_template,
            previous_final_result=previous_final_result,
            post_final_reassessment=post_final_reassessment,
            policy_runtime_context=policy_runtime_context,
        )

        def _single_attempt():
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
                raise ValueError("empty_or_unparseable_response")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    return json.loads(text[start : end + 1])
                raise ValueError("empty_or_unparseable_response")

        return call_with_llm_retries(_single_attempt, retries=DEFAULT_LLM_RETRIES)

    def build_post_final_answer_llm_messages(
        self,
        payload: dict,
        shared_memory: dict,
        final_result: dict,
        *,
        previous_final_result: dict | None = None,
        response_mode: str = ANSWER_ONLY,
        policy_runtime_context=None,
    ) -> list[dict]:
        consultation_round = self._normalize_consultation_round(payload.get("consultation_round"))
        if not self.config.build_post_final_answer_llm_messages:
            return []
        prompt_shared_memory = self._build_prompt_shared_memory(shared_memory, payload)
        return self._call_with_supported_kwargs(
            self.config.build_post_final_answer_llm_messages,
            prompt_shared_memory,
            payload.get("message", ""),
            final_result,
            payload=payload,
            previous_final_result=previous_final_result,
            policy_runtime_context=policy_runtime_context,
            consultation_round=consultation_round,
            response_mode=response_mode,
        ) or []

    def request_post_final_answer_from_llm(
        self,
        payload: dict,
        shared_memory: dict,
        final_result: dict,
        *,
        previous_final_result: dict | None = None,
        response_mode: str = ANSWER_ONLY,
        policy_runtime_context=None,
    ) -> str | None:
        if payload.get("_force_offline_llm"):
            return None
        if not self.llm_settings.get("api_key"):
            return None
        messages = self.build_post_final_answer_llm_messages(
            payload,
            shared_memory,
            final_result,
            previous_final_result=previous_final_result,
            response_mode=response_mode,
            policy_runtime_context=policy_runtime_context,
        )
        if not messages:
            return None

        def _single_attempt():
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
                raise ValueError("empty_or_unparseable_response")
            parsed_text = text.strip()
            try:
                payload_json = json.loads(parsed_text)
                if isinstance(payload_json, dict):
                    for key in ("assistant_message", "answer", "message", "reply"):
                        value = payload_json.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
            except Exception:
                pass
            if parsed_text:
                return parsed_text
            raise ValueError("empty_or_unparseable_response")

        return call_with_llm_retries(_single_attempt, retries=DEFAULT_LLM_RETRIES)

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

    @staticmethod
    def _parse_json_object_from_text(text: str) -> dict | None:
        parsed_text = str(text or "").strip()
        if not parsed_text:
            return None
        try:
            payload_json = json.loads(parsed_text)
            return payload_json if isinstance(payload_json, dict) else None
        except json.JSONDecodeError:
            start = parsed_text.find("{")
            end = parsed_text.rfind("}")
            if start >= 0 and end > start:
                payload_json = json.loads(parsed_text[start : end + 1])
                return payload_json if isinstance(payload_json, dict) else None
        return None

    @staticmethod
    def _coerce_string_list(value) -> list[str]:
        if isinstance(value, str):
            values = [part.strip() for part in value.replace(";", ",").split(",")]
        elif isinstance(value, list):
            values = [str(item).strip() for item in value]
        else:
            values = []
        return [item for item in values if item]

    def _request_json_from_llm_messages(self, messages: list[dict], *, timeout: int = 18) -> dict | None:
        if not messages:
            return None

        def _single_attempt():
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
            with urlrequest.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            text = self.extract_text_from_response(data)
            parsed = self._parse_json_object_from_text(text)
            if parsed is None:
                raise ValueError("empty_or_unparseable_response")
            return parsed

        return call_with_llm_retries(_single_attempt, retries=DEFAULT_LLM_RETRIES)

    @staticmethod
    def _looks_like_physical_exam_action_message(message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return True
        action_tokens = (
            "please",
            "let me",
            "i will",
            "i'll",
            "i am going to",
            "open your mouth",
            "listen to",
            "请",
            "让我",
            "我来",
            "我先",
            "张开嘴",
            "听一下",
            "检查一下",
        )
        finding_tokens = (
            "find",
            "finding",
            "show",
            "heard",
            "not heard",
            "clear",
            "redness",
            "查体",
            "检查显示",
            "可见",
            "未见",
            "闻及",
            "未闻及",
            "呼吸音",
            "充血",
            "肿大",
            "压痛",
        )
        return any(token in text for token in action_tokens) and not any(token in text for token in finding_tokens)

    def _build_physical_exam_result_fallback(self, exam_decision: dict, message: str = "") -> dict:
        targets = self._coerce_string_list(exam_decision.get("exam_targets"))
        target_text = " ".join(targets).lower()
        patient_text = str(message or "").lower()
        findings: list[str] = []

        if any(token in target_text for token in ("throat", "咽", "喉", "tonsil", "扁桃体")):
            findings.append("咽部轻度充血，扁桃体未见明显肿大")
        if any(token in target_text for token in ("lung", "肺", "auscultation", "呼吸", "胸")):
            if any(token in patient_text for token in ("wheeze", "喘", "气短", "胸闷", "shortness of breath")):
                findings.append("双肺呼吸音基本对称，未闻及明显干湿啰音")
            else:
                findings.append("双肺呼吸音清，未闻及明显干湿啰音")
        if any(token in target_text for token in ("abdomen", "腹", "tenderness", "压痛")):
            findings.append("腹部初筛未见明显腹膜刺激征")
        if any(token in target_text for token in ("wound", "伤口", "incision", "切口")):
            findings.append("局部伤口外观未见活动性出血")
        if not findings:
            findings.append("基础查体未见明显急性阳性体征")

        impression = "基础门诊查体暂未提示需要立即急诊处理的明显阳性体征"
        assistant_message = f"查体结果：{'；'.join(findings)}。"
        return {
            "assistant_message": assistant_message,
            "physical_exam": {
                "needed": True,
                "exam_type": str(exam_decision.get("exam_type") or "basic_outpatient_exam").strip(),
                "exam_targets": targets,
                "findings": findings,
                "impression": impression,
                "source": "fallback_simulated_physical_exam",
            },
        }

    def build_physical_exam_decision_llm_messages(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        policy_runtime_context=None,
    ) -> list[dict]:
        if not self.config.build_physical_exam_decision_llm_messages:
            return []
        consultation_round = self._normalize_consultation_round(payload.get("consultation_round"))
        prompt_shared_memory = self._build_prompt_shared_memory(shared_memory, payload)
        return self._call_with_supported_kwargs(
            self.config.build_physical_exam_decision_llm_messages,
            prompt_shared_memory,
            payload.get("message", ""),
            missing_fields,
            payload=payload,
            policy_runtime_context=policy_runtime_context,
            consultation_round=consultation_round,
        ) or []

    def request_physical_exam_decision_from_llm(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        policy_runtime_context=None,
    ) -> dict | None:
        if payload.get("_force_offline_llm"):
            return None
        if not self.llm_settings.get("api_key"):
            return None
        messages = self.build_physical_exam_decision_llm_messages(
            payload,
            shared_memory,
            missing_fields,
            policy_runtime_context=policy_runtime_context,
        )
        result = self._request_json_from_llm_messages(messages)
        if not isinstance(result, dict):
            return None
        exam_needed = bool(result.get("exam_needed"))
        exam_type = str(result.get("exam_type") or "").strip()
        exam_targets = self._coerce_string_list(result.get("exam_targets"))
        doctor_action_message = str(result.get("doctor_action_message") or "").strip()
        if exam_needed and not doctor_action_message:
            target_text = "、".join(exam_targets) if exam_targets else "相关体征"
            doctor_action_message = f"我先为您做一个基础门诊查体，重点看一下{target_text}。"
        return {
            "exam_needed": exam_needed,
            "exam_type": exam_type if exam_needed else "",
            "exam_targets": exam_targets if exam_needed else [],
            "doctor_action_message": doctor_action_message if exam_needed else "",
        }

    def _request_physical_exam_decision_with_diagnostics(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        policy_runtime_context=None,
    ) -> tuple[dict | None, dict]:
        diagnostics = {
            "llm_attempted": False,
            "llm_succeeded": False,
            "llm_error": None,
            "response_source": "fallback",
            "llm_response_kind": "physical_exam_decision",
        }
        if payload.get("_force_offline_llm") or not self.llm_settings.get("api_key"):
            diagnostics["llm_error"] = "llm_unavailable"
            return None, diagnostics
        if not self.config.build_physical_exam_decision_llm_messages:
            diagnostics["llm_error"] = "physical_exam_decision_prompt_unavailable"
            return None, diagnostics
        diagnostics["llm_attempted"] = True
        try:
            result = self.request_physical_exam_decision_from_llm(
                payload,
                shared_memory,
                missing_fields,
                policy_runtime_context=policy_runtime_context,
            )
        except Exception as exc:
            diagnostics["llm_error"] = str(exc)
            return None, diagnostics
        if result is not None:
            diagnostics["llm_succeeded"] = True
            diagnostics["response_source"] = "llm"
        else:
            diagnostics["llm_error"] = "empty_or_unparseable_response"
        return result, diagnostics

    def build_physical_exam_result_llm_messages(
        self,
        payload: dict,
        shared_memory: dict,
        exam_decision: dict,
        *,
        policy_runtime_context=None,
    ) -> list[dict]:
        if not self.config.build_physical_exam_result_llm_messages:
            return []
        consultation_round = self._normalize_consultation_round(payload.get("consultation_round"))
        prompt_shared_memory = self._build_prompt_shared_memory(shared_memory, payload)
        return self._call_with_supported_kwargs(
            self.config.build_physical_exam_result_llm_messages,
            prompt_shared_memory,
            payload.get("message", ""),
            exam_decision,
            payload=payload,
            policy_runtime_context=policy_runtime_context,
            consultation_round=consultation_round,
        ) or []

    def request_physical_exam_result_from_llm(
        self,
        payload: dict,
        shared_memory: dict,
        exam_decision: dict,
        *,
        policy_runtime_context=None,
    ) -> dict | None:
        if payload.get("_force_offline_llm"):
            return None
        if not self.llm_settings.get("api_key"):
            return None
        messages = self.build_physical_exam_result_llm_messages(
            payload,
            shared_memory,
            exam_decision,
            policy_runtime_context=policy_runtime_context,
        )
        result = self._request_json_from_llm_messages(messages)
        if not isinstance(result, dict):
            return None
        physical_exam = dict(result.get("physical_exam") or {})
        exam_type = str(physical_exam.get("exam_type") or exam_decision.get("exam_type") or "basic_outpatient_exam").strip()
        exam_targets = self._coerce_string_list(physical_exam.get("exam_targets") or exam_decision.get("exam_targets"))
        findings = physical_exam.get("findings") or result.get("findings") or []
        if isinstance(findings, str):
            findings = [findings.strip()] if findings.strip() else []
        elif isinstance(findings, list):
            findings = [item for item in findings if item not in (None, "", [], {})]
        else:
            findings = []
        impression = str(physical_exam.get("impression") or result.get("impression") or "").strip()
        assistant_message = str(result.get("assistant_message") or result.get("message") or "").strip()
        if (not findings and not impression) or self._looks_like_physical_exam_action_message(assistant_message):
            return self._build_physical_exam_result_fallback(exam_decision, payload.get("message", ""))
        if not assistant_message and (findings or impression):
            findings_text = "；".join(str(item) for item in findings) if findings else impression
            assistant_message = f"基础查体结果：{findings_text}"
        if not assistant_message:
            return None
        return {
            "assistant_message": assistant_message,
            "physical_exam": {
                "needed": True,
                "exam_type": exam_type,
                "exam_targets": exam_targets,
                "findings": findings,
                "impression": impression,
                "source": "llm_simulated_physical_exam",
            },
        }

    def _request_physical_exam_result_with_diagnostics(
        self,
        payload: dict,
        shared_memory: dict,
        exam_decision: dict,
        *,
        policy_runtime_context=None,
    ) -> tuple[dict | None, dict]:
        diagnostics = {
            "llm_attempted": False,
            "llm_succeeded": False,
            "llm_error": None,
            "response_source": "fallback",
            "llm_response_kind": "physical_exam_result",
        }
        if payload.get("_force_offline_llm") or not self.llm_settings.get("api_key"):
            diagnostics["llm_error"] = "llm_unavailable"
            return None, diagnostics
        if not self.config.build_physical_exam_result_llm_messages:
            diagnostics["llm_error"] = "physical_exam_result_prompt_unavailable"
            return None, diagnostics
        diagnostics["llm_attempted"] = True
        try:
            result = self.request_physical_exam_result_from_llm(
                payload,
                shared_memory,
                exam_decision,
                policy_runtime_context=policy_runtime_context,
            )
        except Exception as exc:
            diagnostics["llm_error"] = str(exc)
            return None, diagnostics
        if result is not None:
            diagnostics["llm_succeeded"] = True
            diagnostics["response_source"] = "llm"
        else:
            diagnostics["llm_error"] = "empty_or_unparseable_response"
        return result, diagnostics

    def request_follow_up_message_from_llm(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        question_focus: str | None = None,
        policy_runtime_context=None,
    ) -> str | None:
        if payload.get("_force_offline_llm"):
            return None
        if not self.llm_settings.get("api_key"):
            return None
        if not self.config.build_follow_up_llm_messages:
            return None
        allow_no_followup = bool(payload.get("_allow_no_followup"))
        prompt_shared_memory = self._build_prompt_shared_memory(shared_memory, payload)
        prompt_payload = dict(payload or {})
        session_id = prompt_payload.get("session_id")
        if session_id and "recent_turns" not in prompt_payload:
            prompt_payload["recent_turns"] = self.session_repo.list_turns(str(session_id), limit=8)
        if prompt_payload.get("recent_turns"):
            prompt_shared_memory["recent_turns"] = prompt_payload.get("recent_turns")
        messages = self._call_with_supported_kwargs(
            self.config.build_follow_up_llm_messages,
            prompt_shared_memory,
            payload.get("message", ""),
            missing_fields,
            question_focus=question_focus,
            payload=prompt_payload,
            policy_runtime_context=policy_runtime_context,
        )
        if not messages:
            return None

        def _single_attempt():
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
                raise ValueError("empty_or_unparseable_response")
            parsed_text = text.strip()
            try:
                payload_json = json.loads(parsed_text)
                if isinstance(payload_json, dict):
                    for key in ("assistant_message", "follow_up_question", "question", "message", "reply"):
                        value = payload_json.get(key)
                        if isinstance(value, str) and value.strip():
                            return value.strip()
                    if allow_no_followup:
                        return None
            except Exception:
                pass
            if allow_no_followup and parsed_text in {"{}", "[]"}:
                return None
            if parsed_text:
                return parsed_text
            raise ValueError("empty_or_unparseable_response")

        return call_with_llm_retries(_single_attempt, retries=DEFAULT_LLM_RETRIES)

    def _request_follow_up_message_with_diagnostics(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        question_focus: str | None = None,
        policy_runtime_context=None,
    ) -> tuple[str | None, dict]:
        diagnostics = {
            "llm_attempted": False,
            "llm_succeeded": False,
            "llm_error": None,
            "response_source": "fallback",
        }
        if payload.get("_force_offline_llm") or not self.llm_settings.get("api_key"):
            diagnostics["llm_error"] = "llm_unavailable"
            return None, diagnostics
        diagnostics["llm_attempted"] = True
        try:
            message = self.request_follow_up_message_from_llm(
                payload,
                shared_memory,
                missing_fields,
                question_focus=question_focus,
                policy_runtime_context=policy_runtime_context,
            )
        except Exception as exc:
            diagnostics["llm_error"] = str(exc)
            return None, diagnostics
        if message:
            diagnostics["llm_succeeded"] = True
            diagnostics["response_source"] = "llm"
            return message, diagnostics
        diagnostics["llm_error"] = "empty_or_unparseable_response"
        return None, diagnostics

    def _classify_post_final_answer_mode(self, payload: dict, memory, previous_final_result: dict | None = None) -> str:
        del previous_final_result
        latest_extraction = dict(memory.private_memory.get("latest_extraction") or {})
        return infer_answer_mode_from_message(payload.get("message", ""), latest_extraction)

    def _request_post_final_answer_with_diagnostics(
        self,
        payload: dict,
        shared_memory: dict,
        final_result: dict,
        *,
        previous_final_result: dict | None = None,
        response_mode: str = ANSWER_ONLY,
        policy_runtime_context=None,
    ) -> tuple[str | None, dict]:
        diagnostics = {
            "llm_attempted": False,
            "llm_succeeded": False,
            "llm_error": None,
            "response_source": "fallback",
            "llm_response_kind": "direct_answer",
        }
        if payload.get("_force_offline_llm") or not self.llm_settings.get("api_key"):
            diagnostics["llm_error"] = "llm_unavailable"
            return None, diagnostics
        diagnostics["llm_attempted"] = True
        try:
            result = self.request_post_final_answer_from_llm(
                payload,
                shared_memory,
                final_result,
                previous_final_result=previous_final_result,
                response_mode=response_mode,
                policy_runtime_context=policy_runtime_context,
            )
        except Exception as exc:
            diagnostics["llm_error"] = str(exc)
            return None, diagnostics
        if result:
            diagnostics["llm_succeeded"] = True
            diagnostics["response_source"] = "llm_then_validated"
        else:
            diagnostics["llm_error"] = "empty_or_unparseable_response"
        return result, diagnostics

    def _build_post_final_answer_fallback(
        self,
        final_result: dict,
        *,
        response_mode: str,
        previous_final_result: dict | None = None,
        payload: dict | None = None,
        memory=None,
    ) -> tuple[str, str, str]:
        reassessment_intent = reassessment_intent_from_answer_mode(response_mode)
        reply_rendering_mode = infer_reply_rendering_mode(reassessment_intent, message_type=response_mode)
        if self.config.build_post_final_answer_fallback is not None:
            style = self._call_with_supported_kwargs(
                self.config.patient_reply_style_selector or select_patient_reply_style,
                consultation_round=self._normalize_consultation_round((payload or {}).get("consultation_round")),
                message_type=response_mode,
                complete=True,
                progress_completed=bool(getattr(getattr(memory, "consultation_progress", None), "completed", True)),
                final_result=final_result,
                previous_final_result=previous_final_result or {},
                changed_fields=[],
                update_reason=None,
                payload=payload or {},
                memory=memory,
            )
            reply = self._call_with_supported_kwargs(
                self.config.build_post_final_answer_fallback,
                final_result,
                message_type=response_mode,
                consultation_round=self._normalize_consultation_round((payload or {}).get("consultation_round")),
                reply_style=style,
                previous_final_result=previous_final_result or {},
                changed_fields=[],
                update_reason=None,
                reassessment_intent=reassessment_intent,
                reply_rendering_mode=reply_rendering_mode,
                payload=payload or {},
                memory=memory,
            )
            if isinstance(reply, str) and reply.strip():
                return reply.strip(), style, "fallback_formatter"
        return self._build_patient_reply(
            final_result,
            message_type=response_mode,
            consultation_round=self._normalize_consultation_round((payload or {}).get("consultation_round")),
            complete=True,
            progress_completed=bool(getattr(getattr(memory, "consultation_progress", None), "completed", True)),
            previous_final_result=previous_final_result or {},
            changed_fields=[],
            update_reason=None,
            reassessment_intent=reassessment_intent,
            reply_rendering_mode=reply_rendering_mode,
            payload=payload or {},
            memory=memory,
        )

    def _build_patient_reply(
        self,
        final_result: dict,
        *,
        message_type: str,
        consultation_round: int,
        complete: bool,
        progress_completed: bool,
        previous_final_result: dict | None = None,
        changed_fields: list[str] | None = None,
        update_reason: str | None = None,
        reassessment_intent: str | None = None,
        reply_rendering_mode: str | None = None,
        payload: dict | None = None,
        memory=None,
    ) -> tuple[str, str, str]:
        style = self._call_with_supported_kwargs(
            self.config.patient_reply_style_selector or select_patient_reply_style,
            consultation_round=consultation_round,
            message_type=message_type,
            complete=complete,
            progress_completed=progress_completed,
            final_result=final_result,
            previous_final_result=previous_final_result or {},
            changed_fields=changed_fields or [],
            update_reason=update_reason,
            payload=payload or {},
            memory=memory,
        )
        if self.config.build_patient_reply is not None:
            reply = self._call_with_supported_kwargs(
                self.config.build_patient_reply,
                final_result,
                message_type=message_type,
                consultation_round=consultation_round,
                reply_style=style,
                previous_final_result=previous_final_result or {},
                changed_fields=changed_fields or [],
                update_reason=update_reason,
                reassessment_intent=reassessment_intent,
                reply_rendering_mode=reply_rendering_mode,
                payload=payload or {},
                memory=memory,
            )
            if isinstance(reply, str) and reply.strip():
                return reply.strip(), style, "reply_builder"
        if self.config.build_final_message is not None:
            return self.config.build_final_message(final_result, message_type=message_type), style, "fallback_formatter"
        return default_patient_reply_from_result(final_result, message_type=message_type), style, "fallback_formatter"

    def _request_consultation_with_diagnostics(
        self,
        payload: dict,
        shared_memory: dict,
        missing_fields: list[str],
        *,
        historical_records_template: dict | None = None,
        previous_final_result: dict | None = None,
        post_final_reassessment: bool = False,
        policy_runtime_context=None,
    ) -> tuple[dict | None, dict]:
        diagnostics = {
            "llm_attempted": False,
            "llm_succeeded": False,
            "llm_error": None,
            "response_source": "fallback",
        }
        if payload.get("_force_offline_llm") or not self.llm_settings.get("api_key"):
            diagnostics["llm_error"] = "llm_unavailable"
            return None, diagnostics
        diagnostics["llm_attempted"] = True
        try:
            result = self.request_consultation_from_llm(
                payload,
                shared_memory,
                missing_fields,
                historical_records_template=historical_records_template,
                previous_final_result=previous_final_result,
                post_final_reassessment=post_final_reassessment,
                policy_runtime_context=policy_runtime_context,
            )
        except Exception as exc:
            diagnostics["llm_error"] = str(exc)
            return None, diagnostics
        if result is not None:
            diagnostics["llm_succeeded"] = True
            diagnostics["response_source"] = "llm_then_validated"
        else:
            diagnostics["llm_error"] = "empty_or_unparseable_response"
        return result, diagnostics

    @staticmethod
    def _with_extra_turns(assistant_payload: dict, extra_turns: list[dict]) -> dict:
        if not extra_turns:
            return assistant_payload
        payload = dict(assistant_payload)
        payload["extra_turns"] = list(payload.get("extra_turns") or []) + list(extra_turns)
        return payload

    @staticmethod
    def _surgery_localized_issue_needs_location_before_exam(merged_payload: dict, memory) -> bool:
        text = " ".join(
            str(part or "")
            for part in [
                merged_payload.get("chief_complaint"),
                merged_payload.get("symptoms"),
                merged_payload.get("message"),
                *(((memory.shared_memory.get("clinical_memory") or {}).get("symptoms") or []) if memory is not None else []),
            ]
        ).lower()
        localized_issue_tokens = (
            "wound",
            "postoperative",
            "post-op",
            "surgery wound",
            "lump",
            "mass",
            "nodule",
            "swelling",
            "redness",
            "伤口",
            "术后",
            "手术伤口",
            "刀口",
            "切口",
            "包块",
            "肿块",
            "结节",
            "红肿",
            "肿胀",
        )
        if not any(token in text for token in localized_issue_tokens):
            return False
        location_tokens = (
            "upper",
            "lower",
            "arm",
            "forearm",
            "wrist",
            "hand",
            "finger",
            "leg",
            "calf",
            "thigh",
            "knee",
            "ankle",
            "foot",
            "toe",
            "abdomen",
            "abdominal",
            "chest",
            "back",
            "neck",
            "shoulder",
            "elbow",
            "左侧",
            "右侧",
            "左边",
            "右边",
            "手腕",
            "手臂",
            "前臂",
            "手指",
            "手掌",
            "胳膊",
            "小腿",
            "大腿",
            "膝",
            "脚踝",
            "脚",
            "足",
            "腹",
            "肚",
            "胸",
            "背",
            "颈",
            "肩",
            "肘",
            "腰",
        )
        return not any(token in text for token in location_tokens)

    def _maybe_start_round1_physical_exam(
        self,
        *,
        merged_payload: dict,
        memory,
        mode: str,
        consultation_round: int,
        missing_fields: list[str],
        force_offline_llm: bool,
        policy_runtime_context=None,
    ) -> dict | None:
        private_memory = memory.private_memory
        progress = memory.consultation_progress
        if mode != "continue_session" or consultation_round != 1:
            return None
        if progress.patient_reply_count < 1:
            return None
        if private_memory.get("physical_exam_decision_checked"):
            return None
        if (
            self.config.agent_type == "surgery"
            and self._surgery_localized_issue_needs_location_before_exam(merged_payload, memory)
        ):
            private_memory["physical_exam_deferred_reason"] = "missing_surgical_location"
            return None

        private_memory["physical_exam_decision_checked"] = True
        private_memory["physical_exam_patient_message"] = merged_payload.get("message", "")
        private_memory["physical_exam_missing_fields"] = list(missing_fields or [])
        decision, decision_diagnostics = self._request_physical_exam_decision_with_diagnostics(
            {**merged_payload, "_force_offline_llm": force_offline_llm},
            memory.shared_memory,
            missing_fields,
            policy_runtime_context=policy_runtime_context,
        )
        private_memory["physical_exam_decision_diagnostics"] = dict(decision_diagnostics)
        if not decision:
            private_memory["physical_exam_completed"] = False
            return None
        private_memory["physical_exam_decision"] = dict(decision)
        if not bool(decision.get("exam_needed")):
            private_memory["physical_exam_completed"] = False
            return None
        intent_message = str(decision.get("doctor_action_message") or "").strip()
        if not intent_message:
            private_memory["physical_exam_completed"] = False
            return None
        private_memory["pending_physical_exam_stage"] = "result"
        return {
            "assistant_message": intent_message,
            "message_type": "physical_exam_intent",
            "response_mode": "physical_exam",
            "judgment_changed": False,
            "judgment_action": "none",
            "answer_source": "llm",
            "llm_response_kind": "physical_exam_decision",
            "llm_diagnostics": decision_diagnostics,
            "pending_auto_continue": True,
            "physical_exam": {
                "needed": True,
                "exam_type": decision.get("exam_type"),
                "exam_targets": list(decision.get("exam_targets") or []),
            },
        }

    def _continue_pending_round1_physical_exam(
        self,
        *,
        merged_payload: dict,
        memory,
        mode: str,
        consultation_round: int,
        force_offline_llm: bool,
        policy_runtime_context=None,
    ) -> dict | None:
        private_memory = memory.private_memory
        if mode != "system_continue" or consultation_round != 1:
            return None
        stage = str(private_memory.get("pending_physical_exam_stage") or "")
        if stage == "result":
            decision = dict(private_memory.get("physical_exam_decision") or {})
            if not decision:
                private_memory.pop("pending_physical_exam_stage", None)
                return None
            exam_payload = {
                **merged_payload,
                "message": private_memory.get("physical_exam_patient_message") or merged_payload.get("message", ""),
                "_force_offline_llm": force_offline_llm,
            }
            result, result_diagnostics = self._request_physical_exam_result_with_diagnostics(
                exam_payload,
                memory.shared_memory,
                decision,
                policy_runtime_context=policy_runtime_context,
            )
            private_memory["physical_exam_result_diagnostics"] = dict(result_diagnostics)
            if not result:
                private_memory["physical_exam_completed"] = False
                private_memory.pop("pending_physical_exam_stage", None)
                return None
            physical_exam = dict(result.get("physical_exam") or {})
            result_message = str(result.get("assistant_message") or "").strip()
            if not physical_exam or not result_message:
                private_memory["physical_exam_completed"] = False
                private_memory.pop("pending_physical_exam_stage", None)
                return None
            private_memory["physical_exam"] = physical_exam
            private_memory["physical_exam_completed"] = True
            private_memory["pending_physical_exam_stage"] = "resume_consultation"
            merged_payload["physical_exam"] = physical_exam
            return {
                "assistant_message": result_message,
                "message_type": "physical_exam_result",
                "response_mode": "physical_exam",
                "judgment_changed": False,
                "judgment_action": "none",
                "answer_source": "llm",
                "llm_response_kind": "physical_exam_result",
                "llm_diagnostics": result_diagnostics,
                "pending_auto_continue": True,
                "physical_exam": physical_exam,
            }
        if stage == "resume_consultation":
            private_memory.pop("pending_physical_exam_stage", None)
            private_memory.pop("pending_auto_continue", None)
            if private_memory.get("physical_exam_patient_message"):
                merged_payload["message"] = private_memory.get("physical_exam_patient_message")
            if isinstance(private_memory.get("physical_exam"), dict):
                merged_payload["physical_exam"] = private_memory.get("physical_exam")
            return None
        return None

    def _select_optional_round1_followup_focus(
        self,
        *,
        memory,
        mode: str,
        consultation_round: int,
        missing_fields: list[str],
    ) -> str | None:
        if mode not in {"continue_session", "system_continue"} or consultation_round != 1:
            return None
        if missing_fields:
            return None
        optional_fields = tuple(self.config.optional_round1_followup_fields or ())
        if not optional_fields:
            return None
        progress = memory.consultation_progress
        profile = memory.shared_memory.get("profile") or {}
        for field_name in optional_fields:
            if field_name in progress.asked_fields_history:
                continue
            if field_name == "past_medical_history":
                status = str(profile.get("chronic_conditions_status") or "unknown").strip().lower()
                if profile.get("chronic_conditions") or status in {"known", "uncertain"}:
                    continue
                return field_name
        return None

    def evaluate(self, merged_payload: dict, memory, mode: str) -> tuple[dict, list[dict], list[str], dict, bool]:
        progress = memory.consultation_progress
        consultation_round = self._normalize_consultation_round(memory.private_memory.get("consultation_round"))
        force_offline_llm = bool(memory.private_memory.get("force_offline_llm"))
        previous_final_result = memory.private_memory.get("final_result") if isinstance(memory.private_memory.get("final_result"), dict) else {}
        is_post_final_reassessment = mode == "continue_session" and progress.completed
        policy_runtime_context = self.resolve_policy_runtime_context(
            merged_payload,
            merged_payload,
            memory,
            mode,
        )
        missing_fields = self._call_with_supported_kwargs(
            self.config.prioritize_missing_fields,
            memory.shared_memory,
            asked_fields_history=progress.asked_fields_history,
            last_question_focus=progress.last_question_focus,
            policy_runtime_context=policy_runtime_context,
        )
        rules = self.config.retrieve_rules(merged_payload, top_k=3)
        evidence = [{"id": rule.get("id"), "title": rule.get("title"), "source": rule.get("source")} for rule in rules]
        fallback = self.config.fallback_result(merged_payload)

        if mode == "create_session" and consultation_round == 1:
            initial_missing_fields = self._call_with_supported_kwargs(
                self.config.build_missing_fields,
                memory.shared_memory,
                policy_runtime_context=policy_runtime_context,
            )
            question_focus = initial_missing_fields[0] if initial_missing_fields else None
            assistant_message, llm_diagnostics = self._request_follow_up_message_with_diagnostics(
                {**merged_payload, "_force_offline_llm": force_offline_llm},
                memory.shared_memory,
                initial_missing_fields,
                question_focus=question_focus,
                policy_runtime_context=policy_runtime_context,
            )
            answer_source = "llm"
            if not assistant_message:
                assistant_message = self._call_with_supported_kwargs(
                    self.config.build_initial_message,
                    memory.shared_memory,
                    progress,
                    consultation_round=consultation_round,
                    policy_runtime_context=policy_runtime_context,
                )
                answer_source = "fallback_formatter"
            if question_focus:
                progress.asked_fields_history.append(question_focus)
                progress.last_question_focus = question_focus
            else:
                progress.last_question_focus = None
            progress.last_question_text = assistant_message
            assistant_payload = {"assistant_message": assistant_message, "message_type": "followup"}
            consultation_result, missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                merged_payload=merged_payload,
                memory=memory,
                consultation_result=fallback,
                missing_fields=initial_missing_fields,
                assistant_payload={
                    **assistant_payload,
                    "response_mode": "followup",
                    "judgment_changed": False,
                    "judgment_action": "none",
                    "answer_source": answer_source,
                    "llm_response_kind": "followup_question",
                    "llm_diagnostics": llm_diagnostics,
                },
                complete=False,
                policy_runtime_context=policy_runtime_context,
            )
            return (
                consultation_result,
                evidence,
                missing_fields,
                assistant_payload,
                complete,
            )

        pending_physical_exam_payload = self._continue_pending_round1_physical_exam(
            merged_payload=merged_payload,
            memory=memory,
            mode=mode,
            consultation_round=consultation_round,
            force_offline_llm=force_offline_llm,
            policy_runtime_context=policy_runtime_context,
        )
        if pending_physical_exam_payload:
            return fallback, evidence, missing_fields, pending_physical_exam_payload, False

        physical_exam_payload = self._maybe_start_round1_physical_exam(
            merged_payload=merged_payload,
            memory=memory,
            mode=mode,
            consultation_round=consultation_round,
            missing_fields=missing_fields,
            force_offline_llm=force_offline_llm,
            policy_runtime_context=policy_runtime_context,
        )
        if physical_exam_payload:
            return fallback, evidence, missing_fields, physical_exam_payload, False

        if is_post_final_reassessment:
            response_mode = self._classify_post_final_answer_mode(
                merged_payload,
                memory,
                previous_final_result=previous_final_result,
            )
            if response_mode in {ANSWER_ONLY, ANSWER_WITH_GUIDANCE}:
                assistant_message, llm_diagnostics = self._request_post_final_answer_with_diagnostics(
                    {**merged_payload, "_force_offline_llm": force_offline_llm},
                    memory.shared_memory,
                    previous_final_result,
                    previous_final_result=previous_final_result,
                    response_mode=response_mode,
                    policy_runtime_context=policy_runtime_context,
                )
                reply_style = None
                answer_source = "llm"
                patient_reply_source = "llm"
                reply_rendering_mode = infer_reply_rendering_mode(
                    reassessment_intent_from_answer_mode(response_mode),
                    message_type=response_mode,
                )
                if not assistant_message:
                    assistant_message, reply_style, answer_source = self._build_post_final_answer_fallback(
                        previous_final_result,
                        response_mode=response_mode,
                        previous_final_result=previous_final_result,
                        payload=merged_payload,
                        memory=memory,
                    )
                    patient_reply_source = answer_source
                    answer_source = "fallback_formatter"
                progress.last_question_focus = None
                progress.last_question_text = assistant_message
                consultation_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                    merged_payload=merged_payload,
                    memory=memory,
                    consultation_result=previous_final_result,
                    missing_fields=[],
                    assistant_payload={
                        "assistant_message": assistant_message,
                        "message_type": response_mode,
                        "response_mode": response_mode,
                        "judgment_changed": False,
                        "judgment_action": "none",
                        "answer_source": answer_source,
                        "llm_response_kind": "direct_answer",
                        "patient_reply_style": reply_style,
                        "patient_reply_source": patient_reply_source,
                        "update_reason": None,
                        "result_changed_fields": [],
                        "reassessment_intent": reassessment_intent_from_answer_mode(response_mode),
                        "reply_rendering_mode": reply_rendering_mode,
                        "llm_diagnostics": llm_diagnostics,
                    },
                    complete=True,
                    policy_runtime_context=policy_runtime_context,
                )
                return consultation_result, evidence, validated_missing_fields, assistant_payload, complete

            llm_result, llm_diagnostics = self._request_consultation_with_diagnostics(
                {**merged_payload, "_force_offline_llm": force_offline_llm},
                memory.shared_memory,
                missing_fields,
                historical_records_template=merged_payload.get("historical_records_template"),
                previous_final_result=previous_final_result,
                post_final_reassessment=True,
                policy_runtime_context=policy_runtime_context,
            )
            final_result = self._call_with_supported_kwargs(
                self.config.validate_result,
                llm_result,
                fallback,
                merged_payload,
                policy_runtime_context=policy_runtime_context,
                memory=memory,
                mode=mode,
                complete=True,
            )
            changed = self.config.final_result_changed(previous_final_result, final_result) if self.config.final_result_changed else final_result != previous_final_result
            changed_fields = infer_result_changed_fields(previous_final_result, final_result) if changed else []
            update_reason = self._call_with_supported_kwargs(
                self.config.result_update_reason_inferer or infer_update_reason,
                merged_payload.get("message", ""),
                changed_fields,
                consultation_round=consultation_round,
                message_type="final_update" if changed else "final_no_change",
                final_result=final_result,
                previous_final_result=previous_final_result,
            )
            if changed:
                message_type = "final_update"
                reassessment_intent = self._call_with_supported_kwargs(
                    self.config.reassessment_intent_inferer or infer_reassessment_intent,
                    merged_payload.get("message", ""),
                    changed_fields,
                    consultation_round=consultation_round,
                    message_type=message_type,
                    update_reason=update_reason,
                    final_result=final_result,
                    previous_final_result=previous_final_result,
                )
                reply_rendering_mode = infer_reply_rendering_mode(reassessment_intent, message_type=message_type)
                assistant_message, reply_style, patient_reply_source = self._build_patient_reply(
                    final_result,
                    message_type=message_type,
                    consultation_round=consultation_round,
                    complete=True,
                    progress_completed=progress.completed,
                    previous_final_result=previous_final_result,
                    changed_fields=changed_fields,
                    update_reason=update_reason,
                    reassessment_intent=reassessment_intent,
                    reply_rendering_mode=reply_rendering_mode,
                    payload=merged_payload,
                    memory=memory,
                )
                progress.last_question_focus = None
                progress.last_question_text = assistant_message
                final_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                    merged_payload=merged_payload,
                    memory=memory,
                    consultation_result=final_result,
                    missing_fields=[],
                    assistant_payload={
                        "assistant_message": assistant_message,
                        "message_type": message_type,
                        "response_mode": "final_update",
                        "judgment_changed": True,
                        "judgment_action": "reassessed_changed",
                        "answer_source": patient_reply_source,
                        "llm_response_kind": "final_update",
                        "patient_reply_style": reply_style,
                        "patient_reply_source": patient_reply_source,
                        "update_reason": update_reason,
                        "result_changed_fields": changed_fields,
                        "reassessment_intent": reassessment_intent,
                        "reply_rendering_mode": reply_rendering_mode,
                        "llm_diagnostics": {**llm_diagnostics, "llm_response_kind": "final_update"},
                    },
                    complete=True,
                    policy_runtime_context=policy_runtime_context,
                )
                return final_result, evidence, validated_missing_fields, assistant_payload, complete

            unchanged_answer_mode = ANSWER_WITH_GUIDANCE if response_mode == REASSESS_REQUIRED else response_mode
            assistant_message, answer_llm_diagnostics = self._request_post_final_answer_with_diagnostics(
                {**merged_payload, "_force_offline_llm": force_offline_llm},
                memory.shared_memory,
                previous_final_result,
                previous_final_result=previous_final_result,
                response_mode=unchanged_answer_mode,
                policy_runtime_context=policy_runtime_context,
            )
            reply_style = None
            answer_source = "llm"
            patient_reply_source = "llm"
            reassessment_intent = self._call_with_supported_kwargs(
                self.config.reassessment_intent_inferer or infer_reassessment_intent,
                merged_payload.get("message", ""),
                changed_fields,
                consultation_round=consultation_round,
                message_type="final_no_change",
                update_reason=update_reason,
                final_result=previous_final_result,
                previous_final_result=previous_final_result,
            )
            reply_rendering_mode = infer_reply_rendering_mode(
                reassessment_intent,
                message_type=unchanged_answer_mode,
            )
            if not assistant_message:
                assistant_message, reply_style, patient_reply_source = self._build_post_final_answer_fallback(
                    previous_final_result,
                    response_mode=unchanged_answer_mode,
                    previous_final_result=previous_final_result,
                    payload=merged_payload,
                    memory=memory,
                )
                answer_source = "fallback_formatter"
            progress.last_question_focus = None
            progress.last_question_text = assistant_message
            consultation_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                merged_payload=merged_payload,
                memory=memory,
                consultation_result=previous_final_result,
                missing_fields=[],
                assistant_payload={
                    "assistant_message": assistant_message,
                    "message_type": unchanged_answer_mode,
                    "response_mode": unchanged_answer_mode,
                    "judgment_changed": False,
                    "judgment_action": "reassessed_unchanged",
                    "answer_source": answer_source,
                    "llm_response_kind": "direct_answer",
                    "patient_reply_style": reply_style,
                    "patient_reply_source": patient_reply_source,
                    "update_reason": update_reason,
                    "result_changed_fields": [],
                    "reassessment_intent": reassessment_intent,
                    "reply_rendering_mode": reply_rendering_mode,
                    "llm_diagnostics": {
                        **llm_diagnostics,
                        **answer_llm_diagnostics,
                        "llm_response_kind": "direct_answer",
                    },
                },
                complete=True,
                policy_runtime_context=policy_runtime_context,
            )
            return consultation_result, evidence, validated_missing_fields, assistant_payload, complete

        minimum_reply_count_before_complete = self.config.min_patient_reply_count_before_complete if consultation_round == 1 else 0

        if missing_fields or progress.patient_reply_count < minimum_reply_count_before_complete:
            progress.followup_count += 1
            question_focus = missing_fields[0] if missing_fields else None
            llm_followup_message = None
            llm_followup_message, followup_llm_diagnostics = self._request_follow_up_message_with_diagnostics(
                {**merged_payload, "_force_offline_llm": force_offline_llm},
                memory.shared_memory,
                missing_fields,
                question_focus=question_focus,
                policy_runtime_context=policy_runtime_context,
            )
            if question_focus:
                asked_count = sum(1 for item in progress.asked_fields_history if item == question_focus)
                assistant_message = llm_followup_message
                if not assistant_message:
                    assistant_message = self._call_with_supported_kwargs(
                        self.config.build_follow_up_question,
                        question_focus,
                        memory.shared_memory,
                        asked_count=asked_count,
                        is_repeated=question_focus == progress.last_question_focus and asked_count > 0,
                        last_question_text=progress.last_question_text,
                        policy_runtime_context=policy_runtime_context,
                    )
                progress.asked_fields_history.append(question_focus)
                progress.last_question_focus = question_focus
            else:
                assistant_message = llm_followup_message
                if not assistant_message:
                    assistant_message = self._call_with_supported_kwargs(
                        self.config.build_transition_follow_up_question,
                        memory.shared_memory,
                        policy_runtime_context=policy_runtime_context,
                    )
                progress.last_question_focus = None
            progress.last_question_text = assistant_message
            consultation_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                merged_payload=merged_payload,
                memory=memory,
                consultation_result=fallback,
                missing_fields=missing_fields,
                assistant_payload={
                    "assistant_message": assistant_message,
                    "message_type": "followup",
                    "response_mode": "followup",
                    "judgment_changed": False,
                    "judgment_action": "none",
                    "answer_source": "llm" if llm_followup_message else "fallback_formatter",
                    "llm_response_kind": "followup_question",
                    "llm_diagnostics": followup_llm_diagnostics,
                },
                complete=False,
                policy_runtime_context=policy_runtime_context,
            )
            return consultation_result, evidence, validated_missing_fields, assistant_payload, complete

        optional_question_focus = self._select_optional_round1_followup_focus(
            memory=memory,
            mode=mode,
            consultation_round=consultation_round,
            missing_fields=missing_fields,
        )
        if optional_question_focus:
            optional_message, optional_llm_diagnostics = self._request_follow_up_message_with_diagnostics(
                {
                    **merged_payload,
                    "_force_offline_llm": force_offline_llm,
                    "_allow_no_followup": True,
                    "optional_followup_focus": optional_question_focus,
                },
                memory.shared_memory,
                [],
                question_focus=optional_question_focus,
                policy_runtime_context=policy_runtime_context,
            )
            if optional_message:
                progress.followup_count += 1
                progress.asked_fields_history.append(optional_question_focus)
                progress.last_question_focus = optional_question_focus
                progress.last_question_text = optional_message
                consultation_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                    merged_payload=merged_payload,
                    memory=memory,
                    consultation_result=fallback,
                    missing_fields=[],
                    assistant_payload={
                        "assistant_message": optional_message,
                        "message_type": "followup",
                        "response_mode": "followup",
                        "judgment_changed": False,
                        "judgment_action": "none",
                        "answer_source": "llm",
                        "llm_response_kind": "optional_followup_question",
                        "llm_diagnostics": optional_llm_diagnostics,
                    },
                    complete=False,
                    policy_runtime_context=policy_runtime_context,
                )
                return consultation_result, evidence, validated_missing_fields, assistant_payload, complete

        llm_result, llm_diagnostics = self._request_consultation_with_diagnostics(
            {**merged_payload, "_force_offline_llm": force_offline_llm},
            memory.shared_memory,
            missing_fields,
            historical_records_template=merged_payload.get("historical_records_template"),
            policy_runtime_context=policy_runtime_context,
        )
        final_result = self._call_with_supported_kwargs(
            self.config.validate_result,
            llm_result,
            fallback,
            merged_payload,
            policy_runtime_context=policy_runtime_context,
            memory=memory,
            mode=mode,
            complete=True,
        )
        changed_fields: list[str] = []
        update_reason = None
        reassessment_intent = None
        reply_rendering_mode = None
        assistant_message, reply_style, patient_reply_source = self._build_patient_reply(
            final_result,
            message_type="final",
            consultation_round=consultation_round,
            complete=True,
            progress_completed=progress.completed,
            previous_final_result=previous_final_result,
            changed_fields=changed_fields,
            update_reason=update_reason,
            reassessment_intent=reassessment_intent,
            reply_rendering_mode=reply_rendering_mode,
            payload=merged_payload,
            memory=memory,
        )
        progress.last_question_focus = None
        progress.last_question_text = assistant_message
        final_result, validated_missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
            merged_payload=merged_payload,
            memory=memory,
            consultation_result=final_result,
            missing_fields=[],
            assistant_payload={
                "assistant_message": assistant_message,
                "message_type": "final",
                "response_mode": "final",
                "judgment_changed": False,
                "judgment_action": "none",
                "answer_source": patient_reply_source,
                "llm_response_kind": "final_update",
                "patient_reply_style": reply_style,
                "patient_reply_source": patient_reply_source,
                "update_reason": update_reason,
                "result_changed_fields": changed_fields,
                "reassessment_intent": reassessment_intent,
                "reply_rendering_mode": reply_rendering_mode,
                "llm_diagnostics": {**llm_diagnostics, "llm_response_kind": "final_update"},
            },
            complete=True,
            policy_runtime_context=policy_runtime_context,
        )
        return final_result, evidence, validated_missing_fields, assistant_payload, complete

    def persist_result(
        self,
        *,
        patient_id: str,
        session_id: str,
        payload: dict,
        memory,
        dialogue_state,
        consultation_result: dict,
        evidence: list[dict],
        missing_fields: list[str],
        assistant_payload: dict,
        complete: bool,
    ):
        base_timestamp = datetime.now(timezone.utc)
        timestamp = base_timestamp.isoformat()
        shared = memory.shared_memory
        private_memory = memory.private_memory
        progress = memory.consultation_progress
        was_completed = progress.completed
        progress.completed = complete
        message_type = assistant_payload.get("message_type", "final" if complete else "followup")
        assistant_message = assistant_payload.get("assistant_message", "")

        shared["clinical_memory"]["last_department"] = consultation_result.get("department")
        private_memory["dialogue_state"] = dialogue_state.value
        private_memory["assistant_message"] = assistant_message
        private_memory["missing_fields"] = missing_fields
        private_memory["evidence"] = evidence
        private_memory["message_type"] = message_type
        private_memory["response_mode"] = assistant_payload.get("response_mode") or message_type
        private_memory["judgment_changed"] = bool(assistant_payload.get("judgment_changed", False))
        private_memory["judgment_action"] = assistant_payload.get("judgment_action")
        private_memory["answer_source"] = assistant_payload.get("answer_source")
        private_memory["llm_response_kind"] = assistant_payload.get("llm_response_kind")
        private_memory["final_result"] = consultation_result if complete else private_memory.get("final_result", {})
        private_memory["patient_reply_style"] = assistant_payload.get("patient_reply_style")
        private_memory["patient_reply_source"] = assistant_payload.get("patient_reply_source")
        private_memory["update_reason"] = assistant_payload.get("update_reason")
        private_memory["result_changed_fields"] = list(assistant_payload.get("result_changed_fields") or [])
        private_memory["reassessment_intent"] = assistant_payload.get("reassessment_intent")
        private_memory["reply_rendering_mode"] = assistant_payload.get("reply_rendering_mode")
        private_memory["llm_diagnostics"] = dict(assistant_payload.get("llm_diagnostics") or {})
        private_memory["pending_auto_continue"] = bool(assistant_payload.get("pending_auto_continue", False))
        private_memory[self.config.progress_memory_key] = progress.to_dict()
        private_memory["latest_summary"] = {
            "department": consultation_result.get("department"),
            "priority": consultation_result.get("priority"),
            "complete": complete,
            "message_type": message_type,
            "response_mode": private_memory.get("response_mode"),
            "judgment_changed": bool(private_memory.get("judgment_changed", False)),
            "judgment_action": private_memory.get("judgment_action"),
            "red_flags": consultation_result.get("red_flags", []),
            "update_reason": assistant_payload.get("update_reason"),
            "result_changed_fields": list(assistant_payload.get("result_changed_fields") or []),
            "reassessment_intent": assistant_payload.get("reassessment_intent"),
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory, agent_type=self.config.agent_type)
        self.session_repo.update_state(session_id, dialogue_state.value)
        assistant_turn_index = 0
        for extra_turn in assistant_payload.get("extra_turns") or []:
            extra_content = str(extra_turn.get("content") or extra_turn.get("assistant_message") or "").strip()
            if not extra_content:
                continue
            extra_timestamp = (base_timestamp + timedelta(milliseconds=assistant_turn_index * 900)).isoformat()
            assistant_turn_index += 1
            extra_message_type = str(extra_turn.get("message_type") or "assistant_extra")
            extra_metadata = self.build_assistant_turn_metadata(consultation_result, extra_message_type, progress, private_memory)
            extra_metadata.update(dict(extra_turn.get("metadata") or {}))
            extra_metadata["agent_type"] = self.config.agent_type
            extra_metadata["message_type"] = extra_message_type
            extra_metadata["response_mode"] = extra_turn.get("response_mode") or extra_metadata.get("response_mode")
            extra_metadata["llm_response_kind"] = extra_turn.get("llm_response_kind") or extra_metadata.get("llm_response_kind")
            self.session_repo.append_turn(
                session_id,
                patient_id,
                "assistant",
                extra_content,
                extra_timestamp,
                metadata=extra_metadata,
            )
        assistant_timestamp = (base_timestamp + timedelta(milliseconds=assistant_turn_index * 900)).isoformat()
        assistant_metadata = self.build_assistant_turn_metadata(consultation_result, message_type, progress, private_memory)
        if assistant_payload.get("pending_auto_continue"):
            assistant_metadata["pending_auto_continue"] = True
            assistant_metadata["pending_stage"] = private_memory.get("pending_physical_exam_stage")
        if assistant_payload.get("physical_exam") is not None:
            assistant_metadata["physical_exam"] = assistant_payload.get("physical_exam")
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_message,
            assistant_timestamp,
            metadata=assistant_metadata,
        )

        existing_patient = self.patient_repo.get(patient_id)
        next_patient_state, next_location = self.resolve_patient_transition(
            existing_patient=existing_patient,
            consultation_result=consultation_result,
            complete=complete,
            was_completed=was_completed,
            private_memory=private_memory,
        )

        patient_update_payload = {
            "session_id": session_id,
            "visit_id": payload.get("visit_id"),
            "priority": consultation_result.get("priority", existing_patient["priority"] if existing_patient else None),
        }
        if next_patient_state:
            patient_update_payload["lifecycle_state"] = next_patient_state.value
            if next_location:
                patient_update_payload["location"] = next_location
        self.patient_repo.update_patient(patient_id, **patient_update_payload)
        if next_patient_state:
            self.bus.publish(
                PATIENT_STATE_CHANGED,
                {
                    "patient_id": patient_id,
                    "lifecycle_state": next_patient_state.value,
                },
            )

        visit_id = payload.get("visit_id")
        visit_row = self.visit_repo.get(visit_id) if visit_id and self.visit_repo is not None else None
        self.after_persist_result(
            patient_id=patient_id,
            session_id=session_id,
            payload=payload,
            memory=memory,
            consultation_result=consultation_result,
            evidence=evidence,
            missing_fields=missing_fields,
            assistant_message=assistant_message,
            message_type=message_type,
            complete=complete,
            was_completed=was_completed,
            visit_row=visit_row,
            timestamp=assistant_timestamp,
        )

    def build_response(self, patient_id: str, session_id: str):
        patient_view = self.get_patient_view(patient_id)
        session_row = self.session_repo.get(session_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=self.config.agent_type)
        progress = self._get_progress(private_memory)
        dialogue = {
            "status": private_memory.get("dialogue_state", self.config.state_enum.IDLE.value),
            "assistant_message": private_memory.get("assistant_message", ""),
            "missing_fields": private_memory.get("missing_fields", []),
            "turns": self.session_repo.list_turns(session_id),
            "message_type": private_memory.get("message_type", "followup"),
            "response_mode": private_memory.get("response_mode"),
            "judgment_changed": bool(private_memory.get("judgment_changed", False)),
            "judgment_action": private_memory.get("judgment_action"),
            "answer_source": private_memory.get("answer_source"),
            "llm_response_kind": private_memory.get("llm_response_kind"),
            "question_focus": progress.last_question_focus,
            "asked_fields_history": progress.asked_fields_history,
            "final_result": private_memory.get("final_result", {}),
            "update_reason": private_memory.get("update_reason"),
            "result_changed_fields": private_memory.get("result_changed_fields", []),
            "reassessment_intent": private_memory.get("reassessment_intent"),
            "reply_rendering_mode": private_memory.get("reply_rendering_mode"),
            "patient_reply_source": private_memory.get("patient_reply_source"),
            "patient_reply_style": private_memory.get("patient_reply_style"),
            "response_source": (private_memory.get("llm_diagnostics") or {}).get("response_source"),
            "pending_auto_continue": bool(private_memory.get("pending_auto_continue", False)),
            "pending_stage": private_memory.get("pending_physical_exam_stage"),
        }
        dialogue.update(self.extend_dialogue_payload(private_memory, progress))
        visit_state = None
        if patient_view and getattr(patient_view, "visit_state", None) is not None:
            visit_state = patient_view.visit_state.value
        elif isinstance(patient_view, dict):
            raw_visit_state = patient_view.get("visit_state")
            visit_state = getattr(raw_visit_state, "value", raw_visit_state)
        patient_payload = patient_view.model_dump() if hasattr(patient_view, "model_dump") else patient_view
        return {
            "ok": True,
            "session_id": session_id,
            "visit_id": session_row.get("visit_id") if session_row else None,
            "visit_state": visit_state,
            "patient": patient_payload,
            "dialogue": dialogue,
        }

    def configure_private_memory_defaults(self, private_memory: dict, payload: dict) -> None:
        pass

    def after_prepare_context(self, payload: dict, shared_memory: dict, private_memory: dict) -> None:
        pass

    def load_historical_records_template(self, *, patient_id: str, visit_id: str) -> dict:
        return {"current_visit": None, "previous_visits": [], "clinician_note": ""}

    def extend_merged_payload(self, merged: dict, payload: dict, shared_memory: dict, private_memory: dict) -> None:
        pass

    def build_assistant_turn_metadata(self, consultation_result: dict, message_type: str, progress, private_memory: dict) -> dict:
        return {
            "agent_type": self.config.agent_type,
            "message_type": message_type,
            "response_mode": private_memory.get("response_mode"),
            "judgment_changed": bool(private_memory.get("judgment_changed", False)),
            "judgment_action": private_memory.get("judgment_action"),
            "answer_source": private_memory.get("answer_source"),
            "llm_response_kind": private_memory.get("llm_response_kind"),
            "department": consultation_result.get("department"),
            "priority": consultation_result.get("priority"),
            "question_focus": progress.last_question_focus,
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
        return None, None

    def after_persist_result(self, **kwargs) -> None:
        pass

    def extend_dialogue_payload(self, private_memory: dict, progress) -> dict:
        return {}

    def build_policy_snapshot(
        self,
        *,
        merged_payload: dict,
        memory,
        consultation_result: dict,
        missing_fields: list[str],
        assistant_payload: dict,
        complete: bool,
        policy_runtime_context,
    ) -> dict | None:
        if policy_runtime_context is None or policy_runtime_context.primary_card is None:
            return None
        clinical = memory.shared_memory.get("clinical_memory") or {}
        chief_complaint = str(merged_payload.get("chief_complaint") or clinical.get("chief_complaint") or "").strip()
        symptoms = [str(item).strip() for item in (clinical.get("symptoms") or []) if str(item).strip()]
        final_red_flags = consultation_result.get("red_flags") or clinical.get("risk_flags") or []
        red_flags = [str(item).strip() for item in final_red_flags if str(item).strip()]
        priority = str(consultation_result.get("priority") or "").strip().upper()
        urgency = "urgent" if priority == "H" or red_flags else "routine"
        if complete and red_flags:
            stage = "escalation"
            next_action = "escalate_urgency"
        elif complete:
            stage = "summary"
            next_action = "summarize_case"
        elif red_flags:
            stage = "red_flag_screening"
            next_action = "escalate_urgency"
        elif assistant_payload.get("message_type") == "followup":
            stage = "history_taking" if chief_complaint else "chief_complaint_clarification"
            next_action = "ask_follow_up"
        elif missing_fields:
            stage = "history_taking" if chief_complaint else "chief_complaint_clarification"
            next_action = "ask_follow_up"
        else:
            stage = "continue_consultation"
            next_action = "continue_consultation"
        summary = chief_complaint or ", ".join(symptoms)
        return {
            "agent_role": policy_runtime_context.primary_card.agent_scope,
            "consultation_stage": stage,
            "chief_complaint": chief_complaint,
            "key_symptoms_collected": symptoms,
            "missing_information": list(missing_fields),
            "red_flags": red_flags,
            "urgency": urgency,
            "follow_up_questions": [assistant_payload.get("assistant_message", "")] if assistant_payload.get("message_type") == "followup" else [],
            "patient_summary": summary,
            "next_action": next_action,
        }

    def apply_policy_snapshot_validation(
        self,
        *,
        merged_payload: dict,
        memory,
        consultation_result: dict,
        missing_fields: list[str],
        assistant_payload: dict,
        complete: bool,
        policy_runtime_context,
    ) -> tuple[dict, list[str], dict, bool]:
        snapshot = self.build_policy_snapshot(
            merged_payload=merged_payload,
            memory=memory,
            consultation_result=consultation_result,
            missing_fields=missing_fields,
            assistant_payload=assistant_payload,
            complete=complete,
            policy_runtime_context=policy_runtime_context,
        )
        if snapshot is None:
            return consultation_result, missing_fields, assistant_payload, complete

        validation = self.policy_runtime.validate_snapshot(snapshot, policy_runtime_context)
        if self.config.policy_validator is not None:
            custom_validation = self._call_with_supported_kwargs(
                self.config.policy_validator,
                snapshot,
                policy_runtime_context,
                merged_payload,
                validation_result=validation,
                memory=memory,
                consultation_result=consultation_result,
                assistant_payload=assistant_payload,
                complete=complete,
            )
            if isinstance(custom_validation, ClinicalPolicyValidatorResult):
                validation = custom_validation

        memory.private_memory["latest_policy"] = {
            "card_id": policy_runtime_context.primary_card.id,
            "phase": policy_runtime_context.policy_context.get("phase"),
            "snapshot": validation.normalized_output or snapshot,
            "violations": list(validation.violations),
            "ok": validation.ok,
        }
        memory.private_memory["latest_payload"] = dict(merged_payload)

        if validation.ok:
            return consultation_result, missing_fields, assistant_payload, complete

        fallback = None
        if self.config.policy_fallback_builder is not None:
            fallback = self._call_with_supported_kwargs(
                self.config.policy_fallback_builder,
                policy_runtime_context,
                merged_payload,
                validation.fallback_reason,
                snapshot=snapshot,
                validation_result=validation,
                memory=memory,
                consultation_result=consultation_result,
                assistant_payload=assistant_payload,
                complete=complete,
                policy_runtime=self.policy_runtime,
            )
        if isinstance(fallback, dict):
            consultation_result = fallback.get("consultation_result", consultation_result)
            missing_fields = fallback.get("missing_fields", missing_fields)
            assistant_payload = fallback.get("assistant_payload", assistant_payload)
            complete = bool(fallback.get("complete", complete))
            memory.private_memory["latest_policy"]["fallback_reason"] = validation.fallback_reason
        return consultation_result, missing_fields, assistant_payload, complete

    @staticmethod
    def _normalize_consultation_round(value) -> int:
        try:
            return max(1, int(value or 1))
        except Exception:
            return 1

    @staticmethod
    def _normalize_department_token(value: str | None) -> str:
        return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())

    def _department_aliases(self) -> set[str]:
        values = {
            self.config.agent_type,
            self.config.agent_type.replace("_", " "),
            self.config.route_slug,
            self.config.route_slug.replace("-", " "),
            self.config.metadata.get("department_id"),
            self.config.metadata.get("department_label"),
        }
        aliases = {self._normalize_department_token(value) for value in values if str(value or "").strip()}
        aliases.discard("")
        return aliases

    @staticmethod
    def _blank_clinical_memory() -> dict:
        return {
            "chief_complaint": None,
            "symptoms": [],
            "onset_time": None,
            "vitals": {},
            "risk_flags": [],
        }

    def _ensure_shared_memory_shape(self, shared_memory: dict | None, patient_name: str) -> dict:
        payload = deepcopy(shared_memory or {})
        profile = payload.setdefault("profile", {})
        clinical = payload.setdefault("clinical_memory", {})
        profile.setdefault("name", patient_name)
        profile.setdefault("allergies", [])
        profile.setdefault("allergy_status", "unknown")
        profile.setdefault("chronic_conditions", [])
        profile.setdefault("chronic_conditions_status", "known" if profile.get("chronic_conditions") else "unknown")
        clinical.setdefault("chief_complaint", None)
        clinical.setdefault("symptoms", [])
        clinical.setdefault("onset_time", None)
        clinical.setdefault("vitals", {})
        clinical.setdefault("risk_flags", [])
        return payload

    def _reset_shared_memory_for_receiving_doctor(self, shared_memory: dict, patient_name: str) -> dict:
        reset = self._ensure_shared_memory_shape(shared_memory, patient_name)
        reset["clinical_memory"] = self._blank_clinical_memory()
        return reset

    def _build_consultation_context(self, *, consultation_round: int, visit_data: dict, private_memory: dict) -> dict:
        existing = dict(private_memory.get("consultation_context") or {})
        if consultation_round >= 2:
            return {
                "intake_mode": "return_consultation",
                "doctor_memory_policy": "continuity_round2",
                "special_event_type": existing.get("special_event_type"),
                "recommended_department": existing.get("recommended_department"),
                "recommended_department_id": existing.get("recommended_department_id"),
                "handoff_reason": existing.get("handoff_reason"),
            }

        handoff = self._extract_referral_handoff(visit_data)
        if handoff is not None:
            return handoff
        return {
            "intake_mode": "standard_round1",
            "doctor_memory_policy": "shared_memory",
            "special_event_type": None,
            "recommended_department": None,
            "recommended_department_id": None,
            "handoff_reason": None,
        }

    def _build_prompt_shared_memory(self, shared_memory: dict, payload: dict) -> dict:
        prompt_shared_memory = deepcopy(shared_memory or {})
        consultation_context = dict(payload.get("consultation_context") or {})
        chart_view = payload.get("chart_view")
        if consultation_context:
            prompt_shared_memory["consultation_context"] = consultation_context
        if isinstance(payload.get("physical_exam"), dict):
            prompt_shared_memory["physical_exam"] = payload.get("physical_exam")
        if chart_view and str(consultation_context.get("intake_mode") or "").strip() == "referral_handoff":
            prompt_shared_memory["doctor_chart_view"] = chart_view
        return prompt_shared_memory

    @staticmethod
    def _augment_prompt_context_for_handoff(policy_prompt_context: str, payload: dict) -> str:
        consultation_context = dict(payload.get("consultation_context") or {})
        if str(consultation_context.get("intake_mode") or "").strip() != "referral_handoff":
            return policy_prompt_context
        handoff_instruction = (
            "Referral handoff rule: this is a fresh receiving-doctor consultation. "
            "Do not rely on hidden memory from the previous workflow or previous doctor. "
            "Use only the visible chart, available reports, and the patient's current statements."
        )
        if not policy_prompt_context:
            return handoff_instruction
        if handoff_instruction in policy_prompt_context:
            return policy_prompt_context
        return f"{policy_prompt_context}\n{handoff_instruction}"

    def _extract_referral_handoff(self, visit_data: dict) -> dict | None:
        disposition = dict(visit_data.get("disposition") or {})
        category = str(disposition.get("category") or "").strip()
        recommended_department = str(
            visit_data.get("recommended_department")
            or disposition.get("target_department")
            or ""
        ).strip()
        recommended_department_id = str(disposition.get("target_department_id") or "").strip()
        if category != "specialty_referral" and not recommended_department:
            return None
        if not bool(visit_data.get("requires_new_registration", False)):
            return None
        targets = {
            self._normalize_department_token(recommended_department),
            self._normalize_department_token(recommended_department_id),
            self._normalize_department_token((visit_data.get("carry_forward_summary") or {}).get("target_department")),
        }
        targets.discard("")
        if not targets.intersection(self._department_aliases()):
            return None
        return {
            "intake_mode": "referral_handoff",
            "doctor_memory_policy": "chart_only",
            "special_event_type": "specialty_referral",
            "recommended_department": recommended_department or None,
            "recommended_department_id": recommended_department_id or None,
            "handoff_reason": visit_data.get("handoff_reason") or disposition.get("reason"),
        }

    @staticmethod
    def _extract_previous_round_summary(visit_data: dict) -> dict | None:
        for key, value in (visit_data or {}).items():
            if key.endswith("_round1_summary") and isinstance(value, dict):
                return value
        return None
