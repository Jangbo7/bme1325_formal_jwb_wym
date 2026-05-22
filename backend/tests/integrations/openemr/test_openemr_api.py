import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

PATIENT_ID = "P-11111111"


def _build_client(monkeypatch, db_name: str) -> TestClient:
    temp_root = Path(__file__).resolve().parents[2] / ".tmp_openemr_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"openemr-api-{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_dir / db_name}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def _headers():
    return {"X-API-Key": "mock-key-001"}


def _write_headers():
    return {
        **_headers(),
        "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
    }


def _get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def test_openemr_health_route_dry_run(monkeypatch):
    monkeypatch.setenv("OPENEMR_ENABLED", "true")
    monkeypatch.setenv("OPENEMR_DRY_RUN", "true")
    client = _build_client(monkeypatch, "openemr_health.db")

    response = client.get("/api/v1/openemr/health", headers=_headers())
    assert response.status_code == 200
    payload = _get_data(response)
    assert payload["mode"] == "dry_run"


def test_openemr_notes_sync_route_is_idempotent_by_default(monkeypatch):
    monkeypatch.setenv("OPENEMR_ENABLED", "true")
    monkeypatch.setenv("OPENEMR_DRY_RUN", "true")
    client = _build_client(monkeypatch, "openemr_notes.db")

    visit_resp = client.post(
        "/api/v1/visits",
        headers=_write_headers(),
        json={"patient_id": PATIENT_ID, "name": "Player"},
    )
    assert visit_resp.status_code == 200
    visit_id = _get_data(visit_resp)["visit"]["id"]

    app = client.app
    visit_repo = app.state.container["visit_repo"]
    visit_row = visit_repo.get(visit_id)
    visit_data = visit_repo.to_view(visit_row).data
    visit_data["simulated_report"] = {
        "category_code": "medical_laboratory",
        "window_label": "Lab Window",
        "report_text": "CBC completed.",
        "report_summary": {"findings": ["WBC elevated"]},
    }
    visit_repo.update_visit(visit_id, data=visit_data)

    first = client.post(f"/api/v1/openemr/sync/visit/{visit_id}/notes", headers=_write_headers())
    second = client.post(f"/api/v1/openemr/sync/visit/{visit_id}/notes", headers=_write_headers())
    assert first.status_code == 200
    assert second.status_code == 200
    second_payload = _get_data(second)
    assert second_payload["triage_note"]["skipped"] is True
    assert second_payload["internal_medicine_note"]["skipped"] is True
    assert second_payload["test_report"]["skipped"] is True

    visit_after = _get_data(client.get(f"/api/v1/visits/{visit_id}", headers=_headers()))["visit"]
    openemr_sync = visit_after["data"].get("openemr_sync", {})
    assert openemr_sync.get("triage_note_id")
    assert openemr_sync.get("internal_medicine_note_id")
    assert openemr_sync.get("test_report_id")
