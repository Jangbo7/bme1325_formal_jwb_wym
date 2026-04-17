import json
import re
from pathlib import Path


INTERNAL_MEDICINE_RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "internal_medicine_rules.json"


def load_internal_medicine_rules() -> list[dict]:
    if INTERNAL_MEDICINE_RULE_STORE_PATH.exists():
        try:
            return json.loads(INTERNAL_MEDICINE_RULE_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_rules()


def _default_rules() -> list[dict]:
    return [
        {
            "id": "im-rule-fever",
            "title": "Fever or infection-like symptoms",
            "keywords": ["fever", "cough", "chills", "infection"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Internal Medicine",
                "note": "Possible infection-related complaint. Continue outpatient evaluation.",
            },
            "source": "Internal medicine fallback rules",
        },
        {
            "id": "im-rule-gastro",
            "title": "GI discomfort",
            "keywords": ["stomach", "abdominal", "nausea", "vomit", "diarrhea"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Internal Medicine",
                "note": "Possible gastrointestinal complaint. Continue outpatient evaluation.",
            },
            "source": "Internal medicine fallback rules",
        },
        {
            "id": "im-rule-general",
            "title": "General outpatient follow-up",
            "keywords": [],
            "result": {
                "diagnosis_level": 1,
                "priority": "L",
                "department": "Internal Medicine",
                "note": "General outpatient follow-up is recommended.",
            },
            "source": "Internal medicine fallback rules",
        },
    ]


def split_symptoms(text: str) -> list[str]:
    normalized = (text or "").replace(";", ",").replace("/", ",").replace(" and ", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def merge_unique(old_values: list | None, new_values: list | None) -> list:
    merged = list(old_values or [])
    for value in new_values or []:
        if value and value not in merged:
            merged.append(value)
    return merged


def merge_vitals(old_vitals: dict | None, new_vitals: dict | None) -> dict:
    merged = dict(old_vitals or {})
    for key, value in (new_vitals or {}).items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ["chest", "heart", "palpitation"]):
        risk_flags.append("cardiac_alert")
    if any(term in joined for term in ["breath", "dyspnea", "shortness"]):
        risk_flags.append("respiratory_alert")
    if any(term in joined for term in ["headache", "dizzy", "numb"]):
        risk_flags.append("neurological_alert")
    try:
        if vitals.get("temp_c") is not None and float(vitals.get("temp_c")) >= 38.0:
            risk_flags.append("fever")
    except Exception:
        pass
    return sorted(set(risk_flags))


def build_missing_fields(shared_memory: dict) -> list[str]:
    clinical = shared_memory.get("clinical_memory", {})
    profile = shared_memory.get("profile", {})
    missing = []
    if not clinical.get("chief_complaint"):
        missing.append("chief_complaint")
    if not clinical.get("onset_time"):
        missing.append("onset_time")
    if profile.get("allergy_status") != "known":
        missing.append("allergies")
    return missing


def extract_structured_updates(message: str) -> dict:
    text = (message or "").strip()
    lowered = text.lower()
    extracted = {
        "chief_complaint": None,
        "onset_time": None,
        "allergies": None,
        "allergy_status": None,
        "symptoms": [],
    }
    if text and len(text) > 4:
        extracted["symptoms"] = split_symptoms(text)
        extracted["chief_complaint"] = text[:120]

    onset_patterns = [
        r"(today|this morning|this afternoon|tonight|yesterday)",
        r"(\d+\s*(minute|minutes|hour|hours|day|days|week|weeks))",
        r"(since\s+[a-zA-Z0-9\s:]+)",
    ]
    for pattern in onset_patterns:
        match = re.search(pattern, lowered)
        if match:
            extracted["onset_time"] = match.group(1)
            break

    if any(token in lowered for token in ["no allergy", "no allergies", "none", "nkda"]):
        extracted["allergies"] = []
        extracted["allergy_status"] = "known"
    elif "allergy" in lowered or "allergic" in lowered:
        extracted["allergies"] = [text]
        extracted["allergy_status"] = "known"
    return extracted


def retrieve_relevant_internal_medicine_rules(payload: dict, top_k: int = 3) -> list[dict]:
    text = ((payload.get("symptoms") or "") + " " + (payload.get("chief_complaint") or "")).lower()
    scored = []
    for rule in load_internal_medicine_rules():
        score = 0
        for keyword in rule.get("keywords", []):
            if keyword and keyword.lower() in text:
                score += 1
        if score > 0 or not rule.get("keywords"):
            scored.append((score, rule))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def rule_based_internal_medicine(payload: dict) -> dict:
    rules = retrieve_relevant_internal_medicine_rules(payload, top_k=1)
    if rules:
        return dict(rules[0]["result"])
    return {
        "diagnosis_level": 1,
        "priority": "L",
        "department": "Internal Medicine",
        "note": "General outpatient follow-up is recommended.",
    }


def validate_internal_medicine_result(llm_result: dict | None, fallback: dict) -> dict:
    if not llm_result:
        return fallback
    try:
        result = {
            "diagnosis_level": int(llm_result.get("diagnosis_level", fallback["diagnosis_level"])),
            "priority": str(llm_result.get("priority", fallback["priority"])),
            "department": str(llm_result.get("department", fallback["department"])),
            "note": str(llm_result.get("note", fallback["note"])),
        }
        if result["priority"] not in {"H", "M", "L"}:
            result["priority"] = fallback["priority"]
        result["diagnosis_level"] = max(1, min(3, result["diagnosis_level"]))
        return result
    except Exception:
        return fallback
