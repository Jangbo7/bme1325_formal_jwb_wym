import uuid

from fastapi.testclient import TestClient

from app.agents.patient_agent.schemas import PatientAgentTurnResult
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'agent_chat_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    return TestClient(create_app())


def api_headers():
    return {"X-API-Key": "mock-key-001"}


def post_json(client: TestClient, path: str, payload: dict | None = None):
    return client.post(
        path,
        headers={**api_headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
        json=payload if payload is not None else {},
    )


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def install_fake_patient_agent(client: TestClient):
    service = client.app.state.container["patient_agent_service"]

    def fake_reply(*, case_card, context):
        return PatientAgentTurnResult(
            message="I mainly want to know what the result means and what to do next.",
            used_facts=["chief_complaint", "known_test_results"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.reply = fake_reply


def test_triage_agent_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/triage-agent-debug")
    assert page.status_code == 200
    assert "Triage Agent Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/triage-agent-debug/preload", {"preset_id": "triage_respiratory_mild"}))
    assert preload["agent_type"] == "triage"
    assert preload["trace"]["rag_hits"]
    assert "merged_payload" in preload["trace"]

    message = get_data(post_json(client, "/api/v1/triage-agent-debug/message", {"message": "It started 2 days ago and my temperature is around 37.8"}))
    assert message["transcript"]
    assert message["latest_reply"] is not None
    assert "parsed_result" in message["trace"]
    assert "memory_delta" in message["trace"]


def test_internal_medicine_agent_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/internal-medicine-agent-debug")
    assert page.status_code == 200
    assert "Internal Medicine Agent Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/internal-medicine-agent-debug/preload", {"preset_id": "im_round2_with_report"}))
    assert preload["agent_type"] == "internal_medicine"
    assert preload["trace"]["extra"]["historical_records_template"] is not None
    assert "simulated_report" in preload["trace"]["merged_payload"]

    message = get_data(post_json(client, "/api/v1/internal-medicine-agent-debug/message", {"message": "The pain is still there at night, and I want to know what the report means."}))
    assert message["transcript"]
    assert "rag_hits" in message["trace"]
    assert "parsed_result" in message["trace"]


def test_patient_agent_chat_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)

    page = client.get("/patient-agent-chat-debug")
    assert page.status_code == 200
    assert "Patient Agent Chat Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/patient-agent-chat-debug/preload", {"preset_id": "patient_gastritis_round2"}))
    assert preload["agent_type"] == "patient_agent"
    assert "case_card" in preload["trace"]["merged_payload"]

    message = get_data(post_json(client, "/api/v1/patient-agent-chat-debug/message", {"message": "What do you want to understand most from this report?"}))
    assert message["latest_reply"] is not None
    assert message["trace"]["parsed_result"]["case_summary"]["case_id"] == "PAC-PRESET-002"
    assert "allowed_fact_keys" in message["trace"]["merged_payload"]["policy_decision"]
    assert len(message["transcript"]) >= 2
