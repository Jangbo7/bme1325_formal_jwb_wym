import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.agents.internal_medicine.rules import extract_structured_updates, prioritize_missing_fields
from app.main import create_app

PATIENT_ID = "P-11111111"


def create_test_client(monkeypatch):
    db_dir = Path(__file__).resolve().parents[1] / "_tmp_test_dbs"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"test_internal_medicine_followup_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def headers():
    return {
        "X-API-Key": "mock-key-001",
        "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
    }


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def test_extract_structured_updates_handles_chronic_condition_history():
    negative = extract_structured_updates("没有高血压糖尿病")
    assert negative["chronic_conditions"] == []
    assert negative["chronic_conditions_status"] == "known"
    assert "past_medical_history" in negative["extracted_fields"]

    english_negative = extract_structured_updates("I have no hypertension or diabetes.")
    assert english_negative["chronic_conditions"] == []
    assert english_negative["chronic_conditions_status"] == "known"

    positive = extract_structured_updates("有高血压和糖尿病")
    assert positive["chronic_conditions"] == ["hypertension", "diabetes"]
    assert positive["chronic_conditions_status"] == "known"
    assert "past_medical_history" in positive["extracted_fields"]

    uncertain = extract_structured_updates("不太清楚有没有慢性病")
    assert uncertain["chronic_conditions_status"] == "uncertain"
    assert "past_medical_history" in uncertain["extracted_fields"]


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
    assert triage_resp.status_code == 200
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
        assert followup_resp.status_code == 200
        triage_data = get_data(followup_resp)
    assert triage_data["visit_state"] == "triaged", triage_data

    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload("Player"),
    )
    assert register_resp.status_code == 200

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=data)

    progress_resp = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp.status_code == 200
    assert get_data(progress_resp)["visit"]["state"] == "waiting_consultation"

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200
    assert get_data(enter_resp)["visit"]["state"] == "in_consultation"
    return visit_id


def test_prioritize_missing_fields_demotes_recently_asked():
    shared_memory = {
        "profile": {"allergy_status": "unknown"},
        "clinical_memory": {
            "chief_complaint": "胸闷",
            "onset_time": None,
            "symptoms": ["胸闷"],
            "risk_flags": [],
        },
    }

    ordered = prioritize_missing_fields(shared_memory, asked_fields_history=[], last_question_focus=None)
    assert ordered[:2] == ["onset_time", "allergies"]

    reordered = prioritize_missing_fields(
        shared_memory,
        asked_fields_history=["onset_time"],
        last_question_focus="onset_time",
    )
    assert reordered[:2] == ["allergies", "onset_time"]


def test_internal_medicine_repeated_followup_rephrases_and_tracks_progress(monkeypatch):
    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    memory_repo = client.app.state.container["memory_repo"]
    shared_memory = memory_repo.get_shared_memory(PATIENT_ID, "Player")
    shared_memory["clinical_memory"]["onset_time"] = None
    memory_repo.save_shared_memory(PATIENT_ID, shared_memory)

    create_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
            "chief_complaint": "胸闷",
            "allergies": [],
        },
    )
    assert create_resp.status_code == 200
    create_data = get_data(create_resp)
    session_id = create_data["session_id"]

    first_reply = client.post(
        f"/api/v1/internal-medicine-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "还是不太清楚。",
        },
    )
    assert first_reply.status_code == 200
    first_data = get_data(first_reply)
    assert first_data["dialogue"]["status"] == "awaiting_patient_reply"
    assert first_data["dialogue"]["question_focus"] == "onset_time"
    assert first_data["dialogue"]["message_type"] == "followup"
    first_question = first_data["dialogue"]["assistant_message"]

    second_reply = client.post(
        f"/api/v1/internal-medicine-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "我现在还是记不清开始时间。",
        },
    )
    assert second_reply.status_code == 200
    second_data = get_data(second_reply)
    assert second_data["visit_state"] == "in_consultation"
    assert second_data["dialogue"]["status"] == "awaiting_patient_reply"
    assert second_data["dialogue"]["question_focus"] == "onset_time"
    assert second_data["dialogue"]["message_type"] == "followup"
    second_question = second_data["dialogue"]["assistant_message"]
    assert second_question != first_question

    session_memory = memory_repo.get_agent_session_memory(session_id, PATIENT_ID, agent_type="internal_medicine")
    progress = session_memory["consultation_progress"]
    assert progress["last_question_focus"] == "onset_time"
    assert progress["last_question_text"] == second_question
    assert isinstance(progress["last_extracted_fields"], list)
    assert progress["asked_fields_history"][-2:] == ["onset_time", "onset_time"]
