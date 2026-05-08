import uuid
from pathlib import Path

from app.database import Database
from app.events.subscribers.openemr_sync import OpenEMRSyncSubscriber
from app.repositories.sessions import SessionRepository
from app.repositories.visits import VisitRepository


class FakeEMRService:
    def __init__(self, should_raise: bool = False):
        self.should_raise = should_raise
        self.calls = []

    def sync_triage_summary(self, patient_id, visit_id, session_id=None):
        self.calls.append(("triage", patient_id, visit_id, session_id))
        if self.should_raise:
            raise RuntimeError("boom")

    def sync_internal_medicine_summary(self, patient_id, visit_id, session_id=None):
        self.calls.append(("internal", patient_id, visit_id, session_id))
        if self.should_raise:
            raise RuntimeError("boom")

    def sync_test_report(self, patient_id, visit_id):
        self.calls.append(("test", patient_id, visit_id, None))
        if self.should_raise:
            raise RuntimeError("boom")

    def archive_prepared_snapshot_for_visit(self, visit_id):
        self.calls.append(("snapshot", None, visit_id, None))
        if self.should_raise:
            raise RuntimeError("boom")


def _build_db(name: str) -> Database:
    temp_root = Path(__file__).resolve().parents[2] / ".tmp_openemr_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"openemr-subscriber-{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return Database(f"sqlite:///{temp_dir / name}")


def test_subscriber_recovers_missing_ids_from_visit_and_session():
    db = _build_db("subscriber.db")
    db.init_schema()
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    visit = visit_repo.create(patient_id="P-self")
    session_repo.create_or_update(
        session_id="session-1",
        patient_id="P-self",
        dialogue_state="triaged",
        agent_type="triage",
        visit_id=visit["id"],
    )
    visit_repo.update_visit(visit["id"], data={"triage_session_id": "session-1"})

    fake_service = FakeEMRService()
    subscriber = OpenEMRSyncSubscriber(
        emr_service=fake_service,
        visit_repo=visit_repo,
        session_repo=session_repo,
    )
    subscriber.handle_triage_completed({"visit_id": visit["id"]})
    assert fake_service.calls == [("triage", "P-self", visit["id"], "session-1")]


def test_subscriber_failure_does_not_raise():
    db = _build_db("subscriber_failure.db")
    db.init_schema()
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    visit = visit_repo.create(patient_id="P-self")

    subscriber = OpenEMRSyncSubscriber(
        emr_service=FakeEMRService(should_raise=True),
        visit_repo=visit_repo,
        session_repo=session_repo,
    )
    subscriber.handle_test_report_generated({"patient_id": "P-self", "visit_id": visit["id"]})


def test_visit_state_changed_registered_triggers_prepared_snapshot():
    db = _build_db("subscriber_snapshot.db")
    db.init_schema()
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    visit = visit_repo.create(patient_id="P-self")
    visit_repo.update_visit(visit["id"], state="registered")

    fake_service = FakeEMRService()
    subscriber = OpenEMRSyncSubscriber(
        emr_service=fake_service,
        visit_repo=visit_repo,
        session_repo=session_repo,
    )
    subscriber.handle_visit_state_changed({"visit_id": visit["id"], "state": "registered"})
    assert ("snapshot", None, visit["id"], None) in fake_service.calls
