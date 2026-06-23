import uuid

from fastapi.testclient import TestClient

from app.agents.test_simulator.service import TestSimulationAgent
from app.main import create_app


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test_report_generation.db'}")
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


def test_test_simulator_generates_structured_chinese_laboratory_report():
    agent = TestSimulationAgent()

    report = agent.generate_report(
        {
            "diagnosis_level": 1,
            "priority": "M",
            "test_items": ["血常规", "C反应蛋白", "基础生化"],
        },
        {"clinical_memory": {"symptoms": ["发热", "咳嗽"]}},
    )

    assert report["report_type"] == "medical_laboratory"
    assert report["template_version"] == "cn_structured_v1"
    assert report["preliminary_assessment"]["review_required"] is True
    assert "二轮医生复核" in report["preliminary_assessment"]["review_note"]
    assert report["display_text_cn"]
    assert "检查类型" in report["display_text_cn"]
    assert "Simulated auxiliary report" not in report["display_text_cn"]
    assert any(item["unit"] for item in report["report_items"])
    assert any(item["is_abnormal"] for item in report["report_items"])


def test_test_simulator_generates_structured_chinese_imaging_report():
    agent = TestSimulationAgent()

    report = agent.generate_report(
        {
            "diagnosis_level": 3,
            "priority": "M",
            "test_category": "medical_imaging",
            "test_items": ["胸部X线", "床旁超声"],
        },
        {"clinical_memory": {"symptoms": ["咳嗽", "胸闷"]}},
    )

    assert report["report_type"] == "medical_imaging"
    assert report["preliminary_assessment"]["review_required"] is True
    assert report["display_text_cn"]
    assert any(item["body_part"] for item in report["report_items"])
    assert any(item["finding"] for item in report["report_items"])
    assert any(item["impression"] for item in report["report_items"])
    assert "检查类型" in report["display_text_cn"]


def test_simulated_report_route_returns_normalized_structured_report(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    patient_id = f"P-REPORT-{uuid.uuid4().hex[:8]}"
    patient_repo = client.app.state.container["patient_repo"]
    visit_repo = client.app.state.container["visit_repo"]

    patient_repo.upsert_basic(patient_id, "Report Route Patient")
    visit_row = visit_repo.create(
        patient_id=patient_id,
        data={
            "simulated_report": {
                "category_code": "medical_laboratory",
                "category_label": "医学实验室检查",
                "test_items": ["血常规"],
                "report_summary": {
                    "key_findings": ["炎症指标轻度升高"],
                    "acuity_level": "routine",
                },
            }
        },
    )

    response = client.get(
        f"/api/v1/visits/{visit_row['id']}/simulated-report",
        headers=api_headers(),
    )
    assert response.status_code == 200
    payload = get_data(response)
    report = payload["report"]

    assert report["report_type"] == "medical_laboratory"
    assert report["display_text_cn"]
    assert report["preliminary_assessment"]["review_required"] is True
    assert isinstance(report["report_items"], list)
    assert report["report_items"]
