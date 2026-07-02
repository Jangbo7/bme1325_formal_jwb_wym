import json
import re
from pathlib import Path
from typing import Any

from app.agents.clinical_policy import ClinicalPolicyRuntimeContext
from app.agents.department_runtime.conclusions import normalize_round2_conclusion, preserve_round2_escalation_floor
from app.agents.department_runtime.replies import normalize_prescription_plan
from app.agents.internal_medicine.rules import merge_unique, merge_vitals, split_symptoms


SURGERY_RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "surgery_rules.json"
ROUND1_DECISIONS = {
    "urgent_escalation",
    "test_first",
    "treat_and_discharge",
    "recommend_other_clinic",
}


def load_surgery_rules() -> list[dict]:
    if SURGERY_RULE_STORE_PATH.exists():
        try:
            return json.loads(SURGERY_RULE_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_rules()


def _default_rules() -> list[dict]:
    return [
        {
            "id": "surgery-rule-trauma-wound",
            "title": "Trauma or wound concern",
            "keywords": ["wound", "bleeding", "cut", "laceration", "abrasion", "injury", "trauma"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Surgery",
                "note": "The complaint is compatible with a surgical wound or trauma concern and usually needs focused surgical assessment.",
                "test_required": True,
                "test_category": "medical_imaging",
                "test_items": ["X-ray or ultrasound if needed", "Basic wound assessment"],
                "test_reason": "Used to clarify wound depth, retained foreign body, or bone and soft-tissue injury when indicated.",
            },
            "source": "Surgery fallback rules",
        },
        {
            "id": "surgery-rule-abdominal",
            "title": "Abdominal surgical concern",
            "keywords": ["abdominal pain", "vomiting", "distension", "black stool", "bloody stool", "appendix"],
            "result": {
                "diagnosis_level": 2,
                "priority": "M",
                "department": "Surgery",
                "note": "The complaint is compatible with an abdominal surgical concern and may need laboratory tests or imaging first.",
                "test_required": True,
                "test_category": "medical_imaging",
                "test_items": ["Abdominal ultrasound or CT if indicated", "Blood routine"],
                "test_reason": "Used to clarify whether urgent abdominal surgical pathology should be excluded.",
            },
            "source": "Surgery fallback rules",
        },
        {
            "id": "surgery-rule-postoperative",
            "title": "Postoperative follow-up concern",
            "keywords": ["postoperative", "post-op", "dressing change", "suture removal", "wound check"],
            "result": {
                "diagnosis_level": 1,
                "priority": "L",
                "department": "Surgery",
                "note": "The complaint is compatible with a routine postoperative surgery follow-up concern.",
                "test_required": False,
                "test_category": "none",
                "test_items": [],
                "test_reason": "No immediate test is suggested unless red flags or worsening symptoms are reported.",
            },
            "source": "Surgery fallback rules",
        },
        {
            "id": "surgery-rule-soft-tissue-lump",
            "title": "Stable superficial soft tissue lump",
            "keywords": ["lump", "mass", "nodule", "bump", "肿块", "包块", "结节", "疙瘩"],
            "result": {
                "diagnosis_level": 1,
                "priority": "L",
                "department": "Surgery",
                "note": "初步考虑局部皮下结节或软组织包块，需要先做局部软组织超声进一步判断性质。",
                "test_required": True,
                "test_category": "medical_imaging",
                "test_items": ["局部软组织超声"],
                "test_reason": "用于判断包块的位置、大小、边界、内部回声和周围软组织情况。",
            },
            "source": "Surgery fallback rules",
        },
        {
            "id": "surgery-rule-general",
            "title": "General surgical outpatient concern",
            "keywords": [],
            "result": {
                "diagnosis_level": 1,
                "priority": "L",
                "department": "Surgery",
                "note": "A routine first-round surgical assessment is needed before deciding the next step.",
                "test_required": True,
                "test_category": "medical_imaging",
                "test_items": ["Focused surgical review", "Additional imaging or laboratory tests if indicated"],
                "test_reason": "Used to complete a safe first-round surgical outpatient assessment.",
            },
            "source": "Surgery fallback rules",
        },
    ]


def derive_risk_flags(symptoms: list[str], vitals: dict) -> list[str]:
    text = " ".join(symptoms or []).lower()
    flags = []
    if any(term in text for term in ["bleeding", "hemorrhage", "blood loss", "heavy bleeding", "出血"]):
        flags.append("bleeding_alert")
    if any(term in text for term in ["fracture", "dislocation", "cannot move", "can't move", "numbness", "loss of sensation", "骨折", "脱位", "麻木"]):
        flags.append("trauma_alert")
    if any(term in text for term in ["abdominal pain", "rigid abdomen", "distension", "cannot pass gas", "cannot pass stool", "vomiting", "黑便", "血便", "腹痛", "腹胀", "呕吐"]):
        flags.append("abdominal_alert")
    postoperative_negative = any(
        phrase in text
        for phrase in [
            "no fever",
            "without fever",
            "no pus",
            "without pus",
            "no drainage",
            "without drainage",
            "没有发热",
            "无发热",
            "没有脓",
            "无脓",
        ]
    )
    if not postoperative_negative and any(
        term in text for term in ["postoperative fever", "post-op fever", "dehiscence", "pus", "purulent", "drainage", "术后发热", "伤口裂开", "脓性"]
    ):
        flags.append("postoperative_alert")
    try:
        if vitals.get("temp_c") is not None and float(vitals.get("temp_c")) >= 38.0:
            flags.append("fever")
    except Exception:
        pass
    try:
        if vitals.get("heart_rate") is not None and float(vitals.get("heart_rate")) >= 130:
            flags.append("hemodynamic_alert")
    except Exception:
        pass
    try:
        if vitals.get("systolic_bp") is not None and float(vitals.get("systolic_bp")) <= 90:
            flags.append("hemodynamic_alert")
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
    risk_flags = set(clinical.get("risk_flags") or [])
    symptoms_text = " ".join(clinical.get("symptoms") or []).lower()
    asked_history = asked_fields_history or []

    if {"bleeding_alert", "trauma_alert", "abdominal_alert", "postoperative_alert", "hemodynamic_alert"} & risk_flags:
        preferred = ["onset_time", "chief_complaint", "allergies"]
    elif any(token in symptoms_text for token in ("wound", "trauma", "bleeding", "postoperative", "abdominal", "腹痛", "伤口")):
        preferred = ["chief_complaint", "onset_time", "allergies"]
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
        ("this morning", "this morning"),
        ("today", "today"),
        ("yesterday", "yesterday"),
        ("after surgery", "after surgery"),
        ("after the injury", "after the injury"),
        ("术后", "术后"),
        ("受伤后", "受伤后"),
        ("今天", "今天"),
        ("昨天", "昨天"),
    ):
        if phrase in lowered or phrase in text:
            return mapped, 0.85
    match = re.search(r"(\d+\s*(?:minute|minutes|min|hour|hours|day|days|week|weeks)\s*(?:ago)?)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1), 0.95
    return None, 0.0


def _extract_allergy_status(text: str, lowered: str) -> tuple[list[str] | None, str | None, float]:
    no_allergy_tokens = ["no allergy", "no allergies", "none", "no known allergies", "无过敏", "没有过敏"]
    unsure_tokens = ["not sure", "unsure", "uncertain", "不清楚", "不确定"]
    has_allergy_tokens = ["allergy", "allergic", "过敏"]

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
        segments = re.split(r"[.!?\n。！？]", text)
        first_segment = next((seg.strip() for seg in segments if seg.strip()), text)
        extracted["chief_complaint"] = first_segment[:120]
        extracted["extracted_fields"].append("chief_complaint")
        extracted["confidence_by_field"]["chief_complaint"] = 0.7

        onset_time, onset_confidence = _extract_onset_time(text, lowered)
        if onset_time:
            extracted["onset_time"] = onset_time
            extracted["extracted_fields"].append("onset_time")
            extracted["confidence_by_field"]["onset_time"] = onset_confidence

        allergies, allergy_status, allergy_confidence = _extract_allergy_status(text, lowered)
        if allergy_status:
            extracted["allergies"] = allergies
            extracted["allergy_status"] = allergy_status
            extracted["extracted_fields"].append("allergies")
            extracted["confidence_by_field"]["allergies"] = allergy_confidence

    return extracted


def retrieve_relevant_surgery_rules(payload: dict, top_k: int = 3) -> list[dict]:
    rules = load_surgery_rules()
    text = f"{payload.get('chief_complaint', '')} {payload.get('symptoms', '')} {payload.get('message', '')}".lower()
    scored = []
    for rule in rules:
        keywords = [str(item).lower() for item in (rule.get("keywords") or []) if str(item).strip()]
        score = sum(1 for keyword in keywords if keyword in text)
        if score > 0 or not keywords:
            scored.append((score, rule))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def _normalize_string_list(value, fallback: list[str] | None = None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
    return list(fallback or [])


def _build_patient_plan(result: dict) -> str:
    if not result.get("test_required", True):
        return "Complete the recommended next step in the surgery clinic and return urgently if symptoms worsen."
    tests = _normalize_string_list(result.get("tests_suggested"), result.get("test_items"))
    if tests:
        return f"Complete the recommended tests first: {', '.join(tests)}, then return for surgical follow-up."
    return "Complete the recommended tests first and then return for surgical follow-up."


def _build_medication_or_action(result: dict) -> list[str]:
    if not result.get("test_required", True):
        return ["Continue the surgical outpatient follow-up plan and return urgently if symptoms worsen."]
    return ["Complete the recommended tests first before the next surgical decision."]


def _infer_test_plan(result: dict, payload: dict) -> dict:
    category = str(result.get("test_category") or "").strip()
    if category:
        if category == "none":
            result["tests_suggested"] = []
            result["test_items"] = []
            result["test_required"] = False
        else:
            result["tests_suggested"] = _normalize_string_list(result.get("tests_suggested"), result.get("test_items"))
            result["test_items"] = _normalize_string_list(result.get("test_items"), result.get("tests_suggested"))
    else:
        rules = retrieve_relevant_surgery_rules(payload, top_k=1)
        fallback = rules[0]["result"] if rules else {}
        result["test_category"] = fallback.get("test_category", "medical_imaging")
        result["test_items"] = _normalize_string_list(result.get("test_items"), fallback.get("test_items", []))
        result["tests_suggested"] = _normalize_string_list(result.get("tests_suggested"), result["test_items"])
        result["test_required"] = bool(result.get("test_required", True))
        result["test_reason"] = str(result.get("test_reason") or fallback.get("test_reason") or "")
    if _looks_like_low_risk_soft_tissue_lump(payload):
        vague_tests = {
            "focused surgical review",
            "additional imaging or laboratory tests if indicated",
            "basic wound assessment",
            "additional imaging",
            "辅助检查",
            "相关检查",
            "进一步检查",
        }
        tests = _normalize_string_list(result.get("test_items"), result.get("tests_suggested"))
        if not tests or all(str(item).strip().lower() in vague_tests for item in tests):
            result["test_category"] = "medical_imaging"
            result["test_items"] = ["局部软组织超声"]
            result["tests_suggested"] = ["局部软组织超声"]
            result["test_required"] = True
            result["test_reason"] = result.get("test_reason") or "用于判断包块的位置、大小、边界、内部结构和周围软组织情况。"
    return result


def _detect_surgery_red_flags(payload: dict) -> list[str]:
    symptoms_text = f"{payload.get('symptoms', '')} {payload.get('chief_complaint', '')} {payload.get('message', '')}".lower()
    vitals = payload.get("vitals") or {}
    flags = []
    no_fever = any(phrase in symptoms_text for phrase in ["no fever", "without fever", "没有发热", "无发热"])
    no_pus = any(phrase in symptoms_text for phrase in ["no pus", "without pus", "没有脓", "无脓"])
    no_drainage = any(phrase in symptoms_text for phrase in ["no drainage", "without drainage", "没有渗液", "无渗液"])

    def has_any(*tokens: str) -> bool:
        return any(token.lower() in symptoms_text for token in tokens)

    if has_any("uncontrolled bleeding", "heavy bleeding", "bleeding will not stop", "失控出血", "大量出血"):
        flags.append("uncontrolled bleeding")
    if has_any("deep wound", "contaminated wound", "foreign body", "deep cut", "深伤口", "污染伤口", "异物"):
        flags.append("deep or contaminated wound")
    if has_any("fracture", "dislocation", "cannot move", "can't move", "numbness", "loss of sensation", "骨折", "脱位", "麻木"):
        flags.append("suspected fracture or dislocation")
    if has_any(
        "rapidly worsening swelling",
        "rapidly enlarging",
        "quickly enlarging",
        "rapidly growing",
        "swelling is getting worse",
        "肿胀明显加重",
        "迅速肿大",
        "快速肿大",
        "迅速增大",
        "快速增大",
        "肿块突然变大",
    ):
        flags.append("rapidly worsening swelling")
    if has_any("severe abdominal pain", "rigid abdomen", "persistent vomiting", "cannot pass gas", "cannot pass stool", "black stool", "bloody stool", "板状腹", "持续呕吐", "停气停便", "黑便", "血便"):
        flags.append("urgent abdominal surgical concern")
    if has_any("postoperative fever", "post-op fever", "wound dehiscence", "术后发热", "伤口裂开") or (
        (not no_pus and has_any("pus", "purulent drainage", "脓性分泌物"))
        or (not no_drainage and has_any("drainage", "渗液"))
    ):
        flags.append("postoperative wound complication")
    if has_any("fainting", "confusion", "晕厥", "意识异常"):
        flags.append("systemic instability")
    try:
        if vitals.get("systolic_bp") is not None and int(vitals.get("systolic_bp")) <= 90:
            flags.append("clearly abnormal vital signs")
    except Exception:
        pass
    try:
        if vitals.get("heart_rate") is not None and int(vitals.get("heart_rate")) >= 130:
            flags.append("clearly abnormal vital signs")
    except Exception:
        pass
    try:
        if not no_fever and vitals.get("temp_c") is not None and float(vitals.get("temp_c")) >= 38.5 and has_any("postoperative", "post-op", "wound", "surgery", "术后", "伤口"):
            flags.append("fever after surgery")
    except Exception:
        pass
    return list(dict.fromkeys(flags))


def _looks_like_low_risk_soft_tissue_lump(payload: dict) -> bool:
    text = f"{payload.get('symptoms', '')} {payload.get('chief_complaint', '')} {payload.get('message', '')}".lower()
    if not any(token in text for token in ("lump", "mass", "nodule", "bump", "肿块", "包块", "结节", "疙瘩")):
        return False
    if _detect_surgery_red_flags(payload):
        return False
    high_risk_tokens = (
        "severe pain",
        "worsening pain",
        "rapidly worsening",
        "rapidly enlarging",
        "quickly enlarging",
        "redness spreading",
        "skin breakdown",
        "ulcer",
        "pus",
        "purulent",
        "fever",
        "麻木",
        "活动受限",
        "明显加重",
        "快速增大",
        "迅速增大",
        "破溃",
        "流脓",
        "发热",
        "皮肤发黑",
    )
    negative_context = any(
        phrase in text
        for phrase in (
            "no redness",
            "no skin breakdown",
            "no ulcer",
            "no pus",
            "no fever",
            "无红肿",
            "没有红肿",
            "无破溃",
            "没有破溃",
            "无脓",
            "没有脓",
            "无发热",
            "没有发热",
        )
    )
    if not negative_context and any(token in text for token in high_risk_tokens):
        return False
    return True


def _supported_round1_surgery_red_flags(payload: dict) -> list[str]:
    return _detect_surgery_red_flags(payload)


def _usable_round1_impression(applied: dict, fallback: str) -> str:
    impression = str(applied.get("clinical_impression") or applied.get("note") or "").strip().rstrip("。")
    generic_markers = (
        "信息还不足",
        "辅助检查",
        "safe first-round",
        "routine first-round",
        "continue surgical",
        "recommended next step",
        "complete the recommended",
        "preliminary impression",
    )
    if impression and not any(marker.lower() in impression.lower() for marker in generic_markers):
        return impression
    return fallback.rstrip("。")


def _default_round1_outcome_policy() -> dict:
    return {
        "allowed_decisions": list(ROUND1_DECISIONS),
        "default_decision": "test_first",
        "direct_treat_scenarios": [],
        "referral_targets": [],
    }


def _round1_outcome_policy(policy_runtime_context: ClinicalPolicyRuntimeContext | None) -> dict:
    if policy_runtime_context is None or policy_runtime_context.primary_card is None:
        return _default_round1_outcome_policy()
    policy = dict(policy_runtime_context.primary_card.outcome_policy or {})
    merged = _default_round1_outcome_policy()
    merged.update(policy)
    return merged


def _surgery_context_text(payload: dict, memory=None) -> str:
    parts = [payload.get("chief_complaint"), payload.get("message")]
    if memory is not None:
        clinical = memory.shared_memory.get("clinical_memory") or {}
        parts.extend(clinical.get("symptoms") or [])
    return " ".join(str(part or "") for part in parts).lower()


def _round1_minimum_data_collected(payload: dict, memory=None) -> bool:
    if memory is not None:
        clinical = memory.shared_memory.get("clinical_memory") or {}
        profile = memory.shared_memory.get("profile") or {}
        return bool(clinical.get("chief_complaint")) and bool(clinical.get("onset_time")) and profile.get("allergy_status") == "known"
    return bool(payload.get("chief_complaint")) and bool(payload.get("onset_time")) and "allergies" in payload


def _match_referral_target(payload: dict, memory, outcome_policy: dict) -> dict | None:
    text = _surgery_context_text(payload, memory)
    for target in outcome_policy.get("referral_targets") or []:
        keywords = [str(item).lower() for item in (target.get("keywords") or []) if str(item).strip()]
        if any(keyword in text for keyword in keywords):
            return {
                "department": str(target.get("department") or "").strip(),
                "department_id": str(target.get("department_id") or "").strip(),
                "reason": str(target.get("reason") or "").strip(),
            }
    return None


def _matches_direct_treat_whitelist(payload: dict, memory, result: dict, outcome_policy: dict) -> bool:
    scenarios = list(outcome_policy.get("direct_treat_scenarios") or [])
    text = " ".join(str(part or "") for part in [payload.get("chief_complaint"), payload.get("message")]).lower()
    sanitized_text = text
    for phrase in [
        "no fever",
        "without fever",
        "no pus",
        "without pus",
        "no drainage",
        "without drainage",
        "pain is not worse",
        "not getting worse",
        "没有发热",
        "无发热",
        "没有脓",
        "无脓",
    ]:
        sanitized_text = sanitized_text.replace(phrase, " ")
    for scenario in scenarios:
        required_keywords = [str(item).lower() for item in (scenario.get("required_keywords_any") or []) if str(item).strip()]
        forbidden_keywords = [str(item).lower() for item in (scenario.get("forbidden_keywords_any") or []) if str(item).strip()]
        if required_keywords and not any(keyword in text for keyword in required_keywords):
            continue
        if any(keyword in sanitized_text for keyword in forbidden_keywords):
            continue
        try:
            diagnosis_level = int(result.get("diagnosis_level") or 1)
        except Exception:
            diagnosis_level = 1
        if diagnosis_level > 1:
            continue
        return True
    return False


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
    normalized["department"] = str(normalized.get("department") or "Surgery")
    normalized["note"] = str(normalized.get("note") or "Continue surgical outpatient follow-up.")
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
    normalized["prescription_plan"] = normalize_prescription_plan(normalized.get("prescription_plan"))
    normalized["needs_outpatient_procedure"] = bool(normalized.get("needs_outpatient_procedure", False))
    normalized["outpatient_procedure_category"] = str(normalized.get("outpatient_procedure_category") or "").strip()
    normalized["outpatient_procedure_reason"] = str(normalized.get("outpatient_procedure_reason") or "").strip()
    normalized["procedure_can_parallel_with_tests"] = bool(normalized.get("procedure_can_parallel_with_tests", False))
    normalized["icu_escalation"] = False
    return normalized


def _extract_round2_report(payload: dict) -> dict[str, Any]:
    report = payload.get("simulated_report")
    if isinstance(report, dict):
        return report
    diagnostic_session = payload.get("diagnostic_session")
    if isinstance(diagnostic_session, dict) and isinstance(diagnostic_session.get("report"), dict):
        return diagnostic_session.get("report") or {}
    return {}


def _round2_report_summary_text(report: dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return ""
    pieces: list[str] = []
    report_text = str(report.get("report_text") or "").strip()
    if report_text:
        pieces.append(report_text)
    summary = report.get("report_summary")
    if isinstance(summary, dict):
        for key, value in summary.items():
            value_text = str(value or "").strip()
            if value_text:
                pieces.append(f"{key} {value_text}")
    return " ".join(pieces).lower()


def _round2_base_result(
    *,
    clinical_impression: str,
    final_assessment_summary: str,
    patient_facing_plan: str,
    primary_disposition: str,
    priority: str = "M",
    department: str = "Surgery",
    diagnosis_level: int = 2,
    next_step_decision: str = "treat_and_discharge",
    admission_recommendation: dict | None = None,
    procedure_recommendation: dict | None = None,
    followup_recommendation: dict | None = None,
    return_precautions: list[str] | None = None,
    medication_recommendation: dict | None = None,
    prescription_plan: list[dict] | None = None,
    recommended_department: str | None = None,
    recommended_department_reason: str | None = None,
    handoff_reason: str | None = None,
    requires_new_registration: bool = False,
    carry_forward_summary: dict | None = None,
    note: str | None = None,
) -> dict:
    return {
        "department": department,
        "priority": priority,
        "diagnosis_level": diagnosis_level,
        "note": note or clinical_impression,
        "clinical_impression": clinical_impression,
        "final_assessment_summary": final_assessment_summary,
        "patient_facing_plan": patient_facing_plan,
        "patient_plan": patient_facing_plan,
        "disposition_advice": patient_facing_plan,
        "primary_disposition": primary_disposition,
        "next_step_decision": next_step_decision,
        "test_required": False,
        "test_category": "none",
        "test_items": [],
        "tests_suggested": [],
        "test_reason": "",
        "needs_tests": False,
        "needs_medication": bool((medication_recommendation or {}).get("recommended")) or bool(prescription_plan),
        "needs_second_consultation": False,
        "needs_second_internal_medicine_consultation": False,
        "admission_recommendation": admission_recommendation or {
            "recommended": False,
            "reason": "",
        },
        "procedure_recommendation": procedure_recommendation or {
            "surgery_evaluation_recommended": False,
            "urgency": "none",
            "reason": "",
        },
        "followup_recommendation": followup_recommendation or {
            "observation_required": False,
            "observation_setting": "none",
            "revisit_required": False,
            "revisit_window": "",
            "revisit_conditions": [],
        },
        "return_precautions": list(return_precautions or []),
        "medication_recommendation": medication_recommendation or {
            "recommended": False,
            "intent": "",
            "summary": "",
        },
        "prescription_plan": list(prescription_plan or []),
        "recommended_department": recommended_department,
        "recommended_department_reason": recommended_department_reason,
        "handoff_reason": handoff_reason,
        "requires_new_registration": requires_new_registration,
        "carry_forward_summary": dict(carry_forward_summary or {}),
        "red_flags": [],
        "medication_or_action": [],
    }


def _build_round2_surgery_result(payload: dict) -> dict | None:
    report = _extract_round2_report(payload)
    if not report:
        return None

    procedure_completed = bool(payload.get("procedure_completed"))
    procedure_summary = payload.get("outpatient_procedure_summary") or {}
    report_text = _round2_report_summary_text(report)
    combined_text = " ".join(
        part for part in [
            str(payload.get("chief_complaint") or ""),
            str(payload.get("symptoms") or ""),
            str(payload.get("message") or ""),
            report_text,
            str(procedure_summary.get("category") or ""),
        ] if part
    ).lower()
    red_flags = _detect_surgery_red_flags(payload)
    report_summary = report.get("report_summary") if isinstance(report.get("report_summary"), dict) else {}
    escalation_clues = dict(report_summary.get("escalation_clues") or {})
    referral_clues = list(report_summary.get("cross_specialty_clues") or [])

    if escalation_clues.get("to_icu"):
        reason = str(escalation_clues.get("reason") or "Report-level findings suggest ICU-level deterioration risk.").strip()
        return _round2_base_result(
            clinical_impression="The current report no longer supports routine surgery follow-up and raises concern for ICU-level instability.",
            final_assessment_summary="Immediate emergency/ICU escalation is more appropriate than continued outpatient surgery review.",
            patient_facing_plan="Go for immediate emergency reassessment now so the team can decide ICU monitoring or rescue care.",
            primary_disposition="icu_escalation",
            priority="H",
            department="Emergency",
            diagnosis_level=3,
            recommended_department="ICU",
            recommended_department_reason=reason,
            handoff_reason=reason,
            followup_recommendation={
                "observation_required": False,
                "observation_setting": "none",
                "revisit_required": False,
                "revisit_window": "",
                "revisit_conditions": [],
            },
            return_precautions=[reason],
        )

    if escalation_clues.get("to_emergency"):
        reason = str(escalation_clues.get("reason") or "Report-level findings suggest urgent emergency reassessment.").strip()
        return _round2_base_result(
            clinical_impression="The current report no longer supports routine surgery follow-up and raises time-sensitive concern.",
            final_assessment_summary="Emergency reassessment is more appropriate than continued outpatient surgery review.",
            patient_facing_plan="Go for immediate emergency reassessment now.",
            primary_disposition="emergency_escalation",
            priority="H",
            department="Emergency",
            diagnosis_level=3,
            recommended_department="Emergency",
            recommended_department_reason=reason,
            handoff_reason=reason,
            followup_recommendation={
                "observation_required": False,
                "observation_setting": "none",
                "revisit_required": False,
                "revisit_window": "",
                "revisit_conditions": [],
            },
            return_precautions=[reason],
        )

    if referral_clues:
        referral = dict(referral_clues[0] or {})
        target_department = str(referral.get("target_department") or referral.get("department") or "").strip()
        referral_reason = str(referral.get("reason") or "The remaining issue fits another specialty better after the current surgery loop.").strip()
        if target_department:
            return _round2_base_result(
                clinical_impression="The report suggests the remaining issue is better handled by another specialty after the surgery loop closes.",
                final_assessment_summary="The surgery outpatient loop can close, but the next registration should be with a more suitable specialty.",
                patient_facing_plan=f"Complete this surgery loop, then re-register with {target_department} for further assessment.",
                primary_disposition="specialty_referral",
                recommended_department=target_department,
                recommended_department_reason=referral_reason,
                handoff_reason=referral_reason,
                requires_new_registration=True,
                carry_forward_summary={
                    "origin_department": "Surgery",
                    "target_department": target_department,
                    "current_assessment": "Current surgery assessment is complete for this loop.",
                    "referral_reason": referral_reason,
                    "completed_workup": list(report.get("test_items") or []),
                    "next_department_focus": referral_reason,
                },
                return_precautions=[referral_reason],
            )

    if red_flags:
        return _round2_base_result(
            clinical_impression="结合目前症状变化和这次检查结果，提示外科风险已经升高，不能按普通门诊复查处理。",
            final_assessment_summary="当前更需要尽快回到高优先级外科评估，必要时转急诊处理，而不是继续居家观察。",
            patient_facing_plan="建议立即回诊或直接前往急诊，由外科团队尽快重新评估当前风险和下一步处理。",
            primary_disposition="emergency_escalation",
            priority="H",
            department="Emergency",
            diagnosis_level=3,
            next_step_decision="urgent_escalation",
            followup_recommendation={
                "observation_required": False,
                "observation_setting": "none",
                "revisit_required": False,
                "revisit_window": "",
                "revisit_conditions": [],
            },
            return_precautions=red_flags,
        )

    if any(token in combined_text for token in ("postoperative", "post-op", "wound", "dressing", "suture", "伤口", "术后", "换药")):
        stable_wound = any(
            token in combined_text
            for token in ("normal healing", "healing well", "no abscess", "clean wound", "granulation", "no retained foreign body", "stable", "恢复良好", "未见脓肿", "伤口清洁")
        )
        if stable_wound:
            return _round2_base_result(
                clinical_impression="这次复查结果更支持伤口恢复总体平稳，目前没有明确提示需要紧急外科升级处理。",
                final_assessment_summary="当前更适合继续门诊换药和观察恢复情况，不需要重复基础检查。",
                patient_facing_plan="建议继续按门诊伤口护理和换药方案处理，并在短期内复诊观察恢复情况。",
                primary_disposition="observe_then_revisit",
                priority="L",
                diagnosis_level=1,
                followup_recommendation={
                    "observation_required": True,
                    "observation_setting": "outpatient_home",
                    "revisit_required": True,
                    "revisit_window": "48-72小时",
                    "revisit_conditions": ["伤口红肿加重", "渗液增多", "发热", "疼痛明显加重"],
                },
                return_precautions=["伤口红肿加重", "脓性分泌物增多", "发热", "疼痛明显加重"],
                medication_recommendation={
                    "recommended": True,
                    "intent": "wound_care_support",
                    "summary": "是否需要局部处理或辅助用药，建议由外科医生结合伤口情况当面确认。",
                },
            )

        return _round2_base_result(
            clinical_impression="这次复查更像术后伤口问题仍需持续外科处理，当前不能只按普通恢复期观察。",
            final_assessment_summary="建议继续由外科门诊密切复查；如果伤口表现继续恶化，需要尽快升级处理。",
            patient_facing_plan="建议尽快回外科门诊复查伤口，必要时根据现场情况决定是否进一步清创、引流或住院。",
            primary_disposition="outpatient_management",
            diagnosis_level=2,
            procedure_recommendation={
                "surgery_evaluation_recommended": True,
                "urgency": "expedited",
                "reason": "若伤口局部情况持续不理想，需要外科医生尽快评估是否要进一步处置。",
            },
            followup_recommendation={
                "observation_required": False,
                "observation_setting": "none",
                "revisit_required": True,
                "revisit_window": "24-48小时",
                "revisit_conditions": ["渗液增加", "脓性分泌物", "发热", "伤口裂开"],
            },
            return_precautions=["渗液增加", "脓性分泌物", "发热", "伤口裂开"],
            medication_recommendation={
                "recommended": True,
                "intent": "postoperative_care",
                "summary": "是否需要抗感染或局部处理，应由外科医生结合伤口表现和既往处理方案确认。",
            },
        )

    if any(token in combined_text for token in ("fracture", "sprain", "ankle", "x-ray", "ultrasound", "foreign body", "injury", "trauma", "骨折", "扭伤", "异物", "外伤")):
        if any(token in combined_text for token in ("fracture", "dislocation", "retained foreign body", "suspicious collection", "骨折", "脱位", "异物残留")):
            return _round2_base_result(
                clinical_impression="这次复查结果提示局部损伤问题还需要进一步专科处理，已经不适合只按普通外科随访观察。",
                final_assessment_summary="当前重点是尽快完成针对性的专科评估，而不是重复基础检查。",
                patient_facing_plan="建议尽快按结果转入更合适的专科或由外科进一步评估是否需要处理创口/异物/固定。",
                primary_disposition="specialty_referral",
                diagnosis_level=2,
                recommended_department="Orthopedics",
                recommended_department_reason="影像或局部结果提示后续更适合由骨科/创伤方向进一步处理。",
                procedure_recommendation={
                    "surgery_evaluation_recommended": True,
                    "urgency": "expedited",
                    "reason": "局部损伤结果提示仍需尽快判断是否存在需要进一步外科处置的情况。",
                },
                followup_recommendation={
                    "observation_required": False,
                    "observation_setting": "none",
                    "revisit_required": True,
                    "revisit_window": "48-72小时",
                    "revisit_conditions": ["疼痛加重", "活动受限加重", "麻木", "肿胀明显增加"],
                },
                return_precautions=["疼痛加重", "活动受限加重", "麻木", "肿胀明显增加"],
            )

        return _round2_base_result(
            clinical_impression="这次复查结果没有提示需要急诊升级的局部损伤问题，目前更适合继续门诊处理和恢复期观察。",
            final_assessment_summary="当前不需要重复基础检查，重点是继续局部护理、观察症状变化，并按时复查。",
            patient_facing_plan="建议继续门诊随访和局部护理；如果症状加重，再提前回诊评估。",
            primary_disposition="outpatient_management",
            priority="L",
            diagnosis_level=1,
            followup_recommendation={
                "observation_required": True,
                "observation_setting": "outpatient_home",
                "revisit_required": True,
                "revisit_window": "3-5天",
                "revisit_conditions": ["疼痛加重", "肿胀明显增加", "活动受限", "麻木"],
            },
            return_precautions=["疼痛加重", "肿胀明显增加", "活动受限", "麻木"],
        )

    if any(token in combined_text for token in ("abdominal", "append", "gall", "vomiting", "appendix", "腹痛", "呕吐", "胆")):
        if any(token in combined_text for token in ("appendicitis", "obstruction", "perforation", "collection", "free fluid", "appendix", "阑尾", "梗阻", "穿孔", "积液")):
            return _round2_base_result(
                clinical_impression="这次检查结果和症状变化更提示仍存在外科腹部问题，需要进一步住院或加快外科评估。",
                final_assessment_summary="当前不适合继续按普通门诊随访，建议尽快由外科团队决定是否需要住院观察和手术评估。",
                patient_facing_plan="建议今天尽快回外科评估住院处理，并由外科团队根据检查结果决定是否需要手术方案。",
                primary_disposition="inpatient_admission_recommended",
                diagnosis_level=3,
                admission_recommendation={
                    "recommended": True,
                    "reason": "腹部症状结合检查结果，当前更需要住院观察和进一步外科处理。",
                },
                procedure_recommendation={
                    "surgery_evaluation_recommended": True,
                    "urgency": "expedited",
                    "reason": "检查结果提示可能存在需要尽快做外科决策的腹部问题。",
                },
                followup_recommendation={
                    "observation_required": False,
                    "observation_setting": "none",
                    "revisit_required": False,
                    "revisit_window": "",
                    "revisit_conditions": [],
                },
                return_precautions=["腹痛明显加重", "持续呕吐", "发热", "不能排气排便"],
            )

        return _round2_base_result(
            clinical_impression="这次检查结果暂时没有提示必须急诊升级的腹部外科问题，但仍建议继续门诊复查症状变化。",
            final_assessment_summary="当前更适合短期观察后复诊，不建议重复基础检查。",
            patient_facing_plan="建议按门诊方案继续观察，并在短期内复诊复核症状变化。",
            primary_disposition="observe_then_revisit",
            diagnosis_level=2,
            followup_recommendation={
                "observation_required": True,
                "observation_setting": "outpatient_home",
                "revisit_required": True,
                "revisit_window": "24-48小时",
                "revisit_conditions": ["腹痛加重", "持续呕吐", "发热", "黑便"],
            },
            return_precautions=["腹痛加重", "持续呕吐", "发热", "黑便"],
        )

    return _round2_base_result(
        clinical_impression="这次复查结果暂时没有提示需要急诊升级的外科问题，当前更适合继续门诊处理。",
        final_assessment_summary="现阶段不需要重复基础检查，重点是结合这次结果继续外科门诊随访。",
        patient_facing_plan="建议按当前外科门诊方案继续处理，并根据症状变化安排后续复诊。",
        primary_disposition="outpatient_management",
        priority="L",
        diagnosis_level=1,
        followup_recommendation={
            "observation_required": True,
            "observation_setting": "outpatient_home",
            "revisit_required": True,
            "revisit_window": "3-7天",
            "revisit_conditions": ["症状持续加重", "出现新的出血", "发热"],
        },
        return_precautions=["症状持续加重", "出现新的出血", "发热"],
    )


def _infer_outpatient_procedure_plan(payload: dict, *, decision: str, recommended_department: str | None) -> dict:
    if decision in {"urgent_escalation", "recommend_other_clinic"}:
        return {
            "needs_outpatient_procedure": False,
            "outpatient_procedure_category": "",
            "outpatient_procedure_reason": "",
            "procedure_can_parallel_with_tests": False,
        }
    if recommended_department and str(recommended_department).strip() and str(recommended_department).strip().lower() != "surgery":
        return {
            "needs_outpatient_procedure": False,
            "outpatient_procedure_category": "",
            "outpatient_procedure_reason": "",
            "procedure_can_parallel_with_tests": False,
        }

    text = " ".join(
        str(part or "")
        for part in [
            payload.get("chief_complaint"),
            payload.get("symptoms"),
            payload.get("message"),
        ]
    ).lower()
    category = ""
    reason = ""
    if any(token in text for token in ("dressing change", "wound care", "postoperative dressing", "wound check", "换药", "包扎", "伤口")):
        category = "wound_care"
        reason = "The current wound-focused presentation is more suitable for outpatient wound care before the second surgical review."
    elif any(token in text for token in ("debridement", "laceration", "abrasion", "cut", "清创", "裂伤", "擦伤")):
        category = "debridement_dressing"
        reason = "The local wound presentation may need outpatient debridement or dressing management before follow-up."
    elif any(token in text for token in ("cast", "splint", "immobilization", "plaster", "石膏", "夹板", "固定")):
        category = "immobilization"
        reason = "The injury presentation may need outpatient immobilization handling before follow-up reassessment."

    needs_outpatient_procedure = bool(category)
    return {
        "needs_outpatient_procedure": needs_outpatient_procedure,
        "outpatient_procedure_category": category,
        "outpatient_procedure_reason": reason,
        "procedure_can_parallel_with_tests": needs_outpatient_procedure and decision == "test_first",
    }


def _apply_completed_procedure_context(result: dict, payload: dict) -> dict:
    if not bool(payload.get("procedure_completed")):
        return result
    applied = dict(result)
    summary = dict(payload.get("outpatient_procedure_summary") or {})
    category = str(summary.get("category") or "").strip()
    prefix = "前面的门诊处置已经完成，当前重点是"
    patient_plan = str(applied.get("patient_facing_plan") or "").strip()
    if patient_plan and "前面的门诊处置已经完成" not in patient_plan:
        patient_plan = patient_plan.lstrip("，,。.;； ")
        applied["patient_facing_plan"] = f"{prefix}{patient_plan}"
    followup = dict(applied.get("followup_recommendation") or {})
    if followup and not applied.get("medication_recommendation", {}).get("recommended") and category in {"wound_care", "debridement_dressing"}:
        applied["medication_recommendation"] = {
            "recommended": True,
            "intent": "post_procedure_care",
            "summary": "处置后的换药、局部护理或辅助用药，建议由外科医生结合复查情况继续评估。",
        }
    procedure = dict(applied.get("procedure_recommendation") or {})
    if applied.get("primary_disposition") in {"outpatient_management", "observe_then_revisit"} and procedure.get("surgery_evaluation_recommended"):
        applied["procedure_recommendation"] = {
            "surgery_evaluation_recommended": False,
            "urgency": "none",
            "reason": "前面的门诊处置已经完成，当前重点转为复查、维护和后续观察。",
        }
    return applied


def _apply_round1_outcome_policy(
    result: dict,
    payload: dict,
    *,
    memory=None,
    policy_runtime_context: ClinicalPolicyRuntimeContext | None = None,
) -> dict:
    applied = dict(result)
    outcome_policy = _round1_outcome_policy(policy_runtime_context)
    default_decision = str(outcome_policy.get("default_decision") or "test_first").strip()
    if default_decision not in ROUND1_DECISIONS:
        default_decision = "test_first"

    deterministic_red_flags = _supported_round1_surgery_red_flags(payload)
    red_flags = list(dict.fromkeys(deterministic_red_flags))
    applied["red_flags"] = red_flags
    if red_flags:
        applied["priority"] = "H"
    elif str(applied.get("priority") or "").upper() == "H":
        applied["priority"] = "M"

    if red_flags or str(applied.get("priority") or "").upper() == "H":
        decision = "urgent_escalation"
        recommended_department = "Emergency"
        recommended_department_reason = "当前存在外科危险信号，需要立即急诊评估。"
        clinical_impression = "当前表现存在外科危险信号，不适合继续按普通外科门诊流程等待。"
        next_step_reason = recommended_department_reason
        disposition_advice = "请立即前往急诊或高优先级外科通道处理。"
    else:
        referral_target = _match_referral_target(payload, memory, outcome_policy)
        if referral_target is not None:
            decision = "recommend_other_clinic"
            recommended_department = referral_target["department"]
            recommended_department_reason = referral_target["reason"] or f"当前问题更适合到{recommended_department}进一步评估。"
            clinical_impression = f"当前表现更适合到{recommended_department}评估，而不是继续普通外科复诊。"
            next_step_reason = recommended_department_reason
            disposition_advice = f"请下一步挂{recommended_department}进一步评估。"
        elif _round1_minimum_data_collected(payload, memory) and _matches_direct_treat_whitelist(payload, memory, applied, outcome_policy):
            decision = "treat_and_discharge"
            recommended_department = None
            recommended_department_reason = None
            clinical_impression = _usable_round1_impression(applied, "当前表现整体偏低风险，暂时不需要二轮外科复诊。")
            next_step_reason = "已收集最低必要信息，未见外科急症危险信号，符合保守直接完成本轮门诊的条件。"
            disposition_advice = "本轮外科初步评估可以完成，请按门诊流程继续结算和离院指导。"
        else:
            decision = default_decision
            recommended_department = None
            recommended_department_reason = None
            clinical_impression = _usable_round1_impression(
                applied,
                (
                    "从目前查体和描述看，更像局部皮下结节或软组织包块，暂时没有明确急诊危险信号"
                    if _looks_like_low_risk_soft_tissue_lump(payload)
                    else "目前还不能下定论，需要先结合针对性检查结果进一步判断"
                ),
            )
            next_step_reason = "当前不符合急诊升级条件，也不符合保守直接离院条件。"
            disposition_advice = "请先完成已开具的相关检查，再带结果回来外科复诊。"

    procedure_only_override = False
    procedure_plan = _infer_outpatient_procedure_plan(
        payload,
        decision=decision,
        recommended_department=recommended_department,
    )
    if procedure_plan["needs_outpatient_procedure"] and decision == "treat_and_discharge":
        decision = "test_first"
        procedure_only_override = True
        clinical_impression = _usable_round1_impression(applied, "当前表现整体风险不高，但需要先完成门诊外科处置后，才能回到外科复诊判断。")
        next_step_reason = procedure_plan["outpatient_procedure_reason"] or "需要先完成门诊外科处置，再进行下一步复诊评估。"
        disposition_advice = "我已为你安排门诊外科处置，请先完成处置，再回来进行外科复诊。"
    elif (
        procedure_plan["outpatient_procedure_category"] == "wound_care"
        and decision == "test_first"
        and not red_flags
    ):
        procedure_only_override = True
        next_step_reason = procedure_plan["outpatient_procedure_reason"] or next_step_reason
        disposition_advice = "我已为你安排门诊伤口处理，请先完成伤口处理，再回来进行外科复诊。"
    elif procedure_plan["needs_outpatient_procedure"] and decision == "test_first" and not red_flags:
        procedure_name = {
            "debridement_dressing": "门诊清创换药",
            "immobilization": "门诊固定处理",
            "wound_care": "门诊伤口处理",
        }.get(procedure_plan["outpatient_procedure_category"], "门诊外科处置")
        next_step_reason = procedure_plan["outpatient_procedure_reason"] or next_step_reason
        disposition_advice = f"我已为你开具相关检查，并安排{procedure_name}；请先完成检查和处置，再回来进行外科复诊。"

    applied["next_step_decision"] = decision
    applied["needs_second_internal_medicine_consultation"] = decision == "test_first" or procedure_plan["needs_outpatient_procedure"]
    applied["needs_second_consultation"] = decision == "test_first" or procedure_plan["needs_outpatient_procedure"]
    applied["next_step_reason"] = next_step_reason
    applied["clinical_impression"] = clinical_impression
    applied["needs_tests"] = decision == "test_first" and not procedure_only_override
    applied["needs_medication"] = False
    applied["recommended_department"] = recommended_department
    applied["recommended_department_reason"] = recommended_department_reason
    applied["disposition_advice"] = disposition_advice
    applied["needs_outpatient_procedure"] = procedure_plan["needs_outpatient_procedure"]
    applied["outpatient_procedure_category"] = procedure_plan["outpatient_procedure_category"]
    applied["outpatient_procedure_reason"] = procedure_plan["outpatient_procedure_reason"]
    applied["procedure_can_parallel_with_tests"] = procedure_plan["procedure_can_parallel_with_tests"]

    if decision == "urgent_escalation":
        applied["department"] = "Emergency"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = ["立即前往急诊或高优先级外科通道评估"]
        applied["note"] = f"初步判断：{clinical_impression}"
    elif decision == "recommend_other_clinic":
        applied["department"] = recommended_department or applied.get("department") or "Surgery"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = [f"请优先到{recommended_department}进一步评估，再决定后续处理。"] if recommended_department else []
        applied["note"] = f"初步判断：{clinical_impression}"
    elif decision == "treat_and_discharge":
        applied["department"] = "Surgery"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = ["继续按外科门诊流程完成结算和离院指导"]
        applied["note"] = f"初步判断：{clinical_impression}"
        applied["red_flags"] = []
    else:
        applied["department"] = "Surgery"
        applied["test_required"] = bool(applied.get("needs_tests"))
        if not applied["test_required"]:
            applied["test_category"] = "none"
            applied["test_items"] = []
            applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["note"] = f"初步判断：{clinical_impression}"

    return applied


def rule_based_surgery(payload: dict) -> dict:
    consultation_round = 1
    try:
        consultation_round = int(payload.get("consultation_round") or 1)
    except Exception:
        consultation_round = 1
    if consultation_round >= 2:
        round2_result = _build_round2_surgery_result(payload)
        if round2_result is not None:
            return _apply_completed_procedure_context(round2_result, payload)
    rules = retrieve_relevant_surgery_rules(payload, top_k=1)
    if rules:
        result = dict(rules[0]["result"])
    else:
        result = {
            "diagnosis_level": 1,
            "priority": "L",
            "department": "Surgery",
            "note": "A routine first-round surgery assessment is needed before deciding the next step.",
            "test_required": True,
            "test_category": "medical_imaging",
            "test_items": ["Focused surgical review"],
            "test_reason": "Used to complete a safe first-round surgical outpatient assessment.",
        }
    result.update(_infer_test_plan(result, payload))
    return result


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
        "next_step_decision",
        "needs_second_consultation",
        "needs_second_internal_medicine_consultation",
        "recommended_department",
        "recommended_department_reason",
        "handoff_reason",
        "requires_new_registration",
        "carry_forward_summary",
        "needs_outpatient_procedure",
        "outpatient_procedure_category",
        "primary_disposition",
        "medication_recommendation",
        "admission_recommendation",
        "procedure_recommendation",
        "followup_recommendation",
        "return_precautions",
        "prescription_plan",
    }
    comparable_previous = {key: previous.get(key) for key in significant_keys}
    comparable_current = {key: current.get(key) for key in significant_keys}
    return comparable_previous != comparable_current


def validate_surgery_result(
    llm_result: dict | None,
    fallback: dict,
    payload: dict,
    *,
    policy_runtime_context: ClinicalPolicyRuntimeContext | None = None,
    memory=None,
    mode: str | None = None,
    complete: bool | None = None,
) -> dict:
    del mode, complete
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
                    "test_category": llm_result.get("test_category", base.get("test_category", "medical_imaging")),
                    "test_items": llm_result.get("test_items", base.get("test_items", [])),
                    "test_reason": llm_result.get("test_reason", base.get("test_reason", "")),
                    "next_step_decision": llm_result.get("next_step_decision"),
                    "needs_second_consultation": llm_result.get("needs_second_consultation"),
                    "needs_second_internal_medicine_consultation": llm_result.get("needs_second_internal_medicine_consultation"),
                    "next_step_reason": llm_result.get("next_step_reason"),
                    "clinical_impression": llm_result.get("clinical_impression"),
                    "final_assessment_summary": llm_result.get("final_assessment_summary"),
                    "primary_disposition": llm_result.get("primary_disposition"),
                    "medication_recommendation": llm_result.get("medication_recommendation"),
                    "prescription_plan": llm_result.get("prescription_plan"),
                    "admission_recommendation": llm_result.get("admission_recommendation"),
                    "procedure_recommendation": llm_result.get("procedure_recommendation"),
                    "followup_recommendation": llm_result.get("followup_recommendation"),
                    "return_precautions": llm_result.get("return_precautions"),
                    "patient_facing_plan": llm_result.get("patient_facing_plan"),
                    "needs_tests": llm_result.get("needs_tests"),
                    "needs_medication": llm_result.get("needs_medication"),
                    "recommended_department": llm_result.get("recommended_department"),
                    "recommended_department_reason": llm_result.get("recommended_department_reason"),
                    "handoff_reason": llm_result.get("handoff_reason"),
                    "requires_new_registration": llm_result.get("requires_new_registration"),
                    "carry_forward_summary": llm_result.get("carry_forward_summary"),
                    "disposition_advice": llm_result.get("disposition_advice"),
                    "icu_escalation": llm_result.get("icu_escalation"),
                    "needs_outpatient_procedure": llm_result.get("needs_outpatient_procedure"),
                    "outpatient_procedure_category": llm_result.get("outpatient_procedure_category"),
                    "outpatient_procedure_reason": llm_result.get("outpatient_procedure_reason"),
                    "procedure_can_parallel_with_tests": llm_result.get("procedure_can_parallel_with_tests"),
                }
            )
    except Exception:
        base = dict(fallback)

    if base.get("needs_second_consultation") is None and base.get("needs_second_internal_medicine_consultation") is not None:
        base["needs_second_consultation"] = bool(base.get("needs_second_internal_medicine_consultation"))
    if (
        base.get("needs_second_internal_medicine_consultation") is None
        and base.get("needs_second_consultation") is not None
    ):
        base["needs_second_internal_medicine_consultation"] = bool(base.get("needs_second_consultation"))

    normalized = _normalize_final_result(base, payload)
    consultation_round = None
    if memory is not None:
        try:
            consultation_round = int(memory.private_memory.get("consultation_round") or 1)
        except Exception:
            consultation_round = 1
    if consultation_round == 1:
        normalized = _apply_round1_outcome_policy(
            normalized,
            payload,
            memory=memory,
            policy_runtime_context=policy_runtime_context,
        )
    else:
        normalized = normalize_round2_conclusion(normalized, consultation_round=consultation_round or 2)
        normalized = preserve_round2_escalation_floor(
            normalized,
            fallback_result=fallback,
            consultation_round=consultation_round or 2,
        )
    return _normalize_final_result(normalized, payload)
