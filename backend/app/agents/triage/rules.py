import json
import re
from pathlib import Path


RULE_STORE_PATH = Path(__file__).resolve().parents[3] / "rag" / "rule_store.json"
KNOWN_SYMPTOM_TERMS = {
    "chest pain": ["chest pain", "\u80f8\u75db"],
    "chest tightness": ["chest tightness", "\u80f8\u95f7", "\u80f8\u53e3\u95f7"],
    "shortness of breath": [
        "shortness of breath",
        "breathless",
        "dyspnea",
        "\u547c\u5438\u56f0\u96be",
        "\u6c14\u77ed",
        "\u5598\u4e0d\u4e0a\u6c14",
    ],
    "fever": ["fever", "\u53d1\u70ed", "\u53d1\u70e7"],
    "dizziness": ["dizz", "\u5934\u6655"],
    "cough": ["cough", "\u54b3\u55fd"],
    "abdominal pain": ["abdominal pain", "stomach ache", "\u809a\u5b50\u75db", "\u8179\u75db"],
    "headache": ["headache", "\u5934\u75db"],
}
STOP_SYMPTOM_PHRASES = (
    "started",
    "ago",
    "today",
    "morning",
    "evening",
    "hours",
    "hour",
    "minutes",
    "minute",
    "\u6ca1\u6709\u8fc7\u654f",
    "\u4e0d\u6e05\u695a",
    "pain score",
)


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_rules() -> list[dict]:
    return json.loads(RULE_STORE_PATH.read_text(encoding="utf-8"))


def split_symptoms(text: str) -> list[str]:
    normalized = (text or "").replace(";", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def extract_symptoms(message: str) -> list[str]:
    lowered = (message or "").lower()
    found = []
    for symptom, patterns in KNOWN_SYMPTOM_TERMS.items():
        if any(term.lower() in lowered for term in patterns):
            found.append(symptom)
    if found:
        return found
    raw_items = split_symptoms(message)
    cleaned = []
    for item in raw_items:
        lowered_item = item.lower()
        if any(token in lowered_item for token in STOP_SYMPTOM_PHRASES):
            continue
        if len(item.strip()) < 2:
            continue
        cleaned.append(item.strip())
    return cleaned[:4]


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ("chest", "breath", "dyspnea", "tightness", "\u80f8\u75db", "\u80f8\u95f7", "\u547c\u5438\u56f0\u96be")):
        risk_flags.append("cardiopulmonary_alert")
    if any(term in joined for term in ("faint", "syncope", "collapse", "\u5934\u6655", "\u6655")):
        risk_flags.append("consciousness_alert")
    if _safe_float(vitals.get("temp_c"), 0.0) >= 38.5:
        risk_flags.append("fever")
    if _safe_int(vitals.get("pain_score"), 0) >= 8:
        risk_flags.append("severe_pain")
    return sorted(set(risk_flags))


def merge_vitals(old_vitals: dict, new_vitals: dict) -> dict:
    merged = dict(old_vitals or {})
    for key, value in (new_vitals or {}).items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def merge_unique(old_values: list, new_values: list) -> list:
    merged = list(old_values or [])
    for value in new_values or []:
        if value and value not in merged:
            merged.append(value)
    return merged


def build_missing_fields(shared_memory: dict) -> list[str]:
    missing = []
    clinical = shared_memory["clinical_memory"]
    profile = shared_memory["profile"]
    if not clinical.get("chief_complaint"):
        missing.append("chief_complaint")
    if not clinical.get("symptoms"):
        missing.append("symptoms")
    if not clinical.get("onset_time"):
        missing.append("onset_time")
    if "temp_c" not in (clinical.get("vitals") or {}):
        missing.append("temp_c")
    if "pain_score" not in (clinical.get("vitals") or {}):
        missing.append("pain_score")
    if profile.get("allergy_status") != "known":
        missing.append("allergies")
    return missing


def prioritize_missing_fields(shared_memory: dict, private_memory: dict | None = None) -> list[str]:
    missing = build_missing_fields(shared_memory)
    if not missing:
        return []
    clinical = shared_memory["clinical_memory"]
    symptoms_text = " ".join(clinical.get("symptoms") or []).lower()
    risk_flags = set(clinical.get("risk_flags") or [])
    asked_fields_history = (private_memory or {}).get("asked_fields_history", [])
    last_question_focus = (private_memory or {}).get("last_question_focus")

    if "cardiopulmonary_alert" in risk_flags or any(term in symptoms_text for term in ("chest", "breath", "\u80f8\u75db", "\u80f8\u95f7", "\u547c\u5438\u56f0\u96be")):
        preferred = ["onset_time", "pain_score", "temp_c", "allergies", "symptoms", "chief_complaint"]
    elif "fever" in risk_flags or "fever" in symptoms_text or "\u53d1\u70ed" in symptoms_text or "\u53d1\u70e7" in symptoms_text:
        preferred = ["temp_c", "onset_time", "symptoms", "allergies", "pain_score", "chief_complaint"]
    else:
        preferred = ["chief_complaint", "symptoms", "onset_time", "pain_score", "temp_c", "allergies"]

    preferred_order = {field: idx for idx, field in enumerate(preferred)}

    def sort_key(field: str):
        asked_count = sum(1 for item in asked_fields_history if item == field)
        same_as_last = 1 if field == last_question_focus else 0
        return (same_as_last, asked_count, preferred_order.get(field, 999), field)

    return sorted(missing, key=sort_key)


def score_rule(rule: dict, payload: dict) -> int:
    score = 0
    symptoms = (payload.get("symptoms") or "").lower()
    vitals = payload.get("vitals") or {}
    conditions = rule.get("conditions") or {}
    for term in rule.get("keywords") or []:
        if term.lower() in symptoms:
            score += 2
    for symptom in conditions.get("symptoms_any", []):
        if symptom.lower() in symptoms:
            score += 4
    if "heart_rate_gte" in conditions and _safe_int(vitals.get("heart_rate"), 0) >= _safe_int(conditions.get("heart_rate_gte"), 999):
        score += 3
    if "temp_c_gte" in conditions and _safe_float(vitals.get("temp_c"), 0.0) >= _safe_float(conditions.get("temp_c_gte"), 999.0):
        score += 3
    if "pain_score_gte" in conditions and _safe_int(vitals.get("pain_score"), 0) >= _safe_int(conditions.get("pain_score_gte"), 999):
        score += 3
    if conditions.get("default"):
        score += 1
    return score


def retrieve_relevant_rules(payload: dict, top_k: int = 3) -> list[dict]:
    rules = load_rules()
    scored = []
    for rule in rules:
        score = score_rule(rule, payload)
        if score > 0:
            scored.append({"score": score, "rule": rule})
    scored.sort(key=lambda item: item["score"], reverse=True)
    picked = [item["rule"] for item in scored if not (item["rule"].get("conditions") or {}).get("default")][:top_k]
    if picked:
        return picked
    for rule in rules:
        if (rule.get("conditions") or {}).get("default"):
            return [rule]
    return []


def rule_based_triage(payload: dict) -> dict:
    vitals = payload.get("vitals") or {}
    hr = _safe_int(vitals.get("heart_rate"), 90)
    pain = _safe_int(vitals.get("pain_score"), 3)
    temp = _safe_float(vitals.get("temp_c"), 36.8)
    symptoms = (payload.get("symptoms") or "").lower()
    level = 4
    priority = "L"
    dept = "General Medicine"
    note = "Low to medium risk. Continue standard consultation process."
    if hr >= 120 or pain >= 8 or any(term in symptoms for term in ("chest", "breath", "faint", "severe", "\u80f8\u75db", "\u547c\u5438\u56f0\u96be")):
        level = 2
        priority = "H"
        dept = "Emergency"
        note = "High risk detected. Priority handling is recommended."
    elif temp >= 38.5:
        level = 3
        priority = "M"
        dept = "Fever Clinic"
        note = "Fever symptoms detected. Route to fever clinic."
    return {
        "triage_level": level,
        "priority": priority,
        "department": dept,
        "note": note,
    }


def validate_triage_result(result: dict | None, fallback_result: dict) -> dict:
    if not isinstance(result, dict):
        return fallback_result
    triage_level = result.get("triage_level")
    priority = result.get("priority")
    department = result.get("department")
    note = result.get("note")
    if not isinstance(triage_level, int) or not 1 <= triage_level <= 5:
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


def extract_time_text(message: str) -> tuple[str | None, float]:
    lowered = (message or "").lower()
    for phrase, mapped in (
        ("just now", "just now"),
        ("\u521a\u521a", "just now"),
        ("today morning", "today morning"),
        ("this morning", "today morning"),
        ("\u4eca\u5929\u65e9\u4e0a", "today morning"),
        ("\u4eca\u65e9", "today morning"),
        ("\u6628\u665a", "last night"),
        ("\u6628\u5929\u665a\u4e0a", "last night"),
        ("\u6709\u4e00\u9635\u5b50", "a while"),
    ):
        if phrase in lowered or phrase in message:
            return mapped, 0.8
    if "half hour" in lowered or "30 min" in lowered or "\u534a\u5c0f\u65f6" in message:
        return "30 minutes", 0.95
    for pattern in (
        r"(\d+)\s*(min|mins|minute|minutes|hour|hours|day|days)",
        r"(\d+)\s*(\u5206\u949f|\u5c0f\u65f6|\u5929)",
        r"\u6301\u7eed\u4e86?\s*(\d+)\s*(\u5c0f\u65f6|\u5206\u949f|\u5929)",
        r"\u5927\u6982\s*(\d+)\s*(\u5c0f\u65f6|\u5206\u949f|\u5929)",
    ):
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(0), 0.9
    return None, 0.0


def extract_pain_score(message: str) -> tuple[int | None, float]:
    match = re.search(r"(\d{1,2})\s*(?:/10|\u5206|points|point)", message, flags=re.IGNORECASE)
    if match:
        return max(0, min(10, int(match.group(1)))), 0.95
    lowered = (message or "").lower()
    if "\u4e0d\u662f\u7279\u522b\u75db" in message or "not very painful" in lowered:
        return 3, 0.75
    if "\u6709\u70b9\u75db" in message or "slight pain" in lowered:
        return 2, 0.75
    if "\u633a\u75db" in message or "quite painful" in lowered:
        return 6, 0.75
    if "\u5f88\u75db" in message or "severe pain" in lowered:
        return 8, 0.8
    return None, 0.0


def extract_temp_c(message: str) -> tuple[float | None, float]:
    match = re.search(r"(\d{2}(?:\.\d)?)\s*(?:c|\u2103|\u5ea6)", message, flags=re.IGNORECASE)
    if match:
        value = float(match.group(1))
        if value >= 30:
            return value, 0.95
    lowered = (message or "").lower()
    if "no fever" in lowered or "\u6ca1\u53d1\u70e7" in message or "\u6ca1\u6709\u53d1\u70e7" in message:
        return 37.0, 0.8
    if "\u6709\u70b9\u53d1\u70ed" in message or "\u611f\u89c9\u53d1\u70ed" in message:
        return 37.8, 0.6
    if "38\u5ea6\u591a" in message:
        return 38.2, 0.75
    return None, 0.0


def extract_allergies(message: str):
    lowered = (message or "").lower()
    if any(term in lowered for term in ("no allergy", "no allergies")) or any(
        term in message for term in ("\u6ca1\u6709\u8fc7\u654f", "\u6ca1\u53d1\u73b0\u8fc7\u654f", "\u4ee5\u524d\u6ca1\u53d1\u73b0\u8fc7\u654f")
    ):
        return [], 0.9, "known"
    if any(term in message for term in ("\u5e94\u8be5\u6ca1\u6709", "\u4e0d\u6e05\u695a", "\u4e0d\u592a\u6e05\u695a")):
        return None, 0.4, "uncertain"
    return None, 0.0, None


def extract_structured_updates(message: str, target_fields: list[str] | None = None) -> dict:
    symptoms = extract_symptoms(message)
    onset_time, onset_conf = extract_time_text(message)
    pain_score, pain_conf = extract_pain_score(message)
    temp_c, temp_conf = extract_temp_c(message)
    allergies, allergy_conf, allergy_status = extract_allergies(message)

    confidence_by_field = {}
    extracted_fields = []
    if symptoms:
        confidence_by_field["symptoms"] = 0.7
        extracted_fields.append("symptoms")
    if onset_time:
        confidence_by_field["onset_time"] = onset_conf
        extracted_fields.append("onset_time")
    if pain_score is not None:
        confidence_by_field["pain_score"] = pain_conf
        extracted_fields.append("pain_score")
    if temp_c is not None:
        confidence_by_field["temp_c"] = temp_conf
        extracted_fields.append("temp_c")
    if allergy_status == "known":
        confidence_by_field["allergies"] = allergy_conf
        extracted_fields.append("allergies")

    target_fields = target_fields or []
    unresolved_targets = [field for field in target_fields if field not in extracted_fields]

    return {
        "onset_time": onset_time,
        "pain_score": pain_score,
        "temp_c": temp_c,
        "allergies": allergies,
        "allergy_status": allergy_status,
        "symptoms": symptoms,
        "extracted_fields": extracted_fields,
        "confidence_by_field": confidence_by_field,
        "unresolved_targets": unresolved_targets,
    }
