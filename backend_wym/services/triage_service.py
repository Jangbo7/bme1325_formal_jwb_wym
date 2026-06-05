from rag.retriever import retrieve_relevant_rules
from services.llm_client import request_triage_from_llm
from services.memory_service import finalize_memory_context, prepare_chat_memory_context, prepare_memory_context
from services.validator import validate_triage_result


FIELD_PROMPTS = {
    "chief_complaint": "请再用一句话描述最困扰你的主诉，比如“胸闷、呼吸急”。",
    "symptoms": "请补充更具体的症状表现，比如疼痛部位、呼吸情况、是否头晕或咳嗽。",
    "onset_time": "症状大概从什么时候开始的？可以直接回答“刚刚”“30分钟”“2小时”或“1天”。",
    "temp_c": "你现在体温大概多少？如果不清楚，也可以回答“没发烧”或“感觉发热”。",
    "pain_score": "如果用 0 到 10 分表示疼痛，0 是不痛，10 是最痛，你现在大概几分？",
    "allergies": "你有已知药物或食物过敏吗？可以直接回答“没有过敏”或说出具体过敏原。",
}


def rule_based_triage(payload):
    vitals = payload.get("vitals") or {}
    hr = int(vitals.get("heart_rate", 90))
    pain = int(vitals.get("pain_score", 3))
    temp = float(vitals.get("temp_c", 36.8))
    symptoms = (payload.get("symptoms") or "").lower()

    level = 3
    priority = "M"
    dept = "General Medicine"
    note = "Please proceed to consultation soon."

    danger_keywords = ("chest", "breath", "faint", "severe")
    if hr >= 120 or pain >= 8 or any(k in symptoms for k in danger_keywords):
        level = 2
        priority = "H"
        dept = "Emergency"
        note = "High risk detected. Priority handling is recommended."
    elif temp >= 38.5:
        level = 3
        priority = "M"
        dept = "Fever Clinic"
        note = "Fever symptoms detected. Route to fever clinic."
    else:
        level = 4
        priority = "L"
        dept = "General Medicine"
        note = "Low to medium risk. Continue standard consultation process."

    return {
        "triage_level": level,
        "priority": priority,
        "department": dept,
        "note": note,
    }


def _evaluate_triage(merged_payload, memory_context):
    retrieved_rules = retrieve_relevant_rules(merged_payload, top_k=3)
    fallback_result = rule_based_triage(merged_payload)

    try:
        llm_result = request_triage_from_llm(merged_payload, retrieved_rules, memory_context=memory_context)
    except Exception:
        llm_result = None

    final_result = validate_triage_result(llm_result, fallback_result)
    evidence = [
        {
            "id": rule.get("id"),
            "title": rule.get("title"),
            "source": rule.get("source"),
        }
        for rule in retrieved_rules
    ]
    return final_result, evidence


def _build_follow_up_message(missing_fields, triage_result):
    if not missing_fields:
        return (
            f"初步建议你前往 {triage_result['department']}，分诊等级为 {triage_result['triage_level']}。"
            f" {triage_result['note']}"
        )

    next_field = missing_fields[0]
    intro = (
        f"目前先给出初步建议：优先级 {triage_result['priority']}，建议科室 {triage_result['department']}。"
        f" 为了让分诊更准确，我还想继续确认一个问题。"
    )
    return f"{intro}\n{FIELD_PROMPTS.get(next_field, '请再补充一些信息。')}"


def _build_dialogue_payload(triage_result, evidence, memory_snapshots, missing_fields):
    needs_more_info = bool(missing_fields)
    message = _build_follow_up_message(missing_fields, triage_result)
    return {
        "status": "needs_more_info" if needs_more_info else "triaged",
        "assistant_message": message,
        "expected_field": missing_fields[0] if needs_more_info else None,
        "missing_fields": missing_fields,
        "triage": triage_result,
        "evidence": evidence,
        "memory": memory_snapshots,
    }


def run_triage(payload):
    memory_context = prepare_memory_context(payload)
    merged_payload = memory_context["payload_for_triage"]
    final_result, evidence = _evaluate_triage(merged_payload, memory_context)
    missing_fields = list(memory_context["missing_fields"])
    assistant_message = _build_follow_up_message(missing_fields, final_result)
    memory_snapshots = finalize_memory_context(
        memory_context,
        final_result,
        evidence,
        assistant_message=assistant_message,
        summary_updates={"expected_field": missing_fields[0] if missing_fields else None},
    )
    return {
        "triage": final_result,
        "evidence": evidence,
        "memory": memory_snapshots,
        "dialogue": _build_dialogue_payload(final_result, evidence, memory_snapshots, missing_fields),
    }


def continue_triage_chat(payload):
    memory_context = prepare_chat_memory_context(payload)
    merged_payload = memory_context["payload_for_triage"]
    final_result, evidence = _evaluate_triage(merged_payload, memory_context)
    missing_fields = list(memory_context["missing_fields"])
    assistant_message = _build_follow_up_message(missing_fields, final_result)
    memory_snapshots = finalize_memory_context(
        memory_context,
        final_result,
        evidence,
        assistant_message=assistant_message,
        summary_updates={"expected_field": missing_fields[0] if missing_fields else None},
    )
    return {
        "triage": final_result,
        "evidence": evidence,
        "memory": memory_snapshots,
        "dialogue": _build_dialogue_payload(final_result, evidence, memory_snapshots, missing_fields),
    }
