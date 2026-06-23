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
from app.services.department_capabilities import DEPARTMENT_CAPABILITY_OVERRIDES, DepartmentCapability, list_departments_for_mode


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


def install_fake_patient_agent(client: TestClient, captured_departments: list[str | None] | None = None):
    service = client.app.state.container["patient_agent_service"]

    def fake_generate_case(seed=None, department_id=None):
        if captured_departments is not None:
            captured_departments.append(department_id)
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
    assert snapshot["currently_blocked_patients"] >= 0
    for department_id in department_ids:
        assert snapshot["department_coverage"].get(department_id, 0) >= 1
    assigned_department_ids = {item["assigned_department_id"] for item in snapshot["patients"]}
    for department_id in department_ids:
        assert department_id in assigned_department_ids

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
    assert all(item["patient_source"] == "scripted" for item in snapshot["patients"])
    assert all(item["llm_mode"] == "offline" for item in snapshot["patients"])
    assert all(item["llm_probability"] == 0.0 for item in snapshot["patients"])


def test_multi_patient_debug_probabilistic_mode_one_probability_spawns_generated_patients_as_unassigned(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    generated_departments: list[str | None] = []
    install_fake_patient_agent(client, captured_departments=generated_departments)
    controller = client.app.state.container["multi_patient_debug_controller"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "legacy_probabilistic_llm",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 10.0,
            "max_active_patients": 4,
            "llm_probability": 1.0,
        },
    )
    assert start_resp.status_code == 200

    controller.tick_once()

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["llm_probability"] == 1.0
    assert snapshot["total_spawned"] == 1
    assert snapshot["active_count"] == 1
    assert len(snapshot["patients"]) == 1
    assert all(item["mode"] == "legacy_probabilistic_llm" for item in snapshot["patients"])
    assert all(item["execution_runner_kind"] == "intelligent" for item in snapshot["patients"])
    assert all(item["patient_source"] == "generated" for item in snapshot["patients"])
    assert all(item["llm_mode"] == "online" for item in snapshot["patients"])
    assert all(item["llm_probability"] == 1.0 for item in snapshot["patients"])
    assert all(item["assigned_department_id"] is None for item in snapshot["patients"])
    assert all(item["target_node_id"] is None for item in snapshot["patients"])
    assert all(item["latest_consultation_response_source"] is None for item in snapshot["patients"])
    assert snapshot["patients"][0]["display_stage"] in {"triage", "unassigned", "pending_registration"}
    assert snapshot["patients"][0]["dispatch_state"] == "ready"
    assert snapshot["patients"][0]["resource_assignment"]["department_id"] is None
    assert snapshot["patients"][0]["blocking"] is None
    assert snapshot["patients"][0]["generation_hint_department_id"] is not None
    assert snapshot["patients"][0]["generation_hint_department_name"] is not None
    assert snapshot["patients"][0]["case_summary"]["generation_hint_department_id"] == snapshot["patients"][0]["generation_hint_department_id"]
    assert snapshot["patients"][0]["medical_record_card"]["status"] == "pending"
    assert snapshot["patients"][0]["medical_record_card"]["structured"]["主诉"] == "无"
    assert generated_departments == [snapshot["patients"][0]["generation_hint_department_id"]]


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
    generated_departments: list[str | None] = []
    install_fake_patient_agent(client, captured_departments=generated_departments)
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
    assert all(item["execution_runner_kind"] == "intelligent" for item in snapshot["patients"])
    assert all(item["department_agent_enabled"] is True for item in snapshot["patients"])
    assert set(generated_departments) == {"internal", "surgery"}
    assert set(item["generation_hint_department_id"] for item in snapshot["patients"]) == {"internal", "surgery"}
    assert set(item["assigned_department_id"] for item in snapshot["patients"]).issubset({"internal", "surgery"})
    assert all(item["case_summary"] is not None for item in snapshot["patients"])
    assert all(item["assigned_department_id"] is not None for item in snapshot["patients"])
    assert all("next_step_at" in item for item in snapshot["patients"])
    assert all(item["display_stage"] is not None for item in snapshot["patients"])
    assert all(item["dispatch_state"] is not None for item in snapshot["patients"])
    assert all(item["resource_assignment"] is not None for item in snapshot["patients"])

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
    assert 'id="patientFilter"' in response.text
    assert "multi-patient-debug-open-details" in response.text
    assert "card--rare-event" in response.text
    assert "Special event color" in response.text
    assert "电子病历卡" in response.text


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
    assert all(item["mode"] == "department_mixed" for item in snapshot["patients"])
    runner_kinds = {item["execution_runner_kind"] for item in snapshot["patients"]}
    assert "legacy" in runner_kinds
    assert "intelligent" in runner_kinds


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


def test_multi_patient_debug_department_mixed_script_only_departments_never_use_real_agent(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    controller = client.app.state.container["multi_patient_debug_controller"]
    patient_agent_service = client.app.state.container["patient_agent_service"]
    internal_medicine_service = client.app.state.container["internal_medicine_service"]
    surgery_service = client.app.state.container.get("surgery_service")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("script-only departments should not use real agent services")

    patient_agent_service.agent.generate_case = fail_if_called
    internal_medicine_service.create_session = fail_if_called
    internal_medicine_service.continue_session = fail_if_called
    if surgery_service is not None:
        surgery_service.create_session = fail_if_called
        surgery_service.continue_session = fail_if_called
    controller._department_ids = ["ophthalmology"]

    start_resp = post_json(
        client,
        "/api/v1/multi-patient-debug/start",
        {
            "mode": "department_mixed",
            "spawn_interval_seconds": 0.0,
            "step_interval_seconds": 0.1,
            "max_active_patients": 1,
        },
    )
    assert start_resp.status_code == 200

    for _ in range(80):
        controller.tick_once()
        time.sleep(0.01)

    snapshot = get_data(client.get("/api/v1/multi-patient-debug/snapshot", headers=api_headers()))
    assert snapshot["total_spawned"] >= 1
    assert all(item["mode"] == "department_mixed" for item in snapshot["patients"])
    assert all(item["assigned_department_id"] == "ophthalmology" for item in snapshot["patients"])
    assert all(item["execution_runner_kind"] == "legacy" for item in snapshot["patients"])
    assert all(item["department_agent_enabled"] is False for item in snapshot["patients"])
    assert all(item["department_capability_class"] == "script_only" for item in snapshot["patients"])


def test_multi_patient_debug_intelligent_mode_accepts_new_agent_enabled_department_via_capability_config(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    generated_departments: list[str | None] = []
    install_fake_patient_agent(client, captured_departments=generated_departments)
    controller = client.app.state.container["multi_patient_debug_controller"]

    monkeypatch.setitem(
        DEPARTMENT_CAPABILITY_OVERRIDES,
        "ophthalmology",
        DepartmentCapability(
            department_id="ophthalmology",
            supports_patient_agent=True,
            supports_consultation_agent=True,
            supports_scripted_fallback=True,
            preferred_runner_kind="intelligent",
        ),
    )
    controller._department_ids = ["ophthalmology"]

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
    assert snapshot["total_spawned"] == 1
    assert snapshot["patients"][0]["mode"] == "intelligent_agent"
    assert snapshot["patients"][0]["execution_runner_kind"] == "intelligent"
    assert snapshot["patients"][0]["generation_hint_department_id"] == "ophthalmology"
    assert generated_departments == ["ophthalmology"]
    assert snapshot["patients"][0]["assigned_department_id"] in {"ophthalmology", "internal", "surgery"}
    assert snapshot["patients"][0]["department_agent_enabled"] is True
    assert snapshot["patients"][0]["department_capability_class"] == "agent_enabled"


def test_list_departments_for_mode_intelligent_uses_capability_config():
    assert list_departments_for_mode("intelligent_agent") == ["internal", "surgery"]
