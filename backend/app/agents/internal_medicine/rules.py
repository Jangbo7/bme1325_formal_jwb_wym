import json
import re
from pathlib import Path


INTERNAL_MEDICINE_RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "internal_medicine_rules.json"


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


def load_internal_medicine_rules() -> list[dict]:
    if INTERNAL_MEDICINE_RULE_STORE_PATH.exists():
        return json.loads(INTERNAL_MEDICINE_RULE_STORE_PATH.read_text(encoding="utf-8"))
    return _get_default_rules()


def _get_default_rules() -> list[dict]:
    return [
        {
            "id": "im-rule-001",
            "title": "Hypertension - High blood pressure",
            "keywords": ["hypertension", "high blood pressure", "elevated bp", "高压", "高血压", "blood pressure", "bp"],
            "conditions": {
                "symptoms_any": ["hypertension", "high blood pressure", "elevated bp", "高压", "高血压", "blood pressure"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with hypertension. Recommend lifestyle modifications and possibly antihypertensive medication.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-002",
            "title": "Type 2 Diabetes Mellitus",
            "keywords": ["diabetes", "type 2 diabetes", "high blood sugar", "血糖高", "糖尿病", "glucose", "prediabetes"],
            "conditions": {
                "symptoms_any": ["diabetes", "type 2 diabetes", "high blood sugar", "血糖高", "糖尿病", "glucose", "prediabetes"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with symptoms suggestive of diabetes. Recommend HbA1c testing and dietary modifications.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-003",
            "title": "Upper Respiratory Infection",
            "keywords": ["cold", "flu", "cough", "sore throat", "runny nose", "感冒", "流感", "咳嗽", "嗓子疼", "URI", "upper respiratory"],
            "conditions": {
                "symptoms_any": ["cold", "flu", "cough", "sore throat", "runny nose", "感冒", "流感", "咳嗽", "嗓子疼", "upper respiratory infection"],
            },
            "result": {
                "diagnosis_level": 3,
                "priority": "L",
                "department": "General Medicine",
                "note": "Patient presents with common cold or flu symptoms. Recommend rest, hydration, and symptomatic treatment.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-004",
            "title": "Gastroenteritis - Stomach flu",
            "keywords": ["gastroenteritis", "stomach flu", "vomiting", "diarrhea", "nausea", "胃炎", "肠胃炎", "呕吐", "腹泻", "恶心", "stomach ache"],
            "conditions": {
                "symptoms_any": ["gastroenteritis", "stomach flu", "vomiting", "diarrhea", "nausea", "胃炎", "肠胃炎", "呕吐", "腹泻", "stomach ache"],
            },
            "result": {
                "diagnosis_level": 3,
                "priority": "L",
                "department": "General Medicine",
                "note": "Patient presents with gastroenteritis. Recommend oral rehydration, bland diet, and rest.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-005",
            "title": "Chronic Kidney Disease",
            "keywords": ["kidney disease", "renal", "CKD", "kidney function", "肾", "肾功能", "nephrology"],
            "conditions": {
                "symptoms_any": ["kidney disease", "renal", "CKD", "kidney function", "肾", "肾功能"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with signs of kidney disease. Recommend kidney function tests and referral to nephrology if needed.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-006",
            "title": "Anemia",
            "keywords": ["anemia", "low hemoglobin", "fatigue", "tiredness", "贫血", "血红蛋白低", "weakness", "dizziness"],
            "conditions": {
                "symptoms_any": ["anemia", "low hemoglobin", "fatigue", "tiredness", "贫血", "血红蛋白低", "weakness", "dizziness"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with symptoms of anemia. Recommend complete blood count and iron studies.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-007",
            "title": "Thyroid Disorder",
            "keywords": ["thyroid", "hypothyroidism", "hyperthyroidism", "甲亢", "甲减", "甲状腺", "goiter"],
            "conditions": {
                "symptoms_any": ["thyroid", "hypothyroidism", "hyperthyroidism", "甲亢", "甲减", "甲状腺", "goiter"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with thyroid symptoms. Recommend thyroid function tests (TSH, T3, T4).",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-008",
            "title": "Asthma - mild to moderate",
            "keywords": ["asthma", "wheezing", "shortness of breath", "bronchitis", "哮喘", "喘息", "呼吸困难"],
            "conditions": {
                "symptoms_any": ["asthma", "wheezing", "shortness of breath", "bronchitis", "哮喘", "喘息", "呼吸困难"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with asthma symptoms. Recommend spirometry and bronchodilator therapy.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-009",
            "title": "COPD - Chronic Obstructive Pulmonary Disease",
            "keywords": ["COPD", "chronic bronchitis", "emphysema", "慢阻肺", "慢性支气管炎", "肺气肿", "smoker"],
            "conditions": {
                "symptoms_any": ["COPD", "chronic bronchitis", "emphysema", "慢阻肺", "慢性支气管炎", "肺气肿"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with COPD symptoms. Recommend pulmonary function tests and smoking cessation support.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-010",
            "title": "Gastritis and Peptic Ulcer Disease",
            "keywords": ["gastritis", "stomach pain", "acid reflux", "GERD", "heartburn", "胃炎", "胃痛", "反酸", "ulcer"],
            "conditions": {
                "symptoms_any": ["gastritis", "stomach pain", "acid reflux", "GERD", "heartburn", "胃炎", "胃痛", "反酸", "ulcer"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with GI symptoms. Recommend PPI therapy and H. pylori testing if indicated.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-011",
            "title": "Hyperlipidemia - High Cholesterol",
            "keywords": ["high cholesterol", "hyperlipidemia", "lipids", "胆固醇高", "血脂", "triglycerides"],
            "conditions": {
                "symptoms_any": ["high cholesterol", "hyperlipidemia", "lipids", "胆固醇高", "血脂", "triglycerides"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with hyperlipidemia. Recommend lipid panel and lifestyle modifications.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-012",
            "title": "Arthritis - Joint Pain",
            "keywords": ["arthritis", "joint pain", "joint swelling", "osteoarthritis", "rheumatoid", "关节炎", "关节痛", "膝盖痛", "back pain"],
            "conditions": {
                "symptoms_any": ["arthritis", "joint pain", "joint swelling", "osteoarthritis", "rheumatoid", "关节炎", "关节痛", "膝盖痛", "back pain"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with joint symptoms. Recommend X-ray and rheumatological evaluation if needed.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-013",
            "title": "Anxiety and Depression Screening",
            "keywords": ["anxiety", "depression", "stress", "insomnia", "sleep problems", "心理健康", "焦虑", "抑郁", "失眠", "mood"],
            "conditions": {
                "symptoms_any": ["anxiety", "depression", "stress", "insomnia", "sleep problems", "心理健康", "焦虑", "抑郁", "失眠", "mood"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with possible mental health concerns. Recommend PHQ-9 and GAD-7 screening.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-014",
            "title": "Allergic Rhinitis",
            "keywords": ["allergies", "allergic rhinitis", "sneezing", "nasal congestion", "过敏", "鼻炎", "花粉过敏", "hay fever"],
            "conditions": {
                "symptoms_any": ["allergies", "allergic rhinitis", "sneezing", "nasal congestion", "过敏", "鼻炎", "花粉过敏", "hay fever"],
            },
            "result": {
                "diagnosis_level": 3,
                "priority": "L",
                "department": "General Medicine",
                "note": "Patient presents with allergic rhinitis. Recommend antihistamines and allergen avoidance.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-015",
            "title": "Headache and Migraine",
            "keywords": ["headache", "migraine", "head pain", "头疼", "头痛", "偏头痛", "tension headache"],
            "conditions": {
                "symptoms_any": ["headache", "migraine", "head pain", "头疼", "头痛", "偏头痛", "tension headache"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with headache. Recommend neurological assessment and imaging if red flags present.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-016",
            "title": "Urinary Tract Infection",
            "keywords": ["UTI", "urinary tract infection", "painful urination", "cystitis", "尿路感染", "尿道炎", "尿频", "dysuria"],
            "conditions": {
                "symptoms_any": ["UTI", "urinary tract infection", "painful urination", "cystitis", "尿路感染", "尿道炎", "尿频", "dysuria"],
            },
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "General Medicine",
                "note": "Patient presents with UTI symptoms. Recommend urinalysis and antibiotic therapy.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-017",
            "title": "Skin Conditions - Eczema, Dermatitis",
            "keywords": ["skin rash", "eczema", "dermatitis", "itching", "皮肤病", "湿疹", "皮炎", "瘙痒", "hives"],
            "conditions": {
                "symptoms_any": ["skin rash", "eczema", "dermatitis", "itching", "皮肤病", "湿疹", "皮炎", "瘙痒", "hives"],
            },
            "result": {
                "diagnosis_level": 3,
                "priority": "L",
                "department": "General Medicine",
                "note": "Patient presents with skin symptoms. Recommend dermatological assessment and topical treatment.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
        {
            "id": "im-rule-018",
            "title": "General wellness check - No acute concerns",
            "keywords": ["checkup", "routine", "annual physical", "general", "体检", "常规检查", "健康检查", " preventive"],
            "conditions": {
                "default": True,
            },
            "result": {
                "diagnosis_level": 3,
                "priority": "L",
                "department": "General Medicine",
                "note": "Patient is here for routine checkup. Recommend preventive care screening based on age and risk factors.",
            },
            "source": "Internal Medicine Guidelines v1",
        },
    ]


def split_symptoms(text: str) -> list[str]:
    normalized = (text or "").replace(";", ",").replace("，", ",").replace("。", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ["chest", "heart", "cardiac", "心", "胸"]):
        risk_flags.append("cardiac_alert")
    if any(term in joined for term in ["respiratory", "breath", "dyspnea", "呼吸", "肺"]):
        risk_flags.append("respiratory_alert")
    if any(term in joined for term in ["neuro", "conscious", "stroke", "意识", "脑", "神经", "headache"]):
        risk_flags.append("neurological_alert")
    if any(term in joined for term in ["sepsis", "infection", "fever", "感染", "发热", "高烧"]):
        risk_flags.append("infection_alert")
    if _safe_float(vitals.get("temp_c"), 0.0) >= 38.0:
        risk_flags.append("fever")
    if _safe_int(vitals.get("heart_rate"), 0) >= 100:
        risk_flags.append("tachycardia")
    if _safe_int(vitals.get("systolic_bp"), 120) >= 140 or _safe_int(vitals.get("systolic_bp"), 120) <= 90:
        risk_flags.append("bp_abnormal")
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
    if profile.get("allergy_status") != "known":
        missing.append("allergies")
    return missing


def score_internal_medicine_rule(rule: dict, payload: dict) -> int:
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
    systolic_bp = _safe_int(vitals.get("systolic_bp"), 120)

    if "heart_rate_gte" in conditions and heart_rate >= _safe_int(conditions.get("heart_rate_gte"), 999):
        score += 3
    if "temp_c_gte" in conditions and temp_c >= _safe_float(conditions.get("temp_c_gte"), 999.0):
        score += 3
    if "bp_gte" in conditions and systolic_bp >= _safe_int(conditions.get("bp_gte"), 999):
        score += 3
    if conditions.get("default"):
        score += 1

    return score


def retrieve_relevant_internal_medicine_rules(payload, top_k=3):
    rules = load_internal_medicine_rules()
    scored = []
    for rule in rules:
        score = score_internal_medicine_rule(rule, payload)
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


def rule_based_internal_medicine(payload: dict) -> dict:
    retrieved = retrieve_relevant_internal_medicine_rules(payload, top_k=1)
    if retrieved:
        rule = retrieved[0]
        return rule["result"].copy()

    symptoms = payload.get("symptoms", "").lower()
    text = symptoms + " " + payload.get("chief_complaint", "").lower()

    if any(k in text for k in ["尿", "urination", "急", "频"]):
        return {
            "diagnosis_level": 1,
            "priority": "M",
            "department": "General Medicine",
            "note": "疑似尿路感染或膀胱炎，建议多喝水，注意个人卫生，必要时进行尿检。",
        }
    if any(k in text for k in ["发烧", "fever", "发热", "体温"]):
        return {
            "diagnosis_level": 2,
            "priority": "M",
            "department": "General Medicine",
            "note": "疑似感染性疾病，建议进行血常规检查，明确感染类型。",
        }
    if any(k in text for k in ["咳嗽", "cough", "咳痰", "咽痛"]):
        return {
            "diagnosis_level": 1,
            "priority": "L",
            "department": "Respiratory Medicine",
            "note": "疑似上呼吸道感染或支气管炎，建议对症治疗，必要时胸片检查。",
        }
    if any(k in text for k in ["头痛", "headache", "头晕", "dizzy"]):
        return {
            "diagnosis_level": 1,
            "priority": "L",
            "department": "General Medicine",
            "note": "疑似紧张性头痛或血管性头痛，建议休息，必要时止痛对症处理。",
        }
    if any(k in text for k in ["腹痛", "stomach", "恶心", "呕吐", "diarrhea", "腹泻"]):
        return {
            "diagnosis_level": 1,
            "priority": "M",
            "department": "Gastroenterology",
            "note": "疑似胃肠炎或消化不良，建议清淡饮食，必要时止泻或护胃治疗。",
        }

    return {
        "diagnosis_level": 1,
        "priority": "L",
        "department": "General Medicine",
        "note": "常见内科症状，根据患者描述进行对症治疗和观察。",
    }


def validate_internal_medicine_result(llm_result: dict | None, fallback: dict) -> dict:
    if not llm_result:
        return fallback

    try:
        validated = {
            "diagnosis_level": int(llm_result.get("diagnosis_level", fallback["diagnosis_level"])),
            "priority": str(llm_result.get("priority", fallback["priority"])),
            "department": str(llm_result.get("department", fallback["department"])),
            "note": str(llm_result.get("note", fallback["note"])),
        }
        validated["diagnosis_level"] = max(1, min(3, validated["diagnosis_level"]))
        valid_priorities = ["H", "M", "L"]
        if validated["priority"] not in valid_priorities:
            validated["priority"] = fallback["priority"]
        return validated
    except (ValueError, TypeError):
        return fallback
