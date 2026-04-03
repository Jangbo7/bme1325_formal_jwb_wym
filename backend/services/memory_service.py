import re
from datetime import datetime, timezone

from memory.patient_memory import PATIENT_MEMORY_STORE
from memory.session_store import SESSION_STORE


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_symptoms(text):
    normalized = (
        (text or "")
        .replace("，", ",")
        .replace("、", ",")
        .replace("；", ",")
        .replace(";", ",")
    )
    parts = [item.strip() for item in normalized.split(",")]
    return [item for item in parts if item]


def _derive_risk_flags(symptoms, vitals):
    joined = " ".join(symptoms).lower()
    risk_flags = []
    if any(term in joined for term in ("chest", "胸", "breath", "呼吸")):
        risk_flags.append("cardiopulmonary_alert")
    if any(term in joined for term in ("faint", "syncope", "晕", "昏")):
        risk_flags.append("consciousness_alert")
    if _safe_float(vitals.get("temp_c")) and _safe_float(vitals.get("temp_c")) >= 38.5:
        risk_flags.append("fever")
    if _safe_int(vitals.get("pain_score")) and _safe_int(vitals.get("pain_score")) >= 8:
        risk_flags.append("severe_pain")
    return sorted(set(risk_flags))


def _merge_vitals(old_vitals, new_vitals):
    merged = dict(old_vitals)
    for key, value in (new_vitals or {}).items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _merge_unique(old_values, new_values):
    merged = list(old_values or [])
    for value in new_values or []:
        if value and value not in merged:
            merged.append(value)
    return merged


def _build_missing_fields(memory):
    missing = []
    clinical_memory = memory["clinical_memory"]
    profile = memory["profile"]
    if not clinical_memory.get("chief_complaint"):
        missing.append("chief_complaint")
    if not clinical_memory.get("symptoms"):
        missing.append("symptoms")
    if not clinical_memory.get("onset_time"):
        missing.append("onset_time")
    if "temp_c" not in clinical_memory.get("vitals", {}):
        missing.append("temp_c")
    if "pain_score" not in clinical_memory.get("vitals", {}):
        missing.append("pain_score")
    if profile.get("allergy_status") != "known":
        missing.append("allergies")
    return missing


def _hydrate_payload_from_memory(payload, memory):
    clinical_memory = memory["clinical_memory"]
    merged_payload = dict(payload)
    merged_payload["symptoms"] = payload.get("symptoms") or ", ".join(clinical_memory.get("symptoms") or [])
    merged_payload["vitals"] = _merge_vitals(clinical_memory.get("vitals") or {}, payload.get("vitals") or {})
    merged_payload["onset_time"] = payload.get("onset_time") or clinical_memory.get("onset_time")
    merged_payload["allergies"] = payload.get("allergies") or memory["profile"].get("allergies") or []
    merged_payload["chronic_conditions"] = payload.get("chronic_conditions") or memory["profile"].get("chronic_conditions") or []
    return merged_payload


def _extract_time_text(message):
    lowered = (message or "").lower()
    if "刚刚" in message or "just now" in lowered:
        return "just now"
    if "半小时" in message:
        return "30 minutes"
    patterns = [
        r"(\d+)\s*(分钟|小时|天)",
        r"(\d+)\s*(min|mins|minute|minutes|hour|hours|day|days)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _extract_pain_score(message):
    match = re.search(r"(\d{1,2})\s*分", message)
    if match:
        return max(0, min(10, int(match.group(1))))
    lowered = (message or "").lower()
    if "很痛" in message or "severe pain" in lowered:
        return 8
    if "有点痛" in message or "slight pain" in lowered:
        return 3
    return None


def _extract_temp_c(message):
    match = re.search(r"(\d{2}(?:\.\d)?)\s*(?:度|°c|c)", message, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    lowered = (message or "").lower()
    if "没发烧" in message or "没有发烧" in message or "no fever" in lowered:
        return 37.0
    return None


def _extract_allergies(message):
    lowered = (message or "").lower()
    if "不过敏" in message or "无过敏" in message or "没有过敏" in message or "no allergy" in lowered or "no allergies" in lowered:
        return []
    return None


def _extract_structured_updates(message):
    return {
        "onset_time": _extract_time_text(message),
        "pain_score": _extract_pain_score(message),
        "temp_c": _extract_temp_c(message),
        "allergies": _extract_allergies(message),
        "symptoms": _split_symptoms(message),
    }


def prepare_memory_context(payload):
    patient_id = payload["patient_id"]
    patient_name = payload.get("name", patient_id)
    session_id = payload.get("session_id") or "default"
    memory = PATIENT_MEMORY_STORE.get_or_create(patient_id, patient_name)

    profile = memory["profile"]
    clinical_memory = memory["clinical_memory"]
    symptoms_from_payload = _split_symptoms(payload.get("symptoms", ""))

    profile["allergies"] = _merge_unique(profile.get("allergies"), payload.get("allergies") or [])
    if payload.get("allergies") is not None:
        profile["allergy_status"] = "known"
    profile["chronic_conditions"] = _merge_unique(profile.get("chronic_conditions"), payload.get("chronic_conditions") or [])
    profile["name"] = patient_name
    if payload.get("age") is not None:
        profile["age"] = payload.get("age")
    if payload.get("sex"):
        profile["sex"] = payload.get("sex")

    clinical_memory["symptoms"] = _merge_unique(clinical_memory.get("symptoms"), symptoms_from_payload)
    clinical_memory["chief_complaint"] = payload.get("chief_complaint") or clinical_memory.get("chief_complaint") or payload.get("symptoms", "")
    clinical_memory["onset_time"] = payload.get("onset_time") or clinical_memory.get("onset_time")
    clinical_memory["vitals"] = _merge_vitals(clinical_memory.get("vitals") or {}, payload.get("vitals") or {})
    clinical_memory["risk_flags"] = _derive_risk_flags(clinical_memory["symptoms"], clinical_memory["vitals"])

    PATIENT_MEMORY_STORE.upsert(patient_id, memory)

    user_content = payload.get("message") or payload.get("symptoms") or clinical_memory["chief_complaint"] or "triage request"
    SESSION_STORE.append_turn(
        patient_id,
        "user",
        user_content,
        now_iso(),
        session_id=session_id,
        metadata={"source": "triage_request"},
    )

    missing_fields = _build_missing_fields(memory)
    SESSION_STORE.update_summary(
        patient_id,
        {
            "chief_complaint": clinical_memory.get("chief_complaint"),
            "risk_flags": clinical_memory.get("risk_flags"),
            "missing_fields": missing_fields,
            "expected_field": missing_fields[0] if missing_fields else None,
        },
        session_id=session_id,
    )

    return {
        "patient_id": patient_id,
        "session_id": session_id,
        "payload_for_triage": _hydrate_payload_from_memory(payload, memory),
        "short_term_memory": SESSION_STORE.get_or_create_session(patient_id, session_id=session_id),
        "long_term_memory": memory,
        "missing_fields": missing_fields,
        "expected_field": missing_fields[0] if missing_fields else None,
    }


def prepare_chat_memory_context(payload):
    patient_id = payload["patient_id"]
    session_id = payload.get("session_id") or "default"
    memory = PATIENT_MEMORY_STORE.get_or_create(patient_id, payload.get("name", patient_id))
    profile = memory["profile"]
    clinical_memory = memory["clinical_memory"]
    message = (payload.get("message") or "").strip()
    extracted = _extract_structured_updates(message)
    current_summary = SESSION_STORE.get_summary(patient_id, session_id=session_id)
    expected_field = current_summary.get("expected_field")

    if message:
        SESSION_STORE.append_turn(
            patient_id,
            "user",
            message,
            now_iso(),
            session_id=session_id,
            metadata={"source": "triage_chat", "expected_field": expected_field},
        )

    if extracted["symptoms"]:
        clinical_memory["symptoms"] = _merge_unique(clinical_memory.get("symptoms"), extracted["symptoms"])
        if not clinical_memory.get("chief_complaint"):
            clinical_memory["chief_complaint"] = extracted["symptoms"][0]
    if extracted["onset_time"]:
        clinical_memory["onset_time"] = extracted["onset_time"]
    if extracted["pain_score"] is not None:
        clinical_memory["vitals"] = _merge_vitals(clinical_memory.get("vitals") or {}, {"pain_score": extracted["pain_score"]})
    if extracted["temp_c"] is not None:
        clinical_memory["vitals"] = _merge_vitals(clinical_memory.get("vitals") or {}, {"temp_c": extracted["temp_c"]})
    if extracted["allergies"] is not None:
        profile["allergies"] = extracted["allergies"]
        profile["allergy_status"] = "known"

    clinical_memory["risk_flags"] = _derive_risk_flags(clinical_memory.get("symptoms") or [], clinical_memory.get("vitals") or {})
    PATIENT_MEMORY_STORE.upsert(patient_id, memory)

    missing_fields = _build_missing_fields(memory)
    SESSION_STORE.update_summary(
        patient_id,
        {
            "chief_complaint": clinical_memory.get("chief_complaint"),
            "risk_flags": clinical_memory.get("risk_flags"),
            "missing_fields": missing_fields,
            "expected_field": expected_field,
        },
        session_id=session_id,
    )

    return {
        "patient_id": patient_id,
        "session_id": session_id,
        "payload_for_triage": _hydrate_payload_from_memory(payload, memory),
        "short_term_memory": SESSION_STORE.get_or_create_session(patient_id, session_id=session_id),
        "long_term_memory": memory,
        "missing_fields": missing_fields,
        "expected_field": expected_field,
        "last_user_message": message,
    }


def finalize_memory_context(memory_context, triage_result, evidence, assistant_message=None, summary_updates=None):
    patient_id = memory_context["patient_id"]
    session_id = memory_context["session_id"]
    memory = PATIENT_MEMORY_STORE.get_or_create(patient_id)
    timestamp = now_iso()

    memory["clinical_memory"]["last_department"] = triage_result.get("department")
    memory["clinical_memory"]["last_triage_level"] = triage_result.get("triage_level")
    memory["triage_history"].append(
        {
            "time": timestamp,
            "triage_level": triage_result.get("triage_level"),
            "priority": triage_result.get("priority"),
            "department": triage_result.get("department"),
            "note": triage_result.get("note"),
            "evidence_ids": [item.get("id") for item in evidence],
        }
    )
    memory["triage_history"] = memory["triage_history"][-10:]
    PATIENT_MEMORY_STORE.upsert(patient_id, memory)

    SESSION_STORE.append_turn(
        patient_id,
        "assistant",
        assistant_message or triage_result.get("note", ""),
        timestamp,
        session_id=session_id,
        metadata={
            "triage_level": triage_result.get("triage_level"),
            "department": triage_result.get("department"),
        },
    )
    summary_payload = {
        "chief_complaint": memory["clinical_memory"].get("chief_complaint"),
        "risk_flags": memory["clinical_memory"].get("risk_flags"),
        "missing_fields": _build_missing_fields(memory),
        "last_department": memory["clinical_memory"].get("last_department"),
        "last_triage_level": memory["clinical_memory"].get("last_triage_level"),
    }
    if summary_updates:
        summary_payload.update(summary_updates)
    SESSION_STORE.update_summary(patient_id, summary_payload, session_id=session_id)

    return {
        "short_term_memory": SESSION_STORE.get_or_create_session(patient_id, session_id=session_id),
        "long_term_memory": PATIENT_MEMORY_STORE.get_or_create(patient_id),
    }
