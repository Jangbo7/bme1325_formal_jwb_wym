from __future__ import annotations


SPECIALTY_HEADINGS = {
    "surgery": "You are a surgery outpatient assistant.",
    "pediatrics": "You are a pediatrics outpatient assistant.",
    "ent": "You are an ENT outpatient assistant.",
}


def build_specialty_system_prompt(agent_type: str) -> str:
    return (
        f"{SPECIALTY_HEADINGS[agent_type]} "
        "Use the supplied specialty rules and patient context to produce a concise JSON assessment. "
        "Return only strict JSON."
    )


def build_specialty_user_prompt(agent_type: str, payload: dict, retrieved_rules: list[dict]) -> str:
    return (
        f"Specialty agent: {agent_type}\n"
        f"Patient payload: {payload}\n"
        f"Retrieved rules: {retrieved_rules}\n"
        "Return JSON with keys: department, priority, diagnosis_level, note, tests_required, tests_suggested, action_plan, red_flags."
    )


def build_specialty_reply_message(agent_type: str, result: dict) -> str:
    title = {
        "surgery": "Surgery Assessment",
        "pediatrics": "Pediatrics Assessment",
        "ent": "ENT Assessment",
    }[agent_type]
    actions = " ; ".join(result.get("action_plan") or []) or "Continue focused outpatient review."
    tests = ", ".join(result.get("tests_suggested") or []) or "No routine tests suggested yet."
    return (
        f"[{title}] "
        f"Priority {result.get('priority', 'M')}. "
        f"{result.get('note', '')} "
        f"Suggested tests: {tests}. "
        f"Next actions: {actions}"
    )
