import json
import re
from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRuntimeContext
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
    normalized["icu_escalation"] = False
    return normalized


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

    deterministic_red_flags = _detect_surgery_red_flags(payload)
    red_flags = list(dict.fromkeys(_normalize_string_list(applied.get("red_flags"), deterministic_red_flags) + deterministic_red_flags))
    applied["red_flags"] = red_flags
    if red_flags:
        applied["priority"] = "H"

    if red_flags or str(applied.get("priority") or "").upper() == "H":
        decision = "urgent_escalation"
        recommended_department = "Emergency"
        recommended_department_reason = "Urgent surgical red flags require immediate emergency evaluation."
        clinical_impression = "The current presentation contains urgent surgical warning features and should not continue as a routine surgery visit."
        next_step_reason = recommended_department_reason
        disposition_advice = "Please go to the emergency department or seek immediate high-priority surgical evaluation now."
    else:
        referral_target = _match_referral_target(payload, memory, outcome_policy)
        if referral_target is not None:
            decision = "recommend_other_clinic"
            recommended_department = referral_target["department"]
            recommended_department_reason = referral_target["reason"] or f"The current complaint is more suitable for {recommended_department}."
            clinical_impression = f"The current presentation appears more suitable for {recommended_department} evaluation than continued routine surgery follow-up."
            next_step_reason = recommended_department_reason
            disposition_advice = f"Recommended next step: register with {recommended_department} for further evaluation."
        elif _round1_minimum_data_collected(payload, memory) and _matches_direct_treat_whitelist(payload, memory, applied, outcome_policy):
            decision = "treat_and_discharge"
            recommended_department = None
            recommended_department_reason = None
            clinical_impression = "The current presentation is most consistent with a low-risk surgical outpatient concern that does not need a second surgery consultation right now."
            next_step_reason = "Minimum information has been collected, there are no urgent surgical red flags, and the case matches the conservative direct-discharge whitelist."
            disposition_advice = "Based on the current first-round surgical assessment, you may proceed with routine outpatient follow-up, checkout, and discharge advice without a second surgery consultation."
        else:
            decision = default_decision
            recommended_department = None
            recommended_department_reason = None
            clinical_impression = "The current information does not safely support direct discharge, so focused tests or follow-up assessment should come first."
            next_step_reason = "The case does not meet urgent escalation criteria and does not qualify for the conservative direct-discharge whitelist."
            disposition_advice = "Recommended next step: complete the suggested tests first and then return for surgical follow-up."

    applied["next_step_decision"] = decision
    applied["needs_second_internal_medicine_consultation"] = decision == "test_first"
    applied["next_step_reason"] = next_step_reason
    applied["clinical_impression"] = clinical_impression
    applied["needs_tests"] = decision == "test_first"
    applied["needs_medication"] = False
    applied["recommended_department"] = recommended_department
    applied["recommended_department_reason"] = recommended_department_reason
    applied["disposition_advice"] = disposition_advice

    if decision == "urgent_escalation":
        applied["department"] = "Emergency"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = ["Seek emergency surgical evaluation immediately."]
        applied["note"] = f"Preliminary impression: {clinical_impression}"
    elif decision == "recommend_other_clinic":
        applied["department"] = recommended_department or applied.get("department") or "Surgery"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = [f"Prefer evaluation in {recommended_department} before further treatment decisions."] if recommended_department else []
        applied["note"] = f"Preliminary impression: {clinical_impression}"
    elif decision == "treat_and_discharge":
        applied["department"] = "Surgery"
        applied["test_required"] = False
        applied["test_category"] = "none"
        applied["test_items"] = []
        applied["tests_suggested"] = []
        applied["patient_plan"] = disposition_advice
        applied["medication_or_action"] = ["Proceed with routine surgical outpatient follow-up, checkout, and discharge instructions."]
        applied["note"] = f"Preliminary impression: {clinical_impression}"
        applied["red_flags"] = []
    else:
        applied["department"] = "Surgery"
        applied["test_required"] = True
        applied["patient_plan"] = disposition_advice
        applied["note"] = f"Preliminary impression: {clinical_impression}"

    return applied


def rule_based_surgery(payload: dict) -> dict:
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
        "next_step_decision",
        "needs_second_internal_medicine_consultation",
        "recommended_department",
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
                    "needs_second_internal_medicine_consultation": llm_result.get("needs_second_internal_medicine_consultation"),
                    "next_step_reason": llm_result.get("next_step_reason"),
                    "clinical_impression": llm_result.get("clinical_impression"),
                    "needs_tests": llm_result.get("needs_tests"),
                    "needs_medication": llm_result.get("needs_medication"),
                    "recommended_department": llm_result.get("recommended_department"),
                    "recommended_department_reason": llm_result.get("recommended_department_reason"),
                    "disposition_advice": llm_result.get("disposition_advice"),
                }
            )
    except Exception:
        base = dict(fallback)

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
    return _normalize_final_result(normalized, payload)
