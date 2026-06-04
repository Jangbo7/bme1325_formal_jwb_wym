from app.agents.department_runtime.prompting import (
    build_shared_consultation_system_prompt,
    build_shared_consultation_user_prompt,
    build_shared_follow_up_llm_messages,
)
from app.agents.department_runtime.conclusions import round2_response_keys
from app.agents.internal_medicine.workflow import ConsultationProgress


FIELD_PROMPTS = {
    "chief_complaint": [
        "想先确认一下，您这次最主要的不舒服是什么？可以用一句话描述。",
        "我再确认一下，这次来就诊最困扰您的主要症状是什么？",
    ],
    "onset_time": [
        "这个不舒服大概是从什么时候开始的？像今天早上、昨天，或者几天前，这种大概时间就可以。",
        "我再确认一下时间经过：这是刚开始不久，还是已经持续了一段时间？",
        "如果记不清具体时间，也可以告诉我是今天、昨晚，还是大概几个小时前开始的。",
    ],
    "allergies": [
        "有已知的药物或食物过敏吗？如果没有，直接告诉我“没有过敏”就可以。",
        "我再确认一下过敏史：目前已知有药物或食物过敏吗？",
    ],
}


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
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "目前这次不适"
    variants = FIELD_PROMPTS.get(field_name)
    if not variants:
        base = "我还需要再补充一点关键信息，才能继续完成这一轮评估。"
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
    symptom_text = ", ".join(symptoms)
    if complaint and symptom_text:
        return (
            f"我先记录到您主要的不适是“{complaint}”，目前提到的症状包括 {symptom_text}。"
            "请再补充一下严重程度、是否在加重，以及有没有影响日常活动。"
        )
    if complaint:
        return f"我先记录到您主要的不适是“{complaint}”。请再补充一下它是从什么时候开始的，以及最近有没有加重。"
    return "请继续补充主要症状、开始时间，以及有没有过敏史。"


def build_initial_message(shared_memory: dict, progress: ConsultationProgress, *, policy_runtime_context=None) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "目前这次不适"
    if progress.patient_reply_count == 0:
        return (
            f"我先为您做这一轮内科初步问诊。您提到的主要问题是“{complaint}”。"
            "请再补充一下它是从什么时候开始的、有没有过敏史，以及现在最难受的表现是什么。"
        )
    return "我收到您的补充了。请继续说明症状的具体变化，这样我能继续判断。"


def build_initial_message(
    shared_memory: dict,
    progress: ConsultationProgress,
    *,
    consultation_round: int = 1,
    policy_runtime_context=None,
) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "当前这次不适"
    if progress.patient_reply_count == 0:
        if int(consultation_round or 1) >= 2:
            return (
                f"我先基于上一轮结论和已有检查结果，继续完成这一轮内科二轮复诊。您这次的主要问题是“{complaint}”。"
                "请先补充最近症状的变化，以及检查后现在最难受的表现是什么。"
            )
        return (
            f"我先为您做这一轮内科初步问诊。您提到的主要问题是“{complaint}”。"
            "请再补充一下它是从什么时候开始的、有没有过敏史，以及现在最难受的表现是什么。"
        )
    return "我收到您的补充了。请继续说明症状的具体变化，这样我能继续判断。"


def build_consultation_system_prompt(*, policy_prompt_context: str = "", policy_runtime_context=None) -> str:
    del policy_runtime_context
    prompt = (
        "你是内科门诊问诊助手。"
        "只能依据患者已经提供的事实进行判断，并返回严格 JSON。"
        "所有患者可见的 assistant_message、note、patient_plan、clinical_impression、disposition_advice、medication_or_action 必须使用中文表达，避免中英文混杂。"
    )
    if policy_prompt_context:
        prompt = f"{prompt}\n{policy_prompt_context}"
    return prompt


def build_consultation_user_prompt(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    historical_records_template: dict | None = None,
    previous_final_result: dict | None = None,
    post_final_reassessment: bool = False,
    policy_prompt_context: str = "",
    policy_runtime_context=None,
) -> str:
    phase = ""
    if policy_runtime_context is not None:
        phase = str(policy_runtime_context.policy_context.get("phase") or "")

    reassessment_instruction = (
        "这是在已经得到阶段性结果后的再次评估，不要继续追问，只返回更新后的最终 JSON。"
        if post_final_reassessment
        else "如果信息已经足够，请直接返回最终 JSON。"
    )
    if phase == "round1_initial_consultation":
        response_keys = (
            "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
            "medication_or_action, red_flags, test_required, test_category, test_items, test_reason, "
            "next_step_decision, needs_second_consultation, needs_second_internal_medicine_consultation, next_step_reason, "
            "clinical_impression, needs_tests, needs_medication, recommended_department, "
            "recommended_department_reason, disposition_advice."
        )
    else:
        response_keys = (
            "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
            "medication_or_action, red_flags, test_required, test_category, test_items, test_reason."
        )

    return (
        f"患者已提供事实：{shared_memory}\n"
        f"历史病历摘要模板：{historical_records_template or {}}\n"
        f"患者最新一句话：{message}\n"
        f"当前缺失字段：{missing_fields}\n"
        f"上一版最终结果：{previous_final_result or {}}\n"
        f"策略上下文：{policy_prompt_context}\n"
        f"{reassessment_instruction}\n"
        f"请返回严格 JSON，字段必须包含：{response_keys}"
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
    del payload
    policy_prompt_context = ""
    if policy_runtime_context is not None:
        policy_prompt_context = str(policy_runtime_context.prompt_policy_context or "")
    missing = ", ".join(missing_fields) if missing_fields else "none"
    focus = question_focus or "none"
    system_prompt = (
        "你是内科追问助手。"
        "请根据当前缺失信息，只提出一个简短、自然、面向患者的中文追问。"
        "不要给诊断、处方或超出事实的安慰。"
        "只输出严格 JSON：{\"assistant_message\":\"...\"}。"
    )
    if policy_prompt_context:
        system_prompt = f"{system_prompt}\n{policy_prompt_context}"
    user_prompt = (
        f"共享记忆：{shared_memory}\n"
        f"患者最新消息：{message}\n"
        f"缺失字段：{missing}\n"
        f"追问焦点：{focus}\n"
        "请生成一句自然的中文追问，尽量简短具体。"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_consultation_system_prompt(
    *,
    policy_prompt_context: str = "",
    policy_runtime_context=None,
    consultation_round: int = 1,
) -> str:
    del policy_runtime_context
    return build_shared_consultation_system_prompt(
        base_role_text="浣犳槸鍐呯闂ㄨ瘖闂瘖鍔╂墜銆?",
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
            "recommended_department_reason, disposition_advice."
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
        assistant_label="鍐呯",
    )


def build_final_message(result: dict, *, message_type: str = "final") -> str:
    def _display_department_name(name: str) -> str:
        mapping = {
            "Internal Medicine": "内科",
            "Emergency": "急诊",
        }
        return mapping.get(name, name)

    heading = {
        "final": "[内科初步评估]",
        "final_update": "[内科评估更新]",
        "final_no_change": "[内科评估未变更]",
    }.get(message_type, "[内科初步评估]")

    if message_type == "final_no_change":
        intro = "结合您刚才补充的信息，目前建议没有变化。"
    elif message_type == "final_update":
        intro = "结合您刚才补充的信息，目前建议更新如下。"
    else:
        intro = "根据目前掌握的信息，当前建议如下。"

    department = _display_department_name(str(result.get("department") or "Internal Medicine"))
    priority = result.get("priority") or "M"
    note = str(result.get("note") or "建议继续门诊随诊。")
    patient_plan = str(result.get("patient_plan") or "请继续按门诊流程完成建议的检查或处理。")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    red_flags = [str(item).strip() for item in (result.get("red_flags") or []) if str(item).strip()]
    next_step_decision = str(result.get("next_step_decision") or "").strip()
    disposition_advice = str(result.get("disposition_advice") or "").strip()
    clinical_impression = str(result.get("clinical_impression") or "").strip()
    recommended_department = _display_department_name(str(result.get("recommended_department") or "").strip())
    needs_second_consult = result.get("needs_second_consultation")
    if needs_second_consult is None:
        needs_second_consult = result.get("needs_second_internal_medicine_consultation")

    lines = [
        heading,
        intro,
        f"建议科室：{department}",
        f"优先级：{priority}",
        f"初步判断：{clinical_impression or note}",
        f"下一步建议：{disposition_advice or patient_plan}",
    ]
    if next_step_decision:
        lines.append(f"分流结果：{next_step_decision}")
    if needs_second_consult is not None:
        lines.append(f"是否需要二轮内科复诊：{'是' if bool(needs_second_consult) else '否'}")
    if recommended_department:
        lines.append(f"建议转诊科室：{recommended_department}")
    lines.append(f"建议检查：{', '.join(tests) if tests else '目前暂无额外检查建议'}")
    lines.append(f"建议处理：{', '.join(actions) if actions else '请继续按当前门诊流程进行'}")
    if red_flags:
        lines.append(f"风险提示：{', '.join(red_flags)}")
    lines.append("如果症状明显加重，请尽快再次就诊或及时急诊处理。")
    return "\n".join(lines)
def build_final_message(result: dict, *, message_type: str = "final") -> str:
    def _display_department_name(name: str) -> str:
        mapping = {
            "Internal Medicine": "内科",
            "Emergency": "急诊",
        }
        return mapping.get(name, name)

    is_round2_result = bool(
        result.get("primary_disposition")
        or result.get("final_assessment_summary")
        or result.get("patient_facing_plan")
        or result.get("medication_recommendation")
        or result.get("followup_recommendation")
    )

    if is_round2_result:
        heading = {
            "final": "[内科二轮结论]",
            "final_update": "[内科二轮结论更新]",
            "final_no_change": "[内科二轮结论未变更]",
        }.get(message_type, "[内科二轮结论]")
        if message_type == "final_no_change":
            intro = "结合您刚才补充的信息，本轮二次评估结论没有变化。"
        elif message_type == "final_update":
            intro = "结合您刚才补充的信息，本轮二次评估结论更新如下。"
        else:
            intro = "结合上一轮判断和现有检查结果，本轮结论如下。"

        department = _display_department_name(str(result.get("department") or "Internal Medicine"))
        priority = result.get("priority") or "M"
        clinical_impression = str(result.get("clinical_impression") or result.get("note") or "").strip()
        final_summary = str(result.get("final_assessment_summary") or clinical_impression or "").strip()
        primary_disposition = str(result.get("primary_disposition") or "").strip() or "outpatient_management"
        patient_plan = str(
            result.get("patient_facing_plan")
            or result.get("patient_plan")
            or result.get("disposition_advice")
            or final_summary
        ).strip()
        tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
        red_flags = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
        medication = dict(result.get("medication_recommendation") or {})
        admission = dict(result.get("admission_recommendation") or {})
        procedure = dict(result.get("procedure_recommendation") or {})
        followup = dict(result.get("followup_recommendation") or {})
        disposition_labels = {
            "outpatient_management": "门诊处理",
            "observe_then_revisit": "观察后复诊",
            "inpatient_admission_recommended": "建议住院",
            "emergency_escalation": "急诊升级",
            "specialty_referral": "转专科处理",
        }

        lines = [
            heading,
            intro,
            f"建议科室：{department}",
            f"优先级：{priority}",
            f"报告解读：{clinical_impression or final_summary}",
            f"本轮结论：{final_summary or clinical_impression}",
            f"主去向：{disposition_labels.get(primary_disposition, primary_disposition)}",
            f"患者计划：{patient_plan}",
        ]
        if medication.get("recommended"):
            lines.append(f"用药建议：{medication.get('summary') or '建议由医生结合本轮结果评估并开具门诊用药。'}")
        if admission.get("recommended"):
            lines.append(f"住院建议：{admission.get('reason') or '建议住院进一步处理。'}")
        if procedure.get("surgery_evaluation_recommended"):
            lines.append(f"手术评估：{procedure.get('reason') or '建议进一步进行手术评估。'}")
        if followup.get("revisit_required"):
            revisit_window = str(followup.get("revisit_window") or "").strip()
            revisit_conditions = [str(item).strip() for item in (followup.get("revisit_conditions") or []) if str(item).strip()]
            followup_text = revisit_window or "按医生安排复诊"
            if revisit_conditions:
                followup_text = f"{followup_text}；若出现 {'、'.join(revisit_conditions)} 请提前复诊"
            lines.append(f"复诊建议：{followup_text}")
        lines.append(f"额外检查：{', '.join(tests) if tests else '当前不建议重复基础检查'}")
        if red_flags:
            lines.append(f"风险提示：{'、'.join(red_flags)}")
        else:
            lines.append("风险提示：如症状明显加重，请及时复诊或急诊处理。")
        return "\n".join(lines)

    heading = {
        "final": "[内科初步评估]",
        "final_update": "[内科评估更新]",
        "final_no_change": "[内科评估未变更]",
    }.get(message_type, "[内科初步评估]")

    if message_type == "final_no_change":
        intro = "结合您刚才补充的信息，目前建议没有变化。"
    elif message_type == "final_update":
        intro = "结合您刚才补充的信息，目前建议更新如下。"
    else:
        intro = "根据目前掌握的信息，当前建议如下。"

    department = _display_department_name(str(result.get("department") or "Internal Medicine"))
    priority = result.get("priority") or "M"
    note = str(result.get("note") or "建议继续门诊随诊。")
    patient_plan = str(result.get("patient_plan") or "请继续按门诊流程完成建议的检查或处理。")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    red_flags = [str(item).strip() for item in (result.get("red_flags") or []) if str(item).strip()]
    next_step_decision = str(result.get("next_step_decision") or "").strip()
    disposition_advice = str(result.get("disposition_advice") or "").strip()
    clinical_impression = str(result.get("clinical_impression") or "").strip()
    recommended_department = _display_department_name(str(result.get("recommended_department") or "").strip())
    needs_second_consult = result.get("needs_second_consultation")
    if needs_second_consult is None:
        needs_second_consult = result.get("needs_second_internal_medicine_consultation")

    lines = [
        heading,
        intro,
        f"建议科室：{department}",
        f"优先级：{priority}",
        f"初步判断：{clinical_impression or note}",
        f"下一步建议：{disposition_advice or patient_plan}",
    ]
    if next_step_decision:
        lines.append(f"分流结果：{next_step_decision}")
    if needs_second_consult is not None:
        lines.append(f"是否需要二轮内科复诊：{'是' if bool(needs_second_consult) else '否'}")
    if recommended_department:
        lines.append(f"建议转诊科室：{recommended_department}")
    lines.append(f"建议检查：{', '.join(tests) if tests else '目前暂无额外检查建议'}")
    lines.append(f"建议处理：{', '.join(actions) if actions else '请继续按当前门诊流程进行'}")
    if red_flags:
        lines.append(f"风险提示：{', '.join(red_flags)}")
    lines.append("如果症状明显加重，请尽快再次就诊或及时急诊处理。")
    return "\n".join(lines)
