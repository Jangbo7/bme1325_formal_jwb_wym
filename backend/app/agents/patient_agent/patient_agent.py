from __future__ import annotations

import json
from socket import timeout as socket_timeout
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from app.api.contract import ContractError
from app.llm_retry import DEFAULT_LLM_RETRIES, call_with_llm_retries
from app.agents.patient_agent.case_generator import PatientCaseGenerator
from app.agents.patient_agent.patient_policy import PatientPolicy
from app.agents.patient_agent.prompt_builder import build_reply_messages
from app.agents.patient_agent.rag_context import PatientAgentRagContext
from app.agents.patient_agent.schemas import PatientAgentTurnResult, PatientCaseCard, PatientReplyContext


ROUND2_PHASES = {"internal_medicine_round2", "consultation_round2"}


class ControlledPatientAgent:
    def __init__(self, llm_settings: dict, *, request_json=None):
        self.llm_settings = llm_settings
        self._request_json_override = request_json
        self.rag_context = PatientAgentRagContext()
        self.policy = PatientPolicy()
        self.case_generator = PatientCaseGenerator(
            request_json=self.request_json,
            rag_context=self.rag_context,
        )

    def generate_case(
        self,
        *,
        seed: str | None = None,
        department_id: str | None = None,
    ) -> PatientCaseCard:
        self._require_llm_config(stage="generate_case")
        return self.case_generator.generate(seed=seed, department_id=department_id)

    def reply(self, *, case_card: PatientCaseCard, context: PatientReplyContext) -> PatientAgentTurnResult:
        decision = self.policy.decide(case_card, context)
        self._require_llm_config(stage=context.phase or "reply")
        try:
            payload = self.request_json(
                build_reply_messages(
                    case_card=case_card,
                    context=context,
                    decision=decision,
                    constraints=self.rag_context.build_reply_constraints(),
                )
            )
        except ContractError:
            return self._fallback_turn(case_card=case_card, context=context, decision=decision)
        if not isinstance(payload, dict):
            return self._fallback_turn(case_card=case_card, context=context, decision=decision)
        try:
            result = PatientAgentTurnResult.model_validate(
                {
                    "message": payload.get("message") or "",
                    "used_facts": payload.get("used_facts") or [],
                    "follow_up_question": payload.get("follow_up_question"),
                    "policy_state": decision.model_dump(),
                }
            )
        except Exception:
            return self._fallback_turn(case_card=case_card, context=context, decision=decision)
        sanitized = self._sanitize_message(
            message=result.message,
            forbidden_terms=[case_card.hidden_diagnosis_hint, *case_card.forbidden_reveals],
        )
        follow_up = self._sanitize_message(
            message=result.follow_up_question or "",
            forbidden_terms=[case_card.hidden_diagnosis_hint, *case_card.forbidden_reveals],
        )
        final_message = sanitized.strip()
        if follow_up and decision.should_ask_follow_up:
            final_message = f"{final_message} {follow_up}".strip()
        if not final_message:
            return self._fallback_turn(case_card=case_card, context=context, decision=decision)
        result.message = final_message
        result.follow_up_question = follow_up or None
        result.policy_state = decision.model_dump()
        return result

    def request_json(self, messages: list[dict]):
        if self._request_json_override is not None:
            return self._request_json_override(messages)
        endpoint = self.llm_settings.get("endpoint")
        api_key = self.llm_settings.get("api_key")
        if not endpoint or not api_key:
            self._require_llm_config(stage="request_json")

        def _single_attempt():
            req = urlrequest.Request(
                endpoint,
                data=json.dumps(
                    {
                        "model": self.llm_settings.get("model"),
                        "messages": messages,
                        "temperature": 0.3,
                        "n": 1,
                        "stream": False,
                        "presence_penalty": 0,
                        "frequency_penalty": 0,
                    }
                ).encode("utf-8"),
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            try:
                with urlrequest.urlopen(req, timeout=18) as response:
                    raw_body = response.read().decode("utf-8")
                    data = json.loads(raw_body)
            except HTTPError as exc:
                response_excerpt = ""
                try:
                    response_excerpt = exc.read().decode("utf-8")[:400]
                except Exception:
                    response_excerpt = ""
                raise ContractError(
                    code="LLM_REQUEST_FAILED",
                    message=f"patient agent LLM request failed with upstream HTTP {exc.code}",
                    details={
                        **self._llm_context(stage="request_json"),
                        "http_status": exc.code,
                        "reason": str(exc.reason),
                        "response_excerpt": response_excerpt or None,
                        "retries": DEFAULT_LLM_RETRIES,
                    },
                    status_code=502,
                ) from exc
            except (TimeoutError, socket_timeout) as exc:
                raise ContractError(
                    code="LLM_REQUEST_FAILED",
                    message="patient agent LLM request timed out",
                    details={
                        **self._llm_context(stage="request_json"),
                        "reason": str(exc) or "timeout",
                        "timeout_seconds": 18,
                        "retries": DEFAULT_LLM_RETRIES,
                    },
                    status_code=504,
                ) from exc
            except URLError as exc:
                raise ContractError(
                    code="LLM_REQUEST_FAILED",
                    message="patient agent LLM request failed to connect",
                    details={
                        **self._llm_context(stage="request_json"),
                        "reason": str(getattr(exc, "reason", exc)),
                        "retries": DEFAULT_LLM_RETRIES,
                    },
                    status_code=502,
                ) from exc
            except json.JSONDecodeError as exc:
                raise ContractError(
                    code="LLM_RESPONSE_INVALID",
                    message="patient agent LLM returned non-JSON HTTP payload",
                    details={
                        **self._llm_context(stage="request_json"),
                        "reason": str(exc),
                        "retries": DEFAULT_LLM_RETRIES,
                    },
                    status_code=502,
                ) from exc
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

        try:
            return call_with_llm_retries(_single_attempt, retries=DEFAULT_LLM_RETRIES)
        except ValueError:
            return None

    @staticmethod
    def extract_text_from_response(data):
        if isinstance(data, str):
            return data.strip()
        if isinstance(data, list):
            return " ".join([ControlledPatientAgent.extract_text_from_response(item) for item in data if item]).strip()
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

    def _fallback_turn(
        self,
        *,
        case_card: PatientCaseCard,
        context: PatientReplyContext,
        decision,
    ) -> PatientAgentTurnResult:
        symptoms = ", ".join(case_card.symptom_facts.symptoms[:3])
        if context.phase in ROUND2_PHASES and context.known_test_results:
            message = "I completed the test and want to understand the report and next steps."
        elif "allergies" in decision.allowed_fact_keys and case_card.patient_profile.allergies:
            message = f"My symptoms are {symptoms}. I also have an allergy history."
        else:
            message = f"My main problem is {case_card.chief_complaint.lower()}, and the symptoms are {symptoms}."
        return PatientAgentTurnResult(
            message=self._sanitize_message(message, [case_card.hidden_diagnosis_hint, *case_card.forbidden_reveals]),
            used_facts=list(decision.allowed_fact_keys),
            follow_up_question=None,
            policy_state=decision.model_dump(),
        )

    @staticmethod
    def _sanitize_message(message: str, forbidden_terms: list[str]) -> str:
        cleaned = (message or "").strip()
        for term in forbidden_terms:
            term = (term or "").strip()
            if not term:
                continue
            cleaned = cleaned.replace(term, "[redacted]")
            cleaned = cleaned.replace(term.lower(), "[redacted]")
            cleaned = cleaned.replace(term.upper(), "[redacted]")
        cleaned = " ".join(cleaned.split())
        return cleaned

    def _require_llm_config(self, *, stage: str) -> None:
        missing: list[str] = []
        if not self.llm_settings.get("api_key"):
            missing.append("api_key")
        if not self.llm_settings.get("endpoint"):
            missing.append("endpoint")
        if not self.llm_settings.get("model"):
            missing.append("model")
        if missing:
            raise ContractError(
                code="LLM_UNAVAILABLE",
                message="patient agent LLM configuration is unavailable",
                details={
                    **self._llm_context(stage=stage),
                    "missing": missing,
                },
                status_code=503,
            )

    def _llm_context(self, *, stage: str) -> dict:
        return {
            "agent": "patient_agent",
            "stage": stage,
            "endpoint": self.llm_settings.get("endpoint"),
            "model": self.llm_settings.get("model"),
        }
