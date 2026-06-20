from __future__ import annotations

import re
from datetime import datetime, timezone

from app.departments.registry import resolve_department
from app.schemas.common import VisitLifecycleState


OUTPATIENT_FINISHED_VISIT_STATES = {
    VisitLifecycleState.IN_EMERGENCY.value,
    VisitLifecycleState.IN_ICU_RESCUE.value,
    VisitLifecycleState.DISPOSITION_REFERRAL.value,
    VisitLifecycleState.ADMITTED.value,
    VisitLifecycleState.TRANSFERRING.value,
    VisitLifecycleState.COMPLETED.value,
}

OUTPATIENT_STOPPED_VISIT_STATES = {
    VisitLifecycleState.CANCELLED.value,
    VisitLifecycleState.ERROR.value,
}

OUTPATIENT_SPECIAL_DISPOSITION_CATEGORIES = {
    "icu_rescue",
    "emergency_escalation",
    "inpatient_admission",
    "specialty_referral",
}

OUTPATIENT_ORDINARY_DISPOSITION_CATEGORIES = {
    "outpatient_treatment",
    "followup_booking",
}


def slugify_service_name(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return normalized or None


def department_identity(name: str | None) -> tuple[str | None, str | None]:
    text = str(name or "").strip()
    if not text:
        return None, None
    resolved = resolve_department(text, "M")
    resolved_id = str(resolved.get("id") or "").strip()
    resolved_label = str(resolved.get("label") or "").strip()
    if text.lower() not in {resolved_id.lower(), resolved_label.lower()} and resolved_id == "internal":
        return slugify_service_name(text), text
    return resolved_id or None, resolved_label or text


def is_outpatient_flow_finished(visit_state: str | None, visit_data: dict | None = None) -> bool:
    state = str(visit_state or "")
    payload = dict(visit_data or {})
    if state in OUTPATIENT_STOPPED_VISIT_STATES:
        return False
    if state in OUTPATIENT_FINISHED_VISIT_STATES:
        return True
    if bool(payload.get("outpatient_flow_finished")) and _finish_flag_matches_state(state, payload):
        return True
    return False


def should_stop_outpatient_automation(visit_state: str | None, visit_data: dict | None = None) -> bool:
    state = str(visit_state or "")
    if state in OUTPATIENT_STOPPED_VISIT_STATES:
        return True
    return is_outpatient_flow_finished(state, visit_data)


def visit_needs_pharmacy(visit_data: dict | None) -> bool:
    payload = dict(visit_data or {})
    explicit = payload.get("needs_pharmacy")
    if isinstance(explicit, bool):
        return explicit
    prescription_plan = payload.get("prescription_plan")
    prescriptions = payload.get("prescriptions")
    medication = dict(payload.get("medication_recommendation") or {})
    if _has_items(prescription_plan) or _has_items(prescriptions):
        return True
    return bool(medication.get("recommended"))


def is_special_outpatient_disposition(disposition: dict | None) -> bool:
    category = str((disposition or {}).get("category") or "").strip()
    return category in OUTPATIENT_SPECIAL_DISPOSITION_CATEGORIES


def is_ordinary_outpatient_disposition(disposition: dict | None) -> bool:
    category = str((disposition or {}).get("category") or "").strip()
    return category in OUTPATIENT_ORDINARY_DISPOSITION_CATEGORIES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_triage_disposition(triage_result: dict, route_hint: dict) -> dict:
    event = str(route_hint.get("event") or "").strip()
    if event == "route_to_icu_rescue":
        return {
            "category": "icu_rescue",
            "target_service": "icu",
            "target_department": "ICU",
            "urgency": "urgent",
            "reason": f"triage level {triage_result.get('triage_level')} requires ICU rescue routing",
            "source_phase": "triage",
            "handoff_status": "planned",
        }
    return {
        "category": "emergency_escalation",
        "target_service": "emergency",
        "target_department": "Emergency",
        "urgency": "urgent",
        "reason": f"triage level {triage_result.get('triage_level')} requires emergency routing",
        "source_phase": "triage",
        "handoff_status": "planned",
    }


def build_consultation_disposition(
    consultation_result: dict,
    *,
    source_phase: str = "doctor_round2",
) -> dict:
    primary_disposition = str(consultation_result.get("primary_disposition") or "").strip() or "outpatient_management"
    department = str(consultation_result.get("department") or "").strip()
    recommended_department = str(consultation_result.get("recommended_department") or "").strip()
    recommended_department_reason = str(consultation_result.get("recommended_department_reason") or "").strip()
    disposition_advice = str(consultation_result.get("disposition_advice") or "").strip()
    handoff_reason = str(consultation_result.get("handoff_reason") or "").strip()
    followup = dict(consultation_result.get("followup_recommendation") or {})
    admission = dict(consultation_result.get("admission_recommendation") or {})
    procedure = dict(consultation_result.get("procedure_recommendation") or {})
    carry_forward_summary = dict(consultation_result.get("carry_forward_summary") or {})
    requires_new_registration = bool(consultation_result.get("requires_new_registration", False))

    if primary_disposition == "icu_escalation" or bool(consultation_result.get("icu_escalation")):
        return {
            "category": "icu_rescue",
            "target_service": "icu",
            "target_department": "ICU",
            "urgency": "urgent",
            "reason": handoff_reason or disposition_advice or "consultation result requires ICU rescue",
            "source_phase": source_phase,
            "handoff_status": "planned",
        }
    if primary_disposition == "emergency_escalation":
        return {
            "category": "emergency_escalation",
            "target_service": "emergency",
            "target_department": "Emergency",
            "urgency": "urgent",
            "reason": handoff_reason or disposition_advice or "consultation result requires emergency escalation",
            "source_phase": source_phase,
            "handoff_status": "planned",
        }
    if primary_disposition == "inpatient_admission_recommended" or bool(admission.get("recommended")):
        target_department = department or recommended_department or "Inpatient"
        target_service = slugify_service_name(target_department) or "inpatient"
        urgency = str(procedure.get("urgency") or "").strip().lower() or "expedited"
        if urgency == "none":
            urgency = "expedited"
        return {
            "category": "inpatient_admission",
            "target_service": target_service,
            "target_department": target_department,
            "urgency": urgency,
            "reason": str(admission.get("reason") or procedure.get("reason") or handoff_reason or disposition_advice or "consultation recommends inpatient admission"),
            "source_phase": source_phase,
            "handoff_status": "planned",
        }
    if primary_disposition == "specialty_referral" or recommended_department:
        target_department = recommended_department or department
        target_department_id, target_department_name = department_identity(target_department)
        origin_department_id, origin_department_name = department_identity(department)
        referral_priority = str(consultation_result.get("referral_priority") or procedure.get("urgency") or "routine").strip().lower() or "routine"
        if referral_priority == "none":
            referral_priority = "routine"
        if referral_priority == "expedited":
            referral_priority = "urgent"
        return {
            "category": "specialty_referral",
            "target_service": slugify_service_name(target_department) or "referral",
            "target_department": target_department_name or target_department or None,
            "target_department_id": target_department_id,
            "urgency": referral_priority,
            "reason": handoff_reason or recommended_department_reason or disposition_advice or "consultation recommends specialty referral",
            "source_phase": source_phase,
            "handoff_status": "planned",
            "requires_new_registration": requires_new_registration or True,
            "referral_reason": recommended_department_reason or handoff_reason or disposition_advice or "specialty follow-up is recommended",
            "referral_priority": referral_priority,
            "referral_origin_department": origin_department_name or department or None,
            "referral_origin_department_id": origin_department_id,
            "carry_forward_summary": carry_forward_summary,
        }
    if primary_disposition == "observe_then_revisit":
        return {
            "category": "followup_booking",
            "target_service": slugify_service_name(department) or "followup",
            "target_department": department or None,
            "urgency": "routine",
            "reason": disposition_advice or _followup_reason(followup) or "consultation recommends follow-up",
            "source_phase": source_phase,
            "handoff_status": "none",
        }
    return {
        "category": "outpatient_treatment",
        "target_service": slugify_service_name(department) or "outpatient",
        "target_department": department or None,
        "urgency": "routine",
        "reason": disposition_advice or "continue outpatient treatment",
        "source_phase": source_phase,
        "handoff_status": "none",
    }


def disposition_event_for_payload(disposition: dict) -> str:
    category = str(disposition.get("category") or "").strip()
    if category == "icu_rescue":
        return "route_to_icu_rescue"
    if category == "emergency_escalation":
        return "route_to_emergency"
    if category == "inpatient_admission":
        return "admit_patient"
    if category == "specialty_referral":
        return "choose_referral"
    return "choose_outpatient_treatment"


def disposition_transition_context(disposition: dict) -> dict[str, str | None]:
    category = str(disposition.get("category") or "").strip()
    target_department = str(disposition.get("target_department") or "").strip() or None
    if category == "icu_rescue":
        return {
            "event": "route_to_icu_rescue",
            "current_node": "icu_transfer",
            "current_department": "ICU",
        }
    if category == "emergency_escalation":
        return {
            "event": "route_to_emergency",
            "current_node": "emergency_transfer",
            "current_department": "Emergency",
        }
    if category == "inpatient_admission":
        return {
            "event": "admit_patient",
            "current_node": "admission",
            "current_department": target_department or "Admission",
        }
    if category == "specialty_referral":
        return {
            "event": "choose_referral",
            "current_node": "referral",
            "current_department": target_department or "Disposition",
        }
    if category == "followup_booking":
        return {
            "event": "choose_followup_booking",
            "current_node": "followup_booking",
            "current_department": "Disposition",
        }
    return {
        "event": "choose_outpatient_treatment",
        "current_node": "outpatient_disposition",
        "current_department": "Disposition",
    }


def _followup_reason(followup: dict) -> str:
    window = str(followup.get("revisit_window") or "").strip()
    if window:
        return f"follow-up recommended within {window}"
    return "follow-up is recommended"


def finalize_disposition_transition_context(
    disposition: dict,
    *,
    needs_pharmacy: bool,
) -> dict[str, str | None]:
    if is_special_outpatient_disposition(disposition):
        return disposition_transition_context(disposition)
    if needs_pharmacy:
        return {
            "event": "choose_pharmacy",
            "current_node": "pharmacy_wait",
            "current_department": "Pharmacy",
        }
    return disposition_transition_context(disposition)


def apply_outpatient_completion_metadata(
    visit_data: dict | None,
    *,
    visit_state: str | None,
    at: str | None = None,
) -> dict:
    payload = dict(visit_data or {})
    if is_outpatient_flow_finished(visit_state, payload):
        payload["outpatient_flow_finished"] = True
        payload["outpatient_finished_at"] = payload.get("outpatient_finished_at") or at or now_iso()
        return payload
    payload["outpatient_flow_finished"] = False
    payload.pop("outpatient_finished_at", None)
    return payload


def _finish_flag_matches_state(visit_state: str, visit_data: dict) -> bool:
    if visit_state == VisitLifecycleState.TRANSFERRING.value:
        return is_special_outpatient_disposition(visit_data.get("disposition"))
    return visit_state in OUTPATIENT_FINISHED_VISIT_STATES


def _has_items(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(bool(item) for item in value)
    return False
