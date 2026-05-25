from __future__ import annotations

from copy import deepcopy


SPECIALTY_PRESETS = {
    "surgery": [
        {
            "preset_id": "surgery_laceration_case",
            "label": "Surgery - Laceration",
            "payload": {
                "patient_profile": {"name": "Gao Ning", "age": 29, "sex": "male"},
                "chief_complaint": "Hand cut with persistent bleeding",
                "symptoms": "hand cut, bleeding, pain after kitchen injury",
                "message": "The cut is on the palm and it kept bleeding for several minutes.",
            },
        },
        {
            "preset_id": "surgery_lump_case",
            "label": "Surgery - Lump",
            "payload": {
                "patient_profile": {"name": "Xu Lan", "age": 45, "sex": "female"},
                "chief_complaint": "New breast-adjacent lump",
                "symptoms": "localized lump, mild tenderness, no trauma",
                "message": "I noticed a small lump a week ago and it feels firmer now.",
            },
        },
    ],
    "pediatrics": [
        {
            "preset_id": "pediatrics_fever_cough_case",
            "label": "Pediatrics - Fever And Cough",
            "payload": {
                "patient_profile": {"name": "Little Chen", "age": 5, "sex": "male"},
                "chief_complaint": "Child fever and cough",
                "symptoms": "child fever, cough, reduced appetite",
                "message": "My child has had a fever since last night and coughs more when lying down.",
            },
        },
        {
            "preset_id": "pediatrics_diarrhea_case",
            "label": "Pediatrics - Diarrhea",
            "payload": {
                "patient_profile": {"name": "Little Sun", "age": 3, "sex": "female"},
                "chief_complaint": "Child diarrhea today",
                "symptoms": "diarrhea, vomiting twice, poor drinking",
                "message": "She vomited twice and has had loose stool three times today.",
            },
        },
    ],
    "ent": [
        {
            "preset_id": "ent_sore_throat_case",
            "label": "ENT - Sore Throat",
            "payload": {
                "patient_profile": {"name": "Li Yue", "age": 24, "sex": "female"},
                "chief_complaint": "Severe sore throat",
                "symptoms": "sore throat, swallowing pain, mild fever",
                "message": "My throat hurts badly when swallowing and speaking.",
            },
        },
        {
            "preset_id": "ent_ear_pain_case",
            "label": "ENT - Ear Pain",
            "payload": {
                "patient_profile": {"name": "Zhang Bo", "age": 37, "sex": "male"},
                "chief_complaint": "Right ear pain",
                "symptoms": "ear pain, ear blockage, reduced hearing",
                "message": "My right ear feels blocked and painful since yesterday.",
            },
        },
    ],
}


def get_specialty_presets(agent_type: str) -> list[dict]:
    return deepcopy(SPECIALTY_PRESETS[agent_type])


def list_specialty_agent_types() -> list[str]:
    return list(SPECIALTY_PRESETS.keys())
