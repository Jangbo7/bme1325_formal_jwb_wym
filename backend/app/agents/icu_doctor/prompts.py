from pathlib import Path


RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "icu_rules.json"


FIELD_PROMPTS = {
    "chief_complaint": "What is the main problem bringing the patient to ICU?",
    "symptoms": "Please describe the symptoms and clinical findings as specifically as you can.",
    "onset_time": "When did the symptoms start or when was the patient admitted?",
    "vitals": "Do you have the latest vital signs for the patient?",
    "allergies": "Does the patient have any known allergies to medication?",
    "chronic_conditions": "Does the patient have any pre-existing conditions?",
    "treatment_history": "What treatments has the patient already received?",
}


def build_initial_prompt(triage_level: int, patient_info: dict) -> str:
    urgency_map = {
        1: "CRITICAL - Immediate life-saving intervention required",
        2: "EMERGENT - High risk, urgent evaluation needed",
        3: "URGENT - Moderate risk, timely evaluation needed",
        4: "LESS_URGENT - Low to moderate risk",
        5: "NON_URGENT - Stable, routine care",
    }
    urgency = urgency_map.get(triage_level, "UNKNOWN")
    return (
        f"You are the ICU attending physician. "
        f"Patient triage level: {triage_level} ({urgency}). "
        f"Patient information: {patient_info}. "
        f"Begin ICU consultation workflow."
    )


def build_follow_up_message(missing_fields: list[str], current_status: dict) -> str:
    if not missing_fields:
        return "ICU consultation is complete."
    next_field = missing_fields[0]
    return (
        f"Current ICU assessment status: {current_status.get('note', 'in progress')}. "
        f"I need additional information to complete the treatment plan. "
        f"{FIELD_PROMPTS.get(next_field, 'Please provide more clinical details.')}"
    )


def build_treatment_plan_prompt(patient_info: dict, icu_assessment: dict, retrieved_rules: list[dict]) -> str:
    return (
        "You are the ICU attending physician developing a treatment plan. "
        "Use the retrieved ICU treatment protocols as supporting evidence. "
        f"Patient data: {patient_info}. "
        f"ICU Assessment: {icu_assessment}. "
        f"Treatment protocols: {retrieved_rules}. "
        "Return strict JSON only with keys: triage_level (integer 1-5), urgency (CRITICAL/EMERGENT/URGENT/LESS_URGENT/NON_URGENT), "
        "treatment_plan (string describing the treatment approach), note (string with clinical reasoning). "
        "Consider the patient's registration information and chief complaint when formulating the treatment plan."
    )


def build_consultation_prompt(patient_info: dict, conversation_history: list[dict], retrieved_rules: list[dict]) -> str:
    return (
        "You are the ICU attending physician conducting a consultation. "
        "Use the retrieved ICU treatment protocols as supporting evidence. "
        f"Patient data: {patient_info}. "
        f"Conversation history: {conversation_history}. "
        f"Treatment protocols: {retrieved_rules}. "
        "Return strict JSON only with keys: triage_level (integer 1-5), urgency (CRITICAL/EMERGENT/URGENT/LESS_URGENT/NON_URGENT), "
        "treatment_plan (string describing the treatment approach), note (string with clinical reasoning). "
        "Engage with the patient's described symptoms and provide appropriate medical guidance."
    )
