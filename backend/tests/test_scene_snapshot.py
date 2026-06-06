import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'scene_snapshot.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def headers():
    return {"X-API-Key": "mock-key-001"}


def post_json(client: TestClient, path: str, payload: dict | None = None):
    return client.post(
        path,
        headers={
            **headers(),
            "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
        },
        json=payload if payload is not None else {},
    )


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def get_snapshot(client: TestClient, patient_id: str | None = None):
    path = "/api/v1/scene-snapshot"
    if patient_id:
        path = f"{path}?patient_id={patient_id}"
    response = client.get(path, headers=headers())
    assert response.status_code == 200
    return get_data(response)


def registration_payload(name: str = "Player"):
    return {
        "name": name,
        "sex": "unknown",
        "age": 30,
        "id_number": "TEMP-REG-0001",
    }


def test_scene_snapshot_default_self_without_active_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    snapshot = get_snapshot(client)

    assert snapshot["patient_id"] == "P-self"
    assert snapshot["self_patient"]["id"] == "P-self"
    assert snapshot["active_visit"] is None
    assert snapshot["active_dialogue"] is None
    assert snapshot["active_queue_ticket"] is None
    assert snapshot["medical_record_summary"] is None
    assert snapshot["latest_test_report"] is None
    assert snapshot["ui_flags"]["has_active_visit"] is False
    assert isinstance(snapshot["queues"], list)
    assert snapshot["sync_token"].startswith("scene-")


def test_scene_snapshot_reflects_triage_registration_and_queue_wait(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-11111111"
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = post_json(
        client,
        "/api/v1/triage-sessions",
        {
            "patient_id": patient_id,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = get_data(triage_resp)["visit_id"]

    triage_snapshot = get_snapshot(client, patient_id)
    assert triage_snapshot["active_visit"]["id"] == visit_id
    assert triage_snapshot["active_dialogue"]["agent_type"] == "triage"
    assert triage_snapshot["ui_flags"]["can_register"] is True
    assert triage_snapshot["ui_flags"]["can_continue_triage"] is True

    register_resp = post_json(
        client,
        f"/api/v1/visits/{visit_id}/register",
        registration_payload("Alice Zhang"),
    )
    assert register_resp.status_code == 200

    registered_snapshot = get_snapshot(client, patient_id)
    assert registered_snapshot["active_visit"]["state"] == "registered"
    assert registered_snapshot["active_queue_ticket"]["status"] == "waiting"
    assert registered_snapshot["ui_flags"]["can_progress_visit"] is False
    assert 0 <= registered_snapshot["timers"]["queue_wait_seconds_remaining"] <= 10
    assert any(queue["department_name"] == "Internal Medicine" for queue in registered_snapshot["queues"])

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=visit_data)

    ready_snapshot = get_snapshot(client, patient_id)
    assert ready_snapshot["timers"]["queue_wait_seconds_remaining"] == 0
    assert ready_snapshot["ui_flags"]["can_progress_visit"] is True
    assert ready_snapshot["sync_token"] != registered_snapshot["sync_token"]


def test_scene_snapshot_reflects_doctor_dialogue_and_report(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-22222222"
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = post_json(
        client,
        "/api/v1/triage-sessions",
        {
            "patient_id": patient_id,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    visit_id = get_data(triage_resp)["visit_id"]
    post_json(client, f"/api/v1/visits/{visit_id}/register", registration_payload("Player"))

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=visit_data)

    progress_resp = post_json(client, f"/api/v1/visits/{visit_id}/progress")
    assert progress_resp.status_code == 200
    enter_resp = post_json(client, f"/api/v1/visits/{visit_id}/enter-consultation")
    assert enter_resp.status_code == 200

    create_doctor_resp = post_json(
        client,
        "/api/v1/internal-medicine-sessions",
        {
            "patient_id": patient_id,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert create_doctor_resp.status_code == 200
    doctor_session_id = get_data(create_doctor_resp)["session_id"]

    doctor_message_resp = post_json(
        client,
        f"/api/v1/internal-medicine-sessions/{doctor_session_id}/messages",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "name": "Player",
            "message": "I have had cough and fever for 3 days, and there are no drug allergies.",
        },
    )
    assert doctor_message_resp.status_code == 200

    doctor_snapshot = get_snapshot(client, patient_id)
    assert doctor_snapshot["active_dialogue"]["agent_type"] == "internal_medicine"
    assert doctor_snapshot["active_dialogue"]["session_id"] == doctor_session_id
    assert doctor_snapshot["ui_flags"]["can_continue_internal_medicine"] is True

    second_message_resp = post_json(
        client,
        f"/api/v1/internal-medicine-sessions/{doctor_session_id}/messages",
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "name": "Player",
            "message": "The symptoms are worse today and there is mild chest tightness.",
        },
    )
    assert second_message_resp.status_code == 200

    report_snapshot = get_snapshot(client, patient_id)
    assert report_snapshot["active_visit"]["state"] == "waiting_test"
    assert report_snapshot["latest_test_report"] is not None
    assert report_snapshot["medical_record_summary"] is not None
    assert report_snapshot["ui_flags"]["can_view_test_report"] is True


def test_scene_snapshot_does_not_reuse_round1_dialogue_in_second_consultation(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-33333333"
    triage_session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = post_json(
        client,
        "/api/v1/triage-sessions",
        {
            "patient_id": patient_id,
            "session_id": triage_session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    visit_id = get_data(triage_resp)["visit_id"]
    post_json(client, f"/api/v1/visits/{visit_id}/register", registration_payload("Player"))

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=visit_data)

    assert post_json(client, f"/api/v1/visits/{visit_id}/progress").status_code == 200
    assert post_json(client, f"/api/v1/visits/{visit_id}/enter-consultation").status_code == 200

    create_doctor_resp = post_json(
        client,
        "/api/v1/internal-medicine-sessions",
        {
            "patient_id": patient_id,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert create_doctor_resp.status_code == 200
    round1_session_id = get_data(create_doctor_resp)["session_id"]

    for message in [
        "I have had cough and fever for 3 days, and there are no drug allergies.",
        "The symptoms are worse today and there is mild chest tightness.",
    ]:
        response = post_json(
            client,
            f"/api/v1/internal-medicine-sessions/{round1_session_id}/messages",
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "name": "Player",
                "message": message,
            },
        )
        assert response.status_code == 200

    for event in [
        "request_test_payment",
        "pay_test",
        "start_exam",
        "finish_exam",
        "results_ready",
        "queue_second_consultation",
        "start_second_consultation",
    ]:
        response = post_json(
            client,
            f"/api/v1/encounters/{visit_id}/events",
            {"event": event},
        )
        assert response.status_code == 200

    second_round_snapshot = get_snapshot(client, patient_id)
    assert second_round_snapshot["active_visit"]["state"] == "in_second_consultation"
    assert second_round_snapshot["self_patient"]["lifecycle_state"] == "in_consultation"
    assert second_round_snapshot["active_dialogue"] is None
    assert second_round_snapshot["ui_flags"]["can_start_internal_medicine"] is True

    create_round2_resp = post_json(
        client,
        "/api/v1/internal-medicine-sessions",
        {
            "patient_id": patient_id,
            "name": "Player",
            "visit_id": visit_id,
            "round": 2,
        },
    )
    assert create_round2_resp.status_code == 200
    round2_session_id = get_data(create_round2_resp)["session_id"]

    round2_snapshot = get_snapshot(client, patient_id)
    assert round2_snapshot["active_dialogue"] is not None
    assert round2_snapshot["active_dialogue"]["agent_type"] == "internal_medicine"
    assert round2_snapshot["active_dialogue"]["session_id"] == round2_session_id


def test_scene_snapshot_reflects_surgery_consultation_dialogue(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-44444444"
    triage_session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = post_json(
        client,
        "/api/v1/triage-sessions",
        {
            "patient_id": patient_id,
            "session_id": triage_session_id,
            "name": "Player",
            "symptoms": "minor wound after kitchen knife cut, no fever, no dizziness",
            "onset_time": "today morning",
            "allergies": [],
            "vitals": {"heart_rate": 84, "temp_c": 36.8, "pain_score": 3},
        },
    )
    visit_id = get_data(triage_resp)["visit_id"]
    post_json(client, f"/api/v1/visits/{visit_id}/register", registration_payload("Player"))

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=visit_data)

    assert post_json(client, f"/api/v1/visits/{visit_id}/progress").status_code == 200
    assert post_json(client, f"/api/v1/visits/{visit_id}/enter-consultation").status_code == 200

    ready_snapshot = get_snapshot(client, patient_id)
    assert ready_snapshot["active_visit"]["assigned_department_id"] == "surgery"
    assert ready_snapshot["active_visit"]["active_agent_type"] == "surgery"
    assert ready_snapshot["active_dialogue"] is None
    assert ready_snapshot["ui_flags"]["consultation_agent_type"] == "surgery"
    assert ready_snapshot["ui_flags"]["can_start_consultation"] is True
    assert ready_snapshot["ui_flags"]["can_continue_consultation"] is False

    create_resp = post_json(
        client,
        "/api/v1/surgery-sessions",
        {
            "patient_id": patient_id,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert create_resp.status_code == 200
    surgery_session_id = get_data(create_resp)["session_id"]

    after_create_snapshot = get_snapshot(client, patient_id)
    assert after_create_snapshot["active_dialogue"] is not None
    assert after_create_snapshot["active_dialogue"]["agent_type"] == "surgery"
    assert after_create_snapshot["active_dialogue"]["session_id"] == surgery_session_id
    assert after_create_snapshot["ui_flags"]["consultation_agent_type"] == "surgery"
    assert after_create_snapshot["ui_flags"]["can_start_consultation"] is False
    assert after_create_snapshot["ui_flags"]["can_continue_consultation"] is True
