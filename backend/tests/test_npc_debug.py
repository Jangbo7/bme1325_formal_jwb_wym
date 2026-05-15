import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'npc_debug.db'}")
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


def test_npc_debug_spawn_snapshot_and_conflict(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    spawn_resp = post_json(client, "/api/v1/npc-debug/spawn", {"profile_id": "respiratory_mild"})
    assert spawn_resp.status_code == 200
    snapshot = get_data(spawn_resp)
    assert snapshot["npc_id"] == "NPC-DEBUG-001"
    assert snapshot["profile_id"] == "respiratory_mild"
    assert snapshot["patient_id"].startswith("P-")
    assert snapshot["encounter_id"].startswith("E-")
    assert snapshot["current_dialogue"] is None
    assert snapshot["step_count"] == 0

    snapshot_resp = client.get("/api/v1/npc-debug/snapshot", headers=api_headers())
    assert snapshot_resp.status_code == 200
    snapshot_data = get_data(snapshot_resp)
    assert snapshot_data["patient_id"] == snapshot["patient_id"]
    assert snapshot_data["encounter_id"] == snapshot["encounter_id"]

    conflict_resp = post_json(client, "/api/v1/npc-debug/spawn", {"profile_id": "abdominal_pain"})
    assert conflict_resp.status_code == 409


def test_npc_debug_step_reaches_waiting_payment_and_records_dialogue(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    spawn_data = get_data(post_json(client, "/api/v1/npc-debug/spawn", {"profile_id": "respiratory_mild"}))
    assert spawn_data["encounter_id"]

    actions = []
    visit_states = []
    saw_non_dialogue_state = False
    final_snapshot = None

    for _ in range(24):
        step_resp = post_json(client, "/api/v1/npc-debug/step")
        assert step_resp.status_code == 200
        snapshot = get_data(step_resp)
        final_snapshot = snapshot
        actions.append(snapshot["last_action"])
        visit_states.append(snapshot["visit_state"])
        if snapshot["current_dialogue"] is None:
            saw_non_dialogue_state = True
        if snapshot["finished"]:
            break

    assert final_snapshot is not None
    assert final_snapshot["finished"] is True
    assert final_snapshot["visit_state"] == "waiting_payment"
    assert "create_triage_session" in actions
    assert "reply_triage" in actions
    assert "register_visit" in actions
    assert "progress_visit" in actions
    assert "enter_consultation" in actions
    assert "create_internal_medicine_session" in actions
    assert "reply_internal_medicine" in actions
    assert "trigger_encounter_event" in actions
    assert "triaged" in visit_states
    assert "waiting_test" in visit_states
    assert "in_second_consultation" in visit_states
    assert saw_non_dialogue_state is True

    transcript = final_snapshot["transcript"]
    assert transcript
    counterparties = {entry["counterparty"] for entry in transcript}
    assert "triage_agent" in counterparties
    assert "internal_medicine_agent" in counterparties
    assert any("[History reviewed]" in entry["message"] for entry in transcript if entry["counterparty"] == "internal_medicine_agent")
    assert final_snapshot["medical_record_summary"] is not None
    assert final_snapshot["medical_record_summary"]["entry_count"] >= 4

    timeline_resp = client.get("/api/v1/npc-debug/medical-record", headers=api_headers())
    assert timeline_resp.status_code == 200
    timeline = get_data(timeline_resp)
    assert timeline is not None
    assert timeline["summary"]["visit_id"] == final_snapshot["encounter_id"]
    entry_types = {entry["entry_type"] for entry in timeline["entries"]}
    assert "triage_note" in entry_types
    assert "initial_consult_note" in entry_types
    assert "test_result_note" in entry_types
    assert "second_consult_note" in entry_types

    mr_resp = client.get(
        f"/api/v1/medical-records/visit/{final_snapshot['encounter_id']}",
        headers=api_headers(),
    )
    assert mr_resp.status_code == 200
    mr_data = get_data(mr_resp)
    assert mr_data["summary"]["record_id"] == timeline["summary"]["record_id"]


def test_npc_debug_reset_keeps_persisted_patient_and_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    spawn_data = get_data(post_json(client, "/api/v1/npc-debug/spawn", {"profile_id": "abdominal_pain"}))
    patient_id = spawn_data["patient_id"]
    encounter_id = spawn_data["encounter_id"]

    step_resp = post_json(client, "/api/v1/npc-debug/step")
    assert step_resp.status_code == 200

    reset_resp = post_json(client, "/api/v1/npc-debug/reset")
    assert reset_resp.status_code == 200
    assert get_data(reset_resp) is None

    snapshot_resp = client.get("/api/v1/npc-debug/snapshot", headers=api_headers())
    assert snapshot_resp.status_code == 200
    assert get_data(snapshot_resp) is None

    patient_repo = client.app.state.container["patient_repo"]
    visit_repo = client.app.state.container["visit_repo"]
    assert patient_repo.get(patient_id) is not None
    assert visit_repo.get(encounter_id) is not None


def test_npc_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    response = client.get("/npc-debug")
    assert response.status_code == 200
    assert "NPC Patient Debug" in response.text
