from app.agents.internal_medicine.workflow import ConsultationProgress


FIELD_PROMPTS = {
    "chief_complaint": [
        "请你用一句话说明这次最主要的不舒服是什么，越具体越好。",
        "换个问法再确认一下：这次最困扰你的症状是什么？",
    ],
    "onset_time": [
        "关于“{complaint}”，请补充大概从什么时候开始的，例如今天早上、昨晚、3天前。",
        "我再确认一下起病时间：这是刚出现，还是已经持续了一段时间？",
        "如果记不清具体时间，也可以回答“今天/昨晚/大概几小时或几天”。",
    ],
    "allergies": [
        "你有药物、食物或其他明确过敏史吗？如果没有，请直接回答“无过敏史”。",
        "再确认一次过敏信息：是否有已知药物或食物过敏？",
    ],
}


def build_follow_up_question(
    field_name: str,
    shared_memory: dict,
    *,
    asked_count: int = 0,
    is_repeated: bool = False,
    last_question_text: str = "",
) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "当前不适"
    variants = FIELD_PROMPTS.get(field_name)
    if not variants:
        base = "我还需要补充一些关键信息来完成初步判断，请继续描述你目前的情况。"
        if is_repeated:
            return "我换个问法确认一下：" + base
        return base

    index = min(asked_count, len(variants) - 1)
    message = variants[index].format(complaint=complaint)
    if is_repeated and message.strip() == (last_question_text or "").strip() and len(variants) > 1:
        alt_index = (index + 1) % len(variants)
        message = variants[alt_index].format(complaint=complaint)
    return message


def build_transition_follow_up_question(shared_memory: dict) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or ""
    symptoms = [item for item in (shared_memory.get("clinical_memory", {}).get("symptoms") or []) if item]
    symptom_text = "、".join(symptoms)
    if complaint and symptom_text:
        return (
            f"目前我已记录你的主要不适“{complaint}”以及症状“{symptom_text}”。"
            "请再补充症状严重程度、是否影响日常活动，以及最近有没有明显加重。"
        )
    if complaint:
        return f"我已记录你的主要不适“{complaint}”，请再补充症状持续时间以及最近是否逐渐加重。"
    return "请继续补充主要症状、开始时间和过敏史，这些信息会影响下一步建议。"


def build_initial_message(shared_memory: dict, progress: ConsultationProgress) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "当前不适"
    if progress.patient_reply_count == 0:
        return (
            f"我会先进行内科初步评估。你提到的主要不适是“{complaint}”。"
            "为了更准确判断，请补充症状开始时间、过敏史，以及目前最难受的表现。"
        )
    return "收到你的补充，我会继续评估。请尽量具体描述症状变化。"


def build_consultation_system_prompt() -> str:
    return (
        "你是内科门诊医生助手。"
        "请基于患者信息给出安全、可执行的中文初步建议。"
        "输出必须是严格 JSON，不要输出 JSON 之外的解释。"
    )


def build_consultation_user_prompt(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    previous_final_result: dict | None = None,
    post_final_reassessment: bool = False,
) -> str:
    reassessment_instruction = (
        "这是 final 之后的补充信息重评估。不要再追问，不要返回 follow-up，只能输出更新后的 final 结构。"
        if post_final_reassessment
        else "如果信息已足够，请直接返回 final 结构。"
    )
    return (
        f"Patient shared facts: {shared_memory}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing_fields}\n"
        f"Previous final result: {previous_final_result or {}}\n"
        f"{reassessment_instruction}\n"
        "Return strict JSON with keys: "
        "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
        "medication_or_action, red_flags, test_required, test_category, test_items, test_reason."
    )


def build_final_message(result: dict, *, message_type: str = "final") -> str:
    heading = {
        "final": "【内科初步结论】",
        "final_update": "【内科更新版结论】",
        "final_no_change": "【内科结论未变】",
    }.get(message_type, "【内科初步结论】")

    if message_type == "final_no_change":
        intro = "根据你刚才补充的信息，当前建议没有变化。"
    elif message_type == "final_update":
        intro = "根据你刚才补充的信息，建议已更新如下。"
    else:
        intro = "根据目前信息，建议如下。"

    department = result.get("department") or "Internal Medicine"
    priority = result.get("priority") or "M"
    note = result.get("note") or "建议继续门诊随诊。"
    patient_plan = result.get("patient_plan") or "请按门诊流程继续完成后续检查和复诊。"
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    red_flags = [str(item).strip() for item in (result.get("red_flags") or []) if str(item).strip()]

    lines = [
        heading,
        intro,
        f"建议科室：{department}",
        f"优先级：{priority}",
        f"判断说明：{note}",
        f"患者计划：{patient_plan}",
        f"建议检查：{'、'.join(tests) if tests else '暂不新增检查'}",
        f"处理建议：{'；'.join(actions) if actions else '先按当前门诊流程处理'}",
    ]
    if red_flags:
        lines.append(f"警示信号：{'、'.join(red_flags)}")
    lines.append("如症状明显加重，请立即复诊或急诊处理。")
    return "\n".join(lines)
