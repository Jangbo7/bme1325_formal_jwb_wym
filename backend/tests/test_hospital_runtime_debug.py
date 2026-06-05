import time
import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'hospital_runtime_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
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


def seed_surgery_patient_runtime(client: TestClient, patient_id: str, *, visit_state: str, patient_state: str) -> None:
    container = client.app.state.container
    encounter = container["encounter_orchestration_service"].create_or_get_encounter(
        patient_id=patient_id,
        patient_name="Surgery Player",
    )
    visit_id = encounter["id"]
    container["visit_repo"].update_visit(
        visit_id,
        state=visit_state,
        assigned_department_id="surgery",
        assigned_department_name="Surgery",
        active_agent_type="surgery",
        current_department="Surgery",
    )
    container["patient_repo"].update_patient(
        patient_id,
        name="Surgery Player",
        lifecycle_state=patient_state,
        location="Surgery",
        visit_id=visit_id,
    )
    container["department_runtime_service"].sync_patient_runtime(
        patient_id=patient_id,
        visit_id=visit_id,
    )


def test_hospital_runtime_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    response = client.get("/hospital-runtime-debug")
    assert response.status_code == 200
    assert "Hospital Runtime Debug" in response.text
    assert "legacy_probabilistic_llm" in response.text
    assert "LLM Probability" in response.text
    assert client.app.state.container["hospital_supervisor"] is client.app.state.container["multi_patient_debug_controller"]


def test_hospital_runtime_snapshot_has_nodes(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/hospital-runtime-debug/start",
        {
            "mode": "legacy_template",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 8,
        },
    )
    assert start_resp.status_code == 200
    for _ in range(40):
        controller.tick_once()
        time.sleep(0.01)
    snapshot = get_data(client.get("/api/v1/hospital-runtime-debug/snapshot", headers=api_headers()))
    node_ids = {item["node"]["node_id"] for item in snapshot["nodes"]}
    assert {"testing", "payment", "pharmacy"}.issubset(node_ids)
    assert {
        "surgery_consult_room_1",
        "surgery_consult_room_2",
        "surgery_outpatient_procedure_room",
    }.issubset(node_ids)
    assert snapshot["departments"]
    assert snapshot["total_spawned"] >= 8
    assert snapshot["active_count"] <= 8
    assert snapshot["supervisor_mode"] == "engine_driven"
    assert snapshot["fairness_policy"] == "oldest_due_first"
    assert snapshot["node_capacities"]["testing"] == 2


def test_hospital_runtime_snapshot_groups_surgery_patient_into_room_nodes(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    seed_surgery_patient_runtime(
        client,
        "P-SURGERY-HOSP-1",
        visit_state="in_outpatient_procedure",
        patient_state="in_test",
    )

    snapshot = get_data(client.get("/api/v1/hospital-runtime-debug/snapshot", headers=api_headers()))
    procedure_node = next(item for item in snapshot["nodes"] if item["node"]["node_id"] == "surgery_outpatient_procedure_room")
    assert procedure_node["node"]["node_type"] == "room"
    assert procedure_node["node"]["department_id"] == "surgery"
    assert procedure_node["node"]["room_type"] == "outpatient_procedure"
    assert procedure_node["summary"]["active_count"] == 1
    assert any(patient["patient_id"] == "P-SURGERY-HOSP-1" for patient in procedure_node["patients"])
