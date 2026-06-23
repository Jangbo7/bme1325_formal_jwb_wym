import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'medical_record_card.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def api_headers():
    return {"X-API-Key": "mock-key-001"}


def get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def test_medical_record_card_route_returns_pending_when_not_generated(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = "P-MRCARD-PENDING"
    patient_repo = client.app.state.container["patient_repo"]
    visit_repo = client.app.state.container["visit_repo"]
    patient_repo.upsert_basic(patient_id, "Pending Patient")
    visit_row = visit_repo.create(patient_id=patient_id, data={})

    response = client.get(
        f"/api/v1/medical-records/visit/{visit_row['id']}/card",
        headers=api_headers(),
    )

    assert response.status_code == 200
    card = get_data(response)
    assert card["status"] == "pending"
    assert card["structured"]["主诉"] == "无"
    assert card["structured"]["药方"] == []


def test_medical_record_card_service_projects_ready_card_from_visit_data(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = f"P-MRCARD-{uuid.uuid4().hex[:8]}"
    patient_repo = client.app.state.container["patient_repo"]
    visit_repo = client.app.state.container["visit_repo"]
    memory_repo = client.app.state.container["memory_repo"]
    medical_record_card_service = client.app.state.container["medical_record_card_service"]

    patient_repo.upsert_basic(patient_id, "Projected Patient")
    memory_repo.save_shared_memory(
        patient_id,
        {
            "patient_id": patient_id,
            "profile": {
                "name": "Projected Patient",
                "age": 30,
                "sex": "female",
                "allergies": [],
                "allergy_status": "none",
                "chronic_conditions": [],
                "baseline_risk_flags": [],
            },
            "clinical_memory": {
                "chief_complaint": "咳嗽伴低热",
                "symptoms": ["咳嗽", "低热", "咽痛"],
                "onset_time": "2天前",
                "vitals": {"temp_c": 37.8, "heart_rate": 92, "pain_score": 3},
                "risk_flags": [],
                "last_department": "internal",
                "last_triage_level": 3,
            },
        },
    )
    visit_row = visit_repo.create(
        patient_id=patient_id,
        data={
            "simulated_report": {
                "category_label": "医学实验室检查",
                "report_summary": {
                    "key_findings": ["炎症指标轻度升高"],
                    "impression": "建议结合门诊复诊综合判断",
                    "acuity_level": "routine",
                },
            },
            "disposition": {
                "category": "outpatient_treatment",
                "reason": "病情稳定，可继续门诊治疗",
            },
            "prescription_plan": [
                {
                    "drug_name": "阿莫西林",
                    "dose_text": "0.5g",
                    "frequency_text": "每日3次",
                    "duration_text": "5天",
                    "instructions": "饭后服用",
                }
            ],
        },
    )

    card = medical_record_card_service.generate_and_store_for_visit(
        visit_id=visit_row["id"],
        patient_id=patient_id,
        consultation_result={
            "clinical_impression": "考虑上呼吸道感染",
            "followup_recommendation": {"timing": "3天后复诊"},
            "return_precautions": ["高热持续", "呼吸困难"],
            "prescription_plan": [
                {
                    "drug_name": "阿莫西林",
                    "dose_text": "0.5g",
                    "frequency_text": "每日3次",
                    "duration_text": "5天",
                    "instructions": "饭后服用",
                }
            ],
            "primary_disposition": "outpatient_management",
        },
        source="agent_structured",
    )

    assert card["status"] == "ready"
    assert card["source"] == "agent_structured"
    assert card["structured"]["主诉"] == "咳嗽伴低热"
    assert "咳嗽" in card["structured"]["症状"]
    assert "体温 37.8℃" in card["structured"]["生命体征摘要"]
    assert "炎症指标轻度升高" in card["structured"]["检查结果摘要"]
    assert "上呼吸道感染" in card["structured"]["诊断结果摘要"]
    assert card["structured"]["药方"][0]["药物名称"] == "阿莫西林"
    assert card["structured"]["药方"][0]["使用频次"] == "每日3次"
    assert "门诊处理" in card["structured"]["处置摘要"]

    response = client.get(
        f"/api/v1/medical-records/visit/{visit_row['id']}/card",
        headers=api_headers(),
    )
    assert response.status_code == 200
    route_card = get_data(response)
    assert route_card["status"] == "ready"
    assert route_card["structured"]["药方"][0]["药物名称"] == "阿莫西林"
