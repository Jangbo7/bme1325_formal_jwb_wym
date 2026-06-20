from __future__ import annotations

from app.agents.patient_agent.schemas import PatientCaseCard, PatientPolicyDecision, PatientReplyContext


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


ROUND1_PHASES = {"internal_medicine_round1", "consultation_round1"}
ROUND2_PHASES = {"internal_medicine_round2", "consultation_round2"}


class PatientPolicy:
    def decide(self, case_card: PatientCaseCard, context: PatientReplyContext) -> PatientPolicyDecision:
        question = (context.recent_question or "").strip().lower()
        phase = context.phase
        allowed = {
            "chief_complaint",
            "symptoms",
            "onset_time",
            "patient_goals",
        }
        topics = ["chief complaint", "current symptoms", "onset time"]
        style_hints = [case_card.communication_style]
        should_follow_up = False

        if _contains_any(question, ["allerg", "drug allergy", "medicine allergy"]):
            allowed.add("allergies")
            topics.append("allergies")
        if _contains_any(question, ["history", "chronic", "past illness", "before this", "previous"]):
            allowed.add("chronic_conditions")
            topics.append("past history")
        if _contains_any(question, ["temperature", "fever", "temp", "heart rate", "pain", "vital"]):
            allowed.add("vitals")
            topics.append("vitals")
        if _contains_any(question, ["what else", "other symptom", "associated", "together with"]):
            allowed.add("associated_symptoms")
            topics.append("associated symptoms")
        if _contains_any(question, ["worse", "better", "trigger", "relieve"]):
            allowed.add("modifiers")
            topics.append("aggravating and relieving factors")

        if phase == "triage":
            style_hints.append("brief, factual, and responsive")
        if phase in ROUND1_PHASES:
            style_hints.append("slightly more descriptive than triage")
            should_follow_up = True
        if phase in ROUND2_PHASES:
            allowed.add("known_test_results")
            topics.append("known test results")
            style_hints.append("focused on understanding the results and next steps")
            should_follow_up = True
        if phase == "testing":
            style_hints.append("not in active dialogue unless asked")

        if _contains_any(question, ["result", "report", "serious", "dangerous", "what next", "treatment", "medicine"]):
            should_follow_up = True
            topics.append("severity and next steps")

        return PatientPolicyDecision(
            allowed_fact_keys=sorted(allowed),
            should_ask_follow_up=should_follow_up,
            avoid_diagnosis_labels=True,
            style_hints=style_hints,
            allowed_topics=topics,
            summary=f"{phase}: allow {', '.join(sorted(allowed))}",
        )
