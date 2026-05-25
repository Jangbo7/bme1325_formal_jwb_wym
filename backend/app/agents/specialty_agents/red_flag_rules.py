def detect_red_flags(payload: dict) -> list[str]:
    text = f"{payload.get('chief_complaint', '')} {payload.get('symptoms', '')} {payload.get('message', '')}".lower()
    flags = []

    def has_any(*tokens: str) -> bool:
        return any(token.lower() in text for token in tokens)

    if has_any("chest pain", "shortness of breath", "呼吸困难", "胸痛"):
        flags.append("possible_cardiopulmonary_emergency")
    if has_any("loss of consciousness", "faint", "昏迷", "意识不清"):
        flags.append("possible_consciousness_emergency")
    if has_any("severe bleeding", "uncontrolled bleeding", "大量出血"):
        flags.append("possible_bleeding_emergency")
    if has_any("suicidal", "self-harm", "自杀", "自伤"):
        flags.append("mental_health_crisis")
    if has_any("severe abdominal pain", "persistent vomiting", "剧烈腹痛", "持续呕吐"):
        flags.append("possible_abdominal_emergency")

    return flags
