FIELD_PROMPTS = {
    "chief_complaint": "What is the main problem you want to address right now?",
    "symptoms": "Please describe the symptoms as specifically as you can.",
    "onset_time": "When did the symptoms start?",
    "temp_c": "Do you know your temperature, or do you feel feverish?",
    "pain_score": "If 0 means no pain and 10 means the worst pain, what is your pain score?",
    "allergies": "Do you have any known allergies to medicine or food?",
}


def build_follow_up_message(missing_fields: list[str], triage_result: dict) -> str:
    if not missing_fields:
        return (
            f"Triage complete. Recommended department: {triage_result['department']}. "
            f"Level {triage_result['triage_level']}. {triage_result['note']}"
        )
    next_field = missing_fields[0]
    return (
        f"Current recommendation is {triage_result['department']} with priority {triage_result['priority']}. "
        f"I still need one more detail to make the advice more reliable. "
        f"{FIELD_PROMPTS.get(next_field, 'Please provide a bit more detail.')}"
    )
