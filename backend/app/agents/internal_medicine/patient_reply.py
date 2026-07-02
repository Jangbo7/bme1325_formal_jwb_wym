from __future__ import annotations

from app.agents.department_runtime.replies import detect_reassessment_topics, normalize_prescription_plan


def _join_items(items: list[str]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "、".join(values)


def _short_text(value: str) -> str:
    return str(value or "").strip().rstrip("。")


def _looks_english(text: str) -> bool:
    value = _short_text(text)
    if not value:
        return False
    ascii_letters = sum(1 for ch in value if ch.isascii() and ch.isalpha())
    cjk_letters = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters >= 16 and ascii_letters > cjk_letters * 2


def _preferred_text(*values: str, fallback: str = "") -> str:
    for value in values:
        text = _short_text(value)
        if text and not _looks_english(text):
            return text
    return fallback


def _default_round2_impression(result: dict) -> str:
    if result.get("primary_disposition") in {"emergency_escalation", "icu_escalation"}:
        return "这次结果提示风险比普通门诊随访更高，需要尽快升级处理"
    if (result.get("medication_recommendation") or {}).get("recommended"):
        return "这次检查结果支持按门诊方案用药处理，并安排后续复诊"
    return "这次检查结果支持继续按门诊方案处理，暂时不需要重复基础检查"


def _default_round2_plan(result: dict) -> str:
    if result.get("primary_disposition") in {"emergency_escalation", "icu_escalation"}:
        return "请现在直接到急诊或高优先级通道进一步评估"
    if (result.get("medication_recommendation") or {}).get("recommended"):
        return "我会按这次检查结果为你安排门诊用药，并按医嘱复诊观察疗效"
    return "先按目前门诊方案处理，如果症状加重或出现新的危险信号，请及时复诊"


def _result_test_items(result: dict) -> list[str]:
    return [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]


def _mentions_test_items(text: str, tests: list[str]) -> bool:
    normalized = str(text or "")
    return bool(normalized and tests and any(item and item in normalized for item in tests))


def _mentions_return_for_review(text: str) -> bool:
    normalized = str(text or "")
    return any(token in normalized for token in ("回来复诊", "回内科复诊", "回来内科复诊", "回来进一步复诊", "带结果回来"))


def _round1_test_instruction(result: dict, tests: list[str]) -> str:
    test_text = _join_items(tests)
    patient_plan = _short_text(result.get("patient_plan") or "")
    disposition_advice = _short_text(result.get("disposition_advice") or "")
    for candidate in (disposition_advice, patient_plan):
        if _mentions_test_items(candidate, tests) and "已开具" in candidate:
            return f"{candidate}。"
    if any(_mentions_test_items(candidate, tests) for candidate in (disposition_advice, patient_plan)):
        return f"我已为你开具{test_text}检查，结果出来后带来复诊。"
    generic_plan = any(token in patient_plan.lower() for token in ("辅助检查", "完善检查", "先做检查", "complete auxiliary tests", "complete tests"))
    if patient_plan and tests and not generic_plan and "建议" not in patient_plan:
        suffix = f"具体项目是{test_text}。" if _mentions_return_for_review(patient_plan) else f"我已为你开具{test_text}检查，结果出来后带来复诊。"
        return f"{patient_plan}；{suffix}"
    variants = [
        f"我已为你开具{test_text}检查，结果出来后带来复诊。",
        f"这次先完成{test_text}检查，拿到结果后我们再看下一步。",
        f"我已把{test_text}检查开好，你先去做，结果出来后带来复诊。",
    ]
    return variants[len(test_text) % len(variants)]


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
        return f"用药方面，我会开具{_join_items(pieces)}。请按这个疗程规律服用；如果你有相关药物过敏、孕期/备孕、严重肝肾功能问题，取药前需要再和医生确认。"

    summary = _short_text((medication_recommendation or {}).get("summary") or "")
    if summary and not _looks_english(summary):
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
    tests = _result_test_items(result)
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
    tests = _result_test_items(result)
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
                lines.append(_round1_test_instruction(result, tests))
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
        lines.append(_round1_test_instruction(result, tests))
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
    clinical_impression = _preferred_text(result.get("clinical_impression") or "", result.get("note") or "", fallback=_default_round2_impression(result))
    final_summary = _preferred_text(result.get("final_assessment_summary") or "", clinical_impression, fallback=clinical_impression)
    patient_plan = _preferred_text(
        result.get("patient_facing_plan") or "",
        result.get("patient_plan") or "",
        result.get("disposition_advice") or "",
        final_summary,
        fallback=_default_round2_plan(result),
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
    clinical_impression = _preferred_text(result.get("clinical_impression") or "", result.get("note") or "", fallback=_default_round2_impression(result))
    final_summary = _preferred_text(result.get("final_assessment_summary") or "", clinical_impression, fallback=clinical_impression)
    patient_plan = _preferred_text(
        result.get("patient_facing_plan") or "",
        result.get("patient_plan") or "",
        result.get("disposition_advice") or "",
        final_summary,
        fallback=_default_round2_plan(result),
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

    lines = ["结合上一轮问诊和这次检查结果，我的判断是这样的。"]
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


def _build_round1_reassessment_answer(result: dict, topics: set[str], *, include_guidance: bool) -> str:
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    patient_plan = _short_text(result.get("patient_plan") or result.get("disposition_advice") or "")
    tests = _result_test_items(result)
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()

    lines: list[str] = []
    if "tests" in topics and tests:
        lines.append(_round1_test_instruction(result, tests))
    elif "medication" in topics and actions:
        lines.append(f"现阶段可以先按{_join_items(actions)}处理。")
    elif recommended_department and ("diagnosis" in topics or "followup" in topics):
        lines.append(f"目前更建议转到{recommended_department}进一步处理。")
    elif clinical_impression:
        lines.append(f"按目前掌握的信息，{clinical_impression}。")

    if include_guidance:
        if tests:
            lines.append(_round1_test_instruction(result, tests))
        elif patient_plan:
            lines.append(f"接下来更重要的是{patient_plan}。")
    return "".join(dict.fromkeys(part for part in lines if part)).strip()


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
    del changed_fields, update_reason
    clinical_impression = _short_text(result.get("clinical_impression") or result.get("note") or "")
    patient_plan = _short_text(result.get("patient_plan") or result.get("disposition_advice") or "")
    tests = _result_test_items(result)
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()
    topics = detect_reassessment_topics((payload or {}).get("message") or "")

    if reply_style == "round1_reassessment":
        if reassessment_intent == "result_update":
            lines = ["基于你刚补充的信息，我把当前判断调整一下。"]
            if recommended_department:
                lines.append(f"这次更建议到{recommended_department}进一步看诊。")
            elif tests:
                lines.append(_round1_test_instruction(result, tests))
            elif patient_plan:
                lines.append(f"{patient_plan}。")
            elif clinical_impression:
                lines.append(f"{clinical_impression}。")
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

    lines: list[str] = []
    generic_impression = "信息还不足" in clinical_impression or "辅助检查" in clinical_impression
    if recommended_department:
        if clinical_impression and not generic_impression:
            lines.append(f"从你现在描述的情况看，{clinical_impression}。")
        lines.append(f"这次更建议到{recommended_department}进一步看诊。")
    elif tests:
        if clinical_impression and not generic_impression:
            lines.append(f"从你现在描述的情况看，{clinical_impression}。")
        lines.append(_round1_test_instruction(result, tests))
    elif patient_plan:
        if clinical_impression and not generic_impression:
            lines.append(f"从你现在描述的情况看，{clinical_impression}。")
        lines.append(f"{patient_plan}。")
    elif clinical_impression:
        lines.append(f"根据你目前提供的情况，{clinical_impression}。")
    else:
        lines.append("我先记录这些信息，后续按门诊流程继续判断。")
    if actions and not tests:
        lines.append(f"目前可以先按{_join_items(actions)}处理。")
    return "".join(lines).strip()


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
