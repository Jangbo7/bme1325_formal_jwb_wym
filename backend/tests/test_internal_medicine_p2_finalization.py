import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

PATIENT_ID = "P-11111111"


def create_test_client(monkeypatch):
    db_dir = Path(__file__).resolve().parents[1] / "_tmp_test_dbs"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"test_internal_medicine_p2_{uuid.uuid4().hex[:8]}.db"
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


def prepare_visit_in_consultation(client: TestClient, *, patient_id: str = PATIENT_ID) -> str:
    triage_session_id = f"triage-{uuid.uuid4().hex[:8]}"
    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": patient_id,
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
                "patient_id": patient_id,
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

    app = client.app
    visit_repo = app.state.container["visit_repo"]
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


def send_internal_medicine_message(client: TestClient, session_id: str, visit_id: str, message: str):
    response = client.post(
        f"/api/v1/internal-medicine-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": message,
        },
    )
    assert response.status_code == 200, response.text
    return get_data(response)


def complete_standard_internal_medicine_session(client: TestClient):
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="发热咳嗽",
        symptoms="发热, 咳嗽",
    )
    session_id = create_data["session_id"]

    first_data = send_internal_medicine_message(client, session_id, visit_id, "3天前开始，没有过敏史。")
    assert first_data["dialogue"]["status"] == "awaiting_patient_reply"
    second_data = send_internal_medicine_message(client, session_id, visit_id, "今天早上明显更重，咳嗽更多。")
    assert second_data["dialogue"]["status"] == "completed"
    return visit_id, session_id, second_data


def test_internal_medicine_final_response_has_structured_schema(monkeypatch):
    client = create_test_client(monkeypatch)
    _, _, final_data = complete_standard_internal_medicine_session(client)

    assert final_data["visit_state"] == "waiting_test"
    assert final_data["dialogue"]["message_type"] == "final"
    final_result = final_data["dialogue"]["final_result"]
    expected_keys = {
        "assistant_message",
        "complete",
        "department",
        "priority",
        "diagnosis_level",
        "note",
        "patient_plan",
        "tests_suggested",
        "medication_or_action",
        "red_flags",
    }
    assert expected_keys.issubset(final_result.keys())
    assert final_result["complete"] is True
    assert isinstance(final_result["tests_suggested"], list)
    assert isinstance(final_result["medication_or_action"], list)
    assert isinstance(final_result["red_flags"], list)


def test_internal_medicine_completed_session_reassesses_without_followup(monkeypatch):
    client = create_test_client(monkeypatch)
    visit_id, session_id, _ = complete_standard_internal_medicine_session(client)

    reassessment = send_internal_medicine_message(client, session_id, visit_id, "补充一下，其他情况没有变化。")

    assert reassessment["visit_state"] == "waiting_test"
    assert reassessment["dialogue"]["status"] == "completed"
    assert reassessment["dialogue"]["message_type"] == "final_no_change"
    assert reassessment["dialogue"]["missing_fields"] == []


def test_internal_medicine_red_flags_force_emergency_priority(monkeypatch):
    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="胸痛胸闷",
        symptoms="胸痛, 呼吸困难",
        onset_time="今天早上",
        allergies=[],
        vitals={"heart_rate": 136, "systolic_bp": 88, "diastolic_bp": 58, "pain_score": 8},
    )
    session_id = create_data["session_id"]

    first_data = send_internal_medicine_message(client, session_id, visit_id, "今天早上开始胸痛胸闷，还伴有呼吸困难，没有过敏史。")
    assert first_data["dialogue"]["status"] == "awaiting_patient_reply"

    final_data = send_internal_medicine_message(client, session_id, visit_id, "现在更严重，还是喘不过气。")
    final_result = final_data["dialogue"]["final_result"]

    assert final_data["dialogue"]["message_type"] == "final"
    assert final_result["priority"] == "H"
    assert final_result["department"] == "Emergency"
    assert final_result["icu_escalation"] is True
    assert final_result["red_flags"]
