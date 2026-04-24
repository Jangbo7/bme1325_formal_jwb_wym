import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def headers():
    return {"X-API-Key": "mock-key-001"}


def test_create_visit_returns_active_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    first = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": "P-self", "name": "Player"},
    )
    assert first.status_code == 200
    visit_id = first.json()["visit"]["id"]

    second = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": "P-self", "name": "Player"},
    )
    assert second.status_code == 200
    assert second.json()["visit"]["id"] == visit_id


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
    assert create_data["visit_id"] is not None
    assert create_data["visit_state"] in {"triaging", "waiting_followup", "triaged"}
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
    assert reply_data["visit_id"] == create_data["visit_id"]
    assert reply_data["dialogue"]["status"] in {"awaiting_patient_reply", "triaged"}


def test_register_requires_triaged_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    visit_resp = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": "P-self", "name": "Player"},
    )
    visit_id = visit_resp.json()["visit"]["id"]

    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
    )
    assert register_resp.status_code == 409


def test_strict_flow_triage_register_wait_call_enter(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "fever",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 90, "temp_c": 38.5, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200
    triage_data = triage_resp.json()
    visit_id = triage_data["visit_id"]
    assert triage_data["visit_state"] == "triaged"

    queues_after_triage = client.get("/api/v1/queues", headers=headers())
    all_waiting_after_triage = [ticket for group in queues_after_triage.json()["queues"] for ticket in group["waiting"]]
    assert not [ticket for ticket in all_waiting_after_triage if ticket["patient_id"] == "P-self"]

    register_resp = client.post(f"/api/v1/visits/{visit_id}/register", headers=headers())
    assert register_resp.status_code == 200
    register_data = register_resp.json()
    assert register_data["visit"]["state"] == "registered"
    assert register_data["patient"]["lifecycle_state"] == "queued"
    assert register_data["queue_ticket"]["status"] == "waiting"

    progress_resp = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp.status_code == 200
    assert progress_resp.json()["ready_for_consultation"] is False

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=data)

    progress_resp_2 = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp_2.status_code == 200
    progress_data = progress_resp_2.json()
    assert progress_data["visit"]["state"] == "waiting_consultation"
    assert progress_data["patient"]["lifecycle_state"] == "called"
    assert progress_data["ready_for_consultation"] is True

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200
    enter_data = enter_resp.json()
    assert enter_data["visit"]["state"] == "in_consultation"
    assert enter_data["patient"]["lifecycle_state"] == "in_consultation"



def test_internal_medicine_session_requires_in_consultation_and_can_continue(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "fever",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 90, "temp_c": 38.5, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = triage_resp.json()["visit_id"]

    register_resp = client.post(f"/api/v1/visits/{visit_id}/register", headers=headers())
    assert register_resp.status_code == 200

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=data)

    progress_resp = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp.status_code == 200
    assert progress_resp.json()["visit"]["state"] == "waiting_consultation"

    blocked_doctor_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert blocked_doctor_resp.status_code == 409

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200
    assert enter_resp.json()["visit"]["state"] == "in_consultation"

    doctor_create_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert doctor_create_resp.status_code == 200
    doctor_create_data = doctor_create_resp.json()
    assert doctor_create_data["visit_id"] == visit_id
    assert doctor_create_data["visit_state"] == "in_consultation"
    assert doctor_create_data["session_id"].startswith("im-session-")

    doctor_message_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "visit_id": visit_id,
            "name": "Player",
            "message": "今早开始，已经持续3小时，伴有轻微咳嗽和发热，没有药物过敏。",
        },
    )
    assert doctor_message_resp.status_code == 200
    doctor_message_data = doctor_message_resp.json()
    assert doctor_message_data["visit_id"] == visit_id
    assert doctor_message_data["session_id"] == doctor_create_data["session_id"]
    assert doctor_message_data["visit_state"] == "in_consultation"
    assert doctor_message_data["dialogue"]["status"] == "awaiting_patient_reply"

    memory_repo = app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(doctor_create_data["session_id"], "P-self", agent_type="internal_medicine")
    assert session_memory["consultation_progress"]["patient_reply_count"] == 1

    second_message_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "visit_id": visit_id,
            "name": "Player",
            "message": "我再补充一下，没有其他不适。",
        },
    )
    assert second_message_resp.status_code == 200
    second_message_data = second_message_resp.json()
    assert second_message_data["visit_id"] == visit_id
    assert second_message_data["visit_state"] == "waiting_test"
    assert second_message_data["dialogue"]["status"] == "completed"

    visit_after_consultation_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    assert visit_after_consultation_resp.status_code == 200
    visit_after_consultation = visit_after_consultation_resp.json()["visit"]
    assert visit_after_consultation["state"] == "waiting_test"
    diagnostic_session = visit_after_consultation["data"].get("diagnostic_session")
    assert isinstance(diagnostic_session, dict)
    assert diagnostic_session["type"] == "imaging_lab"
    assert diagnostic_session["status"] == "pending"
    assert diagnostic_session["source_session_id"] == doctor_create_data["session_id"]
    assert visit_after_consultation["data"]["internal_medicine_session_id"] == doctor_create_data["session_id"]

    patient_resp = client.get("/api/v1/patients/P-self", headers=headers())
    assert patient_resp.status_code == 200
    patient_view = patient_resp.json()["patient"]
    assert patient_view["lifecycle_state"] == "in_test"
    assert patient_view["active_agent_type"] == "internal_medicine"
    assert patient_view["dialogue_source_agent"] == "internal_medicine"
    assert patient_view["session_refs"]["internal_medicine_session_id"] == doctor_create_data["session_id"]

    ready_payment_resp = client.post(f"/api/v1/visits/{visit_id}/ready-payment", headers=headers())
    assert ready_payment_resp.status_code == 200
    assert ready_payment_resp.json()["visit"]["state"] == "waiting_payment"

    duplicate_ready_payment_resp = client.post(f"/api/v1/visits/{visit_id}/ready-payment", headers=headers())
    assert duplicate_ready_payment_resp.status_code == 409
