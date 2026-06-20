import time
import uuid

from fastapi.testclient import TestClient

from app.agents.patient_agent.schemas import (
    PatientAgentTurnResult,
    PatientCaseCard,
    PatientProfileCard,
    PatientSymptomFacts,
)
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'runtime_console.db'}")
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


def sample_case() -> PatientCaseCard:
    return PatientCaseCard(
        case_id="case-runtime-console-001",
        patient_profile=PatientProfileCard(
            name="Lin Wei",
            age=29,
            sex="female",
            allergies=[],
            chronic_conditions=[],
        ),
        chief_complaint="Cough and low fever",
        present_illness="Cough started 2 days ago and became more obvious yesterday.",
        symptom_facts=PatientSymptomFacts(
            symptoms=["cough", "sore throat", "runny nose"],
            onset_time="2 days ago",
            vitals={"temp_c": 37.8, "heart_rate": 92, "pain_score": 3},
            associated_symptoms=["dry throat"],
            negatives=["no chest pain"],
            aggravating_factors=["talking a lot"],
            relieving_factors=["rest"],
        ),
        communication_style="calm and cooperative",
        hidden_diagnosis_hint="viral upper respiratory infection",
        patient_goals=["understand whether it is serious", "get treatment advice"],
        forbidden_reveals=["viral upper respiratory infection"],
    )


def install_fake_patient_agent(client: TestClient):
    service = client.app.state.container["patient_agent_service"]

    def fake_generate_case(seed=None, department_id=None):
        return sample_case()

    def fake_reply(*, case_card, context):
        return PatientAgentTurnResult(
            message="I have cough, sore throat and low fever for 2 days.",
            used_facts=["chief_complaint", "symptoms", "onset_time"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.generate_case = fake_generate_case
    service.agent.reply = fake_reply


def test_runtime_console_page_and_idle_snapshot_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    response = client.get("/runtime-console")
    assert response.status_code == 200
    assert "Runtime Console" in response.text
    assert "patient-row--rare-event" in response.text
    assert "Special event color" in response.text
    assert 'id="fullviewStepGate"' in response.text
    assert 'id="applyConfigBtn"' in response.text
    assert "/fullview-sync-monitor" in response.text
    snapshot = get_data(client.get("/api/v1/runtime-console/snapshot", headers=api_headers()))
    assert snapshot["session"]["status"] == "idle"
    assert snapshot["global_config"]["active_mix_mode"] == "strict_ratio"
    assert snapshot["department_configs"]


def test_fullview_sync_monitor_is_backend_hosted_and_can_toggle_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("FULLVIEW_SYNC_ENABLED", "true")
    monkeypatch.setenv("FULLVIEW_STEP_GATE_ENABLED", "false")
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/fullview-sync-monitor")
    assert page.status_code == 200
    assert "Fullview Sync Monitor" in page.text
    assert "does not modify the Fullview frontend" in page.text

    before = client.get("/api/v1/fullview-sync/control", headers=api_headers())
    assert before.status_code == 200
    assert get_data(before)["control"]["gate"]["enabled"] is False

    updated = client.post(
        "/api/v1/fullview-sync/control",
        headers={**api_headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
        json={"enabled": True},
    )
    assert updated.status_code == 200
    assert get_data(updated)["control"]["gate"]["enabled"] is True


def test_runtime_console_start_creates_session_and_strict_active_ratio(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    controller = client.app.state.container["hospital_supervisor"]

    response = post_json(
        client,
        "/api/v1/runtime-console/session/start",
        {
            "global_config": {
                "max_active_patients": 4,
                "active_mix_mode": "strict_ratio",
                "active_agent_ratio": 0.5,
                "fullview_step_gate_enabled": True,
                "agent_spawn_interval_seconds": 0.0,
                "agent_step_interval_seconds": 10.0,
                "script_spawn_interval_seconds": 0.0,
                "script_step_interval_seconds": 10.0,
            }
        },
    )
    assert response.status_code == 200

    for _ in range(6):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/runtime-console/snapshot", headers=api_headers()))
    assert snapshot["session"]["session_id"]
    assert snapshot["session"]["status"] == "running"
    assert snapshot["active_count"] == 4
    assert snapshot["active_agent_target"] == 2
    assert snapshot["active_script_target"] == 2
    assert snapshot["active_agent_count"] == 2
    assert snapshot["active_script_count"] == 2
    assert snapshot["global_config"]["fullview_step_gate_enabled"] is True
    assert len(snapshot["recent_events"]) >= 4


def test_runtime_console_can_toggle_fullview_step_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("FULLVIEW_SYNC_ENABLED", "true")
    monkeypatch.setenv("FULLVIEW_STEP_GATE_ENABLED", "true")
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["hospital_supervisor"]

    start = post_json(
        client,
        "/api/v1/runtime-console/session/start",
        {
            "global_config": {
                "max_active_patients": 1,
                "active_mix_mode": "strict_ratio",
                "active_agent_ratio": 0.0,
                "fullview_step_gate_enabled": True,
                "agent_spawn_interval_seconds": 60,
                "agent_step_interval_seconds": 2,
                "script_spawn_interval_seconds": 60,
                "script_step_interval_seconds": 2,
            }
        },
    )
    assert start.status_code == 200
    assert controller._fullview_step_gate_enabled is True  # noqa: SLF001

    updated = post_json(
        client,
        "/api/v1/runtime-console/config/global",
        {
            "global_config": {
                "max_active_patients": 1,
                "active_mix_mode": "strict_ratio",
                "active_agent_ratio": 0.0,
                "fullview_step_gate_enabled": False,
                "agent_spawn_interval_seconds": 60,
                "agent_step_interval_seconds": 2,
                "script_spawn_interval_seconds": 60,
                "script_step_interval_seconds": 2,
            }
        },
    )
    assert updated.status_code == 200
    snapshot = get_data(updated)
    assert snapshot["global_config"]["fullview_step_gate_enabled"] is False
    assert controller._fullview_step_gate_enabled is False  # noqa: SLF001


def test_runtime_console_pause_step_freezes_progress(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    controller = client.app.state.container["hospital_supervisor"]

    start_resp = post_json(
        client,
        "/api/v1/runtime-console/session/start",
        {
            "global_config": {
                "max_active_patients": 2,
                "active_mix_mode": "strict_ratio",
                "active_agent_ratio": 0.5,
                "agent_spawn_interval_seconds": 0.0,
                "agent_step_interval_seconds": 0.1,
                "script_spawn_interval_seconds": 0.0,
                "script_step_interval_seconds": 0.1,
            }
        },
    )
    assert start_resp.status_code == 200
    for _ in range(5):
        controller.tick_once()
        time.sleep(0.01)

    before = get_data(client.get("/api/v1/runtime-console/patients", headers=api_headers()))
    before_steps = {item["patient_id"]: item["step_count"] for item in before}
    pause_resp = post_json(client, "/api/v1/runtime-console/session/command", {"command": "pause_step"})
    assert pause_resp.status_code == 200

    for _ in range(5):
        controller.tick_once()
        time.sleep(0.01)

    after = get_data(client.get("/api/v1/runtime-console/patients", headers=api_headers()))
    after_steps = {item["patient_id"]: item["step_count"] for item in after}
    assert after_steps == before_steps


def test_runtime_console_emits_spawn_skipped_when_no_agent_department_allowed(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    controller = client.app.state.container["hospital_supervisor"]
    service = client.app.state.container["runtime_console_service"]
    department_configs = service.default_department_configs()
    disabled_agent_configs = [
        {
            **config.model_dump(),
            "allow_agent_patients": False,
        }
        for config in department_configs
    ]

    start_resp = post_json(
        client,
        "/api/v1/runtime-console/session/start",
        {
            "global_config": {
                "max_active_patients": 2,
                "active_mix_mode": "strict_ratio",
                "active_agent_ratio": 1.0,
                "agent_spawn_interval_seconds": 0.0,
                "agent_step_interval_seconds": 10.0,
                "script_spawn_interval_seconds": 10.0,
                "script_step_interval_seconds": 10.0,
            },
            "department_configs": disabled_agent_configs,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(3):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/runtime-console/snapshot", headers=api_headers()))
    assert snapshot["total_spawned"] == 0
    events = get_data(client.get("/api/v1/runtime-console/events", headers=api_headers()))
    assert any(event["event_type"] == "spawn_skipped" for event in events)

def test_runtime_cleanup_deletes_only_spawned_session_patients():
    from app.services.runtime_console_service import RuntimeConsoleService

    class RepoStub:
        def list_spawned_patient_ids(self, session_id=None):
            assert session_id == "runtime-session-test"
            return ["P-a1b2c3d4", "P-b1c2d3e4"]

    class SyncRepoStub:
        def __init__(self):
            self.calls = []

        def skip_unfinished_for_patients(self, patient_ids, *, reason):
            self.calls.append((patient_ids, reason))
            return 4

    class CleanupSchedulerStub:
        def __init__(self):
            self.deleted_patient_ids = []

        def drain_cleanup(self, patient_ids):
            self.deleted_patient_ids.extend(patient_ids)
            return {patient_id: "deleted" for patient_id in patient_ids}

    sync_repo = SyncRepoStub()
    cleanup_scheduler = CleanupSchedulerStub()
    service = RuntimeConsoleService(
        repo=RepoStub(),
        department_runtime_service=None,
        fullview_event_listener=cleanup_scheduler,
        fullview_sync_repo=sync_repo,
        fullview_sync_enabled=True,
    )

    result = service.cleanup_runtime_patients("runtime-session-test")

    assert result["patient_count"] == 2
    assert result["skipped_commands"] == 4
    assert result["deleted"] == ["P-a1b2c3d4", "P-b1c2d3e4"]
    assert result["failed"] == []
    assert cleanup_scheduler.deleted_patient_ids == ["P-a1b2c3d4", "P-b1c2d3e4"]
    assert sync_repo.calls[0][0] == ["P-a1b2c3d4", "P-b1c2d3e4"]


def test_runtime_cleanup_treats_missing_fullview_patient_as_already_deleted():
    from app.services.runtime_console_service import RuntimeConsoleService

    class RepoStub:
        def list_spawned_patient_ids(self, session_id=None):
            return ["P-a1b2c3d4"]

    class CleanupSchedulerStub:
        def drain_cleanup(self, patient_ids):
            return {patient_id: "deleted" for patient_id in patient_ids}

    service = RuntimeConsoleService(
        repo=RepoStub(),
        department_runtime_service=None,
        fullview_event_listener=CleanupSchedulerStub(),
        fullview_sync_repo=None,
        fullview_sync_enabled=True,
    )

    result = service.cleanup_runtime_patients()

    assert result["deleted"] == ["P-a1b2c3d4"]
    assert result["failed"] == []


def test_prepare_local_runtime_reset_captures_ids_without_clearing_before_cleanup():
    from app.services.runtime_console_service import RuntimeConsoleService

    class DatabaseStub:
        def __init__(self):
            self.reset_calls = 0

        def reset_runtime_data(self):
            self.reset_calls += 1

    class RepoStub:
        def __init__(self):
            self.db = DatabaseStub()

        def list_spawned_patient_ids(self, session_id=None):
            assert session_id == "runtime-session-test"
            return ["P-a1b2c3d4"]

    class SyncRepoStub:
        def skip_unfinished_for_patients(self, patient_ids, *, reason):
            assert patient_ids == ["P-a1b2c3d4"]
            assert "reset" in reason
            return 3

        def list_managed_patient_ids(self):
            return ["P-a1b2c3d4"]

    repo = RepoStub()
    service = RuntimeConsoleService(
        repo=repo,
        department_runtime_service=None,
        fullview_client=None,
        fullview_sync_repo=SyncRepoStub(),
        fullview_sync_enabled=True,
    )

    plan = service.prepare_local_runtime_reset("runtime-session-test")

    assert plan["patient_ids"] == ["P-a1b2c3d4"]
    assert plan["skipped_commands"] == 3
    assert repo.db.reset_calls == 0


def test_runtime_control_request_does_not_wait_for_patient_step_lock(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["hospital_supervisor"]

    controller._lock.acquire()  # noqa: SLF001
    try:
        started = time.perf_counter()
        controller.request_runtime_console_command("pause_step")
        elapsed = time.perf_counter() - started
        assert elapsed < 0.2
    finally:
        controller._lock.release()  # noqa: SLF001

    controller._control_queue.join()  # noqa: SLF001
    assert controller.get_runtime_session().step_paused is True
