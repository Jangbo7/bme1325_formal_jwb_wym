from __future__ import annotations

from copy import deepcopy
from typing import Any


ROUND2_PRIMARY_DISPOSITIONS = {
    "outpatient_management",
    "observe_then_revisit",
    "inpatient_admission_recommended",
    "emergency_escalation",
    "icu_escalation",
    "specialty_referral",
}

ROUND2_PROCEDURE_URGENCIES = {"elective", "expedited", "urgent", "none"}
ROUND2_ESCALATION_FIELDS = (
    "priority",
    "department",
    "diagnosis_level",
    "primary_disposition",
    "clinical_impression",
    "final_assessment_summary",
    "disposition_advice",
    "patient_plan",
    "patient_facing_plan",
    "recommended_department",
    "recommended_department_reason",
    "handoff_reason",
    "return_precautions",
    "followup_recommendation",
    "admission_recommendation",
    "red_flags",
    "note",
    "medication_or_action",
    "icu_escalation",
)


def round2_response_keys() -> str:
    return (
        "department, priority, diagnosis_level, note, patient_plan, tests_suggested, "
        "medication_or_action, red_flags, test_required, test_category, test_items, test_reason, "
        "clinical_impression, final_assessment_summary, primary_disposition, medication_recommendation, "
        "admission_recommendation, procedure_recommendation, prescription_plan, followup_recommendation, "
        "return_precautions, patient_facing_plan, recommended_department, recommended_department_reason, "
        "handoff_reason, requires_new_registration, carry_forward_summary."
    )


def normalize_round2_conclusion(result: dict, *, consultation_round: int) -> dict:
    if consultation_round < 2:
        return dict(result)

    normalized = dict(result)

    medication = _normalize_medication_recommendation(normalized)
    admission = _normalize_admission_recommendation(normalized)
    procedure = _normalize_procedure_recommendation(normalized)
    followup = _normalize_followup_recommendation(normalized)

    primary_disposition = _normalize_primary_disposition(
        normalized,
        medication=medication,
        admission=admission,
        procedure=procedure,
        followup=followup,
    )

    if primary_disposition == "observe_then_revisit":
        followup["observation_required"] = True
        followup["revisit_required"] = True
        if followup["observation_setting"] == "none":
            followup["observation_setting"] = "outpatient_home"
    elif primary_disposition == "inpatient_admission_recommended":
        admission["recommended"] = True
    elif primary_disposition in {"emergency_escalation", "icu_escalation"}:
        admission = {"recommended": False, "reason": ""}
        followup = {
            "observation_required": False,
            "observation_setting": "none",
            "revisit_required": False,
            "revisit_window": "",
            "revisit_conditions": [],
        }
        if not procedure["surgery_evaluation_recommended"]:
            procedure["urgency"] = "none"

    final_assessment_summary = str(
        normalized.get("final_assessment_summary")
        or normalized.get("final_diagnosis")
        or normalized.get("clinical_impression")
        or normalized.get("note")
        or normalized.get("assistant_message")
        or ""
    ).strip()
    patient_facing_plan = str(
        normalized.get("patient_facing_plan")
        or normalized.get("patient_plan")
        or normalized.get("disposition_advice")
        or final_assessment_summary
        or ""
    ).strip()
    return_precautions = _normalize_string_list(
        normalized.get("return_precautions"),
        normalized.get("red_flags"),
    )
    recommended_department = str(normalized.get("recommended_department") or "").strip()
    recommended_department_reason = str(normalized.get("recommended_department_reason") or "").strip()
    handoff_reason = str(
        normalized.get("handoff_reason")
        or recommended_department_reason
        or normalized.get("disposition_advice")
        or final_assessment_summary
        or ""
    ).strip()
    priority = _normalize_round2_priority(
        normalized.get("priority"),
        primary_disposition=primary_disposition,
    )
    if primary_disposition == "icu_escalation":
        if not recommended_department:
            recommended_department = "ICU"
        if not recommended_department_reason:
            recommended_department_reason = handoff_reason or "Immediate ICU-level escalation is recommended."
    elif primary_disposition == "emergency_escalation":
        if not recommended_department:
            recommended_department = "Emergency"
        if not recommended_department_reason:
            recommended_department_reason = handoff_reason or "Immediate emergency escalation is recommended."
    requires_new_registration = _normalize_requires_new_registration(
        normalized.get("requires_new_registration"),
        primary_disposition=primary_disposition,
    )
    carry_forward_summary = _normalize_carry_forward_summary(
        normalized.get("carry_forward_summary"),
        department=str(normalized.get("department") or "").strip(),
        recommended_department=recommended_department,
        handoff_reason=handoff_reason,
        final_assessment_summary=final_assessment_summary,
        tests_suggested=_normalize_string_list(normalized.get("tests_suggested"), normalized.get("test_items")),
    )

    normalized["final_assessment_summary"] = final_assessment_summary
    normalized["priority"] = priority
    normalized["primary_disposition"] = primary_disposition
    normalized["medication_recommendation"] = medication
    normalized["admission_recommendation"] = admission
    normalized["procedure_recommendation"] = procedure
    normalized["followup_recommendation"] = followup
    normalized["return_precautions"] = return_precautions
    normalized["patient_facing_plan"] = patient_facing_plan
    normalized["patient_plan"] = str(normalized.get("patient_plan") or patient_facing_plan)
    normalized["recommended_department"] = recommended_department or None
    normalized["recommended_department_reason"] = recommended_department_reason or None
    normalized["handoff_reason"] = handoff_reason or None
    normalized["requires_new_registration"] = requires_new_registration
    normalized["carry_forward_summary"] = carry_forward_summary
    normalized["icu_escalation"] = primary_disposition == "icu_escalation" or bool(normalized.get("icu_escalation"))
    return normalized


def preserve_round2_escalation_floor(result: dict, *, fallback_result: dict | None, consultation_round: int) -> dict:
    normalized_result = normalize_round2_conclusion(result, consultation_round=consultation_round)
    if consultation_round < 2 or not isinstance(fallback_result, dict):
        return normalized_result

    normalized_fallback = normalize_round2_conclusion(fallback_result, consultation_round=consultation_round)
    if _round2_escalation_rank(normalized_fallback.get("primary_disposition")) <= _round2_escalation_rank(
        normalized_result.get("primary_disposition")
    ):
        return normalized_result

    merged = dict(normalized_result)
    for field in ROUND2_ESCALATION_FIELDS:
        if field in normalized_fallback:
            merged[field] = deepcopy(normalized_fallback.get(field))
    return normalize_round2_conclusion(merged, consultation_round=consultation_round)


def _normalize_primary_disposition(
    result: dict,
    *,
    medication: dict,
    admission: dict,
    procedure: dict,
    followup: dict,
) -> str:
    explicit = str(result.get("primary_disposition") or "").strip()
    if explicit in ROUND2_PRIMARY_DISPOSITIONS:
        return explicit

    next_step_decision = str(result.get("next_step_decision") or "").strip()
    department = str(result.get("department") or "").strip().lower()
    recommended_department = str(result.get("recommended_department") or "").strip()
    priority = str(result.get("priority") or "").strip().upper()
    if bool(result.get("icu_escalation")) or department == "icu" or recommended_department.lower() == "icu":
        return "icu_escalation"
    if next_step_decision == "urgent_escalation" or department == "emergency" or priority == "H":
        return "emergency_escalation"
    if next_step_decision == "recommend_other_clinic" or recommended_department:
        return "specialty_referral"
    if admission["recommended"]:
        return "inpatient_admission_recommended"
    if followup["observation_required"] or followup["revisit_required"]:
        return "observe_then_revisit"
    if medication["recommended"] or procedure["surgery_evaluation_recommended"] or str(result.get("disposition_advice") or "").strip():
        return "outpatient_management"
    return "outpatient_management"


def _normalize_round2_priority(value: Any, *, primary_disposition: str) -> str:
    if primary_disposition in {"emergency_escalation", "icu_escalation"}:
        return "H"
    priority = str(value or "").strip().upper()
    if priority in {"H", "M", "L"}:
        return priority
    return "M"


def _round2_escalation_rank(primary_disposition: Any) -> int:
    disposition = str(primary_disposition or "").strip()
    if disposition == "icu_escalation":
        return 2
    if disposition == "emergency_escalation":
        return 1
    return 0


def _normalize_medication_recommendation(result: dict) -> dict:
    explicit = _as_dict(result.get("medication_recommendation"))
    prescriptions = result.get("prescriptions") or result.get("prescription_plan")
    actions = _normalize_string_list(result.get("medication_or_action"))
    recommended = _coerce_bool(
        explicit.get("recommended"),
        default=bool(prescriptions or result.get("needs_medication") or actions),
    )
    intent = str(explicit.get("intent") or ("symptom_control" if recommended else "none")).strip() or "none"
    summary = str(explicit.get("summary") or "").strip()
    if not summary and recommended:
        if prescriptions:
            summary = "Medication treatment is recommended based on the second-round assessment."
        elif actions:
            summary = "; ".join(actions[:2])
    return {
        "recommended": recommended,
        "intent": intent,
        "summary": summary,
    }


def _normalize_admission_recommendation(result: dict) -> dict:
    explicit = _as_dict(result.get("admission_recommendation"))
    recommended = _coerce_bool(explicit.get("recommended"), default=False)
    reason = str(explicit.get("reason") or "").strip()
    return {
        "recommended": recommended,
        "reason": reason,
    }


def _normalize_procedure_recommendation(result: dict) -> dict:
    explicit = _as_dict(result.get("procedure_recommendation"))
    recommended = _coerce_bool(
        explicit.get("surgery_evaluation_recommended"),
        default=_coerce_bool(
            result.get("surgery_evaluation_recommended"),
            default=_coerce_bool(result.get("needs_surgery"), default=False),
        ),
    )
    urgency = str(explicit.get("urgency") or result.get("procedure_urgency") or "none").strip().lower() or "none"
    if urgency not in ROUND2_PROCEDURE_URGENCIES:
        urgency = "urgent" if recommended else "none"
    reason = str(explicit.get("reason") or result.get("procedure_reason") or "").strip()
    return {
        "surgery_evaluation_recommended": recommended,
        "urgency": urgency,
        "reason": reason,
    }


def _normalize_followup_recommendation(result: dict) -> dict:
    explicit = _as_dict(result.get("followup_recommendation"))
    disposition_advice = str(result.get("disposition_advice") or "").lower()
    patient_plan = str(result.get("patient_plan") or "").lower()
    observe_hint = any(token in f"{disposition_advice} {patient_plan}" for token in ("observe", "observation", "瑙傚療"))
    revisit_hint = any(token in f"{disposition_advice} {patient_plan}" for token in ("revisit", "return visit", "澶嶈瘖", "澶嶆煡"))
    observation_required = _coerce_bool(explicit.get("observation_required"), default=observe_hint)
    observation_setting = str(explicit.get("observation_setting") or ("outpatient_home" if observation_required else "none")).strip()
    if observation_setting not in {"outpatient_home", "none"}:
        observation_setting = "outpatient_home" if observation_required else "none"
    revisit_required = _coerce_bool(explicit.get("revisit_required"), default=revisit_hint or observation_required)
    revisit_window = str(explicit.get("revisit_window") or result.get("revisit_window") or "").strip()
    revisit_conditions = _normalize_string_list(explicit.get("revisit_conditions"), result.get("revisit_conditions"))
    return {
        "observation_required": observation_required,
        "observation_setting": observation_setting,
        "revisit_required": revisit_required,
        "revisit_window": revisit_window,
        "revisit_conditions": revisit_conditions,
    }


def _normalize_requires_new_registration(value: Any, *, primary_disposition: str) -> bool:
    if primary_disposition == "specialty_referral":
        return _coerce_bool(value, default=True)
    return _coerce_bool(value, default=False)


def _normalize_carry_forward_summary(
    value: Any,
    *,
    department: str,
    recommended_department: str,
    handoff_reason: str,
    final_assessment_summary: str,
    tests_suggested: list[str],
) -> dict:
    if isinstance(value, dict):
        normalized = dict(value)
    else:
        normalized = {}
    if not normalized and not recommended_department:
        return {}
    normalized.setdefault("origin_department", department or None)
    normalized.setdefault("target_department", recommended_department or None)
    normalized.setdefault("current_assessment", final_assessment_summary or None)
    normalized.setdefault("referral_reason", handoff_reason or None)
    normalized.setdefault("completed_workup", tests_suggested)
    normalized.setdefault("next_department_focus", handoff_reason or None)
    return normalized


def _normalize_string_list(value: Any, fallback: Any = None) -> list[str]:
    candidates = value if value not in (None, "") else fallback
    if candidates in (None, ""):
        return []
    if isinstance(candidates, str):
        parts = [candidates]
    elif isinstance(candidates, (list, tuple, set)):
        parts = list(candidates)
    else:
        parts = [candidates]
    normalized: list[str] = []
    for item in parts:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _as_dict(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default
