from __future__ import annotations

from app.agents.department_runtime.replies import detect_reassessment_topics, normalize_prescription_plan


def _join_items(items: list[str]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "、".join(values)


def _short_text(value: str) -> str:
    return str(value or "").strip().rstrip("。")


def _build_prescription_reply(prescription_plan: list[dict], medication_recommendation: dict) -> str:
    if prescription_plan:
        pieces = []
        for item in prescription_plan:
            name = item.get("drug_name") or "相关药物"
            usage = "，".join(
                part
                for part in [item.get("dose_text"), item.get("frequency_text"), item.get("duration_text")]
                if str(part or "").strip()
            )
            instructions = str(item.get("instructions") or "").strip()
            if usage and instructions:
                pieces.append(f"{name}，{usage}，{instructions}")
            elif usage:
                pieces.append(f"{name}，{usage}")
            elif instructions:
                pieces.append(f"{name}，{instructions}")
            else:
                pieces.append(str(name))
        return f"用药方面，现阶段更适合按门诊方案评估后使用{_join_items(pieces)}。"

    summary = _short_text((medication_recommendation or {}).get("summary") or "")
    if summary:
        return f"用药方面，{summary}。"
    return ""


def _build_followup_reply(followup: dict, return_precautions: list[str], *, include_precautions: bool) -> list[str]:
    lines: list[str] = []
    revisit_window = _short_text(followup.get("revisit_window") or "")
    revisit_conditions = [str(item).strip() for item in (followup.get("revisit_conditions") or []) if str(item).strip()]

    if revisit_window:
        lines.append(f"建议你在{revisit_window}左右复诊一次。")
    if revisit_conditions:
        lines.append(f"如果出现{_join_items(revisit_conditions)}，不要等到常规复诊时间，提前回来。")
    elif include_precautions and return_precautions:
        lines.append(f"如果出现{_join_items(return_precautions)}，要及时就医。")
    return lines


def _build_round1_reassessment_answer(result: dict, topics: set[str], *, include_guidance: bool) -> str:
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    patient_plan = _short_text(result.get("patient_plan") or result.get("disposition_advice") or "")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()

    lines: list[str] = []
    if "tests" in topics and tests:
        lines.append(f"目前建议检查的重点是{_join_items(tests)}，这样更有助于把当前问题判断清楚。")
    elif "medication" in topics and actions:
        lines.append(f"现阶段可以先按{_join_items(actions)}处理。")
    elif recommended_department and ("diagnosis" in topics or "followup" in topics):
        lines.append(f"目前更建议转到{recommended_department}进一步处理。")
    elif clinical_impression:
        lines.append(f"按目前掌握的信息，{clinical_impression}。")

    if include_guidance:
        if patient_plan:
            lines.append(f"接下来更重要的是{patient_plan}。")
        elif tests:
            lines.append(f"先把{_join_items(tests)}完成，再结合结果决定下一步。")
    return "".join(lines).strip()


def _build_round1_reply(
    result: dict,
    *,
    message_type: str,
    reply_style: str,
    changed_fields: list[str],
    update_reason: str | None,
    reassessment_intent: str | None,
    payload: dict | None,
) -> str:
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    patient_plan = _short_text(result.get("patient_plan") or result.get("disposition_advice") or "")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()
    topics = detect_reassessment_topics((payload or {}).get("message") or "")

    if reply_style == "round1_reassessment":
        if reassessment_intent == "result_update":
            opening = "基于你刚补充的信息，我对当前判断做了调整。"
            lines = [opening]
            if clinical_impression:
                lines.append(f"{clinical_impression}。")
            if recommended_department:
                lines.append(f"这次更建议到{recommended_department}进一步看诊。")
            elif tests:
                lines.append(f"接下来先把{_join_items(tests)}做了，再结合结果决定下一步。")
            elif patient_plan:
                lines.append(f"{patient_plan}。")
            if actions and not tests:
                lines.append(f"目前可以先按{_join_items(actions)}处理。")
            return "".join(lines).strip()

        answer = _build_round1_reassessment_answer(
            result,
            topics,
            include_guidance=reassessment_intent == "question_with_minor_guidance",
        )
        if answer:
            return answer

    lines = ["根据你目前提供的情况，"]
    if clinical_impression:
        lines.append(f"{clinical_impression}。")
    if recommended_department:
        lines.append(f"这次更建议到{recommended_department}进一步看诊。")
    elif tests:
        lines.append(f"我建议你先把{_join_items(tests)}做了，再带结果回来复诊。")
    elif patient_plan:
        lines.append(f"{patient_plan}。")
    if actions and not tests:
        lines.append(f"目前可以先按{_join_items(actions)}处理。")
    return "".join(lines).strip()


def _build_round2_question_answer(
    result: dict,
    *,
    payload: dict | None,
    include_guidance: bool,
) -> str:
    message = (payload or {}).get("message") or ""
    topics = detect_reassessment_topics(message)
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    final_summary = _short_text(result.get("final_assessment_summary") or clinical_impression or "")
    patient_plan = _short_text(
        result.get("patient_facing_plan")
        or result.get("patient_plan")
        or result.get("disposition_advice")
        or final_summary
        or ""
    )
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
    prescription_plan = normalize_prescription_plan(result.get("prescription_plan"))
    medication_recommendation = dict(result.get("medication_recommendation") or {})
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]

    lines: list[str] = []

    if "report" in topics or "diagnosis" in topics:
        if clinical_impression:
            lines.append(f"这次报告主要提示{clinical_impression}。")
        elif final_summary:
            lines.append(f"结合这次结果看，{final_summary}。")

    if "medication" in topics:
        prescription_reply = _build_prescription_reply(prescription_plan, medication_recommendation)
        if prescription_reply:
            lines.append(prescription_reply)

    if "tests" in topics:
        if tests:
            lines.append(f"目前还有必要补做{_join_items(tests)}，这样更利于判断后续方案。")
        else:
            lines.append("按目前这次结果看，暂时没有必要重复基础检查，先按现有结果做门诊处理更合适。")

    if "followup" in topics:
        lines.extend(_build_followup_reply(followup, return_precautions, include_precautions=True))

    if not lines:
        if clinical_impression:
            lines.append(f"按目前掌握的信息，{clinical_impression}。")
        elif patient_plan:
            lines.append(f"{patient_plan}。")

    if include_guidance:
        if "followup" not in topics:
            followup_lines = _build_followup_reply(followup, return_precautions, include_precautions=False)
            if followup_lines:
                lines.append(followup_lines[0])
        if "tests" not in topics and patient_plan:
            lines.append(f"现在更重要的是{patient_plan}。")
        elif return_precautions:
            lines.append(f"如果出现{_join_items(return_precautions)}，要及时就医。")

    return "".join(part for part in lines if part).strip()


def _build_round2_reply(
    result: dict,
    *,
    message_type: str,
    reply_style: str,
    changed_fields: list[str],
    update_reason: str | None,
    reassessment_intent: str | None,
    payload: dict | None,
) -> str:
    del changed_fields, update_reason
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    final_summary = _short_text(result.get("final_assessment_summary") or clinical_impression or "")
    patient_plan = _short_text(
        result.get("patient_facing_plan")
        or result.get("patient_plan")
        or result.get("disposition_advice")
        or final_summary
        or ""
    )
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
    prescription_plan = normalize_prescription_plan(result.get("prescription_plan"))
    medication_recommendation = dict(result.get("medication_recommendation") or {})
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]

    if reply_style == "round2_reassessment":
        if reassessment_intent == "result_update" or message_type == "final_update":
            lines = ["基于你刚补充的信息，我建议把这次判断调整一下。"]
            if clinical_impression:
                lines.append(f"{clinical_impression}。")
            if final_summary and final_summary != clinical_impression:
                lines.append(f"{final_summary}。")
            if patient_plan:
                lines.append(f"{patient_plan}。")
            prescription_reply = _build_prescription_reply(prescription_plan, medication_recommendation)
            if prescription_reply:
                lines.append(prescription_reply)
            if tests:
                lines.append(f"另外还需要结合{_join_items(tests)}进一步处理。")
            lines.extend(_build_followup_reply(followup, return_precautions, include_precautions=True))
            return "".join(part for part in lines if part).strip()

        return _build_round2_question_answer(
            result,
            payload=payload,
            include_guidance=reassessment_intent == "question_with_minor_guidance",
        )

    lines = ["结合上一轮判断和这次检查结果，我的看法是这样的。"]
    if clinical_impression:
        lines.append(f"{clinical_impression}。")
    if final_summary and final_summary != clinical_impression:
        lines.append(f"{final_summary}。")
    if patient_plan:
        lines.append(f"{patient_plan}。")
    prescription_reply = _build_prescription_reply(prescription_plan, medication_recommendation)
    if prescription_reply:
        lines.append(prescription_reply)
    if tests:
        lines.append(f"如果后面情况有变化，再考虑补做{_join_items(tests)}。")
    lines.extend(_build_followup_reply(followup, return_precautions, include_precautions=True))
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
    del previous_final_result, reply_rendering_mode, memory
    if consultation_round >= 2:
        return _build_round2_reply(
            result,
            message_type=message_type,
            reply_style=reply_style,
            changed_fields=changed_fields or [],
            update_reason=update_reason,
            reassessment_intent=reassessment_intent,
            payload=payload,
        )
    return _build_round1_reply(
        result,
        message_type=message_type,
        reply_style=reply_style,
        changed_fields=changed_fields or [],
        update_reason=update_reason,
        reassessment_intent=reassessment_intent,
        payload=payload,
    )
