from __future__ import annotations

import json

from app.departments.registry import resolve_department
from app.agents.patient_agent.schemas import PatientCaseCard, PatientPolicyDecision, PatientRareEventProfile, PatientReplyContext


def _department_hint_text(department_id: str | None) -> str:
    normalized = str(department_id or "").strip()
    if not normalized:
        return ""
    resolved = resolve_department(normalized, "M")
    style_id = resolved["id"]
    if style_id == "surgery":
        style_guidance = (
            "Prefer a surgery-style outpatient branch with a complaint that triage could reasonably route to surgery, "
            "such as localized pain, superficial injury, minor trauma, wound issue, lump, or post-procedure review. "
            "Do not generate a plain cough/fever/general-medical case under a surgery hint."
        )
    elif style_id == "internal":
        style_guidance = (
            "Prefer an internal-medicine-style outpatient branch with a complaint that triage could reasonably route to internal medicine, "
            "such as respiratory symptoms, dizziness, headache, fatigue, gastrointestinal upset, or chronic-disease follow-up. "
            "Do not generate a wound/trauma/procedure-first surgical case under an internal hint."
        )
    else:
        style_guidance = "Prefer a case whose complaint pattern is clearly consistent with the hinted department."
    return (
        "Use this as a soft department hint only: "
        f"{resolved['label']} ({resolved['id']}). "
        f"{style_guidance} "
        "Bias the chief complaint, symptom mix, and present illness toward cases commonly seen there, "
        "but do not treat this hint as the final routing result. "
        "The case must still be a general outpatient triageable case that could be routed elsewhere after triage."
    )


def _rare_event_generation_text(profile: PatientRareEventProfile | None) -> str:
    if profile is None or not (profile.patient_special_event_enabled or profile.report_special_signal_enabled):
        return (
            "Default to a common outpatient case with no rare-event override. "
            "Keep the case suitable for the routine triage -> consultation -> test -> review loop."
        )

    event_type = profile.event_type or "none"
    patient_event_type = profile.patient_special_event_type or "none"
    report_event_type = profile.report_special_signal_type or "none"
    intensity = profile.special_event_intensity or "subtle"
    reveal_phase = profile.special_event_reveal_phase or "round2"
    target_department = str(profile.target_department or "").strip()
    target_reason = str(profile.target_department_reason or "").strip()
    patient_signal_instruction = str(profile.patient_signal_instruction or "").strip()
    report_signal_instruction = str(profile.report_signal_instruction or "").strip()
    report_escalation_target = str(profile.report_escalation_target or "").strip()
    report_escalation_reason = str(profile.report_escalation_reason or "").strip()
    event_specific_guidance = {
        "emergency_escalation": (
            "Build a case that still looks outpatient at the start, but has a believable worsening clue or red flag "
            "that can support later emergency escalation."
        ),
        "icu_escalation": (
            "Build a case that starts as a plausible outpatient presentation, but can later support severe instability, "
            "major bleeding, sepsis risk, or another ICU-level concern after more history or report review."
        ),
        "specialty_referral": (
            "Build a case whose later detail or test review can make another specialty more appropriate after the current department finishes its loop. "
            "Do not make it an obvious wrong-department case at the first line."
        ),
    }.get(
        event_type,
        "Keep the rare-event signal clinically plausible and compatible with the outpatient flow.",
    )
    return (
        "Rare-event profile is enabled. "
        f"Primary event type: {event_type}. "
        f"Patient-layer event: {patient_event_type}. "
        f"Report-layer signal: {report_event_type}. "
        f"Expected intensity: {intensity}. "
        f"Expected reveal phase: {reveal_phase}. "
        f"{event_specific_guidance} "
        f"{f'Target receiving specialty after loop closure: {target_department}. ' if target_department else ''}"
        f"{f'Target referral reason: {target_reason}. ' if target_reason else ''}"
        f"{f'Patient-layer clue guidance: {patient_signal_instruction}. ' if patient_signal_instruction else ''}"
        f"{f'Report-layer clue guidance: {report_signal_instruction}. ' if report_signal_instruction else ''}"
        f"{f'Expected report escalation target: {report_escalation_target}. ' if report_escalation_target else ''}"
        f"{f'Expected report escalation reason: {report_escalation_reason}. ' if report_escalation_reason else ''}"
        "Do not place the full special-event clue directly into the chief complaint when the reveal phase is later than intake. "
        "Keep the initial complaint and initial symptom list routine enough for outpatient entry, and reserve the stronger clue for later dialogue or report interpretation."
    )


def build_generate_case_messages(
    *,
    constraints: str,
    seed: str | None = None,
    department_id: str | None = None,
    rare_event_profile: PatientRareEventProfile | None = None,
    retry_feedback: str | None = None,
) -> list[dict]:
    seed_text = f"Use this reproducibility hint if helpful: {seed}." if seed else ""
    department_hint = _department_hint_text(department_id)
    rare_event_text = _rare_event_generation_text(rare_event_profile)
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
                f"{department_hint} "
                f"{rare_event_text} "
                f"{f'Correction for the previous attempt: {retry_feedback}. ' if retry_feedback else ''}"
                "The patient should be common, mild-to-moderate at presentation, and suitable for a triage -> consultation -> test -> review loop. "
                "The hidden diagnosis hint must not be directly stated by the patient in normal dialogue. "
                "Return JSON matching this shape: "
                + json.dumps(schema_hint, ensure_ascii=False)
            ),
        },
    ]


def _phase_rank(phase: str) -> int:
    if phase == "triage":
        return 0
    if phase in {"consultation_round1", "internal_medicine_round1", "surgery_round1"}:
        return 1
    if phase in {"consultation_round2", "internal_medicine_round2", "surgery_round2"}:
        return 2
    return 1


def _reveal_rank(phase: str | None) -> int:
    if phase == "intake":
        return 0
    if phase == "round1_followup":
        return 1
    if phase == "round2":
        return 2
    return 2


def _rare_event_reply_instructions(case_card: PatientCaseCard, context: PatientReplyContext) -> list[str]:
    profile = case_card.rare_event_profile
    if profile is None or not profile.patient_special_event_enabled:
        return []
    reveal_rank = _reveal_rank(profile.special_event_reveal_phase)
    current_rank = _phase_rank(context.phase)
    if current_rank < reveal_rank:
        return [
            "Do not volunteer the strongest hidden warning clue yet unless the clinician asks a directly relevant safety question.",
            "Keep the answer routine and brief, and avoid prematurely announcing the cross-specialty or escalation-driving detail.",
        ]
    guidance = [
        "If the clinician asks about progression, severity, associated symptoms, injury context, or warning features, naturally reveal the more important clue now.",
        "Reveal the concerning detail in ordinary patient wording, not in diagnosis labels.",
    ]
    if profile.patient_special_event_type == "specialty_referral":
        guidance.append(
            "If asked about mechanism or symptom pattern, make it clear why the problem could fit another specialty better after this loop finishes."
        )
    elif profile.patient_special_event_type == "icu_escalation":
        guidance.append(
            "If asked about worsening or danger signs, mention the stronger instability clue that can justify ICU-level concern."
        )
    elif profile.patient_special_event_type == "emergency_escalation":
        guidance.append(
            "If asked about worsening or danger signs, mention the stronger red-flag clue that can justify emergency escalation."
        )
    return guidance


def build_reply_messages(
    *,
    case_card: PatientCaseCard,
    context: PatientReplyContext,
    decision: PatientPolicyDecision,
    constraints: str,
) -> list[dict]:
    instructions = [
        "Answer the clinician's latest question directly and briefly.",
        "Only use facts allowed by policy_decision.allowed_fact_keys.",
        "If follow_up_question is not natural, return null.",
        "Do not mention hidden_diagnosis_hint or forbidden_reveals literally.",
    ]
    instructions.extend(_rare_event_reply_instructions(case_card, context))
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
                    "instructions": instructions,
                },
                ensure_ascii=False,
            ),
        },
    ]
