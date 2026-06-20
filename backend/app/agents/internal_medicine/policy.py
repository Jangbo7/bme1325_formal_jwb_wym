from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRegistry, ClinicalPolicyValidatorResult


CARD_DIRECTORY = Path(__file__).resolve().parent.parent / "clinical_policy" / "cards"
PATIENT_FACT_FIELDS = ("chief_complaint", "key_symptoms_collected", "patient_summary")
RELAXABLE_VIOLATION_TOKENS = {
    "forbidden action detected: prescribe_medication": (
        "prescribe",
        "dosage",
        "mg",
        "bid",
        "tid",
        "qd",
        "\u5904\u65b9",
        "\u5242\u91cf",
        "\u7528\u836f",
    ),
    "forbidden action detected: change_dosage": (
        "increase dose",
        "decrease dose",
        "change dosage",
        "\u8c03\u6574\u5242\u91cf",
        "\u8c03\u6574\u8fc7\u5242\u91cf",
        "\u52a0\u91cf",
        "\u51cf\u91cf",
        "\u51cf\u534a",
        "\u505c\u836f",
    ),
    "forbidden action detected: individualized_treatment_plan": (
        "treatment plan",
        "individualized plan",
        "\u6cbb\u7597\u65b9\u6848",
    ),
}
URGENT_FALLBACK_MESSAGE = (
    "\u76ee\u524d\u75c7\u72b6\u63d0\u793a\u53ef\u80fd\u9700\u8981\u5c3d\u5feb\u5904\u7406\uff0c"
    "\u8bf7\u53ca\u65f6\u524d\u5f80\u66f4\u9ad8\u4f18\u5148\u7ea7\u533a\u57df\u6216\u6025\u8bca\u8fdb\u4e00\u6b65\u8bc4\u4f30\u3002"
)
FOLLOWUP_FALLBACK_MESSAGE = (
    "\u8bf7\u7ee7\u7eed\u8865\u5145\u4e3b\u8981\u75c7\u72b6\u3001\u5f00\u59cb\u65f6\u95f4\uff0c"
    "\u4ee5\u53ca\u662f\u5426\u6709\u8fc7\u654f\u53f2\u3002"
)


@lru_cache(maxsize=1)
def load_internal_medicine_policy_registry() -> ClinicalPolicyRegistry:
    return ClinicalPolicyRegistry.load(CARD_DIRECTORY)


def select_internal_medicine_policy_phase(
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
    if consultation_round != 1 or progress.completed:
        return None
    return "round1_initial_consultation"


def adapt_internal_medicine_policy_prompt(
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
    prefix = "Round1 intake policy"
    if prompt_kind != "llm":
        prefix = "Round1 policy"
    card_id = policy_runtime_context.primary_card.id if policy_runtime_context and policy_runtime_context.primary_card else "unknown"
    return f"{prefix} ({card_id}):\n{policy_prompt_context}"


def validate_internal_medicine_policy_snapshot(
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
    violations = _filter_patient_fact_false_positives(normalized_output, validation_result.violations)
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


def _filter_patient_fact_false_positives(normalized_output: dict, violations: list[str] | tuple[str, ...]) -> list[str]:
    remaining: list[str] = []
    for violation in violations:
        violation = str(violation)
        tokens = RELAXABLE_VIOLATION_TOKENS.get(violation)
        if not tokens:
            remaining.append(violation)
            continue
        if _follow_up_questions_contain_directive(normalized_output, tokens):
            remaining.append(violation)
            continue
        if _token_hits_only_patient_fact_fields(normalized_output, tokens):
            continue
        remaining.append(violation)
    return remaining


def _follow_up_questions_contain_directive(normalized_output: dict, tokens: tuple[str, ...]) -> bool:
    questions = normalized_output.get("follow_up_questions") or []
    question_text = json.dumps(questions, ensure_ascii=False).lower()
    return any(token.lower() in question_text for token in tokens)


def _token_hits_only_patient_fact_fields(normalized_output: dict, tokens: tuple[str, ...]) -> bool:
    patient_fact_payload = {field: normalized_output.get(field) for field in PATIENT_FACT_FIELDS}
    patient_fact_text = json.dumps(patient_fact_payload, ensure_ascii=False).lower()
    if not any(token.lower() in patient_fact_text for token in tokens):
        return False

    non_patient_fields = {
        key: value for key, value in normalized_output.items() if key not in PATIENT_FACT_FIELDS and key != "follow_up_questions"
    }
    non_patient_text = json.dumps(non_patient_fields, ensure_ascii=False).lower()
    return not any(token.lower() in non_patient_text for token in tokens)


def build_internal_medicine_policy_fallback(
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
    del payload, kwargs, complete, assistant_payload
    fallback_red_flags = _resolve_fallback_red_flags(
        validation_result=validation_result,
        snapshot=snapshot,
        consultation_result=consultation_result,
    )
    fallback_snapshot = policy_runtime.build_safe_fallback(
        policy_runtime_context,
        {
            "shared_memory": memory.shared_memory if memory is not None else {},
            "chief_complaint": (memory.shared_memory.get("clinical_memory") or {}).get("chief_complaint") if memory is not None else "",
            "symptoms": (memory.shared_memory.get("clinical_memory") or {}).get("symptoms") if memory is not None else [],
            "missing_fields": (memory.private_memory.get("missing_fields") or []) if memory is not None else [],
            "red_flags": fallback_red_flags,
        },
        reason=reason,
    )
    next_action = str(fallback_snapshot.get("next_action") or "").strip()
    if next_action == "escalate_urgency":
        assistant_message = URGENT_FALLBACK_MESSAGE
    else:
        questions = fallback_snapshot.get("follow_up_questions") or []
        assistant_message = str(questions[0] if questions else FOLLOWUP_FALLBACK_MESSAGE).strip()

    updated_result = dict(consultation_result or {})
    effective_red_flags = list(fallback_snapshot.get("red_flags") or fallback_red_flags or [])
    if effective_red_flags:
        updated_result["red_flags"] = effective_red_flags
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


def _resolve_fallback_red_flags(
    *,
    validation_result: ClinicalPolicyValidatorResult | None,
    snapshot: dict | None,
    consultation_result: dict | None,
) -> list[str]:
    candidates = []
    if validation_result is not None and validation_result.normalized_output:
        candidates.append(validation_result.normalized_output.get("red_flags"))
    if snapshot:
        candidates.append(snapshot.get("red_flags"))
    if consultation_result:
        candidates.append(consultation_result.get("red_flags"))

    for candidate in candidates:
        red_flags = [str(item).strip() for item in (candidate or []) if str(item).strip()]
        if red_flags:
            return red_flags
    return []
