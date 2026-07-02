from app.agents.department_runtime.conclusions import round2_response_keys
from app.agents.department_runtime.prompting import (
    build_shared_consultation_system_prompt,
    build_shared_consultation_user_prompt,
    build_shared_follow_up_llm_messages,
    build_shared_physical_exam_decision_llm_messages,
    build_shared_physical_exam_result_llm_messages,
)
from app.agents.surgery.workflow import ConsultationProgress


FIELD_PROMPTS = {
    "chief_complaint": [
        "先确认一下，这次最主要想处理的外科问题是什么？",
        "我再确认一下，这次来外科最困扰你的主要问题是什么？",
    ],
    "onset_time": [
        "这个问题大概是从什么时候开始的？和受伤、手术或者换药有没有关系？",
        "我再确认一下时间经过：是今天刚出现，还是受伤/手术后持续了几天？",
    ],
    "allergies": [
        "有没有已知的药物、胶布、消毒材料或者其他过敏史？如果没有，直接说“没有过敏”就可以。",
        "我再确认一下过敏史：目前已知有药物或材料过敏吗？",
    ],
    "pain_score": [
        "如果现在还有疼痛，按 0 到 10 分来说大概几分？",
        "请按 0 到 10 分描述一下现在疼痛的强度，10 分代表最难受。",
    ],
}


def _format_known_vitals(shared_memory: dict) -> str:
    vitals = (shared_memory.get("clinical_memory") or {}).get("vitals") or {}
    parts: list[str] = []
    if vitals.get("temp_c") not in (None, ""):
        parts.append(f"体温{vitals.get('temp_c')}℃")
    if vitals.get("heart_rate") not in (None, ""):
        parts.append(f"心率{vitals.get('heart_rate')}次/分")
    if vitals.get("systolic_bp") not in (None, "") and vitals.get("diastolic_bp") not in (None, ""):
        parts.append(f"血压{vitals.get('systolic_bp')}/{vitals.get('diastolic_bp')}mmHg")
    if vitals.get("pain_score") not in (None, ""):
        parts.append(f"疼痛评分{vitals.get('pain_score')}分")
    return "，".join(parts)


def _triage_info_analysis(shared_memory: dict) -> str:
    vitals = (shared_memory.get("clinical_memory") or {}).get("vitals") or {}
    analyses: list[str] = []
    try:
        temp_c = float(vitals.get("temp_c")) if vitals.get("temp_c") not in (None, "") else None
    except Exception:
        temp_c = None
    try:
        heart_rate = float(vitals.get("heart_rate")) if vitals.get("heart_rate") not in (None, "") else None
    except Exception:
        heart_rate = None
    try:
        pain_score = float(vitals.get("pain_score")) if vitals.get("pain_score") not in (None, "") else None
    except Exception:
        pain_score = None

    if temp_c is not None:
        if temp_c >= 37.3:
            analyses.append("体温有点高")
    if heart_rate is not None and heart_rate >= 100:
        analyses.append("心率偏快")
    if pain_score is not None and pain_score >= 4:
        analyses.append("疼痛评分不低")
    if not analyses and vitals:
        if temp_c is not None:
            analyses.append("体温目前不高，分诊生命体征整体还算平稳")
        else:
            analyses.append("分诊生命体征整体还算平稳")
    return "；".join(analyses)


def build_follow_up_question(
    field_name: str,
    shared_memory: dict,
    *,
    asked_count: int = 0,
    is_repeated: bool = False,
    last_question_text: str = "",
    policy_runtime_context=None,
) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "这次外科问题"
    variants = FIELD_PROMPTS.get(field_name)
    if not variants:
        base = "我还需要再补一条关键信息，才能继续完成这次外科评估。"
        return f"我换个问法再确认一下：{base}" if is_repeated else base

    index = min(asked_count, len(variants) - 1)
    message = variants[index].format(complaint=complaint)
    if is_repeated and message.strip() == (last_question_text or "").strip() and len(variants) > 1:
        alt_index = (index + 1) % len(variants)
        message = variants[alt_index].format(complaint=complaint)
    return message


def build_transition_follow_up_question(shared_memory: dict, *, policy_runtime_context=None) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or ""
    symptoms = [item for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or []) if item]
    symptom_text = "、".join(symptoms)
    if complaint and symptom_text:
        return (
            f"我先记录到你这次的主要外科问题是“{complaint}”，目前提到的情况包括：{symptom_text}。"
            "请再补充一下具体部位、是否和外伤或近期手术有关，以及疼痛、出血、肿胀有没有在加重。"
        )
    if complaint:
        return (
            f"我先记录到你这次的主要外科问题是“{complaint}”。"
            "请再补充一下它是从什么时候开始的，具体部位在哪里，以及是否和受伤或手术有关。"
        )
    return "请继续补充这次外科问题的开始时间、是否和受伤或手术有关，以及有没有过敏史。"


def build_initial_message(
    shared_memory: dict,
    progress: ConsultationProgress,
    *,
    consultation_round: int = 1,
    policy_runtime_context=None,
) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "这次外科问题"
    vitals_text = _format_known_vitals(shared_memory)
    triage_analysis = _triage_info_analysis(shared_memory)
    vitals_sentence = f"分诊记录里我也看到{vitals_text}，{triage_analysis}。" if vitals_text and triage_analysis else ""
    if progress.patient_reply_count == 0:
        if int(consultation_round or 1) >= 2:
            return (
                f"我先结合上一轮判断、已有检查结果和处置情况，继续完成这次外科二轮复诊。"
                f"你这次的主要问题是“{complaint}”。请先说一下最近有哪些变化，现在最难受的点是什么。"
            )
        return (
            f"我先为你做这一轮外科初步问诊。你提到的主要问题是“{complaint}”。"
            f"{vitals_sentence}"
            "请再补充一下它是从什么时候开始的、是否和外伤或近期手术有关、有没有过敏史，以及现在最难受的表现是什么。"
        )
    return "我收到你的补充了。请继续说一下疼痛、出血、肿胀、伤口或活动受限方面有没有新的变化。"


def build_consultation_system_prompt(
    *,
    policy_prompt_context: str = "",
    policy_runtime_context=None,
    consultation_round: int = 1,
) -> str:
    del policy_runtime_context
    style_rules = (
        "所有患者可见字段必须使用中文，包括 note、patient_plan、clinical_impression、disposition_advice、"
        "medication_or_action、outpatient_procedure_reason；不要输出英文句子。"
        "一轮需要检查或门诊外科处置时，措辞应是“我已为你开具/安排……，请你完成后回来复诊”，不要写成仅供参考的“建议”。"
        "一轮最终结论中，如果事实支持，可以用“初步考虑”“更像是”给出1-2个可能诊断方向，但不要写成已经确诊。"
    )
    if policy_prompt_context:
        policy_prompt_context = f"{policy_prompt_context}\n{style_rules}"
    else:
        policy_prompt_context = style_rules
    return build_shared_consultation_system_prompt(
        base_role_text="你是外科门诊问诊助手。",
        consultation_round=consultation_round,
        language="zh",
        policy_prompt_context=policy_prompt_context,
    )


def build_consultation_user_prompt(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    payload: dict | None = None,
    historical_records_template: dict | None = None,
    previous_final_result: dict | None = None,
    post_final_reassessment: bool = False,
    policy_prompt_context: str = "",
    policy_runtime_context=None,
    consultation_round: int = 1,
) -> str:
    return build_shared_consultation_user_prompt(
        shared_memory,
        message,
        missing_fields,
        payload=payload,
        historical_records_template=historical_records_template,
        previous_final_result=previous_final_result,
        post_final_reassessment=post_final_reassessment,
        policy_prompt_context=policy_prompt_context,
        policy_runtime_context=policy_runtime_context,
        consultation_round=consultation_round,
        language="zh",
        round1_response_keys=(
            "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
            "medication_or_action, red_flags, test_required, test_category, test_items, test_reason, "
            "next_step_decision, needs_second_consultation, needs_second_internal_medicine_consultation, next_step_reason, "
            "clinical_impression, needs_tests, needs_medication, recommended_department, "
            "recommended_department_reason, disposition_advice, needs_outpatient_procedure, "
            "outpatient_procedure_category, outpatient_procedure_reason, procedure_can_parallel_with_tests."
        ),
        default_response_keys=round2_response_keys(),
    )


def build_follow_up_llm_messages(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    question_focus: str | None = None,
    payload: dict | None = None,
    policy_runtime_context=None,
) -> list[dict]:
    return build_shared_follow_up_llm_messages(
        shared_memory,
        message,
        missing_fields,
        question_focus=question_focus,
        payload=payload,
        policy_runtime_context=policy_runtime_context,
        language="zh",
        assistant_label="外科门诊",
    )


def build_physical_exam_decision_llm_messages(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    payload: dict | None = None,
    policy_runtime_context=None,
    consultation_round: int = 1,
) -> list[dict]:
    return build_shared_physical_exam_decision_llm_messages(
        shared_memory,
        message,
        missing_fields,
        payload=payload,
        policy_runtime_context=policy_runtime_context,
        consultation_round=consultation_round,
        language="zh",
        assistant_label="Surgery",
    )


def build_physical_exam_result_llm_messages(
    shared_memory: dict,
    message: str,
    exam_decision: dict,
    *,
    payload: dict | None = None,
    policy_runtime_context=None,
    consultation_round: int = 1,
) -> list[dict]:
    return build_shared_physical_exam_result_llm_messages(
        shared_memory,
        message,
        exam_decision,
        payload=payload,
        policy_runtime_context=policy_runtime_context,
        consultation_round=consultation_round,
        language="zh",
        assistant_label="Surgery",
    )


def build_final_message(result: dict, *, message_type: str = "final") -> str:
    def _looks_english(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return False
        ascii_letters = sum(1 for ch in value if ch.isascii() and ch.isalpha())
        cjk_letters = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
        return ascii_letters >= 16 and ascii_letters > cjk_letters * 2

    def _preferred_text(*values: str, fallback: str = "") -> str:
        for value in values:
            text = str(value or "").strip()
            if text and not _looks_english(text):
                return text
        return fallback

    is_round2 = bool(
        result.get("primary_disposition")
        or result.get("final_assessment_summary")
        or result.get("patient_facing_plan")
        or result.get("followup_recommendation")
    )
    if is_round2:
        heading = {
            "final": "[外科二轮结论]",
            "final_update": "[外科二轮结论更新]",
            "final_no_change": "[外科二轮结论未变]",
        }.get(message_type, "[外科二轮结论]")
        summary = _preferred_text(
            result.get("final_assessment_summary") or "",
            result.get("clinical_impression") or "",
            fallback="这次复查结果支持继续按外科门诊方案处理。",
        )
        plan = _preferred_text(
            result.get("patient_facing_plan") or "",
            result.get("patient_plan") or "",
            fallback="请按外科门诊安排继续处理，并根据症状变化按时复诊。",
        )
        return "\n".join(
            part
            for part in [
                heading,
                summary,
                plan,
            ]
            if part
        )

    heading = {
        "final": "[外科初步评估]",
        "final_update": "[外科评估更新]",
        "final_no_change": "[外科评估未变]",
    }.get(message_type, "[外科初步评估]")
    impression = str(result.get("clinical_impression") or result.get("note") or "").strip()
    plan = str(result.get("disposition_advice") or result.get("patient_plan") or "").strip()
    return "\n".join(part for part in [heading, impression, plan] if part)
