from __future__ import annotations

from copy import deepcopy

from app.schemas.common import PatientLifecycleState, VisitLifecycleState


def _base_shared_memory(name: str, age: int, sex: str, *, chief_complaint: str, symptoms: list[str], onset_time: str, vitals: dict, allergies: list[str] | None = None, chronic_conditions: list[str] | None = None) -> dict:
    return {
        "profile": {
            "name": name,
            "age": age,
            "sex": sex,
            "allergies": list(allergies or []),
            "allergy_status": "known" if allergies is not None else "unknown",
            "chronic_conditions": list(chronic_conditions or []),
            "baseline_risk_flags": [],
        },
        "clinical_memory": {
            "chief_complaint": chief_complaint,
            "symptoms": list(symptoms),
            "onset_time": onset_time,
            "vitals": dict(vitals),
            "risk_flags": [],
            "last_department": None,
            "last_triage_level": None,
        },
    }


TRIAGE_PRESETS = [
    {
        "preset_id": "triage_respiratory_mild",
        "label": "Mild Respiratory",
        "payload": {
            "patient_profile": {"name": "Lin Mei", "age": 26, "sex": "female", "allergies": [], "chronic_conditions": []},
            "chief_complaint": "Cough and sore throat for 2 days",
            "symptoms": "cough, sore throat, low fever",
            "onset_time": "2 days ago",
            "vitals": {"temp_c": 37.7, "heart_rate": 88},
            "shared_memory": _base_shared_memory(
                "Lin Mei", 26, "female",
                chief_complaint="Cough and sore throat for 2 days",
                symptoms=["cough", "sore throat", "low fever"],
                onset_time="2 days ago",
                vitals={"temp_c": 37.7, "heart_rate": 88},
            ),
        },
    },
    {
        "preset_id": "triage_abdominal_pain",
        "label": "Abdominal Pain",
        "payload": {
            "patient_profile": {"name": "Zhao Peng", "age": 41, "sex": "male", "allergies": ["penicillin"], "chronic_conditions": []},
            "chief_complaint": "Upper abdominal pain since last night",
            "symptoms": "upper abdominal pain, nausea",
            "onset_time": "last night",
            "vitals": {"pain_score": 5, "heart_rate": 92},
            "shared_memory": _base_shared_memory(
                "Zhao Peng", 41, "male",
                chief_complaint="Upper abdominal pain since last night",
                symptoms=["upper abdominal pain", "nausea"],
                onset_time="last night",
                vitals={"pain_score": 5, "heart_rate": 92},
                allergies=["penicillin"],
            ),
        },
    },
    {
        "preset_id": "triage_headache",
        "label": "Low-risk Headache",
        "payload": {
            "patient_profile": {"name": "He Qian", "age": 31, "sex": "female", "allergies": [], "chronic_conditions": ["migraine"]},
            "chief_complaint": "Headache after poor sleep",
            "symptoms": "headache, fatigue",
            "onset_time": "this morning",
            "vitals": {"pain_score": 4},
            "shared_memory": _base_shared_memory(
                "He Qian", 31, "female",
                chief_complaint="Headache after poor sleep",
                symptoms=["headache", "fatigue"],
                onset_time="this morning",
                vitals={"pain_score": 4},
                chronic_conditions=["migraine"],
            ),
        },
    },
]


INTERNAL_MEDICINE_PRESETS = [
    {
        "preset_id": "im_round1_respiratory",
        "label": "Round1 Respiratory",
        "payload": {
            "patient_profile": {"name": "Lin Mei", "age": 26, "sex": "female", "allergies": [], "chronic_conditions": []},
            "visit_state": VisitLifecycleState.IN_CONSULTATION.value,
            "patient_lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
            "consultation_round": 1,
            "chief_complaint": "Cough and sore throat for 2 days",
            "symptoms": "cough, sore throat, low fever",
            "onset_time": "2 days ago",
            "vitals": {"temp_c": 37.7, "heart_rate": 88},
            "shared_memory": _base_shared_memory(
                "Lin Mei", 26, "female",
                chief_complaint="Cough and sore throat for 2 days",
                symptoms=["cough", "sore throat", "low fever"],
                onset_time="2 days ago",
                vitals={"temp_c": 37.7, "heart_rate": 88},
            ),
            "medical_record_entries": [
                {
                    "phase": "triage",
                    "entry_type": "triage_note",
                    "actor": "triage_agent",
                    "title": "Triage Summary",
                    "content_text": "mild respiratory symptoms, low urgency",
                    "content": {"priority": "M", "department": "Internal Medicine"},
                }
            ],
        },
    },
    {
        "preset_id": "im_round2_with_report",
        "label": "Round2 With Report",
        "payload": {
            "patient_profile": {"name": "Robert Chen", "age": 42, "sex": "male", "allergies": [], "chronic_conditions": []},
            "visit_state": VisitLifecycleState.IN_SECOND_CONSULTATION.value,
            "patient_lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
            "consultation_round": 2,
            "chief_complaint": "Burning upper abdominal pain",
            "symptoms": "epigastric burning pain, nocturnal discomfort",
            "onset_time": "5 days ago",
            "vitals": {"pain_score": 4},
            "shared_memory": _base_shared_memory(
                "Robert Chen", 42, "male",
                chief_complaint="Burning upper abdominal pain",
                symptoms=["epigastric burning pain", "nocturnal discomfort"],
                onset_time="5 days ago",
                vitals={"pain_score": 4},
            ),
            "simulated_report": {
                "category_code": "medical_laboratory",
                "window_label": "Lab Window 2",
                "report_summary": {"cbc": "normal", "h_pylori": "positive"},
                "test_items": ["CBC", "H. pylori breath test"],
            },
            "medical_record_entries": [
                {
                    "phase": "internal_medicine_round1",
                    "entry_type": "initial_consult_note",
                    "actor": "internal_medicine_agent",
                    "title": "Initial Internal Medicine Assessment",
                    "content_text": "suspected gastritis, ordered simple tests",
                    "content": {"impression": "possible gastritis", "test_required": True},
                },
                {
                    "phase": "testing",
                    "entry_type": "test_result_note",
                    "actor": "system",
                    "title": "Auxiliary Test Report",
                    "content_text": "H. pylori positive, CBC normal",
                    "content": {"report_summary": {"cbc": "normal", "h_pylori": "positive"}},
                },
            ],
        },
    },
    {
        "preset_id": "im_chronic_followup",
        "label": "Chronic Follow-up",
        "payload": {
            "patient_profile": {"name": "Liu Fang", "age": 56, "sex": "female", "allergies": ["sulfa"], "chronic_conditions": ["hypertension"]},
            "visit_state": VisitLifecycleState.IN_CONSULTATION.value,
            "patient_lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
            "consultation_round": 1,
            "chief_complaint": "Dizziness and fatigue",
            "symptoms": "dizziness, fatigue, poor sleep",
            "onset_time": "3 days ago",
            "vitals": {"heart_rate": 84, "blood_pressure": "146/92"},
            "shared_memory": _base_shared_memory(
                "Liu Fang", 56, "female",
                chief_complaint="Dizziness and fatigue",
                symptoms=["dizziness", "fatigue", "poor sleep"],
                onset_time="3 days ago",
                vitals={"heart_rate": 84, "blood_pressure": "146/92"},
                allergies=["sulfa"],
                chronic_conditions=["hypertension"],
            ),
            "medical_record_entries": [
                {
                    "phase": "history",
                    "entry_type": "outpatient_history_note",
                    "actor": "system",
                    "title": "Previous Visit",
                    "content_text": "hypertension follow-up, sleep hygiene advised",
                    "content": {"bp_control": "suboptimal"},
                }
            ],
        },
    },
]


SURGERY_PRESETS = [
    {
        "preset_id": "surgery_minor_wound",
        "label": "Minor Surface Wound",
        "payload": {
            "patient_profile": {"name": "Chen Yu", "age": 29, "sex": "male", "allergies": [], "chronic_conditions": []},
            "visit_state": VisitLifecycleState.IN_CONSULTATION.value,
            "patient_lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
            "consultation_round": 1,
            "chief_complaint": "Small superficial cut on the forearm after kitchen work",
            "symptoms": "small cut, mild pain, bleeding stopped, no numbness, no movement problem",
            "onset_time": "2 hours ago",
            "vitals": {"pain_score": 2, "heart_rate": 82},
            "shared_memory": _base_shared_memory(
                "Chen Yu", 29, "male",
                chief_complaint="Small superficial cut on the forearm after kitchen work",
                symptoms=["small cut", "mild pain", "bleeding stopped", "no numbness", "no movement problem"],
                onset_time="2 hours ago",
                vitals={"pain_score": 2, "heart_rate": 82},
            ),
            "medical_record_entries": [
                {
                    "phase": "triage",
                    "entry_type": "triage_note",
                    "actor": "triage_agent",
                    "title": "Triage Summary",
                    "content_text": "minor wound, stable condition",
                    "content": {"priority": "L", "department": "Surgery"},
                }
            ],
        },
    },
    {
        "preset_id": "surgery_postop_wound_check",
        "label": "Stable Post-op Wound Check",
        "payload": {
            "patient_profile": {"name": "Wang Li", "age": 47, "sex": "female", "allergies": ["penicillin"], "chronic_conditions": ["type 2 diabetes"]},
            "visit_state": VisitLifecycleState.IN_CONSULTATION.value,
            "patient_lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
            "consultation_round": 1,
            "chief_complaint": "Routine dressing change after surgery",
            "symptoms": "postoperative dressing change, mild soreness, no fever, no pus, no drainage",
            "onset_time": "3 days after surgery",
            "vitals": {"temp_c": 36.9, "heart_rate": 86, "pain_score": 3},
            "shared_memory": _base_shared_memory(
                "Wang Li", 47, "female",
                chief_complaint="Routine dressing change after surgery",
                symptoms=["postoperative dressing change", "mild soreness", "no fever", "no pus", "no drainage"],
                onset_time="3 days after surgery",
                vitals={"temp_c": 36.9, "heart_rate": 86, "pain_score": 3},
                allergies=["penicillin"],
                chronic_conditions=["type 2 diabetes"],
            ),
        },
    },
]


PATIENT_AGENT_PRESETS = [
    {
        "preset_id": "patient_respiratory_case",
        "label": "Respiratory Patient",
        "payload": {
            "phase": "triage",
            "patient_profile": {"name": "Lin Mei", "age": 26, "sex": "female"},
            "case_card": {
                "case_id": "PAC-PRESET-001",
                "patient_profile": {"name": "Lin Mei", "age": 26, "sex": "female", "allergies": [], "chronic_conditions": []},
                "chief_complaint": "Cough and sore throat for 2 days",
                "present_illness": "Dry cough started 2 days ago with sore throat and mild low fever.",
                "symptom_facts": {
                    "symptoms": ["cough", "sore throat", "low fever"],
                    "onset_time": "2 days ago",
                    "vitals": {"temp_c": 37.7, "heart_rate": 88},
                    "associated_symptoms": ["nasal congestion"],
                    "negatives": ["no chest pain", "no shortness of breath"],
                    "aggravating_factors": ["talking a lot"],
                    "relieving_factors": ["warm water"],
                },
                "communication_style": "calm and cooperative",
                "hidden_diagnosis_hint": "Likely mild upper respiratory infection",
                "patient_goals": ["Relieve symptoms", "Know whether medicine is needed"],
                "forbidden_reveals": ["upper respiratory infection"],
            },
            "recent_turns": [],
            "medical_record_excerpt": [],
            "known_test_results": [],
        },
    },
    {
        "preset_id": "patient_gastritis_round2",
        "label": "Gastritis Review Patient",
        "payload": {
            "phase": "internal_medicine_round2",
            "patient_profile": {"name": "Robert Chen", "age": 42, "sex": "male"},
            "case_card": {
                "case_id": "PAC-PRESET-002",
                "patient_profile": {"name": "Robert Chen", "age": 42, "sex": "male", "allergies": [], "chronic_conditions": []},
                "chief_complaint": "Burning pain in upper abdomen for 5 days",
                "present_illness": "Burning upper abdominal discomfort for 5 days, worse after skipping meals, some nighttime discomfort.",
                "symptom_facts": {
                    "symptoms": ["epigastric burning pain", "nocturnal discomfort", "postprandial relief"],
                    "onset_time": "5 days ago",
                    "vitals": {"pain_score": 4},
                    "associated_symptoms": ["mild nausea"],
                    "negatives": ["no vomiting blood", "no black stool"],
                    "aggravating_factors": ["skipping meals", "coffee"],
                    "relieving_factors": ["eating", "antacid"],
                },
                "communication_style": "slightly anxious but concise",
                "hidden_diagnosis_hint": "Likely gastritis associated with coffee and irregular meals",
                "patient_goals": ["Understand test results", "Get effective treatment"],
                "forbidden_reveals": ["gastritis"],
            },
            "recent_turns": [
                {"role": "assistant", "content": "The test report is back. How are you feeling now?", "timestamp": "2026-05-21T10:00:00+00:00", "metadata": {}}
            ],
            "medical_record_excerpt": [
                {"entry_type": "initial_consult_note", "content_text": "possible gastritis, ordered testing"},
                {"entry_type": "test_result_note", "content_text": "H. pylori positive, CBC normal"},
            ],
            "known_test_results": [
                {"entry_type": "test_result_note", "content": {"report_summary": {"cbc": "normal", "h_pylori": "positive"}}}
            ],
        },
    },
    {
        "preset_id": "patient_headache_case",
        "label": "Headache Patient",
        "payload": {
            "phase": "internal_medicine_round1",
            "patient_profile": {"name": "He Qian", "age": 31, "sex": "female"},
            "case_card": {
                "case_id": "PAC-PRESET-003",
                "patient_profile": {"name": "He Qian", "age": 31, "sex": "female", "allergies": [], "chronic_conditions": ["migraine"]},
                "chief_complaint": "Headache after poor sleep",
                "present_illness": "Headache developed after several nights of poor sleep while working late.",
                "symptom_facts": {
                    "symptoms": ["headache", "fatigue"],
                    "onset_time": "this morning",
                    "vitals": {"pain_score": 4},
                    "associated_symptoms": ["light sensitivity"],
                    "negatives": ["no limb weakness", "no fainting"],
                    "aggravating_factors": ["screen time"],
                    "relieving_factors": ["rest"],
                },
                "communication_style": "reserved and only answers what is asked",
                "hidden_diagnosis_hint": "Likely tension headache or migraine flare",
                "patient_goals": ["Know if it is serious", "Get symptom relief"],
                "forbidden_reveals": ["migraine flare"],
            },
            "recent_turns": [],
            "medical_record_excerpt": [],
            "known_test_results": [],
        },
    },
]


def get_triage_presets() -> list[dict]:
    return deepcopy(TRIAGE_PRESETS)


def get_internal_medicine_presets() -> list[dict]:
    return deepcopy(INTERNAL_MEDICINE_PRESETS)


def get_surgery_presets() -> list[dict]:
    return deepcopy(SURGERY_PRESETS)


def get_patient_agent_presets() -> list[dict]:
    return deepcopy(PATIENT_AGENT_PRESETS)
