from __future__ import annotations

import json
from typing import Any

from app.agents.clinical_policy.models import (
    ClinicalPolicyCard,
    ClinicalPolicyMatchResult,
    ClinicalPolicyRuntimeContext,
    ClinicalPolicyValidatorResult,
)


class ClinicalPolicyRuntime:
    def build_runtime_context(self, match_result: ClinicalPolicyMatchResult) -> ClinicalPolicyRuntimeContext:
        primary_card = match_result.primary_card
        if primary_card is None:
            return ClinicalPolicyRuntimeContext()
        return ClinicalPolicyRuntimeContext(
            matched_cards=match_result.matched_cards,
            primary_card=primary_card,
            policy_context=dict(match_result.policy_context),
            prompt_policy_context=self.build_prompt_context(primary_card, match_result.policy_context),
            output_contract={
                "output_mode": primary_card.output_mode,
                "output_schema_name": primary_card.output_schema_name,
                "required_fields": list(primary_card.required_fields),
                "allowed_next_actions": list(primary_card.allowed_next_actions),
            },
            validator_contract={
                "forbidden_actions": list(primary_card.forbidden_actions),
                "max_questions_per_turn": int(primary_card.question_policy.get("max_questions_per_turn") or 3),
                "red_flags": list(primary_card.red_flags),
            },
            fallback_contract={
                "allowed_outputs": list(primary_card.allowed_outputs),
                "default_urgency": primary_card.escalation_policy.get("default_urgency", "routine"),
                "red_flag_urgency": primary_card.escalation_policy.get("red_flag_urgency", "urgent"),
            },
        )

    def build_prompt_context(self, card: ClinicalPolicyCard, policy_context: dict[str, Any]) -> str:
        sections = [
            f"Policy card: {card.id}",
            f"Phase: {policy_context.get('phase') or ''}",
        ]
        if card.role_boundary:
            sections.append(f"Role boundary: {card.role_boundary}")
        if card.collection_targets:
            target_names = [str(target.get('prompt_label') or target.get('field')) for target in card.collection_targets]
            sections.append(f"Collection targets: {', '.join(target_names)}")
        if card.question_policy:
            sections.append(f"Question policy: {json.dumps(card.question_policy, ensure_ascii=False, sort_keys=True)}")
        if card.forbidden_actions:
            sections.append(f"Forbidden actions: {', '.join(card.forbidden_actions)}")
        if card.allowed_next_actions:
            sections.append(f"Allowed next actions: {', '.join(card.allowed_next_actions)}")
        if card.system_rules:
            sections.append(f"System rules: {' | '.join(card.system_rules)}")
        if card.style_rules:
            sections.append(f"Style rules: {' | '.join(card.style_rules)}")
        if card.summary_rules:
            sections.append(f"Summary rules: {' | '.join(card.summary_rules)}")
        return "\n".join(section for section in sections if section.strip())

    def validate_snapshot(
        self,
        snapshot: dict[str, Any] | None,
        runtime_context: ClinicalPolicyRuntimeContext | None,
    ) -> ClinicalPolicyValidatorResult:
        if runtime_context is None or runtime_context.primary_card is None:
            return ClinicalPolicyValidatorResult(ok=True, normalized_output=dict(snapshot or {}))

        payload = dict(snapshot or {})
        violations: list[str] = []
        contract = runtime_context.output_contract
        validator_contract = runtime_context.validator_contract

        for field_name in contract.get("required_fields", []):
            if field_name not in payload:
                violations.append(f"missing required field: {field_name}")

        allowed_next_actions = set(contract.get("allowed_next_actions") or [])
        next_action = str(payload.get("next_action") or "").strip()
        if next_action and next_action not in allowed_next_actions:
            violations.append(f"invalid next_action: {next_action}")

        follow_up_questions = payload.get("follow_up_questions") or []
        if not isinstance(follow_up_questions, list):
            violations.append("follow_up_questions must be a list")
        elif len(follow_up_questions) > int(validator_contract.get("max_questions_per_turn") or 3):
            violations.append("follow_up_questions exceeds max_questions_per_turn")

        red_flags = payload.get("red_flags") or []
        urgency = str(payload.get("urgency") or "").strip()
        if red_flags and urgency in {"routine", "unknown", ""}:
            violations.append("urgency must be elevated when red_flags are present")

        forbidden_violations = self._detect_forbidden_actions(payload, runtime_context.primary_card)
        violations.extend(forbidden_violations)
        return ClinicalPolicyValidatorResult(
            ok=not violations,
            violations=violations,
            normalized_output=payload,
            fallback_reason="; ".join(violations) if violations else "",
        )

    def build_safe_fallback(
        self,
        runtime_context: ClinicalPolicyRuntimeContext,
        context: dict[str, Any],
        *,
        reason: str = "",
    ) -> dict[str, Any]:
        primary_card = runtime_context.primary_card
        if primary_card is None:
            return {}

        shared_memory = dict(context.get("shared_memory") or {})
        clinical = dict(shared_memory.get("clinical_memory") or {})
        chief_complaint = str(context.get("chief_complaint") or clinical.get("chief_complaint") or "").strip()
        symptoms = [str(item).strip() for item in (clinical.get("symptoms") or context.get("symptoms") or []) if str(item).strip()]
        missing_fields = [str(item).strip() for item in (context.get("missing_fields") or []) if str(item).strip()]
        red_flags = [str(item).strip() for item in (context.get("red_flags") or []) if str(item).strip()]
        has_red_flags = bool(red_flags)
        urgency = runtime_context.fallback_contract.get("red_flag_urgency" if has_red_flags else "default_urgency", "routine")
        next_action = "escalate_urgency" if has_red_flags else "ask_follow_up"
        stage = "red_flag_screening" if has_red_flags else ("history_taking" if missing_fields else "summary")
        question = ""
        if next_action == "ask_follow_up":
            question = "Please continue describing when the symptom started, how severe it is, and any allergies."
        summary = chief_complaint or ", ".join(symptoms)
        if reason:
            summary = f"{summary} [{reason}]".strip()
        return {
            "agent_role": primary_card.agent_scope,
            "consultation_stage": stage,
            "chief_complaint": chief_complaint,
            "key_symptoms_collected": symptoms,
            "missing_information": missing_fields,
            "red_flags": red_flags,
            "urgency": urgency,
            "follow_up_questions": [question] if question else [],
            "patient_summary": summary,
            "next_action": next_action,
        }

    def _detect_forbidden_actions(self, payload: dict[str, Any], card: ClinicalPolicyCard) -> list[str]:
        text = json.dumps(payload, ensure_ascii=False).lower()
        violations: list[str] = []
        mappings = {
            "definitive_diagnosis": ["definitive diagnosis", "final diagnosis", "diagnosed with", "确诊", "最终诊断"],
            "prescribe_medication": ["prescribe", "dosage", "mg", "bid", "tid", "qd", "处方", "剂量", "用药"],
            "change_dosage": ["increase dose", "decrease dose", "change dosage", "调整剂量"],
            "individualized_treatment_plan": ["treatment plan", "individualized plan", "治疗方案"],
            "fabricated_exam_results": ["lab result shows", "ct shows", "imaging shows", "检查结果显示", "化验结果显示"],
        }
        for action in card.forbidden_actions:
            action_key = str(action or "").strip()
            tokens = mappings.get(action_key, [action_key.lower()])
            if any(token and token in text for token in tokens):
                violations.append(f"forbidden action detected: {action_key}")

        red_flags = payload.get("red_flags") or []
        if red_flags and any(token in text for token in ["harmless", "no problem", "nothing serious", "没事", "不要紧"]):
            violations.append("forbidden action detected: false_reassurance_with_red_flags")
        return violations
