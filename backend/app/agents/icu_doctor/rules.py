import json
import re
from pathlib import Path


ICU_RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "icu_rules.json"


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


def load_icu_rules() -> list[dict]:
    if ICU_RULE_STORE_PATH.exists():
        return json.loads(ICU_RULE_STORE_PATH.read_text(encoding="utf-8"))
    return _get_default_icu_rules()


def _get_default_icu_rules() -> list[dict]:
    return [
        {
            "id": "icu-rule-001",
            "title": "Severe respiratory distress requiring immediate intervention",
            "keywords": ["respiratory distress", "shortness of breath", "dyspnea", "respiratory failure", "呼吸困难", "呼吸衰竭", "ICU", "呼吸机"],
            "conditions": {
                "symptoms_any": ["respiratory distress", "shortness of breath", "dyspnea", "respiratory failure", "呼吸困难", "呼吸衰竭"],
                "spo2_lte": 90,
            },
            "result": {
                "triage_level": 1,
                "urgency": "CRITICAL",
                "treatment_plan": "Immediate respiratory support with mechanical ventilation if needed. Airway management and oxygen therapy. ICU admission mandatory.",
                "note": "Patient presents with severe respiratory compromise requiring immediate life-saving intervention."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-002",
            "title": "Cardiac emergency with hemodynamic instability",
            "keywords": ["chest pain", "myocardial infarction", "cardiac arrest", "shock", "心梗", "心脏骤停", "心源性休克", "chest pain", "cardiac"],
            "conditions": {
                "symptoms_any": ["chest pain", "myocardial infarction", "cardiac arrest", "shock", "心梗", "心脏骤停", "心源性休克"],
                "systolic_bp_lte": 90,
            },
            "result": {
                "triage_level": 1,
                "urgency": "CRITICAL",
                "treatment_plan": "Immediate cardiac resuscitation. Establish IV access, administer vasopressors if needed. Continuous cardiac monitoring. Emergency cardiology consultation.",
                "note": "Patient presents with life-threatening cardiac emergency requiring immediate resuscitation."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-003",
            "title": "Severe sepsis or septic shock",
            "keywords": ["sepsis", "septic shock", "infection", "高热", "septic", "败血症", "感染性休克"],
            "conditions": {
                "symptoms_any": ["sepsis", "septic shock", "septic", "败血症", "感染性休克"],
                "temp_c_gte": 39.0,
            },
            "result": {
                "triage_level": 1,
                "urgency": "CRITICAL",
                "treatment_plan": "Immediate broad-spectrum antibiotics within first hour. Fluid resuscitation with crystalloids. Vasopressors if hypotensive despite fluids. Source control.",
                "note": "Patient presents with severe sepsis or septic shock requiring immediate intervention."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-004",
            "title": "Neurological emergency - decreased level of consciousness",
            "keywords": ["coma", "unconscious", "stroke", "GCS", "脑卒中", "昏迷", "意识障碍", "seizure", "癫痫"],
            "conditions": {
                "symptoms_any": ["coma", "unconscious", "stroke", "GCS", "脑卒中", "昏迷", "意识障碍", "seizure", "癫痫"],
            },
            "result": {
                "triage_level": 1,
                "urgency": "CRITICAL",
                "treatment_plan": "Immediate neurological assessment. Secure airway if GCS < 8. CT head to rule out hemorrhage. Monitor for herniation signs.",
                "note": "Patient presents with neurological emergency requiring immediate evaluation."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-005",
            "title": "Trauma with hemodynamic instability",
            "keywords": ["trauma", "injury", "bleeding", "fracture", "创伤", "骨折", "出血", "accident"],
            "conditions": {
                "symptoms_any": ["trauma", "injury", "bleeding", "fracture", "创伤", "骨折", "出血"],
                "systolic_bp_lte": 100,
            },
            "result": {
                "triage_level": 1,
                "urgency": "CRITICAL",
                "treatment_plan": "Immediate hemorrhage control. Fluid resuscitation. Blood transfusion as needed. Surgical consultation for source control.",
                "note": "Patient presents with traumatic injury requiring immediate surgical evaluation."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-006",
            "title": "Post-operative critical care required",
            "keywords": ["post-op", "postoperative", "surgery", "术后", "手术后来", "operation recovery"],
            "conditions": {
                "symptoms_any": ["post-op", "postoperative", "surgery", "术后", "手术后来", "operation recovery"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Close post-operative monitoring. Pain management. Prevention of complications. Routine ICU care protocols.",
                "note": "Patient requires post-operative critical care monitoring."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-007",
            "title": "Acute respiratory failure - non-critical",
            "keywords": ["respiratory failure", "hypoxia", "pneumonia", "COPD exacerbation", "呼吸衰竭", "肺炎", "低氧血症"],
            "conditions": {
                "symptoms_any": ["respiratory failure", "hypoxia", "pneumonia", "COPD exacerbation", "呼吸衰竭", "肺炎", "低氧血症"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Oxygen therapy with target SpO2 88-92% for COPD, >94% for others. Consider non-invasive ventilation. Treat underlying cause.",
                "note": "Patient presents with respiratory failure requiring close monitoring and supportive care."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-008",
            "title": "Acute coronary syndrome - stable",
            "keywords": ["ACS", "unstable angina", "coronary syndrome", "心绞痛", "不稳定心绞痛"],
            "conditions": {
                "symptoms_any": ["ACS", "unstable angina", "coronary syndrome", "心绞痛", "不稳定心绞痛"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Dual antiplatelet therapy. Anticoagulation. Beta-blockers. Statins. Cardiology consultation for angiogram.",
                "note": "Patient presents with acute coronary syndrome requiring urgent cardiac workup."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-009",
            "title": "Diabetic emergency - DKA or HHS",
            "keywords": ["DKA", "ketoacidosis", "diabetic", "hyperglycemia", "hypoglycemia", "血糖", "酮症", "糖尿病急症"],
            "conditions": {
                "symptoms_any": ["DKA", "ketoacidosis", "diabetic emergency", "血糖", "酮症", "糖尿病急症", "hypoglycemia", "hyperglycemia"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Fluid resuscitation with normal saline. Insulin drip. Potassium replacement when K+ < 5.2. Monitor glucose q1h.",
                "note": "Patient presents with diabetic emergency requiring metabolic management."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-010",
            "title": "Gastrointestinal emergency - bleeding or perforation",
            "keywords": ["GI bleed", "GI bleeding", "perforation", "hemorrhage", "消化道出血", "胃肠出血", "穿孔"],
            "conditions": {
                "symptoms_any": ["GI bleed", "GI bleeding", "perforation", "hemorrhage", "消化道出血", "胃肠出血", "穿孔"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Fluid resuscitation. Blood transfusion if needed. NPO status. IV proton pump inhibitor. GI surgery consultation.",
                "note": "Patient presents with GI emergency requiring urgent intervention."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-011",
            "title": "Renal failure requiring ICU monitoring",
            "keywords": ["renal failure", "kidney injury", "AKI", "nephrology", "肾衰", "肾功能", "肾损伤", "透析"],
            "conditions": {
                "symptoms_any": ["renal failure", "kidney injury", "AKI", "nephrology", "肾衰", "肾功能", "肾损伤", "透析"],
            },
            "result": {
                "triage_level": 3,
                "urgency": "URGENT",
                "treatment_plan": "Fluid management. Avoid nephrotoxins. Monitor electrolytes closely. Consider renal replacement therapy if indicated.",
                "note": "Patient requires ICU monitoring for acute kidney injury."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-012",
            "title": "Drug overdose or toxicity",
            "keywords": ["overdose", "toxicity", "poisoning", "drug", "toxin", "中毒", "药物过量", "中毒"],
            "conditions": {
                "symptoms_any": ["overdose", "toxicity", "poisoning", "drug", "toxin", "中毒", "药物过量"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Supportive care. Decontamination if appropriate. Specific antidotes if known toxin. Monitor for complications.",
                "note": "Patient presents with possible overdose requiring toxicology workup and supportive care."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-013",
            "title": "Electrolyte disturbance - severe",
            "keywords": ["electrolyte", "hypokalemia", "hyperkalemia", "hyponatremia", "电解质紊乱", "钾", "钠"],
            "conditions": {
                "symptoms_any": ["electrolyte disturbance", "hypokalemia", "hyperkalemia", "hyponatremia", "电解质紊乱"],
            },
            "result": {
                "triage_level": 3,
                "urgency": "URGENT",
                "treatment_plan": "Correct electrolyte abnormalities per protocol. Monitor cardiac rhythm. Identify and treat underlying cause.",
                "note": "Patient presents with severe electrolyte disturbance requiring ICU monitoring."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-014",
            "title": "Pulmonary embolism",
            "keywords": ["PE", "pulmonary embolism", "DVT", "blood clot", "肺栓塞", "深静脉血栓"],
            "conditions": {
                "symptoms_any": ["PE", "pulmonary embolism", "DVT", "blood clot", "肺栓塞", "深静脉血栓"],
            },
            "result": {
                "triage_level": 2,
                "urgency": "EMERGENT",
                "treatment_plan": "Anticoagulation with heparin. Consider thrombolysis if hemodynamic unstable. Investigate source of embolism.",
                "note": "Patient presents with pulmonary embolism requiring ICU monitoring."
            },
            "source": "ICU Treatment Protocol v1"
        },
        {
            "id": "icu-rule-015",
            "title": "General ICU observation - semi-stable",
            "keywords": ["observation", "monitoring", "general", "观察", "ICU观察", "监护"],
            "conditions": {
                "default": True,
            },
            "result": {
                "triage_level": 3,
                "urgency": "URGENT",
                "treatment_plan": "Close monitoring of vital signs. Supportive care. Regular reassessment. Treat underlying condition.",
                "note": "Patient requires ICU monitoring for ongoing evaluation and management."
            },
            "source": "ICU Treatment Protocol v1"
        },
    ]


def split_symptoms(text: str) -> list[str]:
    normalized = (text or "").replace(";", ",").replace("，", ",").replace("。", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ("chest", "cardiac", "heart", "心", "胸")):
        risk_flags.append("cardiac_alert")
    if any(term in joined for term in ("respiratory", "breath", "dyspnea", "呼吸", "肺")):
        risk_flags.append("respiratory_alert")
    if any(term in joined for term in ("neuro", "conscious", "stroke", "意识", "脑", "神经")):
        risk_flags.append("neurological_alert")
    if any(term in joined for term in ("sepsis", "infection", "septic", "感染", "败血症")):
        risk_flags.append("sepsis_alert")
    if _safe_float(vitals.get("temp_c"), 0.0) >= 38.5:
        risk_flags.append("fever")
    if _safe_int(vitals.get("heart_rate"), 0) >= 110:
        risk_flags.append("tachycardia")
    if _safe_int(vitals.get("systolic_bp"), 120) <= 90:
        risk_flags.append("hypotension")
    if _safe_float(vitals.get("spo2"), 100.0) <= 90:
        risk_flags.append("hypoxia")
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
    clinical = shared_memory.get("clinical_memory", {})
    profile = shared_memory.get("profile", {})
    if not clinical.get("chief_complaint"):
        missing.append("chief_complaint")
    if not clinical.get("symptoms"):
        missing.append("symptoms")
    if not clinical.get("onset_time"):
        missing.append("onset_time")
    if not clinical.get("vitals"):
        missing.append("vitals")
    if profile.get("allergy_status") != "known":
        missing.append("allergies")
    return missing


def score_icu_rule(rule: dict, payload: dict) -> int:
    score = 0
    symptoms_text = (payload.get("symptoms") or "") + " " + (payload.get("chief_complaint") or "")
    symptoms_text = symptoms_text.lower()
    vitals = payload.get("vitals") or {}
    conditions = rule.get("conditions") or {}

    for term in rule.get("keywords") or []:
        if term.lower() in symptoms_text:
            score += 2

    for symptom in conditions.get("symptoms_any", []):
        if symptom.lower() in symptoms_text:
            score += 4

    heart_rate = _safe_int(vitals.get("heart_rate"), 0)
    temp_c = _safe_float(vitals.get("temp_c"), 0.0)
    pain_score = _safe_int(vitals.get("pain_score"), 0)
    spo2 = _safe_float(vitals.get("spo2"), 100.0)
    systolic_bp = _safe_int(vitals.get("systolic_bp"), 120)

    if "heart_rate_gte" in conditions and heart_rate >= _safe_int(conditions.get("heart_rate_gte"), 999):
        score += 3
    if "temp_c_gte" in conditions and temp_c >= _safe_float(conditions.get("temp_c_gte"), 999.0):
        score += 3
    if "pain_score_gte" in conditions and pain_score >= _safe_int(conditions.get("pain_score_gte"), 999):
        score += 3
    if "spo2_lte" in conditions and spo2 <= _safe_float(conditions.get("spo2_lte"), 0.0):
        score += 5
    if "systolic_bp_lte" in conditions and systolic_bp <= _safe_int(conditions.get("systolic_bp_lte"), 999):
        score += 5
    if conditions.get("default"):
        score += 1

    return score


def retrieve_relevant_icu_rules(payload, top_k=3):
    rules = load_icu_rules()
    scored = []
    for rule in rules:
        score = score_icu_rule(rule, payload)
        if score > 0:
            scored.append({"score": score, "rule": rule})

    scored.sort(key=lambda item: item["score"], reverse=True)
    results = [item["rule"] for item in scored if not (item["rule"].get("conditions") or {}).get("default")][:top_k]
    if results:
        return results

    for rule in rules:
        if (rule.get("conditions") or {}).get("default"):
            return [rule]
    return []


def rule_based_icu_triage(payload: dict) -> dict:
    retrieved = retrieve_relevant_icu_rules(payload, top_k=1)
    if retrieved:
        rule = retrieved[0]
        return rule["result"].copy()
    return {
        "triage_level": 3,
        "urgency": "URGENT",
        "treatment_plan": "Close monitoring and supportive care. Regular reassessment of patient condition.",
        "note": "No specific ICU rule matched. General ICU observation and management."
    }


def validate_icu_triage_result(llm_result: dict | None, fallback: dict) -> dict:
    if not llm_result:
        return fallback

    try:
        validated = {
            "triage_level": int(llm_result.get("triage_level", fallback["triage_level"])),
            "urgency": str(llm_result.get("urgency", fallback["urgency"])),
            "treatment_plan": str(llm_result.get("treatment_plan", fallback["treatment_plan"])),
            "note": str(llm_result.get("note", fallback["note"])),
        }
        validated["triage_level"] = max(1, min(5, validated["triage_level"]))
        valid_urgencies = ["CRITICAL", "EMERGENT", "URGENT", "LESS_URGENT", "NON_URGENT"]
        if validated["urgency"] not in valid_urgencies:
            validated["urgency"] = fallback["urgency"]
        return validated
    except (ValueError, TypeError):
        return fallback
