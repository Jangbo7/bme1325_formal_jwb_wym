import json
import re
from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRuntimeContext


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
            "id": "im-rule-fever-respiratory",
            "title": "发热伴呼吸道症状",
            "keywords": ["发热", "fever", "咳嗽", "cough", "寒战", "chills", "感染", "infection"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Internal Medicine",
                "note": "考虑感染性疾病可能，建议先完成基础化验后再复诊评估。",
                "test_required": True,
                "test_category": "medical_laboratory",
                "test_items": ["血常规", "C反应蛋白", "降钙素原"],
                "test_reason": "用于初筛感染类型和炎症水平，指导后续治疗。",
            },
            "source": "Internal medicine fallback rules",
        },
        {
            "id": "im-rule-gastrointestinal",
            "title": "消化系统不适",
            "keywords": ["腹痛", "abdominal", "恶心", "nausea", "呕吐", "vomit", "腹泻", "diarrhea"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Internal Medicine",
                "note": "考虑胃肠道相关问题，建议完善检查后进一步判断是否需要影像检查。",
                "test_required": True,
                "test_category": "medical_laboratory",
                "test_items": ["血常规", "肝肾功能", "便常规"],
                "test_reason": "用于判断炎症、脱水和肝肾受累情况。",
            },
            "source": "Internal medicine fallback rules",
        },
        {
            "id": "im-rule-general",
            "title": "一般内科随访",
            "keywords": [],
            "result": {
                "diagnosis_level": 1,
                "priority": "L",
                "department": "Internal Medicine",
                "note": "当前表现偏向一般内科问题，建议按流程门诊复诊。",
                "test_required": True,
                "test_category": "medical_laboratory",
                "test_items": ["血常规", "基础生化"],
                "test_reason": "用于完成常见内科问题的基础筛查。",
            },
            "source": "Internal medicine fallback rules",
        },
    ]


def split_symptoms(text: str) -> list[str]:
    normalized = (text or "").strip()
    if not normalized:
        return []
    normalized = re.sub(r"[;；、，。/]+", ",", normalized)
    normalized = normalized.replace(" and ", ",")
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
    text = " ".join(symptoms or []).lower()
    flags = []
    if any(term in text for term in ["chest", "chest pain", "chest tightness", "胸痛", "胸闷", "心慌", "palpitation"]):
        flags.append("cardiac_alert")
    if any(term in text for term in ["breath", "dyspnea", "shortness", "呼吸困难", "气促", "喘不过气"]):
        flags.append("respiratory_alert")
    if any(term in text for term in ["headache", "dizzy", "numb", "weakness", "seizure", "头痛", "头晕", "麻木", "无力", "抽搐"]):
        flags.append("neurological_alert")
    try:
        if vitals.get("temp_c") is not None and float(vitals.get("temp_c")) >= 38.0:
            flags.append("fever")
    except Exception:
        pass
    return sorted(set(flags))


def _policy_required_fields(policy_runtime_context: ClinicalPolicyRuntimeContext | None) -> list[str]:
    if policy_runtime_context is None or policy_runtime_context.primary_card is None:
        return []
    required_fields = []
    for target in policy_runtime_context.primary_card.collection_targets:
        if not bool(target.get("required", False)):
            continue
        if target.get("runtime_supported", True) is False:
            continue
        field_name = str(target.get("field") or "").strip()
        if field_name:
            required_fields.append(field_name)
    return required_fields


def build_missing_fields(shared_memory: dict, *, policy_runtime_context: ClinicalPolicyRuntimeContext | None = None) -> list[str]:
    clinical = shared_memory.get("clinical_memory", {})
    profile = shared_memory.get("profile", {})
    missing = []
    required_fields = _policy_required_fields(policy_runtime_context) or ["chief_complaint", "onset_time", "allergies"]
    for field_name in required_fields:
        if field_name == "chief_complaint" and not clinical.get("chief_complaint"):
            missing.append(field_name)
        elif field_name == "onset_time" and not clinical.get("onset_time"):
            missing.append(field_name)
        elif field_name == "allergies" and profile.get("allergy_status") != "known":
            missing.append(field_name)
    return missing


def prioritize_missing_fields(
    shared_memory: dict,
    *,
    asked_fields_history: list[str] | None = None,
    last_question_focus: str | None = None,
    policy_runtime_context: ClinicalPolicyRuntimeContext | None = None,
) -> list[str]:
    missing = build_missing_fields(shared_memory, policy_runtime_context=policy_runtime_context)
    if not missing:
        return []

    clinical = shared_memory.get("clinical_memory", {})
    profile = shared_memory.get("profile", {})
    risk_flags = set(clinical.get("risk_flags") or [])
    symptoms_text = " ".join(clinical.get("symptoms") or []).lower()
    asked_history = asked_fields_history or []

    if {"cardiac_alert", "respiratory_alert"} & risk_flags or any(
        token in symptoms_text for token in ("chest", "breath", "胸痛", "胸闷", "呼吸困难")
    ):
        preferred = ["onset_time", "chief_complaint", "allergies"]
    elif "fever" in risk_flags or "发热" in symptoms_text or "发烧" in symptoms_text:
        preferred = ["onset_time", "allergies", "chief_complaint"]
    elif profile.get("allergy_status") == "uncertain":
        preferred = ["allergies", "onset_time", "chief_complaint"]
    else:
        preferred = _policy_required_fields(policy_runtime_context) or ["chief_complaint", "onset_time", "allergies"]

    preferred_order = {field: idx for idx, field in enumerate(preferred)}

    def sort_key(field: str) -> tuple[int, int, int, str]:
        asked_count = sum(1 for item in asked_history if item == field)
        same_as_last = 1 if field == last_question_focus else 0
        return (same_as_last, asked_count, preferred_order.get(field, 999), field)

    return sorted(missing, key=sort_key)


def _extract_onset_time(text: str, lowered: str) -> tuple[str | None, float]:
    normalized = text.strip()
    if not normalized:
        return None, 0.0

    for phrase, mapped in (
        ("just now", "刚刚"),
        ("this morning", "今天早上"),
        ("today morning", "今天早上"),
        ("today afternoon", "今天下午"),
        ("tonight", "今晚"),
        ("yesterday", "昨天"),
        ("刚刚", "刚刚"),
        ("今天早上", "今天早上"),
        ("今天下午", "今天下午"),
        ("今天", "今天"),
        ("昨晚", "昨晚"),
        ("昨天", "昨天"),
    ):
        if phrase in lowered or phrase in text:
            return mapped, 0.85

    patterns = [
        r"(\d+\s*(?:minute|minutes|min|hour|hours|day|days|week|weeks)\s*(?:ago)?)",
        r"(since\s+[a-zA-Z0-9\s:]+)",
        r"(\d+\s*(?:分钟|小时|天|周)\s*(?:前)?)",
        r"(持续\s*\d+\s*(?:分钟|小时|天|周))",
        r"(大概\s*\d+\s*(?:分钟|小时|天|周))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1), 0.95
    return None, 0.0


def _extract_allergy_status(text: str, lowered: str) -> tuple[list[str] | None, str | None, float]:
    no_allergy_tokens = [
        "no allergy",
        "no allergies",
        "none",
        "nkda",
        "无过敏",
        "无药物过敏",
        "没有过敏史",
        "不过敏",
        "未发现过敏",
    ]
    unsure_tokens = ["不清楚", "不太清楚", "记不清", "不确定", "不记得"]
    has_allergy_tokens = ["allergy", "allergic", "过敏", "药物过敏", "食物过敏"]

    if any(token in lowered for token in no_allergy_tokens) or any(token in text for token in no_allergy_tokens):
        return [], "known", 0.95
    if any(token in lowered for token in unsure_tokens) or any(token in text for token in unsure_tokens):
        return None, "uncertain", 0.5
    if any(token in lowered for token in has_allergy_tokens) or any(token in text for token in has_allergy_tokens):
        return [text], "known", 0.8
    return None, None, 0.0


def extract_structured_updates(message: str) -> dict:
    text = (message or "").strip()
    lowered = text.lower()
    extracted = {
        "chief_complaint": None,
        "onset_time": None,
        "allergies": None,
        "allergy_status": None,
        "symptoms": [],
        "extracted_fields": [],
        "confidence_by_field": {},
    }
    if text and len(text) > 2:
        extracted["symptoms"] = split_symptoms(text)
        segments = re.split(r"[。！？?，,\n]", text)
        first_segment = next((seg.strip() for seg in segments if seg.strip()), text)
        extracted["chief_complaint"] = first_segment[:120]

    onset_time, onset_conf = _extract_onset_time(text, lowered)
    if onset_time:
        extracted["onset_time"] = onset_time
        extracted["extracted_fields"].append("onset_time")
        extracted["confidence_by_field"]["onset_time"] = onset_conf

    allergies, allergy_status, allergy_conf = _extract_allergy_status(text, lowered)
    if allergy_status:
        extracted["allergies"] = allergies
        extracted["allergy_status"] = allergy_status
        extracted["extracted_fields"].append("allergies")
        extracted["confidence_by_field"]["allergies"] = allergy_conf

    if extracted["chief_complaint"]:
        extracted["extracted_fields"].append("chief_complaint")
        extracted["confidence_by_field"]["chief_complaint"] = 0.7
    if extracted["symptoms"]:
        extracted["extracted_fields"].append("symptoms")
        extracted["confidence_by_field"]["symptoms"] = 0.7

    extracted["extracted_fields"] = list(dict.fromkeys(extracted["extracted_fields"]))
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


def _normalize_string_list(value, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[，,；;、\n]", value) if part.strip()]
    return list(fallback or [])


def _detect_icu_red_flags(payload: dict) -> list[str]:
    symptoms_text = f"{payload.get('symptoms', '')} {payload.get('chief_complaint', '')}".lower()
    vitals = payload.get("vitals") or {}
    flags = []

    systolic = vitals.get("systolic_bp")
    heart_rate = vitals.get("heart_rate")
    temp_c = vitals.get("temp_c")

    def has_any(*tokens: str) -> bool:
        return any(token.lower() in symptoms_text for token in tokens)

    if has_any("chest pain", "chest tightness", "胸痛", "胸闷") and has_any("shortness of breath", "dyspnea", "呼吸困难", "气促"):
        flags.append("胸痛伴呼吸困难")
    if has_any("shortness of breath", "dyspnea", "喘不过气", "呼吸困难") and heart_rate is not None:
        try:
            if int(heart_rate) >= 130:
                flags.append("呼吸困难伴心率明显增快")
        except Exception:
            pass
    if has_any("numb", "weakness", "one-sided", "speech", "confusion", "麻木", "无力", "说话含糊", "意识不清", "抽搐"):
        flags.append("疑似神经系统急症")
    try:
        if systolic is not None and int(systolic) <= 90:
            flags.append("收缩压偏低")
    except Exception:
        pass
    try:
        if temp_c is not None and float(temp_c) >= 39.5 and systolic is not None and int(systolic) <= 100:
            flags.append("高热伴循环不稳定")
    except Exception:
        pass
    if has_any("shock", "昏迷", "休克", "濒死感"):
        flags.append("疑似休克或意识障碍")

    return list(dict.fromkeys(flags))


def _infer_test_plan(result: dict, payload: dict) -> dict:
    category = str(result.get("test_category") or "").strip()
    try:
        diagnosis_level = int(result.get("diagnosis_level") or 1)
    except Exception:
        diagnosis_level = 1
    if category not in {"medical_imaging", "medical_laboratory"}:
        text = f"{payload.get('symptoms', '')} {payload.get('chief_complaint', '')}".lower()
        if any(keyword in text for keyword in ["chest", "head", "palpitation", "breath", "dizzy", "numb", "胸", "头"]):
            category = "medical_imaging"
        elif diagnosis_level >= 3:
            category = "medical_imaging"
        else:
            category = "medical_laboratory"

    items = result.get("test_items")
    if not isinstance(items, list) or not [item for item in items if str(item).strip()]:
        if category == "medical_imaging":
            items = ["胸部X线", "超声检查"]
        else:
            items = ["血常规", "C反应蛋白", "基础生化"]

    reason = str(result.get("test_reason") or "").strip()
    if not reason:
        reason = "根据当前症状分布，建议先完成相应检查以提高诊断准确性。"

    return {
        "test_required": bool(result.get("test_required", True)),
        "test_category": category,
        "test_items": [str(item).strip() for item in items if str(item).strip()],
        "test_reason": reason,
    }


def _build_patient_plan(result: dict) -> str:
    if result.get("priority") == "H":
        return "请立即前往急诊或高优先级区域，不要继续等待常规门诊流程。"
    if result.get("test_required", True):
        return "请先完成建议的检查，再携带结果回到门诊复诊。"
    return "请按门诊随诊安排继续观察，如症状加重及时复诊。"


def _build_medication_or_action(result: dict) -> list[str]:
    actions = []
    note = str(result.get("note") or "")
    if result.get("priority") == "H":
        actions.append("立即转急诊或高优先级通道评估")
    if "发热" in note or "感染" in note:
        actions.append("完善感染相关检查后再决定是否需要抗感染治疗")
    if result.get("test_required", True):
        actions.append("先完成建议检查，再由医生结合结果调整方案")
    if not actions:
        actions.append("继续门诊随诊，并观察症状变化")
    return list(dict.fromkeys(actions))


def rule_based_internal_medicine(payload: dict) -> dict:
    rules = retrieve_relevant_internal_medicine_rules(payload, top_k=1)
    if rules:
        result = dict(rules[0]["result"])
    else:
        result = {
            "diagnosis_level": 1,
            "priority": "L",
            "department": "Internal Medicine",
            "note": "建议门诊随诊并完善基础检查。",
            "test_required": True,
            "test_category": "medical_laboratory",
            "test_items": ["血常规", "基础生化"],
            "test_reason": "用于完成常见内科问题的基础筛查。",
        }
    result.update(_infer_test_plan(result, payload))
    return result


def _normalize_final_result(result: dict, payload: dict) -> dict:
    normalized = dict(result)
    normalized.update(_infer_test_plan(normalized, payload))

    if normalized.get("priority") not in {"H", "M", "L"}:
        normalized["priority"] = "M"
    try:
        normalized["diagnosis_level"] = max(1, min(3, int(normalized.get("diagnosis_level") or 1)))
    except Exception:
        normalized["diagnosis_level"] = 1

    normalized["complete"] = True
    normalized["department"] = str(normalized.get("department") or "Internal Medicine")
    normalized["note"] = str(normalized.get("note") or "建议继续门诊随诊。")
    normalized["tests_suggested"] = _normalize_string_list(normalized.get("tests_suggested"), normalized.get("test_items"))
    normalized["test_items"] = _normalize_string_list(normalized.get("test_items"), normalized["tests_suggested"])
    normalized["medication_or_action"] = _normalize_string_list(normalized.get("medication_or_action"))
    normalized["red_flags"] = _normalize_string_list(normalized.get("red_flags"))

    if not normalized["tests_suggested"]:
        normalized["tests_suggested"] = list(normalized["test_items"])
    if not normalized["medication_or_action"]:
        normalized["medication_or_action"] = _build_medication_or_action(normalized)

    normalized["patient_plan"] = str(normalized.get("patient_plan") or _build_patient_plan(normalized))
    normalized["assistant_message"] = str(normalized.get("assistant_message") or "").strip()
    normalized["icu_escalation"] = bool(normalized.get("icu_escalation", False))
    return normalized


def _apply_icu_escalation(result: dict, payload: dict, fallback: dict) -> dict:
    escalated = dict(result)
    deterministic_red_flags = _detect_icu_red_flags(payload)
    escalated["red_flags"] = deterministic_red_flags
    icu_escalation = bool(deterministic_red_flags)
    escalated["icu_escalation"] = icu_escalation

    try:
        current_level = int(escalated.get("diagnosis_level") or 1)
    except Exception:
        current_level = int(fallback.get("diagnosis_level") or 1)

    if icu_escalation:
        escalated["priority"] = "H"
        escalated["department"] = "Emergency"
        escalated["diagnosis_level"] = max(3, current_level)
        base_note = str(escalated.get("note") or "").strip()
        escalation_note = "存在需要立即升级处理的危险信号，建议立刻转急诊并评估是否需要 ICU 监护。"
        if escalation_note not in base_note:
            escalated["note"] = f"{escalation_note}{base_note}" if base_note else escalation_note
        escalated["patient_plan"] = "请立即前往急诊或高优先级区域，不要继续等待常规门诊流程。"
        escalated["medication_or_action"] = list(
            dict.fromkeys(["立即转急诊或高优先级通道评估"] + _normalize_string_list(escalated.get("medication_or_action")))
        )
        return escalated

    if str(escalated.get("department") or "").lower() in {"emergency", "icu"}:
        escalated["department"] = str(fallback.get("department") or "Internal Medicine")
    if escalated.get("priority") == "H":
        escalated["priority"] = str(fallback.get("priority") or "M")
        escalated["diagnosis_level"] = int(fallback.get("diagnosis_level") or 1)

    return escalated


def final_result_changed(previous: dict | None, current: dict | None) -> bool:
    previous = previous or {}
    current = current or {}
    significant_keys = {
        "department",
        "priority",
        "diagnosis_level",
        "red_flags",
        "test_category",
        "icu_escalation",
    }
    comparable_previous = {key: previous.get(key) for key in significant_keys}
    comparable_current = {key: current.get(key) for key in significant_keys}
    return comparable_previous != comparable_current


def validate_internal_medicine_result(llm_result: dict | None, fallback: dict, payload: dict) -> dict:
    base = dict(fallback)
    try:
        if isinstance(llm_result, dict):
            base.update(
                {
                    "department": llm_result.get("department", base.get("department")),
                    "priority": llm_result.get("priority", base.get("priority")),
                    "diagnosis_level": llm_result.get("diagnosis_level", base.get("diagnosis_level")),
                    "note": llm_result.get("note", base.get("note")),
                    "patient_plan": llm_result.get("patient_plan"),
                    "tests_suggested": llm_result.get("tests_suggested"),
                    "medication_or_action": llm_result.get("medication_or_action"),
                    "red_flags": llm_result.get("red_flags"),
                    "test_required": llm_result.get("test_required", base.get("test_required", True)),
                    "test_category": llm_result.get("test_category", base.get("test_category", "medical_laboratory")),
                    "test_items": llm_result.get("test_items", base.get("test_items", [])),
                    "test_reason": llm_result.get("test_reason", base.get("test_reason", "")),
                }
            )
    except Exception:
        base = dict(fallback)

    normalized = _normalize_final_result(base, payload)
    normalized = _apply_icu_escalation(normalized, payload, fallback)
    normalized = _normalize_final_result(normalized, payload)
    return normalized
