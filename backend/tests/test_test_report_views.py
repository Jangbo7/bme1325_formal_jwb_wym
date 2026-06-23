import uuid

from fastapi.testclient import TestClient

from app.agents.patient_agent.schemas import (
    PatientAgentTurnResult,
    PatientCaseCard,
    PatientProfileCard,
    PatientSymptomFacts,
)
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test_report_views.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
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


def install_fake_patient_agent(client: TestClient):
    service = client.app.state.container["patient_agent_service"]

    def fake_generate_case(seed=None, department_id=None):
        return PatientCaseCard(
            case_id="case-report-view-001",
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

    def fake_reply(*, case_card, context):
        return PatientAgentTurnResult(
            message="My main problem is cough and low fever.",
            used_facts=["chief_complaint"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.generate_case = fake_generate_case
    service.agent.reply = fake_reply


def test_multi_patient_snapshot_contains_test_report_card_field(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    controller = client.app.state.container["multi_patient_debug_controller"]

    response = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_probabilistic_llm",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 10.0,
            "max_active_patients": 1,
            "llm_probability": 1.0,
        },
    )
    assert response.status_code == 200

    controller.tick_once()
    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))

    assert snapshot["patients"][0]["test_report_card"]["status"] == "pending"
    assert "title" in snapshot["patients"][0]["test_report_card"]
    assert snapshot["patients"][0]["test_report"] == {}


def test_multi_patient_debug_page_includes_test_report_card_renderer(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    response = client.get("/multi-patient-debug")

    assert response.status_code == 200
    assert "renderTestReportCard" in response.text
    assert "renderRawTestReport" in response.text
    assert "检查报告卡" in response.text
