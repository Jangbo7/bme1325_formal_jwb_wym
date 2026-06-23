from __future__ import annotations

from app.reporting.test_report_card import TestReportCardService


def _compact_entry(entry: dict) -> dict:
    content = dict(entry.get("content") or {})
    return {
        "created_at": entry.get("created_at"),
        "phase": entry.get("phase"),
        "entry_type": entry.get("entry_type"),
        "title": entry.get("title"),
        "content_text": entry.get("content_text"),
        "clinical_summary": {
            "department": content.get("department"),
            "clinical_impression": content.get("clinical_impression"),
            "final_assessment_summary": content.get("final_assessment_summary"),
            "primary_disposition": content.get("primary_disposition"),
            "recommended_department": content.get("recommended_department"),
            "handoff_reason": content.get("handoff_reason"),
            "report_summary": content.get("report_summary"),
        },
    }


def _compact_timeline(timeline: dict | None, *, entry_limit: int = 6) -> dict | None:
    if not timeline:
        return None
    entries = list(timeline.get("entries") or [])
    return {
        "summary": dict(timeline.get("summary") or {}),
        "entries": [_compact_entry(entry) for entry in entries[-entry_limit:]],
    }


def _build_handoff_summary(visit_data: dict) -> dict | None:
    disposition = dict(visit_data.get("disposition") or {})
    category = str(disposition.get("category") or "").strip()
    recommended_department = str(
        visit_data.get("recommended_department")
        or disposition.get("target_department")
        or ""
    ).strip()
    if category != "specialty_referral" and not recommended_department:
        return None
    return {
        "special_event_type": "specialty_referral",
        "recommended_department": recommended_department or None,
        "recommended_department_id": disposition.get("target_department_id"),
        "recommended_department_reason": visit_data.get("recommended_department_reason"),
        "handoff_reason": visit_data.get("handoff_reason") or disposition.get("reason"),
        "requires_new_registration": bool(visit_data.get("requires_new_registration", False)),
        "carry_forward_summary": dict(visit_data.get("carry_forward_summary") or {}),
        "origin_department": disposition.get("referral_origin_department"),
    }


def build_doctor_chart_view(
    *,
    medical_record_repo,
    patient_id: str,
    visit_id: str,
    visit_data: dict | None = None,
    previous_visit_limit: int = 2,
) -> dict:
    visit_payload = dict(visit_data or {})
    current_visit = None
    previous_visits: list[dict] = []

    if medical_record_repo is not None and visit_id:
        current_visit = _compact_timeline(medical_record_repo.get_visit_timeline(visit_id))
        for previous_visit_id in medical_record_repo.list_recent_visit_ids_by_patient(
            patient_id,
            exclude_visit_id=visit_id,
            limit=previous_visit_limit,
        ):
            timeline = _compact_timeline(medical_record_repo.get_visit_timeline(previous_visit_id))
            if timeline:
                previous_visits.append(timeline)

    report = TestReportCardService.normalize_report(visit_payload.get("simulated_report") or {})
    report_summary = dict(report.get("report_summary") or {})
    report_view = None
    if report or report_summary:
        report_view = {
            "report_text": report.get("report_text"),
            "display_text_cn": report.get("display_text_cn"),
            "report_summary": report_summary,
            "test_items": list(report.get("test_items") or []),
            "report_items": list(report.get("report_items") or []),
            "key_findings_cn": list(report.get("key_findings_cn") or []),
            "preliminary_assessment": dict(report.get("preliminary_assessment") or {}),
            "generated_at": report.get("generated_at"),
        }

    return {
        "current_visit": current_visit,
        "previous_visits": previous_visits,
        "handoff": _build_handoff_summary(visit_payload),
        "report": report_view,
    }
