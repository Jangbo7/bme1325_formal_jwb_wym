from __future__ import annotations

from typing import Any


QUESTION_TOKENS = (
    "?",
    "？",
    "what",
    "why",
    "how",
    "when",
    "whether",
    "could",
    "should",
    "do i",
    "is it",
    "什么意思",
    "什么问题",
    "什么情况",
    "是什么",
    "怎么",
    "为何",
    "为什么",
    "多久",
    "需不需要",
    "要不要",
    "能不能",
    "是不是",
    "可不可以",
    "如何",
)

REPORT_TOKENS = ("report", "result", "test result", "检查", "报告", "结果", "化验")
MEDICATION_TOKENS = ("medication", "medicine", "drug", "prescription", "antibiotic", "药", "处方", "药方", "怎么吃", "服用")
FOLLOWUP_TOKENS = ("follow up", "follow-up", "revisit", "review", "come back", "back soon", "复诊", "多久", "什么时候回来")
TEST_TOKENS = ("recheck", "repeat test", "more test", "check again", "还要检查", "还要不要检查", "为什么不用再检查")
DIAGNOSIS_TOKENS = ("what is it", "diagnosis", "what does this mean", "是不是", "是什么问题", "什么意思")
SAFETY_TOKENS = ("worse", "pain", "bleeding", "vomit", "black stool", "fever", "chest pain", "加重", "疼", "黑便", "呕血", "出血", "发热", "胸痛")


def infer_result_changed_fields(previous: dict | None, current: dict | None) -> list[str]:
    previous = previous or {}
    current = current or {}
    changed: list[str] = []
    for key in sorted(set(previous.keys()) | set(current.keys())):
        if previous.get(key) != current.get(key):
            changed.append(key)
    return changed


def is_question_like(message: str) -> bool:
    lowered = str(message or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in QUESTION_TOKENS)


def detect_reassessment_topics(message: str) -> set[str]:
    lowered = str(message or "").strip().lower()
    topics: set[str] = set()
    if any(token in lowered for token in REPORT_TOKENS):
        topics.add("report")
    if any(token in lowered for token in MEDICATION_TOKENS):
        topics.add("medication")
    if any(token in lowered for token in FOLLOWUP_TOKENS):
        topics.add("followup")
    if any(token in lowered for token in TEST_TOKENS):
        topics.add("tests")
    if any(token in lowered for token in DIAGNOSIS_TOKENS):
        topics.add("diagnosis")
    if any(token in lowered for token in SAFETY_TOKENS):
        topics.add("safety")
    return topics


def infer_update_reason(
    message: str,
    changed_fields: list[str],
    *,
    consultation_round: int = 1,
    message_type: str = "final",
    final_result: dict | None = None,
    previous_final_result: dict | None = None,
) -> str:
    del consultation_round, final_result, previous_final_result
    lowered = str(message or "").strip().lower()
    changed = set(changed_fields or [])

    safety_fields = {
        "red_flags",
        "priority",
        "department",
        "primary_disposition",
        "admission_recommendation",
        "procedure_recommendation",
        "return_precautions",
    }
    medication_fields = {
        "prescription_plan",
        "prescriptions",
        "medication_recommendation",
        "medication_or_action",
    }

    if changed & safety_fields:
        return "safety_flag"
    if changed & medication_fields:
        return "medication_issue"
    if any(token in lowered for token in REPORT_TOKENS):
        return "test_update"
    if any(token in lowered for token in SAFETY_TOKENS):
        return "new_symptom"
    if message_type in {"final_update", "final_no_change"}:
        return "patient_question"
    return "patient_question"


def infer_reassessment_intent(
    message: str,
    changed_fields: list[str],
    *,
    consultation_round: int = 1,
    message_type: str = "final",
    update_reason: str | None = None,
    final_result: dict | None = None,
    previous_final_result: dict | None = None,
) -> str:
    del consultation_round, final_result, previous_final_result, update_reason
    if message_type == "final_update" or changed_fields:
        return "result_update"
    if is_question_like(message):
        return "question_only"
    return "question_with_minor_guidance"


def infer_reply_rendering_mode(reassessment_intent: str | None, *, message_type: str = "final") -> str | None:
    if message_type not in {"final_update", "final_no_change"}:
        return None
    if reassessment_intent == "result_update":
        return "updated_summary"
    if reassessment_intent == "question_with_minor_guidance":
        return "answer_plus_guidance"
    return "answer_only"


def select_patient_reply_style(
    *,
    consultation_round: int,
    message_type: str,
    complete: bool,
    progress_completed: bool,
) -> str:
    if not complete:
        return f"round{consultation_round}_followup"
    if progress_completed or message_type in {"final_update", "final_no_change"}:
        return f"round{consultation_round}_reassessment"
    return f"round{consultation_round}_conclusion"


def default_patient_reply_from_result(result: dict, *, message_type: str = "final") -> str:
    department = str(result.get("department") or "Unknown")
    priority = str(result.get("priority") or "M")
    note = str(result.get("clinical_impression") or result.get("note") or result.get("patient_plan") or "").strip()
    if message_type == "final_no_change":
        intro = "Here is the direct answer to your question."
    elif message_type == "final_update":
        intro = "Based on the new information, I would adjust the plan as follows."
    else:
        intro = "The current assessment is as follows."
    body = note or "Please continue the current care plan."
    return f"{intro} {body} Department: {department}. Priority: {priority}."


def normalize_prescription_plan(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "drug_name": str(item.get("drug_name") or "").strip(),
                "intent": str(item.get("intent") or "").strip(),
                "dose_text": str(item.get("dose_text") or "").strip(),
                "frequency_text": str(item.get("frequency_text") or "").strip(),
                "duration_text": str(item.get("duration_text") or "").strip(),
                "instructions": str(item.get("instructions") or "").strip(),
                "requires_doctor_review": bool(item.get("requires_doctor_review", True)),
            }
        )
    return [item for item in normalized if item["drug_name"]]
