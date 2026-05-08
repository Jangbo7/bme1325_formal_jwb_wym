import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.common import PatientLifecycleState, VisitLifecycleState


def create_test_client(monkeypatch):
    db_dir = Path(__file__).resolve().parents[1] / "_tmp_test_dbs"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"triage_reuse_guard_{uuid.uuid4().hex[:8]}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def headers():
    return {"X-API-Key": "mock-key-001"}


def test_triage_session_does_not_reuse_waiting_test_visit(monkeypatch):
    client = create_test_client(monkeypatch)
    app = client.app
    patient_repo = app.state.container["patient_repo"]
    visit_repo = app.state.container["visit_repo"]

    old_visit = visit_repo.create(
        patient_id="P-self",
        state=VisitLifecycleState.WAITING_TEST,
        current_node="diagnostic_wait",
        current_department="Auxiliary Diagnostic Center",
        active_agent_type=None,
        data={"diagnostic_session": {"status": "report_generated"}},
    )
    patient_repo.update_patient(
        "P-self",
        lifecycle_state=PatientLifecycleState.IN_TEST.value,
        state="In Test",
        location="Auxiliary Diagnostic Center",
        visit_id=old_visit["id"],
    )

    session_id = f"session-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "new chest tightness",
            "allergies": [],
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["visit_id"] != old_visit["id"]
    assert data["visit_state"] in {"triaging", "waiting_followup", "triaged"}
