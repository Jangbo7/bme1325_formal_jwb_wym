import json
import inspect
from datetime import datetime, timezone
from urllib import request as urlrequest

from app.agents.clinical_policy import ClinicalPolicyRuntime, ClinicalPolicyValidatorResult
from app.agents.department_runtime.config import DepartmentAgentConfig
from app.agents.department_runtime.replies import (
    infer_reassessment_intent,
    infer_reply_rendering_mode,
    default_patient_reply_from_result,
    infer_result_changed_fields,
    infer_update_reason,
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
        self.policy_runtime = ClinicalPolicyRuntime()
        self._policy_registry = None

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
        shared_memory = self.memory_repo.get_shared_memory(patient_id, patient_name)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=self.config.agent_type)
        turns = self.session_repo.list_turns(session_id)

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

        clinical = shared_memory["clinical_memory"]
        clinical["symptoms"] = self.config.merge_unique(
            clinical.get("symptoms"),
            self.config.split_symptoms(payload.get("symptoms", "")),
        )
        clinical["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint") or payload.get("symptoms", "")
        clinical["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        clinical["vitals"] = self.config.merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        clinical["risk_flags"] = self.config.derive_risk_flags(clinical.get("symptoms") or [], clinical.get("vitals") or {})

        self.configure_private_memory_defaults(private_memory, payload)
        private_memory["force_offline_llm"] = bool(payload.get("_force_offline_llm") or private_memory.get("force_offline_llm"))
        private_memory["dialogue_state"] = dialogue_state.value
        consultation_round = self._normalize_consultation_round(
            private_memory.get("consultation_round") or payload.get("_consultation_round") or payload.get("consultation_round")
        )
        if payload.get("debug_read_historical_records") or consultation_round >= 2:
            template = self.load_historical_records_template(
                patient_id=patient_id,
                visit_id=str(payload.get("visit_id") or ""),
            )
            private_memory["historical_records_template"] = template
            private_memory["historical_records_note"] = template.get("clinician_note") or ""

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
        merged["symptoms"] = payload.get("symptoms") or ", ".join(clinical.get("symptoms") or [])
        merged["chief_complaint"] = payload.get("chief_complaint") or clinical.get("chief_complaint")
        merged["vitals"] = self.config.merge_vitals(clinical.get("vitals") or {}, payload.get("vitals") or {})
        merged["onset_time"] = payload.get("onset_time") or clinical.get("onset_time")
        merged["allergies"] = payload.get("allergies") or shared_memory["profile"].get("allergies") or []
        merged["visit_id"] = payload.get("visit_id")

        visit_id = payload.get("visit_id")
        if visit_id and self.visit_repo is not None:
            visit_row = self.visit_repo.get(visit_id)
            visit_data = self._decode_visit_data(visit_row) if visit_row else {}
            simulated_report = visit_data.get("simulated_report")
            diagnostic_session = visit_data.get("diagnostic_session")
            if isinstance(simulated_report, dict):
                merged["simulated_report"] = simulated_report
            if isinstance(diagnostic_session, dict):
                merged["diagnostic_session"] = diagnostic_session
            if merged["consultation_round"] >= 2:
                previous_round_summary = self._extract_previous_round_summary(visit_data)
                if isinstance(previous_round_summary, dict):
                    merged["previous_round_summary"] = previous_round_summary
        if private_memory and isinstance(private_memory.get("historical_records_template"), dict):
            merged["historical_records_template"] = private_memory.get("historical_records_template")
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
                    shared_memory,
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
        req = urlrequest.Request(
            self.llm_settings["endpoint"],
            data=json.dumps(
                {
                    "model": self.llm_settings["model"],
                    "messages": self.build_consultation_llm_messages(
                        payload,
                        shared_memory,
                        missing_fields,
                        historical_records_template=historical_records_template,
                        previous_final_result=previous_final_result,
                        post_final_reassessment=post_final_reassessment,
                        policy_runtime_context=policy_runtime_context,
                    ),
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
        messages = self._call_with_supported_kwargs(
            self.config.build_follow_up_llm_messages,
            shared_memory,
            payload.get("message", ""),
            missing_fields,
            question_focus=question_focus,
            payload=payload,
            policy_runtime_context=policy_runtime_context,
        )
        if not messages:
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
        parsed_text = text.strip()
        try:
            payload_json = json.loads(parsed_text)
            if isinstance(payload_json, dict):
                for key in ("assistant_message", "follow_up_question", "question", "message", "reply"):
                    value = payload_json.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
        except Exception:
            pass
        return parsed_text or None

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
            assistant_message = self._call_with_supported_kwargs(
                self.config.build_initial_message,
                memory.shared_memory,
                progress,
                consultation_round=consultation_round,
                policy_runtime_context=policy_runtime_context,
            )
            historical_note = str(memory.private_memory.get("historical_records_note") or "").strip()
            if historical_note:
                assistant_message = f"[History reviewed] {historical_note}\n{assistant_message}"
            assistant_payload = {"assistant_message": assistant_message, "message_type": "followup"}
            consultation_result, missing_fields, assistant_payload, complete = self.apply_policy_snapshot_validation(
                merged_payload=merged_payload,
                memory=memory,
                consultation_result=fallback,
                missing_fields=self._call_with_supported_kwargs(
                    self.config.build_missing_fields,
                    memory.shared_memory,
                    policy_runtime_context=policy_runtime_context,
                ),
                assistant_payload=assistant_payload,
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

        if is_post_final_reassessment:
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
            message_type = "final_update" if changed else "final_no_change"
            changed_fields = infer_result_changed_fields(previous_final_result, final_result) if changed else []
            update_reason = self._call_with_supported_kwargs(
                self.config.result_update_reason_inferer or infer_update_reason,
                merged_payload.get("message", ""),
                changed_fields,
                consultation_round=consultation_round,
                message_type=message_type,
                final_result=final_result,
                previous_final_result=previous_final_result,
            )
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
                    "patient_reply_style": reply_style,
                    "patient_reply_source": patient_reply_source,
                    "update_reason": update_reason,
                    "result_changed_fields": changed_fields,
                    "reassessment_intent": reassessment_intent,
                    "reply_rendering_mode": reply_rendering_mode,
                    "llm_diagnostics": llm_diagnostics,
                },
                complete=True,
                policy_runtime_context=policy_runtime_context,
            )
            return final_result, evidence, validated_missing_fields, assistant_payload, complete

        minimum_reply_count_before_complete = self.config.min_patient_reply_count_before_complete if consultation_round == 1 else 0

        if missing_fields or progress.patient_reply_count < minimum_reply_count_before_complete:
            progress.followup_count += 1
            question_focus = missing_fields[0] if missing_fields else None
            llm_followup_message = None
            if mode == "continue_session" and progress.patient_reply_count >= 1:
                try:
                    llm_followup_message = self.request_follow_up_message_from_llm(
                        {**merged_payload, "_force_offline_llm": force_offline_llm},
                        memory.shared_memory,
                        missing_fields,
                        question_focus=question_focus,
                        policy_runtime_context=policy_runtime_context,
                    )
                except Exception:
                    llm_followup_message = None
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
                assistant_payload={"assistant_message": assistant_message, "message_type": "followup"},
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
                "patient_reply_style": reply_style,
                "patient_reply_source": patient_reply_source,
                "update_reason": update_reason,
                "result_changed_fields": changed_fields,
                "reassessment_intent": reassessment_intent,
                "reply_rendering_mode": reply_rendering_mode,
                "llm_diagnostics": llm_diagnostics,
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
        timestamp = now_iso()
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
        private_memory["final_result"] = consultation_result if complete else private_memory.get("final_result", {})
        private_memory["patient_reply_style"] = assistant_payload.get("patient_reply_style")
        private_memory["patient_reply_source"] = assistant_payload.get("patient_reply_source")
        private_memory["update_reason"] = assistant_payload.get("update_reason")
        private_memory["result_changed_fields"] = list(assistant_payload.get("result_changed_fields") or [])
        private_memory["reassessment_intent"] = assistant_payload.get("reassessment_intent")
        private_memory["reply_rendering_mode"] = assistant_payload.get("reply_rendering_mode")
        private_memory["llm_diagnostics"] = dict(assistant_payload.get("llm_diagnostics") or {})
        private_memory[self.config.progress_memory_key] = progress.to_dict()
        private_memory["latest_summary"] = {
            "department": consultation_result.get("department"),
            "priority": consultation_result.get("priority"),
            "complete": complete,
            "message_type": message_type,
            "red_flags": consultation_result.get("red_flags", []),
            "update_reason": assistant_payload.get("update_reason"),
            "result_changed_fields": list(assistant_payload.get("result_changed_fields") or []),
            "reassessment_intent": assistant_payload.get("reassessment_intent"),
        }

        self.memory_repo.save_shared_memory(patient_id, shared)
        self.memory_repo.save_agent_session_memory(session_id, patient_id, private_memory, agent_type=self.config.agent_type)
        self.session_repo.update_state(session_id, dialogue_state.value)
        self.session_repo.append_turn(
            session_id,
            patient_id,
            "assistant",
            assistant_message,
            timestamp,
            metadata=self.build_assistant_turn_metadata(consultation_result, message_type, progress, private_memory),
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
            timestamp=timestamp,
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
    def _extract_previous_round_summary(visit_data: dict) -> dict | None:
        for key, value in (visit_data or {}).items():
            if key.endswith("_round1_summary") and isinstance(value, dict):
                return value
        return None
