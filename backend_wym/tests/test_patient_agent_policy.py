from app.agents.patient_agent.patient_policy import PatientPolicy
from app.agents.patient_agent.schemas import PatientCaseCard, PatientProfileCard, PatientReplyContext, PatientSymptomFacts


def sample_case() -> PatientCaseCard:
    return PatientCaseCard(
        case_id="case-001",
        patient_profile=PatientProfileCard(
            name="Lin Wei",
            age=29,
            sex="female",
            allergies=[],
            chronic_conditions=[],
        ),
        chief_complaint="Cough and low fever",
        present_illness="Cough started 2 days ago and became more obvious yesterday.",
        symptom_facts=PatientSymptomFacts(
            symptoms=["cough", "sore throat", "runny nose"],
            onset_time="2 days ago",
            vitals={"temp_c": 37.8, "heart_rate": 92, "pain_score": 3},
            associated_symptoms=["dry throat"],
            negatives=["no chest pain"],
            aggravating_factors=["talking a lot"],
            relieving_factors=["rest"],
        ),
        communication_style="calm and cooperative",
        hidden_diagnosis_hint="viral upper respiratory infection",
        patient_goals=["understand whether it is serious"],
        forbidden_reveals=["viral upper respiratory infection"],
    )


def test_patient_policy_limits_triage_answer_scope():
    policy = PatientPolicy()
    decision = policy.decide(
        sample_case(),
        PatientReplyContext(
            phase="triage",
            patient_id="P-12345678",
            recent_question="Do you have any drug allergies and when did the symptoms start?",
        ),
    )
    assert "allergies" in decision.allowed_fact_keys
    assert "onset_time" in decision.allowed_fact_keys
    assert decision.avoid_diagnosis_labels is True


def test_patient_policy_round2_allows_results_and_followup():
    policy = PatientPolicy()
    decision = policy.decide(
        sample_case(),
        PatientReplyContext(
            phase="internal_medicine_round2",
            patient_id="P-12345678",
            recent_question="The report is ready. Do you want me to explain the result?",
        ),
    )
    assert "known_test_results" in decision.allowed_fact_keys
    assert decision.should_ask_follow_up is True
    assert any("next steps" in topic or "severity" in topic for topic in decision.allowed_topics)
