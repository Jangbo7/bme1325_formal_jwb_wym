from app.agents.patient_agent.case_generator import PatientCaseGenerator
from app.agents.patient_agent.rag_context import PatientAgentRagContext


def test_patient_case_generator_returns_valid_case_card():
    generator = PatientCaseGenerator(
        request_json=lambda messages: {
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

    card = generator.generate(seed="test-seed")

    assert card.case_id == "case-001"
    assert card.patient_profile.name == "Lin Wei"
    assert card.symptom_facts.onset_time == "2 days ago"
    assert "cough" in card.symptom_facts.symptoms


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
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "patient case generation failed" in str(exc)
    assert attempts["count"] == 3
