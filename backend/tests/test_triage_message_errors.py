import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(monkeypatch):
    db_dir = Path(__file__).resolve().parents[1] / "_tmp_test_dbs"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"triage_message_errors_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    return TestClient(create_app())


def headers():
    return {"X-API-Key": "mock-key-001"}


def test_triage_message_missing_session_returns_404_not_500(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.post(
        "/api/v1/triage-sessions/session-missing/messages",
        headers=headers(),
        json={"patient_id": "P-self", "message": "I have had a fever since yesterday."},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "triage session not found"


def test_triage_message_accepts_visit_id_and_continues(monkeypatch):
    client = create_test_client(monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "fever",
            "allergies": [],
        },
    )
    assert create_response.status_code == 200, create_response.text
    visit_id = create_response.json()["visit_id"]

    response = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "visit_id": visit_id,
            "message": "It started yesterday and my temperature is 38.5 C.",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["session_id"] == session_id
    assert data["visit_id"] == visit_id
