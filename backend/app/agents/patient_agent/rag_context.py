from __future__ import annotations

from app.departments.registry import resolve_department
from app.agents.patient_agent.examples import (
    COMMUNICATION_STYLE_OPTIONS,
    COMMON_OUTPATIENT_CASE_TYPES,
    FOLLOW_UP_STYLE_RULES,
)


class PatientAgentRagContext:
    def build_case_constraints(self, *, department_id: str | None = None) -> str:
        case_types = "; ".join(COMMON_OUTPATIENT_CASE_TYPES)
        styles = "; ".join(COMMUNICATION_STYLE_OPTIONS)

        resolved_department = resolve_department(department_id, "M") if department_id else None
        department_style = str((resolved_department or {}).get("id") or "").strip()
        if department_style == "surgery":
            style_constraint = (
                "Use the surgery-style outpatient branch. "
                "Favor complaints such as localized pain, superficial injury, soft-tissue lump, minor trauma, wound issues, anorectal discomfort, "
                "or post-procedure/postoperative review that can still stay in ordinary outpatient flow. "
                "Avoid purely respiratory, fever-only, or diffuse medical complaints unless they clearly support a surgical pathway."
            )
        elif department_style == "internal":
            style_constraint = (
                "Use the internal-medicine-style outpatient branch. "
                "Favor complaints such as respiratory symptoms, dizziness, headache, fatigue, mild gastrointestinal symptoms, blood-pressure/glucose concerns, "
                "or chronic-disease follow-up that fit ordinary medical consultation and simple test/review flow. "
                "Avoid wound care, trauma, procedure-driven, or clearly surgery-first complaints."
            )
        else:
            style_constraint = (
                "Choose exactly one of two outpatient styles for the case: internal-medicine-style or surgery-style. "
                "Make the case clearly fit one branch rather than mixing both equally."

            )
        return (
            "Allowed case families: "
            f"{case_types}. "
            f"{style_constraint} "
            "The case must be suitable for a common outpatient visit and a simple test/review loop. "
            "Avoid extreme emergencies, pediatrics, pregnancy/obgyn, psychiatry-only, or ICU-only conditions. "
            f"Communication styles: {styles}."
        )

    def build_reply_constraints(self) -> str:
        rules = " ".join(FOLLOW_UP_STYLE_RULES)
        return (
            "Reply as a patient only. "
            "Stay consistent with the case card and with known visit events. "
            "Do not invent new tests, diagnoses, or clinician reasoning. "
            f"{rules}"
        )
