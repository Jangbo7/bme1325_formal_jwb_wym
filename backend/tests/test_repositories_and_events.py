from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.events.bus import EventBus
from app.events.subscribers.queue import QueueSubscriber
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.repositories.visits import VisitRepository


def test_database_schema_contains_visit_columns(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'schema.db'}")
    db.init_schema()
    conn = db.connect()
    try:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "visits" in tables
        patient_cols = {row["name"] for row in conn.execute("PRAGMA table_info(patients)").fetchall()}
        session_cols = {row["name"] for row in conn.execute("PRAGMA table_info(triage_sessions)").fetchall()}
        queue_cols = {row["name"] for row in conn.execute("PRAGMA table_info(queue_tickets)").fetchall()}
        assert "visit_id" in patient_cols
        assert "visit_id" in session_cols
        assert "visit_id" in queue_cols
    finally:
        conn.close()


def test_patient_repo_persists_between_instances(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'repo.db'}")
    db.init_schema()
    repo = PatientRepository(db)
    visit_repo = VisitRepository(db)
    visit = visit_repo.create_or_get_active("P-self")
    repo.update_patient("P-self", location="Emergency", priority="H", triage_level=2, triage_note="High risk", visit_id=visit["id"])
    repo2 = PatientRepository(db)
    patient = repo2.get("P-self")
    assert patient["location"] == "Emergency"
    assert patient["priority"] == "H"
    assert patient["visit_id"] == visit["id"]


def test_queue_subscriber_creates_ticket_with_visit_id(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'events.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    bus = EventBus()
    patient_state_machine = PatientStateMachine()

    visit = visit_repo.create_or_get_active("P-self")
    patient_repo.update_patient("P-self", lifecycle_state="triaged", priority="M", location="General Medicine", visit_id=visit["id"])

    subscriber = QueueSubscriber(patient_repo, queue_repo, patient_state_machine, bus)
    subscriber.handle_triage_completed(
        {
            "patient_id": "P-self",
            "visit_id": visit["id"],
            "department": "General Medicine",
            "priority": "M",
        }
    )

    ticket = queue_repo.get_active_ticket_for_patient("P-self", visit_id=visit["id"])
    patient = patient_repo.get("P-self")
    assert ticket is not None
    assert ticket["department_name"] == "General Medicine"
    assert ticket["visit_id"] == visit["id"]
    assert patient["lifecycle_state"] == "queued"
