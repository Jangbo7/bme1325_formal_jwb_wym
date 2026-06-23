import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app


PATIENT_ID = "P-1234abcd"


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
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


def registration_payload(name: str = "Player"):
    return {
        "name": name,
        "sex": "unknown",
        "age": 30,
        "id_number": "TEMP-REG-0001",
    }


def _bootstrap_surgery_visit(client, patient_id: str, *, name: str = "Player"):
    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": patient_id,
            "session_id": f"session-{uuid.uuid4().hex[:8]}",
            "name": name,
            "symptoms": "minor wound after kitchen knife cut, no fever, no dizziness",
            "onset_time": "today morning",
            "allergies": [],
            "vitals": {"heart_rate": 84, "temp_c": 36.8, "pain_score": 3},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = get_data(triage_resp)["visit_id"]

    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload(name),
    )
    assert register_resp.status_code == 200

    visit_repo = client.app.state.container["visit_repo"]
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


def test_create_visit_returns_active_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)

    first = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": PATIENT_ID, "name": "Player"},
    )
    assert first.status_code == 200
    visit_id = get_data(first)["visit"]["id"]

    second = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": PATIENT_ID, "name": "Player"},
    )
    assert second.status_code == 200
    assert get_data(second)["visit"]["id"] == visit_id


def test_triage_session_and_followup_flow(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"
    create_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "chest tightness",
            "vitals": {"heart_rate": 105, "temp_c": 37.1, "pain_score": 5},
        },
    )
    assert create_resp.status_code == 200
    create_data = get_data(create_resp)
    assert create_data["session_id"] == session_id
    assert create_data["visit_id"] is not None
    assert create_data["visit_state"] in {"triaging", "waiting_followup", "triaged"}
    assert create_data["dialogue"]["status"] in {"awaiting_patient_reply", "triaged"}

    reply_resp = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "message": "Symptoms started 30 minutes ago, no allergies, pain is 6/10, no fever",
        },
    )
    assert reply_resp.status_code == 200
    reply_data = get_data(reply_resp)
    assert reply_data["patient"]["id"] == PATIENT_ID
    assert reply_data["visit_id"] == create_data["visit_id"]
    assert reply_data["dialogue"]["status"] in {"awaiting_patient_reply", "triaged"}


def test_register_requires_triaged_visit(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    visit_resp = client.post(
        "/api/v1/visits",
        headers=headers(),
        json={"patient_id": PATIENT_ID, "name": "Player"},
    )
    visit_id = get_data(visit_resp)["visit"]["id"]

    register_name = "Alice Zhang"
    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload(register_name),
    )
    assert register_resp.status_code == 409


def test_register_heals_stale_orchestration_snapshot(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = get_data(triage_resp)["visit_id"]

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["orchestration_state"] = "ARRIVED"
    visit_repo.update_visit(visit_id, data=data)

    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload("Player"),
    )
    assert register_resp.status_code == 200
    assert get_data(register_resp)["visit"]["state"] == "registered"

    updated_visit = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    assert updated_visit.status_code == 200
    assert get_data(updated_visit)["visit"]["data"]["orchestration_state"] == "REGISTERED"


def test_strict_flow_triage_register_wait_call_enter(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
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
    assert triage_data["visit_state"] == "triaged"

    queues_after_triage = client.get("/api/v1/queues", headers=headers())
    all_waiting_after_triage = [ticket for group in get_data(queues_after_triage)["queues"] for ticket in group["waiting"]]
    assert not [ticket for ticket in all_waiting_after_triage if ticket["patient_id"] == PATIENT_ID]

    register_name = "Alice Zhang"
    register_resp = client.post(
        f"/api/v1/visits/{visit_id}/register",
        headers=headers(),
        json=registration_payload(register_name),
    )
    assert register_resp.status_code == 200
    register_data = get_data(register_resp)
    assert register_data["visit"]["state"] == "registered"
    assert register_data["patient"]["lifecycle_state"] == "queued"
    assert register_data["patient"]["name"] == register_name
    assert register_data["queue_ticket"]["status"] == "waiting"
    queues_after_register = client.get("/api/v1/queues", headers=headers())
    assert queues_after_register.status_code == 200
    waiting_after_register = [ticket for group in get_data(queues_after_register)["queues"] for ticket in group["waiting"]]
    self_ticket = next((ticket for ticket in waiting_after_register if ticket["patient_id"] == PATIENT_ID), None)
    assert self_ticket is not None
    assert self_ticket["patient_name"] == register_name

    progress_resp = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp.status_code == 200
    assert get_data(progress_resp)["ready_for_consultation"] is False

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    data = visit_repo.to_view(visit_row).data
    data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=11)).isoformat()
    visit_repo.update_visit(visit_id, data=data)

    progress_resp_2 = client.post(f"/api/v1/visits/{visit_id}/progress", headers=headers())
    assert progress_resp_2.status_code == 200
    progress_data = get_data(progress_resp_2)
    assert progress_data["visit"]["state"] == "waiting_consultation"
    assert progress_data["patient"]["lifecycle_state"] == "called"
    assert progress_data["ready_for_consultation"] is True

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200
    enter_data = get_data(enter_resp)
    assert enter_data["visit"]["state"] == "in_consultation"
    assert enter_data["patient"]["lifecycle_state"] == "in_consultation"


def test_internal_medicine_session_requires_in_consultation_and_can_continue(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "1 day",
            "allergies": [],
            "vitals": {"heart_rate": 88, "temp_c": 37.2, "pain_score": 2},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = get_data(triage_resp)["visit_id"]

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

    blocked_doctor_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert blocked_doctor_resp.status_code == 409

    enter_resp = client.post(f"/api/v1/visits/{visit_id}/enter-consultation", headers=headers())
    assert enter_resp.status_code == 200
    assert get_data(enter_resp)["visit"]["state"] == "in_consultation"

    doctor_create_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert doctor_create_resp.status_code == 200
    doctor_create_data = get_data(doctor_create_resp)
    assert doctor_create_data["visit_id"] == visit_id
    assert doctor_create_data["visit_state"] == "in_consultation"
    assert doctor_create_data["session_id"].startswith("im-session-")

    doctor_message_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "我发热和咳嗽已经3天了，昨晚体温38.5℃，没有药物过敏。",
        },
    )
    assert doctor_message_resp.status_code == 200
    doctor_message_data = get_data(doctor_message_resp)
    assert doctor_message_data["visit_id"] == visit_id
    assert doctor_message_data["session_id"] == doctor_create_data["session_id"]
    assert doctor_message_data["visit_state"] == "in_consultation"
    assert doctor_message_data["dialogue"]["status"] == "awaiting_patient_reply"

    memory_repo = app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(doctor_create_data["session_id"], PATIENT_ID, agent_type="internal_medicine")
    assert session_memory["consultation_progress"]["patient_reply_count"] == 1

    second_message_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "症状今天早上明显加重，还伴有轻微胸闷。",
        },
    )
    assert second_message_resp.status_code == 200
    second_message_data = get_data(second_message_resp)
    assert second_message_data["visit_id"] == visit_id
    assert second_message_data["visit_state"] == "waiting_test"
    assert second_message_data["dialogue"]["status"] == "completed"

    visit_after_consultation_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    assert visit_after_consultation_resp.status_code == 200
    visit_after_consultation = get_data(visit_after_consultation_resp)["visit"]
    assert visit_after_consultation["state"] == "waiting_test"
    diagnostic_session = visit_after_consultation["data"].get("diagnostic_session")
    assert isinstance(diagnostic_session, dict)
    assert diagnostic_session["type"] == "auxiliary_diagnostic_center"
    assert diagnostic_session["status"] == "report_generated"
    assert diagnostic_session["primary_category"] in {"medical_imaging", "medical_laboratory"}
    assert diagnostic_session["primary_category_label"] in {"医学影像检查", "医学实验室检验"}
    assert diagnostic_session["window_label"] in {"医学影像检查窗", "医学实验室检验窗"}
    assert isinstance(diagnostic_session.get("recommended_items"), list)
    assert diagnostic_session.get("recommended_items")
    simulated_report = diagnostic_session.get("report")
    assert isinstance(simulated_report, dict)
    assert simulated_report.get("simulation") is True
    assert simulated_report.get("report_text")
    assert simulated_report.get("category_code") == diagnostic_session["primary_category"]
    assert diagnostic_session["source_session_id"] == doctor_create_data["session_id"]
    assert visit_after_consultation["data"]["internal_medicine_session_id"] == doctor_create_data["session_id"]
    assert visit_after_consultation["data"]["test_category"] == diagnostic_session["primary_category"]
    assert visit_after_consultation["data"].get("simulated_report", {}).get("report_text")

    patient_resp = client.get(f"/api/v1/patients/{PATIENT_ID}", headers=headers())
    assert patient_resp.status_code == 200
    patient_view = get_data(patient_resp)["patient"]
    assert patient_view["lifecycle_state"] == "in_test"
    assert patient_view["active_agent_type"] == "internal_medicine"
    assert patient_view["dialogue_source_agent"] == "internal_medicine"
    assert patient_view["session_refs"]["internal_medicine_session_id"] == doctor_create_data["session_id"]

    request_test_payment_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "request_test_payment"},
    )
    assert request_test_payment_resp.status_code == 200
    assert get_data(request_test_payment_resp)["encounter"]["state"].lower() == "waiting_test_payment"

    pay_test_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "pay_test"},
    )
    assert pay_test_resp.status_code == 200
    assert get_data(pay_test_resp)["encounter"]["state"].lower() == "test_payment_completed"

    start_exam_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "start_exam"},
    )
    assert start_exam_resp.status_code == 200
    assert get_data(start_exam_resp)["encounter"]["state"].lower() == "in_test"

    finish_exam_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "finish_exam"},
    )
    assert finish_exam_resp.status_code == 200
    assert get_data(finish_exam_resp)["encounter"]["state"].lower() == "waiting_return_consultation"

    results_ready_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "results_ready"},
    )
    assert results_ready_resp.status_code == 200
    assert get_data(results_ready_resp)["encounter"]["state"].lower() == "results_ready"

    queue_second_consultation_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "queue_second_consultation"},
    )
    assert queue_second_consultation_resp.status_code == 200
    assert get_data(queue_second_consultation_resp)["encounter"]["state"].lower() == "waiting_second_consultation"

    start_second_consultation_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "start_second_consultation"},
    )
    assert start_second_consultation_resp.status_code == 200
    assert get_data(start_second_consultation_resp)["encounter"]["state"].lower() == "in_second_consultation"

    doctor_round2_create_resp = client.post(
        "/api/v1/internal-medicine-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert doctor_round2_create_resp.status_code == 200
    doctor_round2_create_data = get_data(doctor_round2_create_resp)
    assert doctor_round2_create_data["visit_state"] == "waiting_payment"
    assert doctor_round2_create_data["dialogue"]["status"] == "completed"
    assert doctor_round2_create_data["patient"]["outpatient_flow_finished"] is False
    assert doctor_round2_create_data["patient"]["disposition"]["category"] in {"outpatient_treatment", "followup_booking"}
    assert doctor_round2_create_data["session_id"] != doctor_create_data["session_id"]

    doctor_round2_message_1_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_round2_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "I completed the test and I am back for report review.",
        },
    )
    assert doctor_round2_message_1_resp.status_code == 200
    doctor_round2_message_1_data = get_data(doctor_round2_message_1_resp)
    assert doctor_round2_message_1_data["visit_state"] == "waiting_payment"
    assert doctor_round2_message_1_data["dialogue"]["status"] == "completed"
    assert doctor_round2_message_1_data["patient"]["outpatient_flow_finished"] is False

    doctor_round2_message_2_resp = client.post(
        f"/api/v1/internal-medicine-sessions/{doctor_round2_create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "Please finalize the diagnosis and treatment plan based on the report.",
        },
    )
    assert doctor_round2_message_2_resp.status_code == 200
    doctor_round2_message_2_data = get_data(doctor_round2_message_2_resp)
    assert doctor_round2_message_2_data["visit_state"] == "waiting_payment"
    assert doctor_round2_message_2_data["dialogue"]["status"] == "completed"
    assert doctor_round2_message_2_data["patient"]["outpatient_flow_finished"] is False

    pay_medical_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "pay_medical"},
    )
    assert pay_medical_resp.status_code == 200
    assert get_data(pay_medical_resp)["encounter"]["state"].lower() == "medical_payment_completed"

    plan_disposition_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "plan_disposition"},
    )
    assert plan_disposition_resp.status_code == 200
    assert get_data(plan_disposition_resp)["encounter"]["state"].lower() == "disposition_pending"

    choose_pharmacy_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "choose_pharmacy"},
    )
    assert choose_pharmacy_resp.status_code == 200
    assert get_data(choose_pharmacy_resp)["encounter"]["state"].lower() == "waiting_pharmacy"

    dispense_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "dispense_medication"},
    )
    assert dispense_resp.status_code == 200
    assert get_data(dispense_resp)["encounter"]["state"].lower() == "completed"

    simulated_report_resp = client.get(f"/api/v1/visits/{visit_id}/simulated-report", headers=headers())
    assert simulated_report_resp.status_code == 200
    assert get_data(simulated_report_resp)["report"]["report_text"]

    medical_record_card_resp = client.get(
        f"/api/v1/medical-records/visit/{visit_id}/card",
        headers=headers(),
    )
    assert medical_record_card_resp.status_code == 200
    medical_record_card = get_data(medical_record_card_resp)
    assert medical_record_card["status"] == "ready"
    assert medical_record_card["structured"]["主诉"] != "无"
    assert medical_record_card["structured"]["检查结果摘要"] != "无"
    assert medical_record_card["structured"]["诊断结果摘要"] != "无"
    if medical_record_card["structured"]["药方"]:
        assert medical_record_card["structured"]["药方"][0]["药物名称"] != "无"
        assert "使用频次" in medical_record_card["structured"]["药方"][0]
    assert "药方" in medical_record_card["display_text"]


def test_surgery_session_route_and_patient_view_follow_surgery_assignment(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    triage_session_id = f"session-{uuid.uuid4().hex[:8]}"

    triage_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": triage_session_id,
            "name": "Player",
            "symptoms": "minor wound after kitchen knife cut, no fever, no dizziness",
            "onset_time": "today morning",
            "allergies": [],
            "vitals": {"heart_rate": 84, "temp_c": 36.8, "pain_score": 3},
        },
    )
    assert triage_resp.status_code == 200
    visit_id = get_data(triage_resp)["visit_id"]

    visit_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    assert visit_resp.status_code == 200
    assert get_data(visit_resp)["visit"]["assigned_department_id"] == "surgery"

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
    enter_data = get_data(enter_resp)
    assert enter_data["visit"]["state"] == "in_consultation"
    assert enter_data["visit"]["active_agent_type"] == "surgery"

    create_resp = client.post(
        "/api/v1/surgery-sessions",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "name": "Player",
            "visit_id": visit_id,
        },
    )
    assert create_resp.status_code == 200
    create_data = get_data(create_resp)
    assert create_data["visit_id"] == visit_id
    assert create_data["visit_state"] == "in_consultation"
    assert create_data["session_id"].startswith("surgery-session-")

    get_session_resp = client.get(
        f"/api/v1/surgery-sessions/{create_data['session_id']}",
        headers=headers(),
    )
    assert get_session_resp.status_code == 200
    get_session_data = get_data(get_session_resp)
    assert get_session_data["session_id"] == create_data["session_id"]
    assert get_session_data["visit_id"] == visit_id

    message_resp = client.post(
        f"/api/v1/surgery-sessions/{create_data['session_id']}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "The wound is still painful and swollen, but there is no fever or pus.",
        },
    )
    assert message_resp.status_code == 200
    message_data = get_data(message_resp)
    assert message_data["visit_id"] == visit_id
    assert message_data["session_id"] == create_data["session_id"]
    assert message_data["dialogue"]["status"] in {"awaiting_patient_reply", "completed"}

    patient_resp = client.get(f"/api/v1/patients/{PATIENT_ID}", headers=headers())
    assert patient_resp.status_code == 200
    patient_view = get_data(patient_resp)["patient"]
    assert patient_view["active_agent_type"] == "surgery"
    assert patient_view["dialogue_source_agent"] == "surgery"
    assert patient_view["session_refs"]["surgery_session_id"] == create_data["session_id"]


def test_surgery_procedure_only_path_reaches_round2_with_completed_procedure(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    visit_id = _bootstrap_surgery_visit(client, "P-5555aaaa")
    surgery_service = client.app.state.container["surgery_service"]
    monkeypatch.setattr(surgery_service, "request_consultation_from_llm", lambda *args, **kwargs: None)

    create_resp = client.post(
        "/api/v1/surgery-sessions",
        headers=headers(),
        json={"patient_id": "P-5555aaaa", "name": "Player", "visit_id": visit_id},
    )
    assert create_resp.status_code == 200
    session_id = get_data(create_resp)["session_id"]

    message_resp = client.post(
        f"/api/v1/surgery-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-5555aaaa",
            "visit_id": visit_id,
            "name": "Player",
            "message": "I mainly need a postoperative dressing change. There is no fever, no pus, and the pain is not getting worse.",
        },
    )
    assert message_resp.status_code == 200
    message_data = get_data(message_resp)
    if message_data["visit_state"] == "in_consultation":
        message_resp = client.post(
            f"/api/v1/surgery-sessions/{session_id}/messages",
            headers=headers(),
            json={
                "patient_id": "P-5555aaaa",
                "visit_id": visit_id,
                "name": "Player",
                "message": "The symptoms started yesterday, there are still no drug allergies, and I mainly want the wound redressed.",
            },
        )
        assert message_resp.status_code == 200
        message_data = get_data(message_resp)
    assert message_data["visit_state"] == "waiting_outpatient_procedure"

    visit_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    visit_data = get_data(visit_resp)["visit"]["data"]
    assert visit_data["pre_round2_requirements"]["tests_required"] is False
    assert visit_data["pre_round2_requirements"]["outpatient_procedure_required"] is True
    assert visit_data["outpatient_procedure_plan"]["category"] == "wound_care"

    start_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "start_outpatient_procedure"},
    )
    assert start_resp.status_code == 200
    assert get_data(start_resp)["encounter"]["state"].lower() == "in_outpatient_procedure"

    finish_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "finish_outpatient_procedure"},
    )
    assert finish_resp.status_code == 200
    assert get_data(finish_resp)["encounter"]["state"].lower() == "results_ready"

    queue_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "queue_second_consultation"},
    )
    assert queue_resp.status_code == 200
    start_round2_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "start_second_consultation"},
    )
    assert start_round2_resp.status_code == 200
    assert get_data(start_round2_resp)["encounter"]["state"].lower() == "in_second_consultation"

    round2_create_resp = client.post(
        "/api/v1/surgery-sessions",
        headers=headers(),
        json={"patient_id": "P-5555aaaa", "name": "Player", "visit_id": visit_id, "round": 2},
    )
    assert round2_create_resp.status_code == 200
    round2_data = get_data(round2_create_resp)
    assert round2_data["visit_state"] == "waiting_payment"
    assert round2_data["dialogue"]["status"] == "completed"
    assert round2_data["patient"]["outpatient_flow_finished"] is False
    assert round2_data["patient"]["disposition"]["category"] in {"outpatient_treatment", "followup_booking"}
    assert round2_data["dialogue"]["final_result"]["procedure_recommendation"]["surgery_evaluation_recommended"] is False

    pay_medical_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "pay_medical"},
    )
    assert pay_medical_resp.status_code == 200
    assert get_data(pay_medical_resp)["encounter"]["state"].lower() == "medical_payment_completed"

    plan_disposition_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "plan_disposition"},
    )
    assert plan_disposition_resp.status_code == 200
    assert get_data(plan_disposition_resp)["encounter"]["state"].lower() == "disposition_pending"

    choose_pharmacy_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "choose_pharmacy"},
    )
    assert choose_pharmacy_resp.status_code == 200
    assert get_data(choose_pharmacy_resp)["encounter"]["state"].lower() == "waiting_pharmacy"

    dispense_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "dispense_medication"},
    )
    assert dispense_resp.status_code == 200
    assert get_data(dispense_resp)["encounter"]["state"].lower() == "completed"

    final_visit_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    final_visit_data = get_data(final_visit_resp)["visit"]["data"]
    assert final_visit_data["outpatient_procedure_summary"]["completed"] is True

    medical_record_card_resp = client.get(
        f"/api/v1/medical-records/visit/{visit_id}/card",
        headers=headers(),
    )
    assert medical_record_card_resp.status_code == 200
    medical_record_card = get_data(medical_record_card_resp)
    assert medical_record_card["status"] == "ready"
    assert medical_record_card["structured"]["主诉"] != "无"
    assert medical_record_card["structured"]["处置摘要"] != "无"


def test_surgery_tests_and_procedure_must_both_complete_before_round2(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    visit_id = _bootstrap_surgery_visit(client, "P-6666bbbb")
    surgery_service = client.app.state.container["surgery_service"]
    monkeypatch.setattr(surgery_service, "request_consultation_from_llm", lambda *args, **kwargs: None)

    create_resp = client.post(
        "/api/v1/surgery-sessions",
        headers=headers(),
        json={"patient_id": "P-6666bbbb", "name": "Player", "visit_id": visit_id},
    )
    assert create_resp.status_code == 200
    session_id = get_data(create_resp)["session_id"]

    message_resp = client.post(
        f"/api/v1/surgery-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-6666bbbb",
            "visit_id": visit_id,
            "name": "Player",
            "message": "I cut my forearm on metal. It is still swollen and may need cleaning or dressing before follow-up.",
        },
    )
    assert message_resp.status_code == 200
    message_data = get_data(message_resp)
    if message_data["visit_state"] == "in_consultation":
        message_resp = client.post(
            f"/api/v1/surgery-sessions/{session_id}/messages",
            headers=headers(),
            json={
                "patient_id": "P-6666bbbb",
                "visit_id": visit_id,
                "name": "Player",
                "message": "The cut started today, there are no drug allergies, and it may need cleaning plus follow-up review.",
            },
        )
        assert message_resp.status_code == 200
        message_data = get_data(message_resp)
    assert message_data["visit_state"] == "waiting_outpatient_procedure"

    visit_resp = client.get(f"/api/v1/visits/{visit_id}", headers=headers())
    visit_data = get_data(visit_resp)["visit"]["data"]
    assert visit_data["pre_round2_requirements"]["tests_required"] is True
    assert visit_data["pre_round2_requirements"]["outpatient_procedure_required"] is True

    finish_proc_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "start_outpatient_procedure"},
    )
    assert finish_proc_resp.status_code == 200
    finish_proc_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "finish_outpatient_procedure"},
    )
    assert finish_proc_resp.status_code == 200
    assert get_data(finish_proc_resp)["encounter"]["state"].lower() == "waiting_test"

    blocked_round2_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "queue_second_consultation"},
    )
    assert blocked_round2_resp.status_code == 422
    assert blocked_round2_resp.json()["error"]["code"] == "STATE_TRANSITION_INVALID"

    for event, expected_state in [
        ("request_test_payment", "waiting_test_payment"),
        ("pay_test", "test_payment_completed"),
        ("start_exam", "in_test"),
        ("finish_exam", "waiting_return_consultation"),
        ("results_ready", "results_ready"),
    ]:
        response = client.post(
            f"/api/v1/encounters/{visit_id}/events",
            headers=headers(),
            json={"event": event},
        )
        assert response.status_code == 200
        assert get_data(response)["encounter"]["state"].lower() == expected_state

    queue_resp = client.post(
        f"/api/v1/encounters/{visit_id}/events",
        headers=headers(),
        json={"event": "queue_second_consultation"},
    )
    assert queue_resp.status_code == 200
    assert get_data(queue_resp)["encounter"]["state"].lower() == "waiting_second_consultation"
