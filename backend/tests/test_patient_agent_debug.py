import uuid

from fastapi.testclient import TestClient

from app.agents.patient_agent.schemas import PatientAgentTurnResult, PatientCaseCard, PatientProfileCard, PatientSymptomFacts
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'patient_agent_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    app = create_app()
    return TestClient(app)


def create_test_client_without_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'patient_agent_debug_no_llm.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("ACTIVE_LLM_PROVIDER", "current")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("CURRENT_LLM_API_KEY", "")
    monkeypatch.setenv("CURRENT_LLM_MODEL", "")
    monkeypatch.setenv("CURRENT_LLM_ENDPOINT", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_V3_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_R1_API_KEY", "")
    monkeypatch.setenv("GPT52_API_KEY", "")
    monkeypatch.setenv("QWEN_API_KEY", "")
    monkeypatch.setenv("QWEN_VL_API_KEY", "")
    app = create_app()
    return TestClient(app)


def api_headers():
    return {"X-API-Key": "mock-key-001"}


def post_json(client: TestClient, path: str, payload: dict | None = None):
    return client.post(
        path,
        headers={
            **api_headers(),
            "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
        },
        json=payload if payload is not None else {},
    )


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def sample_case() -> PatientCaseCard:
    return PatientCaseCard(
        case_id="case-intelligent-001",
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
        patient_goals=["understand whether it is serious", "get treatment advice"],
        forbidden_reveals=["viral upper respiratory infection"],
    )


def install_fake_patient_agent(client: TestClient):
    service = client.app.state.container["patient_agent_service"]

    def fake_generate_case(seed=None, department_id=None):
        return sample_case()

    def fake_reply(*, case_card, context):
        if context.phase == "internal_medicine_round2":
            message = "I completed the test and want to understand the report and treatment plan."
        else:
            message = (
                "My main problem is cough and low fever. "
                "I have cough, sore throat, and a runny nose. "
                "It started 2 days ago. "
                "My temperature is about 37.8 C and the discomfort is around 3 out of 10. "
                "I do not have drug allergies or chronic diseases."
            )
        return PatientAgentTurnResult(
            message=message,
            used_facts=["chief_complaint", "symptoms", "onset_time", "vitals", "allergies", "chronic_conditions"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.generate_case = fake_generate_case
    service.agent.reply = fake_reply


def test_patient_agent_debug_step_reaches_outpatient_disposition(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)

    spawn_resp = post_json(client, "/api/v1/patient-agent-debug/spawn", {"seed": "demo-seed"})
    assert spawn_resp.status_code == 200
    snapshot = get_data(spawn_resp)
    assert snapshot["mode"] == "intelligent_agent"
    assert snapshot["case_summary"]["chief_complaint"] == "Cough and low fever"

    actions = []
    visit_states = []
    final_snapshot = None
    for _ in range(24):
        step_resp = post_json(client, "/api/v1/patient-agent-debug/step")
        assert step_resp.status_code == 200
        final_snapshot = get_data(step_resp)
        actions.append(final_snapshot["last_action"])
        visit_states.append(final_snapshot["visit_state"])
        if final_snapshot["finished"]:
            break

    assert final_snapshot is not None
    assert final_snapshot["finished"] is True
    assert final_snapshot["visit_state"] == "completed"
    assert final_snapshot["outpatient_flow_finished"] is True
    assert final_snapshot["disposition"]["category"] in {"outpatient_treatment", "followup_booking"}
    assert final_snapshot["patient_lifecycle_state"] == "completed"
    assert final_snapshot["medical_record_summary"] is not None
    assert "create_triage_session" in actions
    assert "register_visit" in actions
    assert "progress_visit" in actions
    assert "enter_consultation" in actions
    assert "create_internal_medicine_session" in actions
    assert "reply_internal_medicine" in actions
    assert "trigger_encounter_event" in actions
    assert "triaged" in visit_states
    assert "waiting_test" in visit_states
    assert "in_second_consultation" in visit_states
    assert not any(
        "[History reviewed]" in entry["message"]
        for entry in final_snapshot["transcript"]
        if entry["counterparty"] == "internal_medicine_agent"
    )

    mr_resp = client.get("/api/v1/patient-agent-debug/medical-record", headers=api_headers())
    assert mr_resp.status_code == 200
    timeline = get_data(mr_resp)
    assert timeline["entries"]


def test_patient_agent_debug_spawn_fails_without_llm(tmp_path, monkeypatch):
    client = create_test_client_without_llm(tmp_path, monkeypatch)

    response = post_json(client, "/api/v1/patient-agent-debug/spawn", {})
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "LLM_UNAVAILABLE"
    assert body["error"]["details"]["agent"] == "patient_agent"
    assert body["error"]["details"]["stage"] == "generate_case"
    assert "api_key" in body["error"]["details"]["missing"]


def test_patient_agent_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)

    response = client.get("/patient-agent-debug")
    assert response.status_code == 200
    assert "Patient Agent Debug" in response.text
