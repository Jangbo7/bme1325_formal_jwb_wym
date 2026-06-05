from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRegistry, ClinicalPolicyValidatorResult


CARD_DIRECTORY = Path(__file__).resolve().parent.parent / "clinical_policy" / "cards"


@lru_cache(maxsize=1)
def load_surgery_policy_registry() -> ClinicalPolicyRegistry:
    return ClinicalPolicyRegistry.load(CARD_DIRECTORY)


def select_surgery_policy_phase(
    payload: dict,
    shared_memory: dict,
    private_memory: dict,
    progress,
    mode: str,
    *,
    merged_payload: dict | None = None,
) -> str | None:
    del payload, shared_memory, mode, merged_payload
    consultation_round = int(private_memory.get("consultation_round") or 1)
    if progress.completed:
        return None
    if consultation_round >= 2:
        return "round2_result_review"
    return "round1_initial_consultation"


def adapt_surgery_policy_prompt(
    policy_runtime_context,
    policy_prompt_context: str,
    *,
    prompt_kind: str = "llm",
    payload: dict | None = None,
    missing_fields: list[str] | None = None,
) -> str:
    del payload, missing_fields
    if not policy_prompt_context:
        return ""
    phase = str(policy_runtime_context.policy_context.get("phase") or "") if policy_runtime_context else ""
    if phase == "round2_result_review":
        prefix = "外科二轮复诊策略"
        if prompt_kind != "llm":
            prefix = "外科二轮策略"
    else:
        prefix = "外科初诊策略"
        if prompt_kind != "llm":
            prefix = "外科初诊规则"
    card_id = policy_runtime_context.primary_card.id if policy_runtime_context and policy_runtime_context.primary_card else "unknown"
    return f"{prefix}（{card_id}）:\n{policy_prompt_context}"


def validate_surgery_policy_snapshot(
    snapshot: dict,
    policy_runtime_context,
    payload: dict,
    *,
    validation_result: ClinicalPolicyValidatorResult | None = None,
    **kwargs,
) -> ClinicalPolicyValidatorResult:
    del payload, kwargs, policy_runtime_context
    if validation_result is None:
        return ClinicalPolicyValidatorResult(ok=True, normalized_output=dict(snapshot or {}))

    normalized_output = dict(validation_result.normalized_output or snapshot or {})
    violations = list(validation_result.violations)
    next_action = str(normalized_output.get("next_action") or "").strip()
    missing_information = normalized_output.get("missing_information") or []
    red_flags = normalized_output.get("red_flags") or []

    if next_action == "summarize_case" and missing_information:
        violations.append("cannot summarize while required information is still missing")
    if next_action == "escalate_urgency" and not red_flags:
        violations.append("cannot escalate urgency without red flags")
    return ClinicalPolicyValidatorResult(
        ok=not violations,
        violations=violations,
        normalized_output=normalized_output,
        fallback_reason="; ".join(violations) if violations else validation_result.fallback_reason,
    )


def build_surgery_policy_fallback(
    policy_runtime_context,
    payload: dict,
    reason: str,
    *,
    snapshot: dict | None = None,
    validation_result: ClinicalPolicyValidatorResult | None = None,
    memory=None,
    consultation_result: dict | None = None,
    assistant_payload: dict | None = None,
    complete: bool = False,
    policy_runtime=None,
    **kwargs,
) -> dict:
    del snapshot, validation_result, payload, kwargs, complete, assistant_payload
    fallback_snapshot = policy_runtime.build_safe_fallback(
        policy_runtime_context,
        {
            "shared_memory": memory.shared_memory if memory is not None else {},
            "chief_complaint": (memory.shared_memory.get("clinical_memory") or {}).get("chief_complaint") if memory is not None else "",
            "symptoms": (memory.shared_memory.get("clinical_memory") or {}).get("symptoms") if memory is not None else [],
            "missing_fields": (memory.private_memory.get("missing_fields") or []) if memory is not None else [],
            "red_flags": (consultation_result or {}).get("red_flags") or [],
        },
        reason=reason,
    )
    phase = str(policy_runtime_context.policy_context.get("phase") or "") if policy_runtime_context else ""
    next_action = str(fallback_snapshot.get("next_action") or "").strip()
    if next_action == "escalate_urgency":
        assistant_message = "目前情况提示可能需要尽快回外科或直接到急诊进一步处理，请不要继续按普通复诊节奏等待。"
    else:
        questions = fallback_snapshot.get("follow_up_questions") or []
        if questions:
            assistant_message = str(questions[0]).strip()
        elif phase == "round2_result_review":
            assistant_message = "我还需要补一条和这次复查安全性最相关的信息：现在有没有发热、伤口渗液明显增多，或者疼痛比之前更重？"
        else:
            assistant_message = "请继续补充这次外科问题的开始时间、是否和受伤或手术有关，以及有没有过敏史。"

    updated_result = dict(consultation_result or {})
    if fallback_snapshot.get("red_flags"):
        updated_result["red_flags"] = list(fallback_snapshot.get("red_flags") or [])
        updated_result["priority"] = "H"
    return {
        "consultation_result": updated_result,
        "missing_fields": list(fallback_snapshot.get("missing_information") or []),
        "assistant_payload": {
            "assistant_message": assistant_message,
            "message_type": "followup",
        },
        "complete": False,
    }
