import uuid
from pathlib import Path
import json

from app.database import Database
from app.integrations.openemr.schemas import OpenEMRSyncResult
from app.integrations.openemr.service import EMRService
from app.repositories.agent_memory import AgentMemoryRepository
from app.repositories.patients import PatientRepository
from app.repositories.sessions import SessionRepository
from app.repositories.visits import VisitRepository


class FakeOpenEMRClient:
    def __init__(self):
        self.patient_calls = 0
        self.encounter_calls = 0
        self.note_calls = 0
        self.report_calls = 0

    def create_or_update_patient(self, payload):
        self.patient_calls += 1
        return OpenEMRSyncResult(
            ok=True,
            external_id=f"ext-p-{payload.local_patient_id}",
            resource_type="Patient",
            operation="create_or_update",
        )

    def create_encounter(self, payload):
        self.encounter_calls += 1
        return OpenEMRSyncResult(
            ok=True,
            external_id=f"ext-e-{payload.local_visit_id}",
            resource_type="Encounter",
            operation="create",
        )

    def add_encounter_note(self, payload):
        self.note_calls += 1
        return OpenEMRSyncResult(
            ok=True,
            external_id=f"note-{payload.note_type}-{self.note_calls}",
            resource_type="DocumentReference",
            operation="add_note",
        )

    def add_test_report(self, payload):
        self.report_calls += 1
        return OpenEMRSyncResult(
            ok=True,
            external_id=f"report-{self.report_calls}",
            resource_type="DocumentReference",
            operation="add_test_report",
        )


class FailingOpenEMRClient(FakeOpenEMRClient):
    def create_or_update_patient(self, payload):
        self.patient_calls += 1
        return OpenEMRSyncResult(
            ok=False,
            external_id=None,
            resource_type="Patient",
            operation="create_or_update",
            error="forced failure",
        )


def build_service():
    temp_root = Path(__file__).resolve().parents[2] / ".tmp_openemr_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"openemr-test-{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    db = Database(f"sqlite:///{temp_dir / 'service_openemr.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    memory_repo = AgentMemoryRepository(db)
    client = FakeOpenEMRClient()
    service = EMRService(
        client=client,
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
    )
    return service, client, patient_repo, visit_repo


def test_patient_and_encounter_sync_idempotent():
    service, client, patient_repo, visit_repo = build_service()
    visit = visit_repo.create(patient_id="P-self")

    first_patient = service.ensure_patient_synced("P-self")
    second_patient = service.ensure_patient_synced("P-self")
    assert first_patient.ok is True
    assert second_patient.skipped is True
    assert client.patient_calls == 1

    first_visit = service.ensure_visit_encounter_synced(visit["id"])
    second_visit = service.ensure_visit_encounter_synced(visit["id"])
    assert first_visit.ok is True
    assert second_visit.skipped is True
    assert client.encounter_calls == 1

    patient = patient_repo.get("P-self")
    updated_visit = visit_repo.get(visit["id"])
    assert patient["openemr_patient_id"] == "ext-p-P-self"
    assert updated_visit["openemr_encounter_id"] == f"ext-e-{visit['id']}"


def test_note_and_report_sync_idempotent_with_force():
    service, client, patient_repo, visit_repo = build_service()
    visit = visit_repo.create(patient_id="P-self")
    visit_repo.update_visit(
        visit["id"],
        data={
            "simulated_report": {
                "category_code": "medical_laboratory",
                "window_label": "Lab Window",
                "report_text": "CBC completed.",
                "report_summary": {"findings": ["WBC elevated"]},
            }
        },
    )

    triage_first = service.sync_triage_summary("P-self", visit["id"])
    triage_second = service.sync_triage_summary("P-self", visit["id"])
    triage_force = service.sync_triage_summary("P-self", visit["id"], force=True)
    assert triage_first.ok is True
    assert triage_second.skipped is True
    assert triage_force.ok is True

    internal_first = service.sync_internal_medicine_summary("P-self", visit["id"])
    internal_second = service.sync_internal_medicine_summary("P-self", visit["id"])
    assert internal_first.ok is True
    assert internal_second.skipped is True

    report_first = service.sync_test_report("P-self", visit["id"])
    report_second = service.sync_test_report("P-self", visit["id"])
    report_force = service.sync_test_report("P-self", visit["id"], force=True)
    assert report_first.ok is True
    assert report_second.skipped is True
    assert report_force.ok is True

    visit_after = visit_repo.to_view(visit_repo.get(visit["id"])).data
    openemr_sync = visit_after.get("openemr_sync", {})
    assert openemr_sync.get("triage_note_id")
    assert openemr_sync.get("internal_medicine_note_id")
    assert openemr_sync.get("test_report_id")
    assert client.note_calls >= 3
    assert client.report_calls >= 2


def test_prepared_payload_archived_even_when_sync_fails():
    temp_root = Path(__file__).resolve().parents[2] / ".tmp_openemr_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"openemr-prepared-log-{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    prepared_log_path = temp_dir / "prepared.log"

    db = Database(f"sqlite:///{temp_dir / 'prepared_service.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    memory_repo = AgentMemoryRepository(db)
    client = FailingOpenEMRClient()
    service = EMRService(
        client=client,
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        prepared_log_path=str(prepared_log_path),
    )

    result = service.ensure_patient_synced("P-self")
    assert result.ok is False
    assert prepared_log_path.exists()
    lines = [line for line in prepared_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    last_record = json.loads(lines[-1])
    assert last_record["resource_type"] == "Patient"
    assert last_record["operation"] == "create_or_update"
    assert last_record["payload"]["local_patient_id"] == "P-self"
