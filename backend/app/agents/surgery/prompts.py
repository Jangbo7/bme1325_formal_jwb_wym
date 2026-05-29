from app.agents.surgery.workflow import ConsultationProgress


FIELD_PROMPTS = {
    "chief_complaint": [
        "Please describe the main surgical problem bothering you most in one sentence.",
        "Let me confirm the main surgical concern again. What is the main problem this visit?",
    ],
    "onset_time": [
        "When did this problem start, and was it related to trauma, surgery, or another trigger?",
        "Let me confirm the timeline again. Did this start today, yesterday, after an injury, or after surgery?",
    ],
    "allergies": [
        "Do you have any known drug or material allergies? If none, please reply 'no allergies'.",
        "Let me confirm your allergy history again. Any known drug or material allergies?",
    ],
    "pain_score": [
        "If there is pain, how strong is it now on a 0 to 10 scale?",
        "Please rate the pain from 0 to 10, where 10 is the worst pain you can imagine.",
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
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "the current surgical problem"
    variants = FIELD_PROMPTS.get(field_name)
    if not variants:
        base = (
            "I still need a bit more key information before I can continue the first-round surgical assessment. "
            "Please add the exact location, whether there was trauma or surgery, and whether it is getting worse."
        )
        return f"Let me ask it another way: {base}" if is_repeated else base

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
            f"I have recorded the main surgical concern as '{complaint}' and symptoms such as {symptom_text}. "
            "Please add the exact location, whether there was trauma or surgery, and whether bleeding, swelling, or pain is getting worse."
        )
    if complaint:
        return (
            f"I have recorded the main surgical concern as '{complaint}'. "
            "Please add when it started, the exact location, and whether there was trauma or surgery before it began."
        )
    return "Please continue with the main surgical problem, when it started, and whether you have any allergies."


def build_initial_message(shared_memory: dict, progress: ConsultationProgress, *, policy_runtime_context=None) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "the current surgical problem"
    if progress.patient_reply_count == 0:
        return (
            f"I will start with a first-round surgery intake. You mentioned '{complaint}'. "
            "Please add when it started, whether there was trauma or a recent procedure, any allergy history, and what feels worst right now."
        )
    return "I received your update. Please continue with specific changes in pain, bleeding, swelling, or wound status."


def build_consultation_system_prompt(*, policy_prompt_context: str = "", policy_runtime_context=None) -> str:
    del policy_runtime_context
    prompt = (
        "You are a surgery outpatient consultation assistant. "
        "Base your response only on patient-provided facts and return strict JSON."
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
        "This is a reassessment after a completed result. Do not ask follow-up questions. Return only the updated final JSON."
        if post_final_reassessment
        else "If the information is sufficient, return the final JSON directly."
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
        f"Patient shared facts: {shared_memory}\n"
        f"Historical medical records template: {historical_records_template or {}}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing_fields}\n"
        f"Previous final result: {previous_final_result or {}}\n"
        f"Policy prompt context: {policy_prompt_context}\n"
        f"{reassessment_instruction}\n"
        f"Return strict JSON with keys: {response_keys}"
    )


def build_final_message(result: dict, *, message_type: str = "final") -> str:
    heading = {
        "final": "[Surgery Initial Assessment]",
        "final_update": "[Surgery Updated Assessment]",
        "final_no_change": "[Surgery Assessment Unchanged]",
    }.get(message_type, "[Surgery Initial Assessment]")

    if message_type == "final_no_change":
        intro = "Based on the latest update, the current recommendation does not change."
    elif message_type == "final_update":
        intro = "Based on the latest update, the recommendation is updated as follows."
    else:
        intro = "Based on the current information, the recommendation is as follows."

    department = result.get("department") or "Surgery"
    priority = result.get("priority") or "M"
    note = str(result.get("note") or "Continue outpatient surgical follow-up.")
    patient_plan = str(result.get("patient_plan") or "Please continue the surgical clinic workflow and complete the recommended next step.")
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    red_flags = [str(item).strip() for item in (result.get("red_flags") or []) if str(item).strip()]
    next_step_decision = str(result.get("next_step_decision") or "").strip()
    disposition_advice = str(result.get("disposition_advice") or "").strip()
    clinical_impression = str(result.get("clinical_impression") or "").strip()
    recommended_department = str(result.get("recommended_department") or "").strip()
    needs_second_consult = result.get("needs_second_consultation")
    if needs_second_consult is None:
        needs_second_consult = result.get("needs_second_internal_medicine_consultation")

    lines = [
        heading,
        intro,
        f"Department: {department}",
        f"Priority: {priority}",
        f"Assessment note: {clinical_impression or note}",
        f"Patient plan: {disposition_advice or patient_plan}",
    ]
    if next_step_decision:
        lines.append(f"Next step decision: {next_step_decision}")
    if needs_second_consult is not None:
        lines.append(f"Needs second surgery consultation: {bool(needs_second_consult)}")
    if recommended_department:
        lines.append(f"Recommended clinic: {recommended_department}")
    lines.append(f"Suggested tests: {', '.join(tests) if tests else 'No additional tests suggested for now'}")
    lines.append(f"Suggested actions: {', '.join(actions) if actions else 'Continue the current surgery clinic workflow'}")
    if red_flags:
        lines.append(f"Red flags: {', '.join(red_flags)}")
    lines.append("Seek urgent reassessment immediately if symptoms worsen significantly.")
    return "\n".join(lines)
