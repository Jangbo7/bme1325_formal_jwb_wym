from app.agents.internal_medicine.workflow import ConsultationProgress


def build_follow_up_question(field_name: str, shared_memory: dict) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "your current symptoms"
    if field_name == "chief_complaint":
        return "Please describe the main symptom that is bothering you most right now."
    if field_name == "onset_time":
        return f"I have noted {complaint}. When did it start, and how long has it been going on?"
    if field_name == "allergies":
        return "Before I give advice, I need to confirm whether you have any drug allergies or other known allergies."
    return "I still need one more detail before I can continue."


def build_initial_message(shared_memory: dict, progress: ConsultationProgress) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "your current discomfort"
    if progress.patient_reply_count == 0:
        return (
            f"I can see from the triage record that you mentioned {complaint}. "
            "I will continue the consultation now. Please tell me when it started and what feels most uncomfortable at the moment."
        )
    return "I need a little more detail so I can continue the consultation."


def build_consultation_system_prompt() -> str:
    return (
        "You are an internal medicine outpatient doctor. "
        "Ask focused follow-up questions or give a concise outpatient recommendation. "
        "Respond in Chinese. Keep the answer short and practical."
    )


def build_consultation_user_prompt(shared_memory: dict, message: str, missing_fields: list[str]) -> str:
    return (
        f"Patient shared facts: {shared_memory}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing_fields}\n"
        "Return JSON with keys: assistant_message, complete(bool), department, priority, diagnosis_level, note."
    )


def build_final_message(result: dict) -> str:
    department = result.get("department") or "Internal Medicine"
    priority = result.get("priority") or "M"
    note = result.get("note") or "This looks like a common outpatient internal medicine issue."
    return (
        f"Outpatient recommendation: {department}\n"
        f"Priority: {priority}\n"
        f"{note}\n"
        "This consultation is complete for now. You can continue to the next step."
    )
