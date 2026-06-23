from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.openemr.schemas import (
    OpenEMREncounterPayload,
    OpenEMRNotePayload,
    OpenEMRPatientPayload,
    OpenEMRTestReportPayload,
)
from app.reporting.test_report_card import TestReportCardService


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_patient_to_openemr(patient: dict) -> OpenEMRPatientPayload:
    return map_patient_to_openemr_with_context(patient, None)


def map_patient_to_openemr_with_context(
    patient: dict,
    source_payload: dict | None,
) -> OpenEMRPatientPayload:
    profile = _resolve_profile(source_payload or {})
    age = _safe_int(profile.get("age"))
    birth_date = _normalize_birth_date(profile.get("birth_date") or profile.get("dob"))
    sex = _normalize_sex(profile.get("sex") or profile.get("gender"))
    return OpenEMRPatientPayload(
        local_patient_id=patient["id"],
        name=patient.get("name") or patient["id"],
        external_patient_id=patient.get("openemr_patient_id"),
        age=age,
        sex=sex,
        birth_date=birth_date,
        identifier_system="urn:hos-sim:patient",
    )


def map_visit_to_encounter(visit: dict, patient: dict) -> OpenEMREncounterPayload:
    return OpenEMREncounterPayload(
        local_visit_id=visit["id"],
        local_patient_id=patient["id"],
        external_patient_id=patient.get("openemr_patient_id") or "",
        department=visit.get("current_department") or patient.get("location"),
        status=_map_visit_state_to_encounter_status(visit.get("state")),
        started_at=visit.get("created_at"),
        external_encounter_id=visit.get("openemr_encounter_id"),
        identifier_system="urn:hos-sim:visit",
    )


def map_triage_to_note(
    patient: dict,
    visit: dict,
    triage_session_or_data: dict | None,
) -> OpenEMRNotePayload:
    data = triage_session_or_data or {}
    triage_level = patient.get("triage_level")
    triage_note = patient.get("triage_note") or ""
    department = data.get("department") or visit.get("current_department") or patient.get("location") or "Unknown"
    priority = data.get("priority") or patient.get("priority") or "M"
    chief_complaint = data.get("chief_complaint") or _resolve_chief_complaint(data)
    risk_flags = _resolve_risk_flags(data)

    lines: list[str] = []
    if chief_complaint:
        lines.extend(["Chief Complaint", chief_complaint, ""])
    lines.extend(["Triage Summary"])
    if triage_level is not None:
        lines.append(f"Triage Level: {triage_level}")
    lines.extend(
        [
            f"Priority: {priority}",
            f"Recommended Department: {department}",
        ]
    )
    if triage_note:
        lines.extend(["", "Assessment", triage_note])
    if risk_flags:
        lines.extend(["", "Risk Flags"])
        lines.extend([f"- {item}" for item in risk_flags if item])

    return OpenEMRNotePayload(
        local_visit_id=visit["id"],
        local_patient_id=patient["id"],
        external_patient_id=patient.get("openemr_patient_id") or "",
        external_encounter_id=visit.get("openemr_encounter_id") or "",
        note_type="triage",
        title="Triage Clinical Summary",
        content="\n".join(lines),
        created_at=now_iso(),
    )


def map_internal_medicine_to_note(
    patient: dict,
    visit: dict,
    internal_session_or_data: dict | None,
) -> OpenEMRNotePayload:
    data = internal_session_or_data or {}
    final_result = data.get("final_result") if isinstance(data.get("final_result"), dict) else {}
    chief_complaint = data.get("chief_complaint") or _resolve_chief_complaint(data)
    tests_suggested = final_result.get("tests_suggested") or []
    medication_or_action = final_result.get("medication_or_action") or []
    red_flags = final_result.get("red_flags") or []

    lines = [
        "Chief Complaint",
        chief_complaint or "N/A",
        "",
        "Assessment",
        final_result.get("note") or "N/A",
        "",
        "Plan",
        final_result.get("patient_plan") or "N/A",
        "",
        "Priority",
        final_result.get("priority") or patient.get("priority") or "M",
        "",
        "Recommended Department",
        final_result.get("department") or visit.get("current_department") or "Consultation",
    ]
    if tests_suggested:
        lines.extend(["", "Tests Suggested"])
        lines.extend([f"- {item}" for item in tests_suggested])
    if medication_or_action:
        lines.extend(["", "Medication or Action"])
        lines.extend([f"- {item}" for item in medication_or_action])
    if red_flags:
        lines.extend(["", "Risk Flags"])
        lines.extend([f"- {item}" for item in red_flags])

    return OpenEMRNotePayload(
        local_visit_id=visit["id"],
        local_patient_id=patient["id"],
        external_patient_id=patient.get("openemr_patient_id") or "",
        external_encounter_id=visit.get("openemr_encounter_id") or "",
        note_type="internal_medicine",
        title="Internal Medicine Consultation Summary",
        content="\n".join(lines),
        created_at=now_iso(),
    )


def map_simulated_report_to_report(
    patient: dict,
    visit: dict,
    simulated_report: dict | None,
) -> OpenEMRTestReportPayload:
    report = TestReportCardService.normalize_report(simulated_report or {})
    report_title = report.get("report_title") or report.get("window_label") or report.get("category_label") or "辅助检查报告"
    report_text = report.get("display_text_cn") or report.get("report_text") or "暂无检查报告内容。"

    return OpenEMRTestReportPayload(
        local_visit_id=visit["id"],
        local_patient_id=patient["id"],
        external_patient_id=patient.get("openemr_patient_id") or "",
        external_encounter_id=visit.get("openemr_encounter_id") or "",
        category=report.get("category_code") or visit.get("current_department"),
        report_title=report_title,
        report_content=report_text,
        report_data=report,
        created_at=report.get("generated_at") or now_iso(),
    )


def _map_visit_state_to_encounter_status(visit_state: str | None) -> str:
    if visit_state in {"completed"}:
        return "finished"
    if visit_state in {"cancelled", "error"}:
        return "cancelled"
    return "in-progress"


def _resolve_chief_complaint(data: dict) -> str:
    shared_memory = data.get("shared_memory")
    if isinstance(shared_memory, dict):
        clinical = shared_memory.get("clinical_memory")
        if isinstance(clinical, dict):
            complaint = clinical.get("chief_complaint")
            if complaint:
                return str(complaint)
    return ""


def _resolve_risk_flags(data: dict) -> list[str]:
    flags = data.get("risk_flags")
    if isinstance(flags, list):
        return [str(item) for item in flags if item]
    shared_memory = data.get("shared_memory")
    if isinstance(shared_memory, dict):
        clinical = shared_memory.get("clinical_memory")
        if isinstance(clinical, dict):
            memory_flags = clinical.get("risk_flags")
            if isinstance(memory_flags, list):
                return [str(item) for item in memory_flags if item]
    return []


def _resolve_profile(source_payload: dict) -> dict:
    profile = source_payload.get("profile")
    if isinstance(profile, dict):
        return profile
    shared_memory = source_payload.get("shared_memory")
    if isinstance(shared_memory, dict):
        nested_profile = shared_memory.get("profile")
        if isinstance(nested_profile, dict):
            return nested_profile
    return {}


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_birth_date(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def _normalize_sex(value) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"m", "male", "man", "男"}:
        return "male"
    if normalized in {"f", "female", "woman", "女"}:
        return "female"
    if normalized in {"other", "x"}:
        return "other"
    if normalized in {"unknown", "u", "unk"}:
        return "unknown"
    return None
