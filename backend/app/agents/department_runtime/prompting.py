from __future__ import annotations

import json


def normalize_consultation_round(value) -> int:
    try:
        return max(1, int(value or 1))
    except Exception:
        return 1


def _policy_phase(policy_runtime_context) -> str:
    if policy_runtime_context is None:
        return ""
    return str(policy_runtime_context.policy_context.get("phase") or "")


def _as_prompt_text(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def _resolve_response_keys(
    *,
    consultation_round: int,
    phase: str,
    round1_response_keys: str,
    default_response_keys: str,
) -> str:
    if phase == "round1_initial_consultation" or consultation_round == 1:
        return round1_response_keys
    return default_response_keys


def build_shared_consultation_system_prompt(
    *,
    base_role_text: str,
    consultation_round: int,
    language: str,
    policy_prompt_context: str = "",
) -> str:
    consultation_round = normalize_consultation_round(consultation_round)
    if language == "zh":
        round_instruction = (
            "当前是一轮问诊，请先完成关键信息采集、红旗信号筛查，并在信息足够时给出结构化初步结论。"
            if consultation_round == 1
            else "当前是二轮面诊，请优先结合上一轮摘要、已有检查结果和本次患者更新完成再评估；除非关键安全信息仍缺失，不要重新从头做初诊式采集。"
        )
        prompt = f"{base_role_text}只能依据患者已提供的事实和已有上下文进行判断，并返回严格 JSON。{round_instruction}"
    else:
        round_instruction = (
            "This is a first-round consultation. Collect the key safety information, screen for red flags, and produce a structured preliminary result when enough information is available."
            if consultation_round == 1
            else (
                "This is a second-round consultation. Prioritize the prior consultation summary, available test results, and the patient's current update before deciding the next disposition. "
                "Do not restart the full intake unless key safety information is still missing. "
                "For second-round conclusions, primary_disposition must contain exactly one final disposition, while medication_recommendation, admission_recommendation, procedure_recommendation, and followup_recommendation may coexist."
            )
        )
        prompt = f"{base_role_text} Base your response only on patient-provided facts and the available consultation context, and return strict JSON. {round_instruction}"
    if policy_prompt_context:
        prompt = f"{prompt}\n{policy_prompt_context}"
    return prompt


def build_shared_consultation_user_prompt(
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
    language: str,
    round1_response_keys: str,
    default_response_keys: str,
) -> str:
    payload = payload or {}
    consultation_round = normalize_consultation_round(payload.get("consultation_round") or consultation_round)
    phase = _policy_phase(policy_runtime_context)
    response_keys = _resolve_response_keys(
        consultation_round=consultation_round,
        phase=phase,
        round1_response_keys=round1_response_keys,
        default_response_keys=default_response_keys,
    )
    previous_round_summary = payload.get("previous_round_summary") or {}
    simulated_report = payload.get("simulated_report") or {}
    diagnostic_session = payload.get("diagnostic_session") or {}

    if language == "zh":
        if post_final_reassessment:
            instruction = "这是在已有阶段性结果后的再次评估，不要继续追问，只返回更新后的最终 JSON。"
        elif consultation_round == 2:
            instruction = "这是二轮面诊。请优先结合上一轮摘要、辅助检查结果和患者本次补充完成再评估；除非关键安全信息仍缺失，不要重新从头开始初诊式采集。"
        else:
            instruction = "如果信息已经足够，请直接返回最终 JSON。"
        return (
            f"问诊轮次：第 {consultation_round} 轮\n"
            f"患者已提供事实：{_as_prompt_text(shared_memory)}\n"
            f"上一轮摘要：{_as_prompt_text(previous_round_summary)}\n"
            f"辅助检查/报告摘要：{_as_prompt_text(simulated_report)}\n"
            f"检查会话信息：{_as_prompt_text(diagnostic_session)}\n"
            f"历史病历摘要模板：{_as_prompt_text(historical_records_template or {})}\n"
            f"患者最新一句话：{message}\n"
            f"当前缺失字段：{_as_prompt_text(missing_fields)}\n"
            f"上一版最终结果：{_as_prompt_text(previous_final_result or {})}\n"
            f"策略上下文：{policy_prompt_context}\n"
            f"{instruction}\n"
            f"请返回严格 JSON，字段必须包含：{response_keys}"
        )

    if post_final_reassessment:
        instruction = "This is a reassessment after a completed result. Do not ask follow-up questions. Return only the updated final JSON."
    elif consultation_round == 2:
        instruction = (
            "This is a second-round consultation. Use the prior consultation summary, available test results, and the patient's latest update to complete the reassessment. "
            "Do not restart the full intake unless key safety information is still missing. "
            "primary_disposition must be a single final disposition, while medication_recommendation, admission_recommendation, procedure_recommendation, and followup_recommendation may coexist."
        )
    else:
        instruction = "If the information is sufficient, return the final JSON directly."
    return (
        f"Consultation round: {consultation_round}\n"
        f"Patient shared facts: {_as_prompt_text(shared_memory)}\n"
        f"Previous consultation summary: {_as_prompt_text(previous_round_summary)}\n"
        f"Simulated test report: {_as_prompt_text(simulated_report)}\n"
        f"Diagnostic session: {_as_prompt_text(diagnostic_session)}\n"
        f"Historical medical records template: {_as_prompt_text(historical_records_template or {})}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {_as_prompt_text(missing_fields)}\n"
        f"Previous final result: {_as_prompt_text(previous_final_result or {})}\n"
        f"Policy prompt context: {policy_prompt_context}\n"
        f"{instruction}\n"
        f"Return strict JSON with keys: {response_keys}"
    )


def build_shared_follow_up_llm_messages(
    shared_memory: dict,
    message: str,
    missing_fields: list[str],
    *,
    question_focus: str | None = None,
    payload: dict | None = None,
    policy_runtime_context=None,
    consultation_round: int = 1,
    language: str,
    assistant_label: str,
) -> list[dict]:
    payload = payload or {}
    consultation_round = normalize_consultation_round(payload.get("consultation_round") or consultation_round)
    previous_round_summary = payload.get("previous_round_summary") or {}
    simulated_report = payload.get("simulated_report") or {}
    diagnostic_session = payload.get("diagnostic_session") or {}
    policy_prompt_context = ""
    if policy_runtime_context is not None:
        policy_prompt_context = str(policy_runtime_context.prompt_policy_context or "")
    missing = ", ".join(missing_fields) if missing_fields else "none"
    focus = question_focus or "none"

    if language == "zh":
        system_prompt = (
            f"你是{assistant_label}追问助手。请根据当前缺失信息，只提出一个简短、自然、面向患者的中文追问。不要给诊断、处方或超出事实的安慰。只输出严格 JSON：{{\"assistant_message\":\"...\"}}。"
            if consultation_round == 1
            else f"你是{assistant_label}二轮面诊追问助手。请结合上一轮摘要和已有检查结果，只提出一个有助于完成二轮判断的简短中文追问。不要重新做完整初诊采集，不要给诊断、处方或超出事实的安慰。只输出严格 JSON：{{\"assistant_message\":\"...\"}}。"
        )
        if policy_prompt_context:
            system_prompt = f"{system_prompt}\n{policy_prompt_context}"
        user_prompt = (
            f"问诊轮次：第 {consultation_round} 轮\n"
            f"共享记忆：{_as_prompt_text(shared_memory)}\n"
            f"上一轮摘要：{_as_prompt_text(previous_round_summary)}\n"
            f"辅助检查/报告摘要：{_as_prompt_text(simulated_report)}\n"
            f"检查会话信息：{_as_prompt_text(diagnostic_session)}\n"
            f"患者最新消息：{message}\n"
            f"缺失字段：{missing}\n"
            f"追问焦点：{focus}\n"
            "请生成一句自然、简短、具体的中文追问。"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    system_prompt = (
        f"You are a {assistant_label} follow-up assistant. Ask one short, natural patient-facing follow-up question based on the remaining missing information. Do not diagnose, prescribe treatment, or provide reassurance beyond the available facts. Output strict JSON only: {{\"assistant_message\":\"...\"}}."
        if consultation_round == 1
        else f"You are a {assistant_label} second-round follow-up assistant. Use the prior consultation summary and available test results to ask one short question that helps close the remaining safety or disposition gap. Do not restart the full intake, diagnose definitively, or prescribe treatment. Output strict JSON only: {{\"assistant_message\":\"...\"}}."
    )
    if policy_prompt_context:
        system_prompt = f"{system_prompt}\n{policy_prompt_context}"
    user_prompt = (
        f"Consultation round: {consultation_round}\n"
        f"Shared memory: {_as_prompt_text(shared_memory)}\n"
        f"Previous consultation summary: {_as_prompt_text(previous_round_summary)}\n"
        f"Simulated test report: {_as_prompt_text(simulated_report)}\n"
        f"Diagnostic session: {_as_prompt_text(diagnostic_session)}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing}\n"
        f"Question focus: {focus}\n"
        "Generate one natural, short, concrete follow-up question."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
