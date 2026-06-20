from __future__ import annotations

import hashlib
import random

from app.api.contract import ContractError
from app.agents.patient_agent.prompt_builder import build_generate_case_messages
from app.agents.patient_agent.rag_context import PatientAgentRagContext
from app.agents.patient_agent.schemas import PatientCaseCard, PatientRareEventProfile


DEFAULT_PATIENT_SPECIAL_EVENT_PROBABILITY = 0.2
DEFAULT_REPORT_SPECIAL_SIGNAL_PROBABILITY = 0.12
SPECIAL_EVENT_TYPES = (
    "emergency_escalation",
    "icu_escalation",
    "specialty_referral",
)


class PatientCaseGenerator:
    def __init__(self, *, request_json, rag_context: PatientAgentRagContext):
        self.request_json = request_json
        self.rag_context = rag_context

    def generate(
        self,
        *,
        seed: str | None = None,
        department_id: str | None = None,
        retries: int = 2,
    ) -> PatientCaseCard:

        rare_event_profile = self._sample_rare_event_profile(

            seed=seed,
            department_id=department_id,
        )
        constraints = self.rag_context.build_case_constraints(department_id=department_id)
        last_error = "unknown"
        retry_feedback = None
        for _ in range(retries + 1):
            messages = build_generate_case_messages(
                constraints=constraints,
                seed=seed,
                department_id=department_id,
                rare_event_profile=rare_event_profile,
                retry_feedback=retry_feedback,
            )
            try:
                data = self.request_json(messages)
            except ContractError:
                raise
            if not isinstance(data, dict):
                last_error = "case generator returned non-object payload"
                retry_feedback = last_error
                continue
            try:
                payload = dict(data)
                payload["rare_event_profile"] = rare_event_profile.model_dump()
                card = PatientCaseCard.model_validate(payload)
                alignment_error = self._validate_case_alignment(card, department_id=department_id)
                if alignment_error:
                    last_error = alignment_error
                    retry_feedback = alignment_error
                    continue
                return card
            except Exception as exc:
                last_error = str(exc)
                retry_feedback = last_error
        raise ContractError(
            code="LLM_RESPONSE_INVALID",
            message="patient case generation returned invalid structured JSON",
            details={
                "agent": "patient_agent",
                "stage": "generate_case",
                "last_error": last_error,
                "retries": retries,
            },
            status_code=502,
        )

    def _sample_rare_event_profile(
        self,
        *,
        seed: str | None,
        department_id: str | None,
    ) -> PatientRareEventProfile:
        normalized_department = str(department_id or "").strip().lower() or "general"
        seed_basis = f"{seed or 'default'}|{normalized_department}"
        patient_rng = self._seeded_random(f"{seed_basis}|patient")
        report_rng = self._seeded_random(f"{seed_basis}|report")
        event_rng = self._seeded_random(f"{seed_basis}|event")

        patient_event_type = None
        if patient_rng.random() < DEFAULT_PATIENT_SPECIAL_EVENT_PROBABILITY:
            patient_event_type = self._sample_event_type(patient_rng, normalized_department)

        report_event_type = None
        if report_rng.random() < DEFAULT_REPORT_SPECIAL_SIGNAL_PROBABILITY:
            report_event_type = patient_event_type or self._sample_event_type(report_rng, normalized_department)

        primary_event_type = patient_event_type or report_event_type
        scenario = None
        if primary_event_type:
            scenario = self._build_event_scenario(primary_event_type, normalized_department, event_rng)
            if not report_event_type:
                report_event_type = primary_event_type
        triggered_by = "none"
        if patient_event_type:
            triggered_by = "patient"
        elif report_event_type:
            triggered_by = "report"

        intensity = None
        reveal_phase = None
        if patient_event_type:
            intensity = "moderate" if patient_event_type in {"emergency_escalation", "icu_escalation"} else "subtle"
            reveal_phase = self._default_reveal_phase(patient_event_type, patient_rng)

        return PatientRareEventProfile(
            patient_special_event_enabled=bool(patient_event_type),
            patient_special_event_type=patient_event_type,
            special_event_intensity=intensity,
            special_event_reveal_phase=reveal_phase,
            report_special_signal_enabled=bool(report_event_type),
            report_special_signal_type=report_event_type,
            triggered_by=triggered_by,
            event_type=primary_event_type,
            target_department=(scenario or {}).get("target_department"),
            target_department_id=(scenario or {}).get("target_department_id"),
            target_department_reason=(scenario or {}).get("reason"),
            patient_signal_instruction=(scenario or {}).get("patient_signal_instruction"),
            report_signal_instruction=(scenario or {}).get("report_signal_instruction"),
            report_escalation_target=(scenario or {}).get("report_escalation_target"),
            report_escalation_reason=(scenario or {}).get("report_escalation_reason"),
            alignment_keywords=list((scenario or {}).get("alignment_keywords") or []),
            seed=seed_basis,
        )

    @staticmethod
    def _build_event_scenario(event_type: str, department_id: str, rng: random.Random) -> dict:
        if event_type == "specialty_referral":
            return PatientCaseGenerator._build_specialty_referral_target(department_id, rng)
        if event_type == "emergency_escalation":
            return PatientCaseGenerator._build_emergency_escalation_scenario(department_id, rng)
        if event_type == "icu_escalation":
            return PatientCaseGenerator._build_icu_escalation_scenario(department_id, rng)
        return {}

    @staticmethod
    def _build_specialty_referral_target(department_id: str, rng: random.Random) -> dict:
        if department_id == "surgery":
            options = [
                {
                    "target_department": "Internal Medicine",
                    "target_department_id": "internal",
                    "reason": "After the current surgical loop closes, the residual issue looks more systemic or chronic-disease-related than surgery-first.",
                    "patient_signal_instruction": (
                        "Later in the dialogue, allow mild but clear medical clues such as dizziness, palpitations, fatigue, blood-pressure fluctuation, "
                        "or glucose-control difficulty if the clinician asks follow-up questions."
                    ),
                    "report_signal_instruction": (
                        "The report should be stable from a surgical standpoint but point toward medical follow-up rather than continued surgery review."
                    ),
                    "alignment_keywords": ["dizziness", "palpitation", "fatigue", "blood pressure", "glucose"],
                },
                {
                    "target_department": "Internal Medicine",
                    "target_department_id": "internal",
                    "reason": "The remaining concern is better explained by a medical problem than an ongoing surgical lesion.",
                    "patient_signal_instruction": (
                        "Keep the initial complaint surgery-triageable, but later mention systemic symptoms or chronic-condition context when asked."
                    ),
                    "report_signal_instruction": (
                        "The report should not suggest a surgical emergency; it should support closing the surgery loop and re-registering with internal medicine."
                    ),
                    "alignment_keywords": ["dizziness", "fatigue", "cough", "fever", "chronic"],
                },
            ]
        else:
            options = [
                {
                    "target_department": "Surgery",
                    "target_department_id": "surgery",
                    "reason": "After the current internal-medicine loop closes, the unresolved issue looks more focal, trauma-, wound-, or lump-related than medical-first.",
                    "patient_signal_instruction": (
                        "Do not make the first complaint obviously misrouted, but later allow a clear local symptom pattern such as localized swelling, minor injury history, "
                        "a superficial wound concern, or a palpable lump if the clinician asks."
                    ),
                    "report_signal_instruction": (
                        "The report should remain outpatient-stable but support closing the internal-medicine loop and sending the patient to surgery next."
                    ),
                    "alignment_keywords": ["injury", "trauma", "wound", "swelling", "lump"],
                },
                {
                    "target_department": "Surgery",
                    "target_department_id": "surgery",
                    "reason": "The later detail should suggest a localized structural problem better handled by surgery than repeated internal-medicine follow-up.",
                    "patient_signal_instruction": (
                        "Reserve the localizing clue for later dialogue and make it sound like ordinary patient wording, such as a bump, bruise, wound, or persistent focal pain."
                    ),
                    "report_signal_instruction": (
                        "The report should not look critical; it should indicate the remaining issue fits surgical assessment better than another internal review."
                    ),
                    "alignment_keywords": ["bruise", "wound", "bump", "localized pain", "back pain"],
                },
            ]
        return dict(rng.choice(options))

    @staticmethod
    def _build_emergency_escalation_scenario(department_id: str, rng: random.Random) -> dict:
        if department_id == "surgery":
            options = [
                {
                    "patient_signal_instruction": (
                        "Keep the opening complaint outpatient-compatible, but if the clinician asks about progression or warning signs, reveal worsening wound drainage, fever, or bleeding."
                    ),
                    "report_signal_instruction": (
                        "The report should indicate a time-sensitive postoperative or wound complication that no longer fits routine surgery follow-up."
                    ),
                    "report_escalation_target": "emergency",
                    "report_escalation_reason": "Report-level findings suggest a postoperative or wound-related deterioration that needs immediate emergency reassessment.",
                    "alignment_keywords": ["fever", "drainage", "bleeding", "wound", "postoperative"],
                },
                {
                    "patient_signal_instruction": (
                        "If asked directly, reveal increasing abdominal pain, vomiting, or inability to keep up with the symptoms despite outpatient care."
                    ),
                    "report_signal_instruction": (
                        "The report should support urgent emergency reassessment for an evolving surgical problem rather than routine follow-up."
                    ),
                    "report_escalation_target": "emergency",
                    "report_escalation_reason": "Report-level findings suggest an evolving surgical problem that should leave the outpatient loop now.",
                    "alignment_keywords": ["vomiting", "abdominal pain", "bleeding", "drainage"],
                },
            ]
        else:
            options = [
                {
                    "patient_signal_instruction": (
                        "Keep the initial history routine, but if the clinician asks about progression, reveal chest pain, shortness of breath, or clearly worsening instability."
                    ),
                    "report_signal_instruction": (
                        "The report should indicate a time-sensitive deterioration pattern that requires emergency reassessment instead of routine internal-medicine follow-up."
                    ),
                    "report_escalation_target": "emergency",
                    "report_escalation_reason": "Report-level findings suggest a higher-risk deterioration pattern that now needs emergency reassessment.",
                    "alignment_keywords": ["chest pain", "shortness of breath", "confusion", "bloody stool", "black stool"],
                },
                {
                    "patient_signal_instruction": (
                        "If asked about danger signs, reveal worsening breathing difficulty, persistent vomiting, or confusion in ordinary patient wording."
                    ),
                    "report_signal_instruction": (
                        "The report should no longer look reassuring for outpatient follow-up and should point toward emergency reassessment."
                    ),
                    "report_escalation_target": "emergency",
                    "report_escalation_reason": "Report-level findings suggest a time-sensitive emergency reassessment need.",
                    "alignment_keywords": ["shortness of breath", "vomiting", "confusion", "worsening fever"],
                },
            ]
        return dict(rng.choice(options))

    @staticmethod
    def _build_icu_escalation_scenario(department_id: str, rng: random.Random) -> dict:
        if department_id == "surgery":
            options = [
                {
                    "patient_signal_instruction": (
                        "If the clinician asks about worsening or severity, reveal heavy bleeding, near-fainting, confusion, or collapse risk in ordinary patient language."
                    ),
                    "report_signal_instruction": (
                        "The report should indicate unstable bleeding or another ICU-grade surgical deterioration pattern."
                    ),
                    "report_escalation_target": "icu",
                    "report_escalation_reason": "Report-level findings suggest unstable bleeding or ICU-level deterioration risk.",
                    "alignment_keywords": ["heavy bleeding", "blood loss", "fainting", "confusion", "shock"],
                },
                {
                    "patient_signal_instruction": (
                        "Later in the dialogue, allow signs of severe wound or postoperative instability if directly asked."
                    ),
                    "report_signal_instruction": (
                        "The report should show that the current surgical problem may exceed routine emergency holding and may need ICU-level monitoring."
                    ),
                    "report_escalation_target": "icu",
                    "report_escalation_reason": "Report-level findings suggest ICU-level surgical instability.",
                    "alignment_keywords": ["severe wound", "bleeding", "collapse", "shock", "confusion"],
                },
            ]
        else:
            options = [
                {
                    "patient_signal_instruction": (
                        "If asked about severity or progression, reveal collapse, confusion, one-sided weakness, or severe breathing difficulty in patient wording."
                    ),
                    "report_signal_instruction": (
                        "The report should indicate ICU-level instability rather than routine outpatient internal-medicine follow-up."
                    ),
                    "report_escalation_target": "icu",
                    "report_escalation_reason": "Report-level findings suggest ICU-level deterioration or instability.",
                    "alignment_keywords": ["shock", "collapse", "confusion", "shortness of breath", "weakness"],
                },
                {
                    "patient_signal_instruction": (
                        "Keep the first complaint plausible for outpatient entry, but later reveal fainting, persistent chest pain with dyspnea, or marked instability if asked."
                    ),
                    "report_signal_instruction": (
                        "The report should support ICU escalation because the patient no longer fits routine emergency outpatient reassessment."
                    ),
                    "report_escalation_target": "icu",
                    "report_escalation_reason": "Report-level findings suggest a critical deterioration pattern needing ICU rescue consideration.",
                    "alignment_keywords": ["fainting", "chest pain", "shortness of breath", "confusion", "shock"],
                },
            ]
        return dict(rng.choice(options))

    @staticmethod
    def _validate_case_alignment(card: PatientCaseCard, *, department_id: str | None) -> str | None:
        profile = card.rare_event_profile
        if profile is None or not profile.event_type:
            return None
        text_parts = [
            card.chief_complaint,
            card.present_illness,
            card.hidden_diagnosis_hint,
            " ".join(card.symptom_facts.symptoms),
            " ".join(card.symptom_facts.associated_symptoms),
        ]
        text = " ".join(str(part or "") for part in text_parts).lower()
        required_keywords = [str(item).strip().lower() for item in (profile.alignment_keywords or []) if str(item).strip()]
        if required_keywords and not any(keyword in text for keyword in required_keywords):
            if profile.event_type == "specialty_referral":
                current_department = str(department_id or "current department").strip() or "current department"
                target_department = str(profile.target_department or profile.target_department_id or "another specialty").strip()
                return (
                    f"specialty_referral case is not aligned: the current department hint was {current_department}, "
                    f"the referral target is {target_department}, but the generated case lacks later clues that would plausibly support that handoff."
                )
            return (
                f"{profile.event_type} case is not aligned: the generated case lacks later clues compatible with the configured escalation pattern."
            )
        return None

    @staticmethod
    def _seeded_random(seed_text: str) -> random.Random:
        digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def _default_reveal_phase(event_type: str, rng: random.Random) -> str:
        if event_type == "emergency_escalation":
            return rng.choice(["round1_followup", "round2"])
        if event_type == "icu_escalation":
            return "round2"
        return "round2"

    @staticmethod
    def _sample_event_type(rng: random.Random, department_id: str) -> str:
        weighted_events = PatientCaseGenerator._weighted_event_types_for_department(department_id)
        sample = rng.random()
        cumulative = 0.0
        for event_type, weight in weighted_events:
            cumulative += weight
            if sample <= cumulative:
                return event_type
        return weighted_events[-1][0]

    @staticmethod
    def _weighted_event_types_for_department(department_id: str) -> list[tuple[str, float]]:
        if department_id == "surgery":
            return [
                ("emergency_escalation", 0.30),
                ("icu_escalation", 0.35),
                ("specialty_referral", 0.35),
            ]
        if department_id == "internal":
            return [
                ("emergency_escalation", 0.30),
                ("icu_escalation", 0.15),
                ("specialty_referral", 0.55),
            ]
        return [
            ("emergency_escalation", 0.34),
            ("icu_escalation", 0.16),
            ("specialty_referral", 0.50),
        ]
