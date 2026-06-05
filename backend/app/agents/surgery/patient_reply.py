from __future__ import annotations

from app.agents.department_runtime.replies import detect_reassessment_topics, normalize_prescription_plan


def _join_items(items: list[str]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "、".join(values)


def _clean(value: str) -> str:
    return str(value or "").strip().rstrip("。；;，,")


def _looks_english(text: str) -> bool:
    value = _clean(text)
    if not value:
        return False
    ascii_letters = sum(1 for ch in value if ch.isascii() and ch.isalpha())
    cjk_letters = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters >= 12 and ascii_letters > cjk_letters * 2


def _preferred_text(*values: str, fallback: str = "") -> str:
    for value in values:
        text = _clean(value)
        if text and not _looks_english(text):
            return text
    for value in values:
        text = _clean(value)
        if text:
            return text
    return fallback


def _build_followup_lines(followup: dict, return_precautions: list[str], *, include_precautions: bool) -> list[str]:
    lines: list[str] = []
    revisit_window = _clean(followup.get("revisit_window") or "")
    revisit_conditions = [str(item).strip() for item in (followup.get("revisit_conditions") or []) if str(item).strip()]
    if revisit_window:
        lines.append(f"建议你在 {revisit_window} 左右回来复诊一次。")
    if revisit_conditions:
        lines.append(f"如果出现{_join_items(revisit_conditions)}，不要等到常规复诊时间，提前回来。")
    elif include_precautions and return_precautions:
        lines.append(f"如果出现{_join_items(return_precautions)}，要及时回外科复诊或到急诊处理。")
    return lines


def _detect_topics(message: str) -> set[str]:
    topics = set(detect_reassessment_topics(message or ""))
    lowered = str(message or "").lower()
    if any(token in lowered for token in ("report", "result", "检查结果", "报告", "复查结果")):
        topics.add("report")
        topics.add("diagnosis")
    if any(token in lowered for token in ("follow-up", "follow up", "come back", "revisit", "多久复诊", "什么时候复诊", "多久回来", "复诊", "回来看")):
        topics.add("followup")
    if any(token in lowered for token in ("test", "tests", "检查", "还要不要查", "还要不要检查")):
        topics.add("tests")
    if any(token in lowered for token in ("medicine", "medication", "drug", "药", "用药", "怎么吃")):
        topics.add("medication")
    return topics


def _build_prescription_reply(result: dict) -> str:
    plan = normalize_prescription_plan(result.get("prescription_plan"))
    if plan:
        pieces: list[str] = []
        for item in plan:
            name = str(item.get("drug_name") or "相关药物").strip()
            parts = [
                str(item.get("dose_text") or "").strip(),
                str(item.get("frequency_text") or "").strip(),
                str(item.get("duration_text") or "").strip(),
            ]
            usage = "，".join(part for part in parts if part)
            instructions = str(item.get("instructions") or "").strip()
            detail = "；".join(part for part in [usage, instructions] if part)
            pieces.append(f"{name}（{detail}）" if detail else name)
        return f"用药方面，目前更适合由外科医生结合这次复查情况，评估后按门诊方案使用{_join_items(pieces)}。"

    summary = _preferred_text((result.get("medication_recommendation") or {}).get("summary") or "")
    if summary:
        return f"用药方面，{summary}。"
    return ""


def _default_round2_summary(result: dict, *, procedure_completed: bool) -> str:
    primary_disposition = str(result.get("primary_disposition") or "").strip()
    if primary_disposition == "emergency_escalation":
        return "这次情况提示风险升高，不适合继续按普通门诊复诊节奏观察。"
    if primary_disposition == "inpatient_admission_recommended":
        return "这次复查结果更倾向需要尽快回外科进一步评估是否住院处理。"
    if primary_disposition == "specialty_referral":
        return "这次结果更像需要转到更合适的专科继续处理。"
    if procedure_completed:
        return "前面的门诊处置已经完成，现在重点是结合这次复查结果继续安排后续处理和维护。"
    return "这次复查结果支持继续按外科门诊方案处理，并结合恢复情况安排后续复诊。"


def _build_round1_question_answer(result: dict, topics: set[str], *, include_guidance: bool) -> str:
    impression = _preferred_text(result.get("clinical_impression") or "", result.get("note") or "")
    patient_plan = _preferred_text(result.get("patient_plan") or "", result.get("disposition_advice") or "")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
    lines: list[str] = []

    if "followup" in topics:
        lines.extend(_build_followup_lines(followup, return_precautions, include_precautions=True))
    elif "tests" in topics and tests:
        lines.append(f"目前建议检查的重点是{_join_items(tests)}，这样更有助于把当前外科问题判断清楚。")
    elif "medication" in topics and actions:
        lines.append(f"现阶段可以先按{_join_items(actions)}处理。")
    elif recommended_department and ("diagnosis" in topics or "followup" in topics):
        lines.append(f"目前更建议转到{recommended_department}继续处理。")
    elif impression:
        lines.append(f"按目前掌握的信息，{impression}。")

    if include_guidance:
        if patient_plan:
            lines.append(f"接下来更重要的是{patient_plan}。")
        elif tests:
            lines.append(f"先把{_join_items(tests)}完成，再结合结果决定下一步。")
    return "".join(lines).strip()


def _build_round2_question_answer(
    result: dict,
    topics: set[str],
    *,
    include_guidance: bool,
    payload: dict | None,
) -> str:
    payload = payload or {}
    procedure_completed = bool(payload.get("procedure_completed"))
    impression = _preferred_text(result.get("clinical_impression") or "", result.get("final_assessment_summary") or "")
    final_summary = _preferred_text(result.get("final_assessment_summary") or "", impression)
    patient_plan = _preferred_text(
        result.get("patient_facing_plan") or "",
        result.get("patient_plan") or "",
        result.get("disposition_advice") or "",
        fallback=_default_round2_summary(result, procedure_completed=procedure_completed),
    )
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    lines: list[str] = []

    if "report" in topics or "diagnosis" in topics:
        if procedure_completed:
            lines.append("前面的门诊处置已经完成。")
        if impression:
            lines.append(f"这次复查结果主要提示{impression}。")
        elif final_summary:
            lines.append(f"结合这次结果看，{final_summary}。")

    if "medication" in topics:
        medication_reply = _build_prescription_reply(result)
        if medication_reply:
            lines.append(medication_reply)

    if "tests" in topics:
        if tests:
            lines.append(f"如果后面恢复不理想，可能还需要结合{_join_items(tests)}进一步判断。")
        else:
            lines.append("按目前这次结果看，暂时没有必要重复做基础检查，重点是按现在的恢复情况继续维护和复诊。")

    if "followup" in topics:
        lines.extend(_build_followup_lines(followup, return_precautions, include_precautions=True))

    if not lines:
        if procedure_completed:
            lines.append("前面的门诊处置已经完成。")
        lines.append(patient_plan if patient_plan else _default_round2_summary(result, procedure_completed=procedure_completed))

    if include_guidance:
        if "followup" not in topics:
            followup_lines = _build_followup_lines(followup, return_precautions, include_precautions=False)
            if followup_lines:
                lines.append(followup_lines[0])
        if patient_plan and patient_plan not in lines[-1]:
            lines.append(f"现在更重要的是{patient_plan}。")
        elif return_precautions:
            lines.append(f"如果出现{_join_items(return_precautions)}，要及时回外科复诊或到急诊处理。")

    return "".join(part for part in lines if part).strip()


def _build_round1_reply(
    result: dict,
    *,
    message_type: str,
    reply_style: str,
    reassessment_intent: str | None,
    payload: dict | None,
) -> str:
    impression = _preferred_text(result.get("clinical_impression") or "", result.get("note") or "")
    patient_plan = _preferred_text(result.get("patient_plan") or "", result.get("disposition_advice") or "")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()
    topics = _detect_topics((payload or {}).get("message") or "")

    if reply_style == "round1_reassessment":
        if reassessment_intent == "result_update" or message_type == "final_update":
            lines = ["基于你刚补充的信息，我对这次外科判断做了调整。"]
            if impression:
                lines.append(f"{impression}。")
            if recommended_department:
                lines.append(f"这次更建议转到{recommended_department}进一步处理。")
            elif tests:
                lines.append(f"接下来先把{_join_items(tests)}完成，再结合结果决定下一步。")
            elif patient_plan:
                lines.append(f"{patient_plan}。")
            if actions and not tests:
                lines.append(f"目前可以先按{_join_items(actions)}处理。")
            return "".join(lines).strip()

        answer = _build_round1_question_answer(
            result,
            topics,
            include_guidance=reassessment_intent == "question_with_minor_guidance",
        )
        if answer:
            return answer

    lines = ["根据你目前提供的情况，"]
    if impression:
        lines.append(f"{impression}。")
    if recommended_department:
        lines.append(f"这次更建议转到{recommended_department}进一步处理。")
    elif tests:
        lines.append(f"我建议你先把{_join_items(tests)}做了，再带结果回来复诊。")
    elif patient_plan:
        lines.append(f"{patient_plan}。")
    if actions and not tests:
        lines.append(f"目前可以先按{_join_items(actions)}处理。")
    return "".join(lines).strip()


def _build_round2_reply(
    result: dict,
    *,
    message_type: str,
    reply_style: str,
    reassessment_intent: str | None,
    payload: dict | None,
) -> str:
    payload = payload or {}
    procedure_completed = bool(payload.get("procedure_completed"))
    impression = _preferred_text(result.get("clinical_impression") or "", result.get("final_assessment_summary") or "")
    final_summary = _preferred_text(result.get("final_assessment_summary") or "", impression)
    patient_plan = _preferred_text(
        result.get("patient_facing_plan") or "",
        result.get("patient_plan") or "",
        result.get("disposition_advice") or "",
        fallback=_default_round2_summary(result, procedure_completed=procedure_completed),
    )
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]

    if reply_style == "round2_reassessment":
        if reassessment_intent == "result_update" or message_type == "final_update":
            lines = ["基于你刚补充的信息，我建议把这次外科复查结论调整一下。"]
            if impression:
                lines.append(f"{impression}。")
            if final_summary and final_summary != impression:
                lines.append(f"{final_summary}。")
            if patient_plan:
                lines.append(f"{patient_plan}。")
            medication_reply = _build_prescription_reply(result)
            if medication_reply:
                lines.append(medication_reply)
            lines.extend(_build_followup_lines(followup, return_precautions, include_precautions=True))
            return "".join(part for part in lines if part).strip()

        return _build_round2_question_answer(
            result,
            _detect_topics(payload.get("message") or ""),
            include_guidance=reassessment_intent == "question_with_minor_guidance",
            payload=payload,
        )

    lines: list[str] = []
    if procedure_completed:
        lines.append("前面的门诊处置已经完成。")
    lines.append("我现在结合这次复查结果，继续给你后续处理和维护建议。")
    if impression:
        lines.append(f"这次复查结果主要提示{impression}。")
    if final_summary and final_summary != impression:
        lines.append(f"{final_summary}。")
    if patient_plan:
        lines.append(f"{patient_plan}。")
    medication_reply = _build_prescription_reply(result)
    if medication_reply:
        lines.append(medication_reply)
    lines.extend(_build_followup_lines(followup, return_precautions, include_precautions=True))
    return "".join(part for part in lines if part).strip()


def build_patient_reply(
    result: dict,
    *,
    message_type: str = "final",
    consultation_round: int = 1,
    reply_style: str = "",
    previous_final_result: dict | None = None,
    changed_fields: list[str] | None = None,
    update_reason: str | None = None,
    reassessment_intent: str | None = None,
    reply_rendering_mode: str | None = None,
    payload: dict | None = None,
    memory=None,
) -> str:
    del previous_final_result, changed_fields, update_reason, reply_rendering_mode, memory
    if consultation_round >= 2:
        return _build_round2_reply(
            result,
            message_type=message_type,
            reply_style=reply_style,
            reassessment_intent=reassessment_intent,
            payload=payload,
        )
    return _build_round1_reply(
        result,
        message_type=message_type,
        reply_style=reply_style,
        reassessment_intent=reassessment_intent,
        payload=payload,
    )
