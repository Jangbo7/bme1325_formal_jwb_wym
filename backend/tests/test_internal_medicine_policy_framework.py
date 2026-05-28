import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.internal_medicine.policy import load_internal_medicine_policy_registry
from app.main import create_app


PATIENT_ID = "P-11111111"


def create_test_client(monkeypatch):
    db_dir = Path(__file__).resolve().parents[1] / "_tmp_test_dbs"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"test_internal_medicine_policy_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    return TestClient(create_app())


def headers():
    return {
        "X-API-Key": "mock-key-001",
        "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
    }


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def registration_payload(name: str = "Player"):
    return {
        "name": name,
        "sex": "unknown",
        "age": 30,
        "id_number": "TEMP-REG-0001",
    }


def prepare_visit_in_consultation(client: TestClient) -> str:
    triage_session_id = f"triage-{uuid.uuid4().hex[:8]}"
    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": triage_session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200, triage_resp.text
    triage_data = get_data(triage_resp)
    visit_id = triage_data["visit_id"]
    for _ in range(3):
        if triage_data["visit_state"] == "triaged":
            break
        followup_resp = client.post(
            f"/api/v1/triage-sessions/{triage_data['session_id']}/messages",
            headers=headers(),
            json={
                "patient_id": PATIENT_ID,
                "visit_id": visit_id,
                "name": "Player",
                "message": "Symptoms started 1 day ago, I have no allergies, and the cough remains mild.",
            },
        )
        assert followup_resp.status_code == 200, followup_resp.text
        triage_data = get_data(followup_resp)
    assert triage_data["visit_state"] == "triaged", triage_data

    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload("Player"),
    )
    assert register_resp.status_code == 200, register_resp.text

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=data)

    progress_resp = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp.status_code == 200, progress_resp.text
    assert get_data(progress_resp)["visit"]["state"] == "waiting_consultation"

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200, enter_resp.text
    assert get_data(enter_resp)["visit"]["state"] == "in_consultation"
    return visit_id


def create_internal_medicine_session(client: TestClient, visit_id: str, **extra_payload):
    response = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
            **extra_payload,
        },
    )
    assert response.status_code == 200, response.text
    return get_data(response)


def test_internal_medicine_round1_uses_policy_card(monkeypatch):
    registry = load_internal_medicine_policy_registry()
    assert registry.cards[0].id == "internal_medicine_initial_consultation"

    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="mild cough",
        symptoms="mild cough",
    )

    memory_repo = client.app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(create_data["session_id"], PATIENT_ID, agent_type="internal_medicine")

    assert session_memory["latest_policy"]["card_id"] == "internal_medicine_initial_consultation"
    assert session_memory["latest_policy"]["phase"] == "round1_initial_consultation"
    assert session_memory["latest_policy"]["snapshot"]["next_action"] == "ask_follow_up"


def test_internal_medicine_round1_policy_snapshot_escalates_red_flags(monkeypatch):
    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="chest pain",
        symptoms="chest pain, shortness of breath",
        onset_time="this morning",
        allergies=[],
        vitals={"heart_rate": 136, "systolic_bp": 88, "diastolic_bp": 58, "pain_score": 8},
    )
    session_id = create_data["session_id"]

    response = client.post(
        f"/api/v1/internal-medicine-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "Chest pain started this morning and I have no allergies, but now it is worse and I feel short of breath.",
        },
    )
    assert response.status_code == 200, response.text
    data = get_data(response)

    memory_repo = client.app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(session_id, PATIENT_ID, agent_type="internal_medicine")

    assert data["dialogue"]["status"] == "awaiting_patient_reply"
    assert session_memory["latest_policy"]["snapshot"]["next_action"] == "escalate_urgency"
    assert session_memory["latest_policy"]["snapshot"]["urgency"] == "urgent"
