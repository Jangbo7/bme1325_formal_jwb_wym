import time
import uuid

from fastapi.testclient import TestClient

from app.departments.registry import list_departments
from app.agents.patient_agent.schemas import (
    PatientAgentTurnResult,
    PatientCaseCard,
    PatientProfileCard,
    PatientSymptomFacts,
)
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'multi_patient_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    app = create_app()
    return TestClient(app)


def create_test_client_without_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'multi_patient_debug_no_llm.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("ACTIVE_LLM_PROVIDER", "current")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("CURRENT_LLM_API_KEY", "")
    monkeypatch.setenv("CURRENT_LLM_MODEL", "")
    monkeypatch.setenv("CURRENT_LLM_ENDPOINT", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_V3_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_R1_API_KEY", "")
    monkeypatch.setenv("GPT52_API_KEY", "")
    monkeypatch.setenv("QWEN_API_KEY", "")
    monkeypatch.setenv("QWEN_VL_API_KEY", "")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("ALIYUN_LLM_API_KEY", "")
    monkeypatch.setenv("ALIYUN_LLM_MODEL", "")
    monkeypatch.setenv("ALIYUN_LLM_ENDPOINT", "")
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
        case_id="case-multi-agent-001",
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

    def fake_generate_case(seed=None):
        return sample_case()

    def fake_reply(*, case_card, context):
        return PatientAgentTurnResult(
            message=(
                "My main problem is cough and low fever. "
                "I have cough, sore throat, and a runny nose. "
                "It started 2 days ago. "
                "My temperature is about 37.8 C."
            ),
            used_facts=["chief_complaint", "symptoms", "onset_time", "vitals"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.generate_case = fake_generate_case
    service.agent.reply = fake_reply


def test_multi_patient_debug_legacy_mode_supports_configured_limit_and_department_coverage(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]
    department_ids = [item["id"] for item in list_departments(include_legacy=False)]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_template",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 12,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(60):
        controller.tick_once()
        time.sleep(0.01)

    snapshot_resp = client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers())
    assert snapshot_resp.status_code == 200
    snapshot = get_data(snapshot_resp)
    assert snapshot["total_spawned"] >= 12
    assert snapshot["active_count"] <= 12
    assert len(snapshot["patients"]) == snapshot["total_spawned"]
    assert all(item["mode"] == "legacy_template" for item in snapshot["patients"])
    assert all(item["llm_mode"] == "offline" for item in snapshot["patients"])
    assert all(item["assigned_department_id"] for item in snapshot["patients"])
    assert all(item["assigned_department_name"] for item in snapshot["patients"])
    assert any((item["step_count"] or 0) > 0 for item in snapshot["patients"])
    assert snapshot["supervisor_mode"] == "engine_driven"
    assert snapshot["fairness_policy"] == "oldest_due_first"
    for department_id in department_ids:
        assert snapshot["department_coverage"].get(department_id, 0) >= 1

    stop_resp = post_json(client, "/api/v1/multi-patient-debug/stop")
    assert stop_resp.status_code == 200


def test_multi_patient_debug_legacy_mode_forces_offline_even_when_global_llm_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]
    triage_service = client.app.state.container["triage_service"]
    internal_medicine_service = client.app.state.container["internal_medicine_service"]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM call should not happen in legacy offline mode")

    triage_service.request_triage_from_llm = fail_if_called
    triage_service.request_followup_from_llm = fail_if_called
    internal_medicine_service.request_consultation_from_llm = fail_if_called
    internal_medicine_service.request_follow_up_message_from_llm = fail_if_called

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_template",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 2,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(80):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["total_spawned"] >= 2
    assert snapshot["active_count"] <= 2
    assert len(snapshot["patients"]) == snapshot["total_spawned"]
    assert all(item["llm_mode"] == "offline" for item in snapshot["patients"])
    assert any((item["step_count"] or 0) > 0 for item in snapshot["patients"])


def test_multi_patient_debug_probabilistic_mode_zero_probability_forces_all_offline(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_probabilistic_llm",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 4,
            "llm_probability": 0.0,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(30):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["llm_probability"] == 0.0
    assert snapshot["total_spawned"] >= 4
    assert snapshot["active_count"] <= 4
    assert len(snapshot["patients"]) == snapshot["total_spawned"]
    assert all(item["mode"] == "legacy_probabilistic_llm" for item in snapshot["patients"])
    assert all(item["llm_mode"] == "offline" for item in snapshot["patients"])
    assert all(item["llm_probability"] == 0.0 for item in snapshot["patients"])


def test_multi_patient_debug_probabilistic_mode_one_probability_forces_all_online(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_probabilistic_llm",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 4,
            "llm_probability": 1.0,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(30):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["llm_probability"] == 1.0
    assert snapshot["total_spawned"] >= 4
    assert snapshot["active_count"] <= 4
    assert len(snapshot["patients"]) == snapshot["total_spawned"]
    assert all(item["mode"] == "legacy_probabilistic_llm" for item in snapshot["patients"])
    assert all(item["llm_mode"] == "online" for item in snapshot["patients"])
    assert all(item["llm_probability"] == 1.0 for item in snapshot["patients"])


def test_multi_patient_debug_rejects_invalid_llm_probability(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    response = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_probabilistic_llm",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 1,
            "llm_probability": 1.5,
        },
    )
    assert response.status_code == 422


def test_multi_patient_debug_intelligent_mode_works_with_fake_agent(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "intelligent_agent",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 2,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(30):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["total_spawned"] == 2
    assert len(snapshot["patients"]) == 2
    assert all(item["mode"] == "intelligent_agent" for item in snapshot["patients"])
    assert all(item["case_summary"] is not None for item in snapshot["patients"])
    assert all(item["assigned_department_id"] is not None for item in snapshot["patients"])
    assert all("next_step_at" in item for item in snapshot["patients"])

    stop_resp = post_json(client, "/api/v1/multi-patient-debug/stop")
    assert stop_resp.status_code == 200
    stopped = get_data(stop_resp)
    assert stopped["running"] is False

    reset_resp = post_json(client, "/api/v1/multi-patient-debug/reset")
    assert reset_resp.status_code == 200
    reset_data = get_data(reset_resp)
    assert reset_data["total_spawned"] == 0
    assert reset_data["patients"] == []


def test_multi_patient_debug_page_is_available(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    response = client.get("/multi-patient-debug")
    assert response.status_code == 200
    assert "Multi Patient Debug" in response.text


def test_multi_patient_debug_department_mixed_mode_uses_multiple_agent_types(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)
    triage_service = client.app.state.container["triage_service"]
    internal_medicine_service = client.app.state.container["internal_medicine_service"]
    controller = client.app.state.container["multi_patient_debug_controller"]

    triage_service.request_triage_from_llm = lambda *args, **kwargs: None
    triage_service.request_followup_from_llm = lambda *args, **kwargs: None
    internal_medicine_service.request_consultation_from_llm = lambda *args, **kwargs: None
    internal_medicine_service.request_follow_up_message_from_llm = lambda *args, **kwargs: None

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "department_mixed",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 5,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(30):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    modes = {item["mode"] for item in snapshot["patients"]}
    assert "legacy_template" in modes
    assert "intelligent_agent" in modes


def test_multi_patient_debug_intelligent_mode_exposes_structured_llm_error_in_snapshot(tmp_path, monkeypatch):
    client = create_test_client_without_llm(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "intelligent_agent",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 1,
        },
    )
    assert start_resp.status_code == 200

    controller.tick_once()

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["total_spawned"] == 0
    assert "LLM_UNAVAILABLE" in (snapshot["last_error"] or "")
    assert "\"stage\": \"generate_case\"" in (snapshot["last_error"] or "")
