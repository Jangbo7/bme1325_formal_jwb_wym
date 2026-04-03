import json
import re
from pathlib import Path


RULE_STORE_PATH = Path(__file__).resolve().parents[3] / "rag" / "rule_store.json"


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


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ("chest", "breath", "dyspnea", "tightness")):
        risk_flags.append("cardiopulmonary_alert")
    if any(term in joined for term in ("faint", "syncope", "collapse")):
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
    if hr >= 120 or pain >= 8 or any(term in symptoms for term in ("chest", "breath", "faint", "severe")):
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


def extract_time_text(message: str) -> str | None:
    lowered = (message or "").lower()
    if "just now" in lowered:
        return "just now"
    if "half hour" in lowered or "30 min" in lowered:
        return "30 minutes"
    for pattern in (
        r"(\d+)\s*(min|mins|minute|minutes|hour|hours|day|days)",
        r"(\d+)\s*(minutes|hours|days)",
    ):
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def extract_pain_score(message: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(?:/10|points|point)", message, flags=re.IGNORECASE)
    if match:
        return max(0, min(10, int(match.group(1))))
    lowered = (message or "").lower()
    if "severe pain" in lowered:
        return 8
    if "slight pain" in lowered:
        return 3
    return None


def extract_temp_c(message: str) -> float | None:
    match = re.search(r"(\d{2}(?:\.\d)?)\s*(?:c|°c)", message, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    lowered = (message or "").lower()
    if "no fever" in lowered:
        return 37.0
    return None


def extract_allergies(message: str):
    lowered = (message or "").lower()
    if "no allergy" in lowered or "no allergies" in lowered:
        return []
    return None


def extract_structured_updates(message: str) -> dict:
    return {
        "onset_time": extract_time_text(message),
        "pain_score": extract_pain_score(message),
        "temp_c": extract_temp_c(message),
        "allergies": extract_allergies(message),
        "symptoms": split_symptoms(message),
    }
