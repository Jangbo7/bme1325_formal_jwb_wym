from __future__ import annotations

import json

from app.agents.patient_agent.schemas import PatientCaseCard, PatientPolicyDecision, PatientReplyContext


def build_generate_case_messages(*, constraints: str, seed: str | None = None) -> list[dict]:
    seed_text = f"Use this reproducibility hint if helpful: {seed}." if seed else ""
    schema_hint = {
        "case_id": "string",
        "patient_profile": {
            "name": "string",
            "age": 0,
            "sex": "male|female|unknown",
            "allergies": ["string"],
            "chronic_conditions": ["string"],
        },
        "chief_complaint": "string",
        "present_illness": "string",
        "symptom_facts": {
            "symptoms": ["string"],
            "onset_time": "string",
            "vitals": {"temp_c": 37.5, "heart_rate": 88, "pain_score": 3},
            "associated_symptoms": ["string"],
            "negatives": ["string"],
            "aggravating_factors": ["string"],
            "relieving_factors": ["string"],
        },
        "communication_style": "string",
        "hidden_diagnosis_hint": "string",
        "patient_goals": ["string"],
        "forbidden_reveals": ["string"],
    }
    return [
        {
            "role": "system",
            "content": (
                "You generate structured simulated outpatient patient cases. "
                "Return strict JSON only. No markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate one controlled outpatient patient case. "
                f"{constraints} "
                f"{seed_text} "
                "The patient should be common, mild-to-moderate, and suitable for a triage -> consultation -> test -> review loop. "
                "The hidden diagnosis hint must not be directly stated by the patient in normal dialogue. "
                "Return JSON matching this shape: "
                + json.dumps(schema_hint, ensure_ascii=False)
            ),
        },
    ]


def build_reply_messages(
    *,
    case_card: PatientCaseCard,
    context: PatientReplyContext,
    decision: PatientPolicyDecision,
    constraints: str,
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a controlled simulated patient in a hospital visit. "
                "Return strict JSON only with keys: message, used_facts, follow_up_question. "
                "The message must be from the patient perspective only. "
                "Do not diagnose yourself. "
                "Do not reveal hidden diagnosis labels unless they are ordinary patient wording already allowed by the case. "
                f"{constraints}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "case_card": case_card.model_dump(),
                    "reply_context": context.model_dump(),
                    "policy_decision": decision.model_dump(),
                    "instructions": [
                        "Answer the clinician's latest question directly and briefly.",
                        "Only use facts allowed by policy_decision.allowed_fact_keys.",
                        "If follow_up_question is not natural, return null.",
                        "Do not mention hidden_diagnosis_hint or forbidden_reveals literally.",
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]
