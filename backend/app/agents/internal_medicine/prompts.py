from app.agents.internal_medicine.workflow import ConsultationProgress


FIELD_PROMPTS = {
    "chief_complaint": [
        "Please describe the main problem that bothers you most in one sentence.",
        "Let me confirm the main symptom again. What is the main discomfort this visit?",
    ],
    "onset_time": [
        "When did this problem start? A rough answer like this morning, yesterday, or a few days ago is enough.",
        "Let me confirm the timeline again. Did this just start, or has it been going on for some time?",
        "If you do not remember the exact time, you can answer with a rough time such as today, last night, or several hours ago.",
    ],
    "allergies": [
        "Do you have any known drug or food allergies? If none, please reply 'no allergies'.",
        "Let me confirm your allergy history again. Any known drug or food allergies?",
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
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "the current symptom"
    variants = FIELD_PROMPTS.get(field_name)
    if not variants:
        base = "I still need a bit more key information before I can continue the first-round assessment."
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
            f"I have recorded the main problem as '{complaint}' and symptoms such as {symptom_text}. "
            "Please add how severe it feels, whether it is getting worse, and whether it affects daily activity."
        )
    if complaint:
        return f"I have recorded the main problem as '{complaint}'. Please add when it started and whether it is getting worse."
    return "Please continue with the main symptom, when it started, and whether you have any allergies."


def build_initial_message(shared_memory: dict, progress: ConsultationProgress, *, policy_runtime_context=None) -> str:
    del policy_runtime_context
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "the current symptom"
    if progress.patient_reply_count == 0:
        return (
            f"I will start with a first-round internal medicine intake. You mentioned '{complaint}'. "
            "Please add when it started, any allergy history, and what feels most uncomfortable right now."
        )
    return "I received your update. Please continue with specific symptom changes so I can keep assessing the case."


def build_consultation_system_prompt(*, policy_prompt_context: str = "", policy_runtime_context=None) -> str:
    del policy_runtime_context
    prompt = (
        "You are an internal medicine outpatient consultation assistant. "
        "Base your response only on the patient-provided facts and return strict JSON."
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
    del policy_runtime_context
    reassessment_instruction = (
        "This is a reassessment after a completed result. Do not ask follow-up questions. Return only the updated final JSON."
        if post_final_reassessment
        else "If the information is sufficient, return the final JSON directly."
    )
    return (
        f"Patient shared facts: {shared_memory}\n"
        f"Historical medical records template: {historical_records_template or {}}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing_fields}\n"
        f"Previous final result: {previous_final_result or {}}\n"
        f"Policy prompt context: {policy_prompt_context}\n"
        f"{reassessment_instruction}\n"
        "Return strict JSON with keys: "
        "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
        "medication_or_action, red_flags, test_required, test_category, test_items, test_reason."
    )


def build_final_message(result: dict, *, message_type: str = "final") -> str:
    heading = {
        "final": "[Internal Medicine Initial Assessment]",
        "final_update": "[Internal Medicine Updated Assessment]",
        "final_no_change": "[Internal Medicine Assessment Unchanged]",
    }.get(message_type, "[Internal Medicine Initial Assessment]")

    if message_type == "final_no_change":
        intro = "Based on the latest update, the current recommendation does not change."
    elif message_type == "final_update":
        intro = "Based on the latest update, the recommendation is updated as follows."
    else:
        intro = "Based on the current information, the recommendation is as follows."

    department = result.get("department") or "Internal Medicine"
    priority = result.get("priority") or "M"
    note = result.get("note") or "Continue outpatient follow-up."
    patient_plan = result.get("patient_plan") or "Please continue the clinic workflow and complete the recommended checks."
    tests = [str(item).strip() for item in (result.get("tests_suggested") or []) if str(item).strip()]
    actions = [str(item).strip() for item in (result.get("medication_or_action") or []) if str(item).strip()]
    red_flags = [str(item).strip() for item in (result.get("red_flags") or []) if str(item).strip()]

    lines = [
        heading,
        intro,
        f"Department: {department}",
        f"Priority: {priority}",
        f"Assessment note: {note}",
        f"Patient plan: {patient_plan}",
        f"Suggested tests: {', '.join(tests) if tests else 'No additional tests suggested for now'}",
        f"Suggested actions: {', '.join(actions) if actions else 'Continue the current clinic workflow'}",
    ]
    if red_flags:
        lines.append(f"Red flags: {', '.join(red_flags)}")
    lines.append("Seek urgent reassessment immediately if symptoms worsen significantly.")
    return "\n".join(lines)
