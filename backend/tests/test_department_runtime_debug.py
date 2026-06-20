import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.api.routes.department_runtime_debug import _render_initial_department_snapshot


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


def seed_surgery_patient_runtime(client: TestClient, patient_id: str, *, visit_state: str, patient_state: str) -> str:
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
    return visit_id


def seed_internal_patient_runtime(
    client: TestClient,
    patient_id: str,
    *,
    visit_state: str,
    patient_state: str,
    session_id: str | None = None,
) -> str:
    container = client.app.state.container
    encounter = container["encounter_orchestration_service"].create_or_get_encounter(
        patient_id=patient_id,
        patient_name="Internal Player",
    )
    visit_id = encounter["id"]
    visit_data = {"internal_medicine_session_id": session_id} if session_id else {}
    container["visit_repo"].update_visit(
        visit_id,
        state=visit_state,
        assigned_department_id="internal",
        assigned_department_name="Internal Medicine",
        active_agent_type="internal_medicine",
        current_department="Internal Medicine",
        data=visit_data,
    )
    container["patient_repo"].update_patient(
        patient_id,
        name="Internal Player",
        lifecycle_state=patient_state,
        location="Internal Medicine",
        visit_id=visit_id,
    )
    container["department_runtime_service"].sync_patient_runtime(
        patient_id=patient_id,
        visit_id=visit_id,
    )
    return visit_id


def test_department_runtime_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    response = client.get("/department-runtime-debug")
    assert response.status_code == 200
    assert "Department Runtime Debug" in response.text
    assert "legacy_probabilistic_llm" in response.text
    assert "generated-patient probability" in response.text


def test_department_runtime_page_renders_nested_patient_details():
    stats_html, departments_html, unassigned_html, _display = _render_initial_department_snapshot(
        {
            "running": False,
            "mode": "legacy_template",
            "active_count": 1,
            "total_spawned": 1,
            "llm_probability": None,
            "dispatch_count": 0,
            "blocked_count": 0,
            "last_spawn_at": None,
            "last_tick_at": None,
            "departments": [
                {
                    "department_id": "internal",
                    "department_name": "Internal Medicine",
                    "department_agent_enabled": True,
                    "department_capability_class": "agent_enabled",
                    "summary": {
                        "active_count": 1,
                        "pending_registration_count": 0,
                        "waiting_round1_count": 1,
                        "waiting_round2_count": 0,
                        "called_round1_count": 0,
                        "called_round2_count": 0,
                        "in_consultation_round1_count": 0,
                        "in_consultation_round2_count": 0,
                        "in_test_count": 0,
                        "finished_count": 0,
                        "updated_at": "2026-06-06T00:00:00+00:00",
                    },
                    "doctor_slots": [],
                    "rooms": [],
                    "patients": [
                        {
                            "patient_id": "P-TEST-001",
                            "visit_id": "V-TEST-001",
                            "npc_id": "npc-test-001",
                            "visit_state": "in_consultation",
                            "display_stage": "consultation",
                            "dispatch_state": "ready",
                            "consultation_round": 1,
                            "department_status": "in_consultation_round1",
                            "department_flow_status": "in_consultation_round1",
                            "execution_runner_kind": "legacy",
                            "patient_source": "scripted",
                            "generation_hint_department_id": "internal",
                            "generation_hint_department_name": "Internal Medicine",
                            "department_capability_class": "script_only",
                            "current_room_name": "Internal Room 1",
                            "current_room_node_id": "internal_room_1",
                            "queue_kind": "initial_consultation",
                            "current_counterparty": "doctor",
                            "current_dialogue": {
                                "speaker": "patient",
                                "message": "I still have cough.",
                                "direction": "outbound",
                            },
                            "updated_at": "2026-06-06T00:00:01+00:00",
                        }
                    ],
                }
            ],
            "unassigned_patients": [],
        }
    )

    assert "Patient Details" in departments_html
    assert 'data-detail-id="patient-V-TEST-001"' in departments_html
    assert "I still have cough." in departments_html
    assert "source: scripted" in departments_html
    assert "stage/dispatch: consultation / ready / round 1" in departments_html
    assert stats_html
    assert unassigned_html == ""


def test_department_runtime_page_renders_special_outcome_counts():
    stats_html, departments_html, _unassigned_html, _display = _render_initial_department_snapshot(
        {
            "running": False,
            "mode": "intelligent_agent",
            "active_count": 3,
            "total_spawned": 3,
            "llm_probability": None,
            "dispatch_count": 0,
            "blocked_count": 0,
            "currently_blocked_patients": 0,
            "last_spawn_at": None,
            "last_tick_at": None,
            "departments": [
                {
                    "department_id": "internal",
                    "department_name": "Internal Medicine",
                    "department_agent_enabled": True,
                    "department_capability_class": "agent_enabled",
                    "summary": {
                        "active_count": 3,
                        "pending_registration_count": 0,
                        "waiting_round1_count": 0,
                        "waiting_round2_count": 0,
                        "called_round1_count": 0,
                        "called_round2_count": 0,
                        "in_consultation_round1_count": 0,
                        "in_consultation_round2_count": 0,
                        "in_test_count": 0,
                        "finished_count": 3,
                        "updated_at": "2026-06-12T00:00:00+00:00",
                    },
                    "doctor_slots": [],
                    "rooms": [],
                    "patients": [
                        {
                            "patient_id": "P-REF-001",
                            "visit_id": "V-REF-001",
                            "visit_state": "disposition_referral",
                            "primary_disposition": "specialty_referral",
                            "disposition": {"category": "specialty_referral"},
                        },
                        {
                            "patient_id": "P-ER-001",
                            "visit_id": "V-ER-001",
                            "visit_state": "in_emergency",
                            "primary_disposition": "emergency_escalation",
                            "disposition": {"category": "emergency_escalation"},
                        },
                        {
                            "patient_id": "P-ICU-001",
                            "visit_id": "V-ICU-001",
                            "visit_state": "in_icu_rescue",
                            "primary_disposition": "icu_escalation",
                            "disposition": {"category": "icu_rescue"},
                        },
                    ],
                }
            ],
            "unassigned_patients": [],
        }
    )

    assert "<strong>referrals</strong><div>1</div>" in stats_html
    assert "<strong>emergency</strong><div>1</div>" in stats_html
    assert "<strong>icu</strong><div>1</div>" in stats_html
    assert "referral/emergency/icu: 1/1/1" in departments_html


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
            "max_active_patients": 6,
        },
    )
    assert start_resp.status_code == 200
    start_data = get_data(start_resp)
    assert start_data["running"] is True

    for _ in range(40):
        controller.tick_once()
        time.sleep(0.01)

    snapshot_resp = client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers())
    assert snapshot_resp.status_code == 200
    snapshot = get_data(snapshot_resp)
    assert snapshot["running"] is True
    assert snapshot["total_spawned"] >= 6
    assert snapshot["active_count"] <= 6

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
    assert visit_after_triage["assigned_department_name"] == "Internal Medicine"

    triage_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    internal_after_triage = get_department(triage_snapshot, "internal")
    triage_patient = get_patient(triage_snapshot, patient_id)
    assert internal_after_triage["summary"]["pending_registration_count"] == 1
    assert "waiting_round1_count" in internal_after_triage["summary"]
    assert triage_patient["department_flow_status"] == "assigned_pending_registration"
    assert triage_patient["department_status"] == "assigned_pending_registration"
    assert triage_patient["department_round"] == "none"
    assert triage_patient["display_stage"] == "pending_registration"
    assert triage_patient["dispatch_state"] == "ready"
    assert triage_patient["consultation_round"] is None

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
    assert registered_patient["display_stage"] == "waiting_call"
    assert registered_patient["consultation_round"] == 1
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
    assert get_patient(called_snapshot, patient_id)["display_stage"] == "called"

    enter_resp = post_json(client, f"/api/v1/visits/{visit_id}/enter-consultation")
    assert enter_resp.status_code == 200
    in_consult_snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    assert get_patient(in_consult_snapshot, patient_id)["department_flow_status"] == "in_consultation_round1"
    assert get_patient(in_consult_snapshot, patient_id)["display_stage"] == "consultation"
    assert get_patient(in_consult_snapshot, patient_id)["consultation_round"] == 1

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
    assert get_patient(in_test_snapshot, patient_id)["display_stage"] == "testing"

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
    assert waiting_return_patient["display_stage"] == "waiting_call"
    assert waiting_return_patient["consultation_round"] == 2

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
    assert round2_patient["display_stage"] == "consultation"
    assert round2_patient["consultation_round"] == 2


def test_department_runtime_snapshot_assigns_surgery_doctor_slot_and_consult_room(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-SURGERY-001"
    seed_surgery_patient_runtime(
        client,
        patient_id,
        visit_state="in_consultation",
        patient_state="in_consultation",
    )

    snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    surgery_department = get_department(snapshot, "surgery")
    patient = get_patient(snapshot, patient_id)

    assert patient["assigned_department_id"] == "surgery"
    assert patient["assigned_doctor_slot_id"] in {"surgery_doctor_slot_1", "surgery_doctor_slot_2"}
    assert patient["assigned_doctor_slot_name"] in {"Surgery Doctor Slot 1", "Surgery Doctor Slot 2"}
    assert patient["current_room_node_id"] in {"surgery_consult_room_1", "surgery_consult_room_2"}
    assert patient["room_type"] == "consultation"
    assert patient["display_stage"] == "consultation"
    assert patient["resource_assignment"]["consultation_room_id"] == patient["current_room_node_id"]
    assert surgery_department["doctor_slots"]
    assert surgery_department["rooms"]
    assert any(item["active_count"] == 1 for item in surgery_department["doctor_slots"])
    assert any(item["active_count"] == 1 for item in surgery_department["rooms"] if item["room_type"] == "consultation")


def test_department_runtime_snapshot_assigns_internal_room_and_consultation_observability(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-INTERNAL-001"
    session_id = "im-session-test-001"
    seed_internal_patient_runtime(
        client,
        patient_id,
        visit_state="in_consultation",
        patient_state="in_consultation",
        session_id=session_id,
    )
    client.app.state.container["memory_repo"].save_agent_session_memory(
        session_id,
        patient_id,
        {
            "llm_diagnostics": {
                "response_source": "llm_then_validated",
                "llm_error": None,
            }
        },
        "internal_medicine",
    )

    snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    internal_department = get_department(snapshot, "internal")
    patient = get_patient(snapshot, patient_id)

    assert internal_department["department_gate_capacity"] == 2
    assert patient["assigned_department_id"] == "internal"
    assert patient["assigned_doctor_slot_id"] in {"internal_doctor_slot_1", "internal_doctor_slot_2"}
    assert patient["current_room_node_id"] in {"internal_consult_room_1", "internal_consult_room_2"}
    assert patient["room_type"] == "consultation"
    assert patient["display_stage"] == "consultation"
    assert patient["resource_assignment"]["consultation_room_id"] == patient["current_room_node_id"]
    assert patient["latest_consultation_response_source"] == "llm_then_validated"
    assert patient["latest_consultation_llm_error"] is None


def test_department_runtime_snapshot_maps_surgery_procedure_stage_to_department_room(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-SURGERY-002"
    visit_id = seed_surgery_patient_runtime(
        client,
        patient_id,
        visit_state="waiting_outpatient_procedure",
        patient_state="in_test",
    )

    snapshot = get_data(client.get("/api/v1/department-runtime-debug/snapshot", headers=api_headers()))
    surgery_department = get_department(snapshot, "surgery")
    patient = get_patient(snapshot, patient_id)

    assert patient["visit_id"] == visit_id
    assert patient["assigned_department_id"] == "surgery"
    assert patient["current_room_node_id"] == "surgery_outpatient_procedure_room"
    assert patient["current_room_name"] == "Surgery Outpatient Procedure Room"
    assert patient["room_type"] == "outpatient_procedure"
    assert patient["display_stage"] == "procedure"
    assert patient["resource_assignment"]["target_resource_kind"] in {None, "outpatient_procedure"}
    assert any(
        item["node_id"] == "surgery_outpatient_procedure_room" and item["active_count"] == 1
        for item in surgery_department["rooms"]
    )
