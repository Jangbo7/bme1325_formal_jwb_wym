from app.api.contract import ContractError
from app.agents.patient_agent.patient_agent import ControlledPatientAgent
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


def test_patient_agent_reply_sanitizes_forbidden_reveals():
    agent = ControlledPatientAgent(
        {"endpoint": "unused", "model": "unused", "api_key": "test-key"},
        request_json=lambda messages: {
            "message": "This may be viral upper respiratory infection but I mainly have cough and fever.",
            "used_facts": ["chief_complaint", "symptoms"],
            "follow_up_question": "Is it serious?",
        },
    )

    result = agent.reply(
        case_card=sample_case(),
        context=PatientReplyContext(
            phase="internal_medicine_round1",
            patient_id="P-12345678",
            recent_question="Tell me your symptoms.",
        ),
    )

    assert "viral upper respiratory infection" not in result.message.lower()
    assert "cough" in result.message.lower()
    assert result.policy_state["avoid_diagnosis_labels"] is True


def test_patient_agent_reply_falls_back_on_invalid_llm_payload():
    agent = ControlledPatientAgent(
        {"endpoint": "unused", "model": "unused", "api_key": "test-key"},
        request_json=lambda messages: {"bad": "payload"},
    )

    result = agent.reply(
        case_card=sample_case(),
        context=PatientReplyContext(
            phase="triage",
            patient_id="P-12345678",
            recent_question="What brings you here today?",
        ),
    )

    assert result.message
    assert "cough" in result.message.lower()


def test_patient_agent_reply_falls_back_after_llm_request_failure():
    agent = ControlledPatientAgent(
        {"endpoint": "unused", "model": "unused", "api_key": "test-key"},
        request_json=lambda messages: (_ for _ in ()).throw(
            ContractError(
                code="LLM_REQUEST_FAILED",
                message="patient agent LLM request timed out",
                details={"agent": "patient_agent", "retries": 2},
                status_code=504,
            )
        ),
    )

    result = agent.reply(
        case_card=sample_case(),
        context=PatientReplyContext(
            phase="triage",
            patient_id="P-12345678",
            recent_question="What brings you here today?",
        ),
    )

    assert result.message
    assert "cough" in result.message.lower()
