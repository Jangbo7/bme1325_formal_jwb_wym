from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.events.bus import EventBus
from app.events.subscribers.queue import QueueSubscriber
from app.repositories.agent_memory import AgentMemoryRepository
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


def test_agent_session_memory_uses_composite_primary_key(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'memory_schema.db'}")
    db.init_schema()
    conn = db.connect()
    try:
        rows = conn.execute("PRAGMA table_info(agent_session_memory)").fetchall()
        pk_rows = sorted((row for row in rows if row["pk"] > 0), key=lambda row: row["pk"])
        pk_columns = [row["name"] for row in pk_rows]
        assert pk_columns == ["session_id", "agent_type"]
    finally:
        conn.close()


def test_agent_session_memory_isolated_by_agent_type(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'memory_isolation.db'}")
    db.init_schema()
    memory_repo = AgentMemoryRepository(db)

    shared_session_id = "session-shared"
    memory_repo.save_agent_session_memory(
        shared_session_id,
        "P-self",
        {
            "dialogue_state": "awaiting_patient_reply",
            "assistant_message": "triage followup",
            "message_type": "followup",
        },
        agent_type="triage",
    )
    memory_repo.save_agent_session_memory(
        shared_session_id,
        "P-self",
        {
            "dialogue_state": "completed",
            "assistant_message": "internal medicine final",
            "message_type": "final",
        },
        agent_type="internal_medicine",
    )

    triage_memory = memory_repo.get_agent_session_memory(shared_session_id, "P-self", agent_type="triage")
    internal_memory = memory_repo.get_agent_session_memory(shared_session_id, "P-self", agent_type="internal_medicine")

    assert triage_memory["agent_type"] == "triage"
    assert internal_memory["agent_type"] == "internal_medicine"
    assert triage_memory["assistant_message"] == "triage followup"
    assert internal_memory["assistant_message"] == "internal medicine final"

    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT session_id, agent_type FROM agent_session_memory WHERE session_id = ? ORDER BY agent_type",
            (shared_session_id,),
        ).fetchall()
        assert len(rows) == 2
        assert {(row["session_id"], row["agent_type"]) for row in rows} == {
            (shared_session_id, "triage"),
            (shared_session_id, "internal_medicine"),
        }
    finally:
        conn.close()
