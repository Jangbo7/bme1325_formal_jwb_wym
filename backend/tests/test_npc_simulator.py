from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.domain.visit.state_machine import VisitStateMachine
from app.events.bus import EventBus
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.repositories.sessions import SessionRepository
from app.repositories.visits import VisitRepository
from app.schemas.common import PatientLifecycleState
from app.services.npc_simulator import NpcPatientSimulator, SIMULATED_PATIENT_ID_PREFIX


def build_simulator(
    *,
    patient_repo,
    visit_repo,
    queue_repo,
    session_repo,
    bus,
    spawn_interval_seconds,
    queue_wait_seconds,
    consult_seconds,
    max_active_patients=2,
):
    return NpcPatientSimulator(
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        session_repo=session_repo,
        patient_state_machine=PatientStateMachine(),
        visit_state_machine=VisitStateMachine(),
        bus=bus,
        enabled=True,
        tick_interval_seconds=1.0,
        spawn_interval_seconds=spawn_interval_seconds,
        max_active_patients=max_active_patients,
        queue_wait_seconds=queue_wait_seconds,
        consult_seconds=consult_seconds,
    )


def test_simulator_limits_active_npc_to_two(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'npc_limit.db'}")
    db.init_schema()

    patient_repo = PatientRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    bus = EventBus()

    simulator = build_simulator(
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        session_repo=session_repo,
        bus=bus,
        spawn_interval_seconds=0,
        queue_wait_seconds=999,
        consult_seconds=999,
        max_active_patients=2,
    )

    for _ in range(10):
        simulator.tick()

    active_npc_rows = [
        row
        for row in patient_repo.list()
        if row["id"].startswith(SIMULATED_PATIENT_ID_PREFIX)
        and row["lifecycle_state"] not in {
            PatientLifecycleState.COMPLETED.value,
            PatientLifecycleState.CANCELLED.value,
            PatientLifecycleState.ERROR.value,
        }
    ]
    assert len(active_npc_rows) == 2


def test_simulator_regenerates_after_completion_without_exceeding_limit(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'npc_regen.db'}")
    db.init_schema()

    patient_repo = PatientRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    bus = EventBus()

    simulator = build_simulator(
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        session_repo=session_repo,
        bus=bus,
        spawn_interval_seconds=0,
        queue_wait_seconds=0,
        consult_seconds=0,
        max_active_patients=2,
    )

    for _ in range(30):
        simulator.tick()

    npc_rows = [row for row in patient_repo.list() if row["id"].startswith(SIMULATED_PATIENT_ID_PREFIX)]
    active_npc_count = simulator.count_active_simulated_patients()
    completed_count = sum(1 for row in npc_rows if row["lifecycle_state"] == PatientLifecycleState.COMPLETED.value)

    assert len(npc_rows) > 2
    assert completed_count >= 1
    assert active_npc_count <= 2


def test_queue_view_exposes_patient_name_for_simulated_patients(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'npc_queue_name.db'}")
    db.init_schema()

    patient_repo = PatientRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    session_repo = SessionRepository(db)
    bus = EventBus()

    simulator = build_simulator(
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        session_repo=session_repo,
        bus=bus,
        spawn_interval_seconds=0,
        queue_wait_seconds=999,
        consult_seconds=999,
        max_active_patients=2,
    )

    simulator.tick()

    queue_views = queue_repo.list_views()
    waiting_tickets = [ticket for queue_view in queue_views for ticket in queue_view.waiting]
    npc_ticket = next(ticket for ticket in waiting_tickets if ticket.patient_id.startswith(SIMULATED_PATIENT_ID_PREFIX))

    assert npc_ticket.patient_name is not None
    assert npc_ticket.patient_name.startswith("NPC ")
