from app.api.contract import ContractError
from app.agents.patient_agent.case_generator import PatientCaseGenerator
from app.agents.patient_agent.rag_context import PatientAgentRagContext
from app.agents.patient_agent.schemas import PatientRareEventProfile
from app.agents.test_simulator.service import TestSimulationAgent


def test_patient_case_generator_returns_valid_case_card():
    captured = {"messages": None}

    generator = PatientCaseGenerator(
        request_json=lambda messages: captured.__setitem__("messages", messages) or {
                "case_id": "case-001",
                "patient_profile": {
                    "name": "Lin Wei",
                    "age": 29,
                    "sex": "female",
                    "allergies": [],
                    "chronic_conditions": [],
                },
                "chief_complaint": "Cough and low fever",
                "present_illness": "Cough started 2 days ago and became more obvious yesterday.",
                "symptom_facts": {
                    "symptoms": ["cough", "sore throat", "runny nose"],
                    "onset_time": "2 days ago",
                    "vitals": {"temp_c": 37.8, "heart_rate": 92, "pain_score": 3},
                    "associated_symptoms": ["dry throat"],
                    "negatives": ["no chest pain"],
                    "aggravating_factors": ["talking a lot"],
                    "relieving_factors": ["rest"],
                },
                "communication_style": "calm and cooperative",
                "hidden_diagnosis_hint": "viral upper respiratory infection",
                "patient_goals": ["understand whether it is serious", "get treatment advice"],
                "forbidden_reveals": ["viral upper respiratory infection"],
            },
        rag_context=PatientAgentRagContext(),
    )

    card = generator.generate(seed="test-seed", department_id="surgery")

    assert card.case_id == "case-001"
    assert card.patient_profile.name == "Lin Wei"
    assert card.symptom_facts.onset_time == "2 days ago"
    assert "cough" in card.symptom_facts.symptoms
    assert card.rare_event_profile is not None
    assert card.rare_event_profile.seed == "test-seed|surgery"
    assert "Surgery (surgery)" in captured["messages"][1]["content"]
    assert "soft department hint" in captured["messages"][1]["content"]
    assert "surgery-style outpatient branch" in captured["messages"][1]["content"]
    assert "Do not generate a plain cough/fever/general-medical case under a surgery hint." in captured["messages"][1]["content"]


def test_patient_case_generator_retries_and_fails_on_invalid_payload():
    attempts = {"count": 0}

    def fake_request(messages):
        attempts["count"] += 1
        return {"bad": "payload"}

    generator = PatientCaseGenerator(
        request_json=fake_request,
        rag_context=PatientAgentRagContext(),
    )

    try:
        generator.generate()
        assert False, "expected ContractError"
    except ContractError as exc:
        assert exc.code == "LLM_RESPONSE_INVALID"
        assert exc.details["stage"] == "generate_case"
    assert attempts["count"] == 3



def test_patient_rag_context_switches_between_internal_and_surgery_styles():
    rag_context = PatientAgentRagContext()

    internal_constraints = rag_context.build_case_constraints(department_id="internal")
    surgery_constraints = rag_context.build_case_constraints(department_id="surgery")

    assert "internal-medicine-style outpatient branch" in internal_constraints
    assert "Avoid wound care, trauma, procedure-driven, or clearly surgery-first complaints." in internal_constraints
    assert "surgery-style outpatient branch" in surgery_constraints
    assert "Avoid purely respiratory, fever-only, or diffuse medical complaints unless they clearly support a surgical pathway." in surgery_constraints


def test_specialty_referral_profile_carries_target_metadata_and_report_signal():
    generator = PatientCaseGenerator(
        request_json=lambda messages: {},
        rag_context=PatientAgentRagContext(),
    )

    profile = generator._sample_rare_event_profile(seed="manual-referral", department_id="internal")
    if profile.event_type != "specialty_referral":
        profile = PatientRareEventProfile(
            patient_special_event_enabled=True,
            patient_special_event_type="specialty_referral",
            special_event_intensity="subtle",
            special_event_reveal_phase="round2",
            report_special_signal_enabled=True,
            report_special_signal_type="specialty_referral",
            triggered_by="patient",
            event_type="specialty_referral",
            target_department="Surgery",
            target_department_id="surgery",
            target_department_reason="The unresolved issue is better suited for surgery.",
            patient_signal_instruction="Later dialogue can mention a localized lump or injury context if asked.",
            report_signal_instruction="The report should support surgical follow-up after loop closure.",
            seed="manual-referral|internal",
        )

    assert profile.report_special_signal_enabled is True
    assert profile.report_special_signal_type == "specialty_referral"
    assert profile.target_department == "Surgery"
    assert profile.target_department_id == "surgery"
    assert profile.target_department_reason
    assert profile.patient_signal_instruction
    assert profile.report_signal_instruction


def test_icu_profile_can_carry_report_escalation_metadata():
    profile = PatientRareEventProfile(
        patient_special_event_enabled=True,
        patient_special_event_type="icu_escalation",
        special_event_intensity="moderate",
        special_event_reveal_phase="round2",
        report_special_signal_enabled=True,
        report_special_signal_type="icu_escalation",
        triggered_by="patient",
        event_type="icu_escalation",
        patient_signal_instruction="Reveal collapse or confusion if asked.",
        report_signal_instruction="The report should indicate ICU-level instability.",
        report_escalation_target="icu",
        report_escalation_reason="Report-level findings suggest ICU-level deterioration.",
        alignment_keywords=["collapse", "confusion", "shock"],
        seed="manual-icu|internal",
    )

    assert profile.report_escalation_target == "icu"
    assert profile.report_escalation_reason == "Report-level findings suggest ICU-level deterioration."
    assert profile.alignment_keywords == ["collapse", "confusion", "shock"]


def test_generate_case_retries_when_specialty_referral_case_is_misaligned():
    responses = iter(
        [
            {
                "case_id": "case-bad",
                "patient_profile": {
                    "name": "Lin Wei",
                    "age": 58,
                    "sex": "female",
                    "allergies": [],
                    "chronic_conditions": ["hypertension", "diabetes"],
                },
                "chief_complaint": "Dizziness and poor glucose control",
                "present_illness": "Blood pressure and glucose have been fluctuating recently.",
                "symptom_facts": {
                    "symptoms": ["dizziness", "fatigue"],
                    "onset_time": "1 week ago",
                    "vitals": {"temp_c": 36.7, "heart_rate": 86, "pain_score": 1},
                    "associated_symptoms": ["fatigue"],
                    "negatives": ["no chest pain"],
                    "aggravating_factors": ["standing quickly"],
                    "relieving_factors": ["rest"],
                },
                "communication_style": "calm and cooperative",
                "hidden_diagnosis_hint": "orthostatic symptoms related to diabetes",
                "patient_goals": ["understand whether it is serious"],
                "forbidden_reveals": ["orthostatic symptoms related to diabetes"],
            },
            {
                "case_id": "case-good",
                "patient_profile": {
                    "name": "Lin Wei",
                    "age": 43,
                    "sex": "female",
                    "allergies": [],
                    "chronic_conditions": [],
                },
                "chief_complaint": "Back discomfort after a minor bump",
                "present_illness": "She first thought it was ordinary soreness, but later noticed a localized tender swelling.",
                "symptom_facts": {
                    "symptoms": ["back pain", "localized swelling"],
                    "onset_time": "3 days ago",
                    "vitals": {"temp_c": 36.8, "heart_rate": 84, "pain_score": 4},
                    "associated_symptoms": ["bruising"],
                    "negatives": ["no fever"],
                    "aggravating_factors": ["bending"],
                    "relieving_factors": ["rest"],
                },
                "communication_style": "calm and cooperative",
                "hidden_diagnosis_hint": "localized soft tissue injury that may need surgical evaluation",
                "patient_goals": ["know whether more treatment is needed"],
                "forbidden_reveals": ["localized soft tissue injury that may need surgical evaluation"],
            },
        ]
    )
    captured_messages = []

    generator = PatientCaseGenerator(
        request_json=lambda messages: captured_messages.append(messages) or next(responses),
        rag_context=PatientAgentRagContext(),
    )
    generator._sample_rare_event_profile = lambda **kwargs: PatientRareEventProfile(
        patient_special_event_enabled=True,
        patient_special_event_type="specialty_referral",
        special_event_intensity="subtle",
        special_event_reveal_phase="round2",
        report_special_signal_enabled=True,
        report_special_signal_type="specialty_referral",
        triggered_by="patient",
        event_type="specialty_referral",
        target_department="Surgery",
        target_department_id="surgery",
        target_department_reason="The unresolved issue is better suited for surgery.",
        patient_signal_instruction="Later dialogue can mention a localized lump or injury context if asked.",
        report_signal_instruction="The report should support surgical follow-up after loop closure.",
        alignment_keywords=["injury", "wound", "swelling", "lump"],
        seed="manual-referral|internal",
    )

    card = generator.generate(seed="manual-referral", department_id="internal", retries=1)

    assert card.case_id == "case-good"
    assert len(captured_messages) == 2
    assert "Correction for the previous attempt" in captured_messages[1][1]["content"]


def test_generate_case_retries_when_icu_case_is_misaligned():
    responses = iter(
        [
            {
                "case_id": "case-bad-icu",
                "patient_profile": {
                    "name": "Lin Wei",
                    "age": 35,
                    "sex": "female",
                    "allergies": [],
                    "chronic_conditions": [],
                },
                "chief_complaint": "Mild cough",
                "present_illness": "A mild cough started yesterday.",
                "symptom_facts": {
                    "symptoms": ["cough"],
                    "onset_time": "1 day ago",
                    "vitals": {"temp_c": 37.2, "heart_rate": 90, "pain_score": 1},
                    "associated_symptoms": [],
                    "negatives": ["no chest pain"],
                    "aggravating_factors": [],
                    "relieving_factors": ["rest"],
                },
                "communication_style": "calm and cooperative",
                "hidden_diagnosis_hint": "viral upper respiratory infection",
                "patient_goals": ["know whether it is serious"],
                "forbidden_reveals": ["viral upper respiratory infection"],
            },
            {
                "case_id": "case-good-icu",
                "patient_profile": {
                    "name": "Lin Wei",
                    "age": 57,
                    "sex": "female",
                    "allergies": [],
                    "chronic_conditions": ["hypertension"],
                },
                "chief_complaint": "Chest tightness with near fainting",
                "present_illness": "The symptoms first felt mild, but later she had shortness of breath and almost collapsed.",
                "symptom_facts": {
                    "symptoms": ["chest pain", "shortness of breath"],
                    "onset_time": "today",
                    "vitals": {"temp_c": 37.0, "heart_rate": 132, "pain_score": 7},
                    "associated_symptoms": ["confusion"],
                    "negatives": [],
                    "aggravating_factors": ["walking"],
                    "relieving_factors": ["resting briefly"],
                },
                "communication_style": "anxious but cooperative",
                "hidden_diagnosis_hint": "possible unstable cardiopulmonary deterioration",
                "patient_goals": ["know whether emergency care is needed"],
                "forbidden_reveals": ["possible unstable cardiopulmonary deterioration"],
            },
        ]
    )
    captured_messages = []

    generator = PatientCaseGenerator(
        request_json=lambda messages: captured_messages.append(messages) or next(responses),
        rag_context=PatientAgentRagContext(),
    )
    generator._sample_rare_event_profile = lambda **kwargs: PatientRareEventProfile(
        patient_special_event_enabled=True,
        patient_special_event_type="icu_escalation",
        special_event_intensity="moderate",
        special_event_reveal_phase="round2",
        report_special_signal_enabled=True,
        report_special_signal_type="icu_escalation",
        triggered_by="patient",
        event_type="icu_escalation",
        patient_signal_instruction="Reveal collapse or confusion if asked.",
        report_signal_instruction="The report should indicate ICU-level instability.",
        report_escalation_target="icu",
        report_escalation_reason="Report-level findings suggest ICU-level deterioration.",
        alignment_keywords=["collapse", "confusion", "shortness of breath", "chest pain"],
        seed="manual-icu|internal",
    )

    card = generator.generate(seed="manual-icu", department_id="internal", retries=1)

    assert card.case_id == "case-good-icu"
    assert len(captured_messages) == 2
    assert "Correction for the previous attempt" in captured_messages[1][1]["content"]


def test_simulated_report_prefers_referral_target_from_profile():
    agent = TestSimulationAgent()

    report = agent.generate_report(
        {
            "department": "Internal Medicine",
            "diagnosis_level": 1,
            "priority": "M",
            "test_reason": "Need a focused review before deciding next steps.",
        },
        {"clinical_memory": {"symptoms": ["dizziness", "fatigue"]}},
        rare_event_profile=PatientRareEventProfile(
            event_type="specialty_referral",
            report_special_signal_enabled=True,
            report_special_signal_type="specialty_referral",
            target_department="Surgery",
            target_department_id="surgery",
            target_department_reason="The remaining issue is focal and better handled by surgery.",
        ).model_dump(),
        current_department="Internal Medicine",
    )

    clues = report["report_summary"]["cross_specialty_clues"]
    assert clues
    assert clues[0]["target_department"] == "Surgery"
    assert clues[0]["reason"] == "The remaining issue is focal and better handled by surgery."


def test_simulated_report_prefers_icu_escalation_target_from_profile():
    agent = TestSimulationAgent()

    report = agent.generate_report(
        {
            "department": "Internal Medicine",
            "diagnosis_level": 2,
            "priority": "M",
            "test_reason": "Need reassessment.",
        },
        {"clinical_memory": {"symptoms": ["fatigue"]}},
        rare_event_profile=PatientRareEventProfile(
            event_type="icu_escalation",
            report_special_signal_enabled=True,
            report_special_signal_type="icu_escalation",
            report_escalation_target="icu",
            report_escalation_reason="Report-level findings suggest ICU-level deterioration.",
        ).model_dump(),
        current_department="Internal Medicine",
    )

    clues = report["report_summary"]["escalation_clues"]
    assert clues["to_emergency"] is True
    assert clues["to_icu"] is True
    assert clues["reason"] == "Report-level findings suggest ICU-level deterioration."
