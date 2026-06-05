def validate_triage_result(result, fallback_result):
    if not isinstance(result, dict):
        return fallback_result

    triage_level = result.get("triage_level")
    priority = result.get("priority")
    department = result.get("department")
    note = result.get("note")

    if not isinstance(triage_level, int) or triage_level < 1 or triage_level > 5:
        triage_level = fallback_result["triage_level"]
    if priority not in {"H", "M", "L"}:
        priority = fallback_result["priority"]
    if not isinstance(department, str) or not department.strip():
        department = fallback_result["department"]
    if not isinstance(note, str) or not note.strip():
        note = fallback_result["note"]

    return {
        "triage_level": triage_level,
        "priority": priority,
        "department": department.strip(),
        "note": note.strip(),
    }
