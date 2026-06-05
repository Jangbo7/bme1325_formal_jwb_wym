from __future__ import annotations

from app.agents.patient_agent.examples import (
    COMMUNICATION_STYLE_OPTIONS,
    COMMON_OUTPATIENT_CASE_TYPES,
    FOLLOW_UP_STYLE_RULES,
)


class PatientAgentRagContext:
    def build_case_constraints(self) -> str:
        case_types = "; ".join(COMMON_OUTPATIENT_CASE_TYPES)
        styles = "; ".join(COMMUNICATION_STYLE_OPTIONS)
        return (
            "Allowed case families: "
            f"{case_types}. "
            "The case must be suitable for a common outpatient internal-medicine style visit and a simple test/review loop. "
            "Avoid extreme emergencies, surgery, pregnancy, pediatrics, or ICU-only conditions. "
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
