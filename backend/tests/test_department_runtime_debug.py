import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'department_runtime_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
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


def registration_payload(name: str = "Player"):
    return {
        "name": name,
        "sex": "unknown",
        "age": 30,
        "id_number": "TEMP-REG-0001",
    }


def get_department(snapshot: dict, department_id: str) -> dict:
    return next(item for item in snapshot["departments"] if item["department_id"] == department_id)


def get_patient(snapshot: dict, patient_id: str) -> dict:
    for department in snapshot["departments"]:
        for patient in department["patients"]:
            if patient["patient_id"] == patient_id:
                return patient
    raise AssertionError(f"patient {patient_id} not found in runtime snapshot")


def test_department_runtime_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    response = client.get("/department-runtime-debug")
    assert response.status_code == 200
    assert "Department Runtime Debug" in response.text


def test_department_runtime_debug_start_stop_reset_routes(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/department-runtime-debug/start",
        {
            "mode": "legacy_template",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 2,
        },
    )
    assert start_resp.status_code == 200
    start_data = get_data(start_resp)
    assert start_data["running"] is True

    for _ in range(12):
        controller.tick_once()
        time.sleep(0.01)

    snapshot_resp = client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers())
    assert snapshot_resp.status_code == 200
    snapshot = get_data(snapshot_resp)
    assert snapshot["running"] is True
    assert snapshot["total_spawned"] == 2
    assert snapshot["active_count"] <= 2

    stop_resp = post_json(client, "/api/v1/department-runtime-debug/stop")
    assert stop_resp.status_code == 200
    assert get_data(stop_resp)["running"] is False

    reset_resp = post_json(client, "/api/v1/department-runtime-debug/reset")
    assert reset_resp.status_code == 200
    reset_data = get_data(reset_resp)
    assert reset_data["total_spawned"] == 0
    assert all(not department["patients"] for department in reset_data["departments"])


def test_department_runtime_snapshot_tracks_initial_and_return_queue(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-44444444"
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
    triage_data = get_data(triage_resp)
    visit_id = triage_data["visit_id"]
    visit_after_triage_resp = client.get(f"/api/v1/visits/{visit_id}", headers=api_headers())
    assert visit_after_triage_resp.status_code == 200
    visit_after_triage = get_data(visit_after_triage_resp)["visit"]
    assert visit_after_triage["assigned_department_id"] == "internal"
    assert visit_after_triage["assigned_department_name"] == "General Medicine"

    triage_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    internal_after_triage = get_department(triage_snapshot, "internal")
    triage_patient = get_patient(triage_snapshot, patient_id)
    assert internal_after_triage["summary"]["pending_registration_count"] == 1
    assert "waiting_round1_count" in internal_after_triage["summary"]
    assert triage_patient["department_flow_status"] == "assigned_pending_registration"
    assert triage_patient["department_status"] == "assigned_pending_registration"
    assert triage_patient["department_round"] == "none"

    register_resp = post_json(client, f"/api/v1/visits/{visit_id}/register", registration_payload("Alice Zhang"))
    assert register_resp.status_code == 200
    register_data = get_data(register_resp)
    assert register_data["queue_ticket"]["department_id"] == "internal"
    assert register_data["queue_ticket"]["queue_kind"] == "initial_consultation"

    registered_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    registered_patient = get_patient(registered_snapshot, patient_id)
    assert registered_patient["queue_kind"] == "initial_consultation"
    assert registered_patient["department_flow_status"] == "waiting_queue_round1"
    assert registered_patient["department_status"] == "waiting_queue_round1"
    assert registered_patient["department_round"] == "round1"
    assert get_department(registered_snapshot, "internal")["summary"]["waiting_count"] == 1
    assert get_department(registered_snapshot, "internal")["summary"]["waiting_round1_count"] == 1

    visit_repo = client.app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=visit_data)

    progress_resp = post_json(client, f"/api/v1/visits/{visit_id}/progress")
    assert progress_resp.status_code == 200
    called_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    assert get_patient(called_snapshot, patient_id)["department_flow_status"] == "called_round1"
    assert get_patient(called_snapshot, patient_id)["department_round"] == "round1"

    enter_resp = post_json(client, f"/api/v1/visits/{visit_id}/enter-consultation")
    assert enter_resp.status_code == 200
    in_consult_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    assert get_patient(in_consult_snapshot, patient_id)["department_flow_status"] == "in_consultation_round1"

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

    for message in [
        "I have had cough and fever for 3 days, and there are no drug allergies.",
        "The symptoms are worse today and there is mild chest tightness.",
    ]:
        response = post_json(
            client,
            f"/api/v1/internal-medicine-sessions/{doctor_session_id}/messages",
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "name": "Player",
                "message": message,
            },
        )
        assert response.status_code == 200

    in_test_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    assert get_patient(in_test_snapshot, patient_id)["department_flow_status"] == "in_test"

    for event in [
        "request_test_payment",
        "pay_test",
        "start_exam",
        "finish_exam",
        "results_ready",
        "queue_second_consultation",
    ]:
        response = post_json(
            client,
            f"/api/v1/encounters/{visit_id}/events",
            {"event": event},
        )
        assert response.status_code == 200

    waiting_return_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    waiting_return_patient = get_patient(waiting_return_snapshot, patient_id)
    assert waiting_return_patient["queue_kind"] == "return_consultation"
    assert waiting_return_patient["department_flow_status"] == "waiting_queue_round2"
    assert waiting_return_patient["department_status"] == "waiting_queue_round2"
    assert waiting_return_patient["department_round"] == "round2"

    start_second_resp = post_json(
        client,
        f"/api/v1/encounters/{visit_id}/events",
        {"event": "start_second_consultation"},
    )
    assert start_second_resp.status_code == 200
    round2_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    round2_patient = get_patient(round2_snapshot, patient_id)
    assert round2_patient["queue_kind"] == "return_consultation"
    assert round2_patient["department_flow_status"] == "in_consultation_round2"
    assert round2_patient["department_status"] == "in_consultation_round2"
    assert round2_patient["department_round"] == "round2"
