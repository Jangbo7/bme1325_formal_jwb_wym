from app.integrations.openemr.mapper import (
    map_internal_medicine_to_note,
    map_patient_to_openemr,
    map_patient_to_openemr_with_context,
    map_simulated_report_to_report,
    map_triage_to_note,
    map_visit_to_encounter,
)


def test_map_patient_to_openemr_payload():
    payload = map_patient_to_openemr(
        {
            "id": "P-self",
            "name": "Player",
            "openemr_patient_id": "ext-p-1",
        }
    )
    assert payload.local_patient_id == "P-self"
    assert payload.name == "Player"
    assert payload.external_patient_id == "ext-p-1"


def test_map_patient_to_openemr_with_triage_profile_context():
    payload = map_patient_to_openemr_with_context(
        {
            "id": "P-self",
            "name": "Player",
            "openemr_patient_id": "ext-p-1",
        },
        {
            "shared_memory": {
                "profile": {
                    "age": 35,
                    "sex": "M",
                    "birth_date": "1990-01-02T00:00:00+08:00",
                }
            }
        },
    )
    assert payload.age == 35
    assert payload.sex == "male"
    assert payload.birth_date == "1990-01-02"


def test_map_visit_to_encounter_payload():
    payload = map_visit_to_encounter(
        {
            "id": "visit-1",
            "state": "in_consultation",
            "current_department": "Consultation",
            "created_at": "2026-01-01T00:00:00+00:00",
            "openemr_encounter_id": None,
        },
        {
            "id": "P-self",
            "openemr_patient_id": "ext-p-1",
        },
    )
    assert payload.local_visit_id == "visit-1"
    assert payload.external_patient_id == "ext-p-1"
    assert payload.department == "Consultation"


def test_map_note_and_report_payloads_are_readable():
    patient = {
        "id": "P-self",
        "priority": "M",
        "triage_level": 3,
        "triage_note": "Possible flu symptoms.",
        "openemr_patient_id": "ext-p-1",
    }
    visit = {
        "id": "visit-1",
        "current_department": "Internal Medicine",
        "openemr_encounter_id": "enc-1",
    }
    triage_note = map_triage_to_note(
        patient,
        visit,
        {
            "chief_complaint": "Fever and cough",
            "department": "Internal Medicine",
            "priority": "M",
            "risk_flags": ["persistent fever"],
        },
    )
    assert triage_note.note_type == "triage"
    assert "Chief Complaint" in triage_note.content

    internal_note = map_internal_medicine_to_note(
        patient,
        visit,
        {
            "chief_complaint": "Fever and cough",
            "final_result": {
                "department": "Internal Medicine",
                "priority": "M",
                "note": "Upper respiratory tract infection likely.",
                "patient_plan": "Hydration and rest.",
                "tests_suggested": ["CBC"],
                "medication_or_action": ["Paracetamol"],
                "red_flags": ["dyspnea"],
            },
        },
    )
    assert internal_note.note_type == "internal_medicine"
    assert "Plan" in internal_note.content

    report = map_simulated_report_to_report(
        patient,
        visit,
        {
            "category_code": "medical_laboratory",
            "window_label": "Lab Window",
            "report_text": "CBC completed.",
            "report_summary": {
                "findings": ["WBC mildly elevated"],
                "advice": "Follow up if symptoms worsen.",
            },
        },
    )
    assert report.category == "medical_laboratory"
    assert "Findings" in report.report_content
