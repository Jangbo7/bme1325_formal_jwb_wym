import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    app = create_app()
    return TestClient(app)


def headers():
    return {"X-API-Key": "mock-key-001"}


def test_triage_session_and_followup_flow(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    create_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "chest tightness",
            "vitals": {"heart_rate": 105, "temp_c": 37.1, "pain_score": 5},
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["session_id"] == session_id
    assert create_data["dialogue"]["status"] in {"awaiting_patient_reply", "triaged"}

    reply_resp = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "message": "Symptoms started 30 minutes ago, no allergies, pain is 6/10, no fever",
        },
    )
    assert reply_resp.status_code == 200
    reply_data = reply_resp.json()
    assert reply_data["patient"]["id"] == "P-self"
    assert reply_data["dialogue"]["status"] in {"awaiting_patient_reply", "triaged"}


def test_queue_created_after_triage_completion(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "fever",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 90, "temp_c": 38.9, "pain_score": 2},
        },
    )
    queues = client.get("/api/v1/queues", headers=headers())
    assert queues.status_code == 200
    all_waiting = [ticket for group in queues.json()["queues"] for ticket in group["waiting"]]
    assert any(ticket["patient_id"] == "P-self" for ticket in all_waiting)
