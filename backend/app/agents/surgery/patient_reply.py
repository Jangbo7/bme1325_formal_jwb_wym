from __future__ import annotations

from app.agents.department_runtime.replies import detect_reassessment_topics, normalize_prescription_plan


def _join_items(items: list[str]) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    return "、".join(values)


def _clean(value: str) -> str:
    return str(value or "").strip().rstrip("。")


def _followup_lines(followup: dict, return_precautions: list[str], *, include_precautions: bool) -> list[str]:
    lines: list[str] = []
    revisit_window = _clean(followup.get("revisit_window") or "")
    revisit_conditions = [str(item).strip() for item in (followup.get("revisit_conditions") or []) if str(item).strip()]
    if revisit_window:
        lines.append(f"建议你在{revisit_window}左右复诊一次。")
    if revisit_conditions:
        lines.append(f"如果出现{_join_items(revisit_conditions)}，不要等到常规复诊时间，提前回来。")
    elif include_precautions and return_precautions:
        lines.append(f"如果出现{_join_items(return_precautions)}，要及时就医。")
    return lines


def _prescription_reply(result: dict) -> str:
    prescription_plan = normalize_prescription_plan(result.get("prescription_plan"))
    if prescription_plan:
        parts = []
        for item in prescription_plan:
            detail = "，".join(
                part
                for part in [item.get("dose_text"), item.get("frequency_text"), item.get("duration_text")]
                if str(part or "").strip()
            )
            instructions = str(item.get("instructions") or "").strip()
            if detail and instructions:
                parts.append(f"{item['drug_name']}，{detail}，{instructions}")
            elif detail:
                parts.append(f"{item['drug_name']}，{detail}")
            elif instructions:
                parts.append(f"{item['drug_name']}，{instructions}")
            else:
                parts.append(item["drug_name"])
        return f"用药方面，现阶段更适合由外科医生结合这次复查结果后，再决定是否使用{_join_items(parts)}。"
    summary = _clean((result.get("medication_recommendation") or {}).get("summary") or "")
    if summary:
        return f"用药方面，{summary}。"
    return ""


def _round1_answer(result: dict, topics: set[str], *, include_guidance: bool) -> str:
    impression = _clean(result.get("clinical_impression") or result.get("note") or "")
    patient_plan = _clean(result.get("patient_plan") or result.get("disposition_advice") or "")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or result.get("test_items") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    recommended_department = str(result.get("recommended_department") or "").strip()
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]

    lines: list[str] = []
    if "followup" in topics:
        lines.extend(_followup_lines(followup, return_precautions, include_precautions=True))
    elif "tests" in topics and tests:
        lines.append(f"目前建议检查的重点是{_join_items(tests)}，这样更有助于把外科问题判断清楚。")
    elif "medication" in topics and actions:
        lines.append(f"现阶段可以先按{_join_items(actions)}处理。")
    elif recommended_department and ("diagnosis" in topics or "followup" in topics):
        lines.append(f"目前更适合转到{recommended_department}继续处理。")
    elif impression:
        lines.append(f"按目前掌握的信息，{impression}。")

    if include_guidance:
        if patient_plan:
            lines.append(f"接下来更重要的是{patient_plan}。")
        elif tests:
            lines.append(f"先把{_join_items(tests)}完成，再带结果回来复查。")
    return "".join(lines).strip()


def _round2_answer(result: dict, topics: set[str], *, include_guidance: bool) -> str:
    impression = _clean(result.get("clinical_impression") or result.get("note") or "")
    final_summary = _clean(result.get("final_assessment_summary") or impression or "")
    patient_plan = _clean(
        result.get("patient_facing_plan")
        or result.get("patient_plan")
        or result.get("disposition_advice")
        or final_summary
        or ""
    )
    followup = dict(result.get("followup_recommendation") or {})
    return_precautions = [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()]
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]

    lines: list[str] = []
    if "report" in topics or "diagnosis" in topics:
        if impression:
            lines.append(f"这次复查结果主要提示{impression}。")
        elif final_summary:
            lines.append(f"结合这次结果看，{final_summary}。")
    if "medication" in topics:
        medication = _prescription_reply(result)
        if medication:
            lines.append(medication)
    if "tests" in topics:
        if tests:
            lines.append(f"如果后面情况有变化，可能还需要结合{_join_items(tests)}进一步判断。")
        else:
            lines.append("按目前这次结果看，暂时没有必要重复基础检查，重点是结合现有结果决定下一步处理。")
    if "followup" in topics:
        lines.extend(_followup_lines(followup, return_precautions, include_precautions=True))

    if not lines:
        if impression:
            lines.append(f"按目前掌握的信息，{impression}。")
        elif patient_plan:
            lines.append(f"{patient_plan}。")

    if include_guidance:
        if "followup" not in topics:
            followup_lines = _followup_lines(followup, return_precautions, include_precautions=False)
            if followup_lines:
                lines.append(followup_lines[0])
        if patient_plan:
            lines.append(f"现在更重要的是{patient_plan}。")
        elif return_precautions:
            lines.append(f"如果出现{_join_items(return_precautions)}，要及时就医。")
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
    del previous_final_result, changed_fields, update_reason, reply_rendering_mode, memory
    topics = detect_reassessment_topics((payload or {}).get("message") or "")

    if reply_style.endswith("_reassessment"):
        if reassessment_intent == "result_update" or message_type == "final_update":
            impression = _clean(result.get("clinical_impression") or result.get("note") or "")
            final_summary = _clean(result.get("final_assessment_summary") or "")
            patient_plan = _clean(result.get("patient_facing_plan") or result.get("patient_plan") or result.get("disposition_advice") or "")
            lines = ["基于你刚补充的信息，我建议把这次外科复查判断调整一下。"]
            if impression:
                lines.append(f"{impression}。")
            if final_summary and final_summary != impression:
                lines.append(f"{final_summary}。")
            if patient_plan:
                lines.append(f"{patient_plan}。")
            medication = _prescription_reply(result)
            if medication:
                lines.append(medication)
            lines.extend(
                _followup_lines(
                    dict(result.get("followup_recommendation") or {}),
                    [str(item).strip() for item in (result.get("return_precautions") or result.get("red_flags") or []) if str(item).strip()],
                    include_precautions=True,
                )
            )
            return "".join(part for part in lines if part).strip()

        if consultation_round >= 2:
            return _round2_answer(result, topics, include_guidance=reassessment_intent == "question_with_minor_guidance")
        return _round1_answer(result, topics, include_guidance=reassessment_intent == "question_with_minor_guidance")

    if consultation_round >= 2:
        lines = ["结合上一轮判断和这次检查结果，我的看法是这样的。"]
        base = _round2_answer(result, topics, include_guidance=True)
        if base:
            lines.append(base)
        return "".join(lines).strip()
    return _round1_answer(result, topics, include_guidance=True)
