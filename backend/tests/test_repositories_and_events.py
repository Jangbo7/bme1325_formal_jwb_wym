from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.events.bus import EventBus
from app.events.subscribers.queue import QueueSubscriber
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository


def test_patient_repo_persists_between_instances(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'repo.db'}")
    db.init_schema()
    repo = PatientRepository(db)
    repo.update_patient("P-self", location="Emergency", priority="H", triage_level=2, triage_note="High risk")
    repo2 = PatientRepository(db)
    patient = repo2.get("P-self")
    assert patient["location"] == "Emergency"
    assert patient["priority"] == "H"


def test_queue_subscriber_creates_ticket(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'events.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    queue_repo = QueueRepository(db)
    bus = EventBus()
    patient_state_machine = PatientStateMachine()
    patient_repo.update_patient("P-self", lifecycle_state="triaged", priority="M", location="General Medicine")
    subscriber = QueueSubscriber(patient_repo, queue_repo, patient_state_machine, bus)
    subscriber.handle_triage_completed(
        {
            "patient_id": "P-self",
            "department": "General Medicine",
            "priority": "M",
        }
    )
    ticket = queue_repo.get_active_ticket_for_patient("P-self")
    patient = patient_repo.get("P-self")
    assert ticket is not None
    assert ticket["department_name"] == "General Medicine"
    assert patient["lifecycle_state"] == "queued"
