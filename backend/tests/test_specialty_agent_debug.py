import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'specialty_agent_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
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


def _assert_agent_debug_page(client: TestClient, page_url: str, title_text: str, preload_api: str, message_api: str, preset_id: str, expected_agent: str):
    page = client.get(page_url)
    assert page.status_code == 200
    assert title_text in page.text

    preload = get_data(post_json(client, preload_api, {"preset_id": preset_id}))
    assert preload["agent_type"] == expected_agent
    assert preload["trace"]["rag_hits"]
    assert any(item["source"] == "official_guidance" for item in preload["trace"]["rag_hits"])
    assert preload["trace"]["parsed_result"]["specialty_result"]["department"]
    assert preload["trace"]["parsed_result"]["doctor_decision"]["routing_decision"]["next_node"]

    message = get_data(post_json(client, message_api, {"message": "Please explain the main concern and what to do next."}))
    assert message["transcript"]
    assert message["latest_reply"] is not None
    assert "assistant_message" in message["trace"]["extra"]
    assert "doctor_decision" in message["trace"]["parsed_result"]


def test_surgery_agent_debug(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    _assert_agent_debug_page(
        client,
        "/surgery-agent-debug",
        "Surgery Agent Debug",
        "/api/v1/surgery-agent-debug/preload",
        "/api/v1/surgery-agent-debug/message",
        "surgery_laceration_case",
        "surgery",
    )


def test_pediatrics_agent_debug(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    _assert_agent_debug_page(
        client,
        "/pediatrics-agent-debug",
        "Pediatrics Agent Debug",
        "/api/v1/pediatrics-agent-debug/preload",
        "/api/v1/pediatrics-agent-debug/message",
        "pediatrics_fever_cough_case",
        "pediatrics",
    )


def test_ent_agent_debug(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    _assert_agent_debug_page(
        client,
        "/ent-agent-debug",
        "ENT Agent Debug",
        "/api/v1/ent-agent-debug/preload",
        "/api/v1/ent-agent-debug/message",
        "ent_sore_throat_case",
        "ent",
    )
