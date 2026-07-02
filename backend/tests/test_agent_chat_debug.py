import uuid

from fastapi.testclient import TestClient

from app.agents.patient_agent.schemas import PatientAgentTurnResult
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'agent_chat_debug.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    monkeypatch.setenv("REDIS_MIRROR_ENABLED", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    return TestClient(create_app())


def api_headers():
    return {"X-API-Key": "mock-key-001"}


def post_json(client: TestClient, path: str, payload: dict | None = None):
    return client.post(
        path,
        headers={**api_headers(), "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
        json=payload if payload is not None else {},
    )


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def install_fake_patient_agent(client: TestClient):
    service = client.app.state.container["patient_agent_service"]

    def fake_reply(*, case_card, context):
        return PatientAgentTurnResult(
            message="I mainly want to know what the result means and what to do next.",
            used_facts=["chief_complaint", "known_test_results"],
            follow_up_question=None,
            policy_state={"phase": context.phase, "summary": "fake policy"},
        )

    service.agent.reply = fake_reply


def test_triage_agent_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/triage-agent-debug")
    assert page.status_code == 200
    assert "Triage Agent Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/triage-agent-debug/preload", {"preset_id": "triage_respiratory_mild"}))
    assert preload["agent_type"] == "triage"
    assert preload["trace"]["rag_hits"]
    assert "merged_payload" in preload["trace"]

    message = get_data(post_json(client, "/api/v1/triage-agent-debug/message", {"message": "It started 2 days ago and my temperature is around 37.8"}))
    assert message["transcript"]
    assert message["latest_reply"] is not None
    assert "parsed_result" in message["trace"]
    assert "memory_delta" in message["trace"]


def test_internal_medicine_agent_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/internal-medicine-agent-debug")
    assert page.status_code == 200
    assert "Internal Medicine Agent Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/internal-medicine-agent-debug/preload", {"preset_id": "im_round2_with_report"}))
    assert preload["agent_type"] == "internal_medicine"
    assert preload["trace"]["extra"]["historical_records_template"] is not None
    assert "simulated_report" in preload["trace"]["merged_payload"]
    assert preload["trace"]["merged_payload"]["previous_round_summary"]["impression"] == "possible gastritis"
    assert preload["trace"]["merged_payload"]["diagnostic_session"]["window_label"] == "Lab Window 2"
    assert preload["trace"]["parsed_result"]["message_type"] == "final"
    assert preload["trace"]["structured_result"] == preload["trace"]["parsed_result"]["final_result"]
    assert preload["trace"]["patient_reply"] == preload["latest_reply"]["content"]
    assert preload["trace"]["patient_reply_source"] == "reply_builder"
    assert preload["trace"]["reassessment_intent"] is None
    assert preload["trace"]["reply_rendering_mode"] is None
    assert "血常规" not in preload["latest_reply"]["content"]
    assert "基础生化" not in preload["latest_reply"]["content"]
    assert "初步问诊" not in preload["latest_reply"]["content"]

    message = get_data(post_json(client, "/api/v1/internal-medicine-agent-debug/message", {"message": "The pain is still there at night, and I want to know what the report means."}))
    assert message["transcript"]
    assert "rag_hits" in message["trace"]
    assert "parsed_result" in message["trace"]
    assert message["trace"]["parsed_result"]["reassessment_intent"] in {"question_only", "question_with_minor_guidance", "result_update"}
    assert message["trace"]["reply_rendering_mode"] in {"answer_only", "answer_plus_guidance", "updated_summary"}


def test_unified_doctor_agent_debug_internal_medicine(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    page = client.get("/doctor-agent-debug")
    assert page.status_code == 200
    assert "Doctor Agent Debug" in page.text
    assert 'presetSelect.addEventListener("change", loadSelectedPreset);' in page.text

    preload = get_data(
        post_json(
            client,
            "/api/v1/doctor-agent-debug/preload",
            {"agent_type": "internal_medicine", "preset_id": "im_round1_respiratory"},
        )
    )
    assert preload["agent_type"] == "internal_medicine"
    assert preload["department_id"] == "internal"
    assert preload["agent_label"] == "Internal Medicine Agent Debug"

    message = get_data(
        post_json(
            client,
            "/api/v1/doctor-agent-debug/message",
            {
                "agent_type": "internal_medicine",
                "message": "The cough is a little worse today and there is still no allergy history.",
            },
        )
    )
    assert message["latest_reply"] is not None
    assert "parsed_result" in message["trace"]

    snapshot = client.get("/api/v1/doctor-agent-debug/snapshot?agent_type=internal_medicine", headers=api_headers())
    assert snapshot.status_code == 200
    assert get_data(snapshot)["session_id"] == message["session_id"]


def test_unified_doctor_agent_debug_auto_advance_physical_exam(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    service = client.app.state.container["internal_medicine_service"]
    service.request_follow_up_message_from_llm = lambda *args, **kwargs: "Please tell me a little more."
    service.request_physical_exam_decision_from_llm = lambda *args, **kwargs: {
        "exam_needed": True,
        "exam_type": "respiratory_basic_exam",
        "exam_targets": ["throat", "lung auscultation"],
        "doctor_action_message": "请让我检查一下您的喉咙和听一下肺部。",
    }
    service.request_physical_exam_result_from_llm = lambda *args, **kwargs: {
        "assistant_message": "您的咽部轻度发红，肺部听诊呼吸音清。",
        "physical_exam": {
            "needed": True,
            "exam_type": "respiratory_basic_exam",
            "exam_targets": ["throat", "lung auscultation"],
            "findings": ["咽部轻度发红", "肺部呼吸音清"],
            "impression": "上呼吸道刺激表现，暂无明显肺部阳性体征",
            "source": "llm_simulated_physical_exam",
        },
    }

    get_data(
        post_json(
            client,
            "/api/v1/doctor-agent-debug/preload",
            {"agent_type": "internal_medicine", "preset_id": "im_round1_respiratory"},
        )
    )
    intent = get_data(
        post_json(
            client,
            "/api/v1/doctor-agent-debug/message",
            {
                "agent_type": "internal_medicine",
                "message": "The cough started yesterday and I have no allergies.",
            },
        )
    )
    result = get_data(post_json(client, "/api/v1/doctor-agent-debug/advance?agent_type=internal_medicine", {}))
    resumed = get_data(post_json(client, "/api/v1/doctor-agent-debug/advance", None))

    assert intent["trace"]["parsed_result"]["message_type"] == "physical_exam_intent"
    assert intent["latest_reply"]["content"] == "请让我检查一下您的喉咙和听一下肺部。"
    assert result["trace"]["parsed_result"]["message_type"] == "physical_exam_result"
    assert result["latest_reply"]["content"] == "您的咽部轻度发红，肺部听诊呼吸音清。"
    assert resumed["trace"]["parsed_result"]["message_type"] == "followup"
    assistant_types = [turn["metadata"].get("message_type") for turn in resumed["transcript"] if turn["role"] == "assistant"]
    assert assistant_types[-3:] == ["physical_exam_intent", "physical_exam_result", "followup"]


def test_doctor_debug_registry_contains_surgery_config(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    registry = client.app.state.container["doctor_debug_registry"]

    surgery_config = registry.get("surgery")
    assert surgery_config.agent_type == "surgery"
    assert surgery_config.department_id == "surgery"
    assert surgery_config.service_container_key == "surgery_service"
    assert surgery_config.supports_round2 is True

    available_agents = client.app.state.container["doctor_agent_debug_controller"].list_available_agents()
    assert any(agent["agent_type"] == "internal_medicine" for agent in available_agents)


def test_unified_doctor_agent_debug_surgery_round2_preload_uses_second_round_context(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    preload = get_data(
        post_json(
            client,
            "/api/v1/doctor-agent-debug/preload",
            {"agent_type": "surgery", "preset_id": "surgery_round2_postop_review"},
        )
    )
    assert preload["agent_type"] == "surgery"
    assert preload["preload_summary"]["consultation_round"] == 2
    assert preload["preload_summary"]["visit_state"] == "in_second_consultation"
    assert preload["trace"]["parsed_result"]["message_type"] == "final"
    assert preload["trace"]["merged_payload"]["previous_round_summary"]["needs_outpatient_procedure"] is True
    assert preload["trace"]["merged_payload"]["diagnostic_session"]["window_label"] == "Surgical Review Desk"
    assert preload["trace"]["merged_payload"]["procedure_completed"] is True
    assert "first-round surgery intake" not in preload["latest_reply"]["content"]


def test_patient_agent_chat_debug_preload_and_message(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    install_fake_patient_agent(client)

    page = client.get("/patient-agent-chat-debug")
    assert page.status_code == 200
    assert "Patient Agent Chat Debug" in page.text

    preload = get_data(post_json(client, "/api/v1/patient-agent-chat-debug/preload", {"preset_id": "patient_gastritis_round2"}))
    assert preload["agent_type"] == "patient_agent"
    assert "case_card" in preload["trace"]["merged_payload"]

    message = get_data(post_json(client, "/api/v1/patient-agent-chat-debug/message", {"message": "What do you want to understand most from this report?"}))
    assert message["latest_reply"] is not None
    assert message["trace"]["parsed_result"]["case_summary"]["case_id"] == "PAC-PRESET-002"
    assert "allowed_fact_keys" in message["trace"]["merged_payload"]["policy_decision"]
    assert len(message["transcript"]) >= 2
