from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import Database
from app.repositories.fullview_sync import FullviewSyncRepository
from app.services.fullview_sync import FullviewEventListener, FullviewSyncWorker


def iso_offset(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class EventClient:
    def __init__(self, events=None, send_responses=None):
        self.events = list(events or [])
        self.send_responses = list(send_responses or [])
        self.sent = []
        self.deleted = []

    def fetch_events(self, after_seq: int, *, limit: int = 200):
        return [
            event
            for event in self.events
            if int(event["eventSeq"]) > after_seq
        ][:limit]

    def send(self, request_type: str, payload: dict, idempotency_key: str):
        self.sent.append((request_type, payload, idempotency_key))
        return self.send_responses.pop(0)

    def delete_patient(self, patient_id: str):
        self.deleted.append(patient_id)
        return {"accepted": True, "eventSeq": 1000 + len(self.deleted)}


def event(seq: int, patient_id: str, *, event_id: str = "OP_ARRIVAL_TO_TRIAGE"):
    return {
        "eventSeq": seq,
        "eventType": "patient.moved",
        "eventId": event_id,
        "patientId": patient_id,
        "animationPlan": {
            "patientId": patient_id,
            "fromRoomId": "outside",
            "toRoomId": "R-OP-TRIAGE",
        },
        "occurredAt": iso_offset(-1),
    }


def command(
    patient_id: str,
    encounter_id: str,
    sequence: int,
    *,
    request_type: str,
    event_id: str | None = None,
):
    return {
        "command_id": f"cmd-{patient_id}-{sequence}",
        "transition_key": f"transition-{patient_id}-{sequence}",
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "request_type": request_type,
        "event_id": event_id,
        "payload": {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "room_id": "R-OP-REGISTRATION",
            "from_room_id": "R-OP-REGISTRATION",
            "to_room_id": "R-OP-TRIAGE",
        },
        "idempotency_key": f"idem-{patient_id}-{sequence}",
    }


def make_repo(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'listener.db'}")
    db.init_schema()
    return db, FullviewSyncRepository(db)


def observe(repo, seq: int, patient_id: str):
    repo.observe_event(event(seq, patient_id))


def expire_visual_hold(db, command_id: str):
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE fullview_sync_outbox SET visual_ready_at=? WHERE command_id=?",
            (iso_offset(-1), command_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_listener_pages_idempotently_and_restores_cursor(tmp_path):
    _, repo = make_repo(tmp_path)
    client = EventClient([event(seq, f"P-{seq}") for seq in range(1, 251)])
    listener = FullviewEventListener(
        repo=repo,
        client=client,
        enabled=True,
        interval_seconds=0.1,
        observe_timeout_seconds=30,
        cleanup_idle_seconds=3,
    )

    assert listener.tick() is True
    assert repo.get_listener_cursor() == 250
    assert listener.tick() is False

    restarted_repo = FullviewSyncRepository(repo.db)
    assert restarted_repo.get_listener_cursor() == 250
    conn = repo.db.connect()
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS count FROM fullview_observed_events"
        ).fetchone()["count"] == 250
    finally:
        conn.close()


def test_restart_cleanup_skips_orphan_commands_and_queues_all_managed_patients(tmp_path):
    _, repo = make_repo(tmp_path)
    repo.enqueue_batch(
        [
            command("P-1", "E-1", 1, request_type="patient_upsert"),
            command("P-1", "E-1", 2, request_type="movement_request"),
        ]
    )
    repo.enqueue_batch([command("P-2", "E-2", 1, request_type="patient_upsert")])

    result = repo.prepare_restart_cleanup()

    assert result["patient_ids"] == ["P-1", "P-2"]
    assert result["skipped_commands"] == 3
    assert result["queued_patients"] == 2
    assert repo.get_visual_backlog_patient_count() == 0
    assert repo.cleanup_status(["P-1", "P-2"]) == {
        "P-1": "cleanup_pending",
        "P-2": "cleanup_pending",
    }


def test_event_observation_is_required_and_handles_event_before_http_response(tmp_path):
    db, repo = make_repo(tmp_path)
    repo.enqueue_batch([command("P-1", "E-1", 1, request_type="patient_upsert")])
    observe(repo, 10, "P-1")
    repo.mark_accepted(
        "cmd-P-1-1",
        {"accepted": True, "core_response": {"eventSeq": 10}},
        visual_cooldown_seconds=4,
    )
    row = repo.get("cmd-P-1-1")
    assert row["status"] == "observed"
    assert row["accepted_at"]
    assert row["observed_at"]
    assert row["visual_ready_at"]

    repo.enqueue_batch([command("P-2", "E-2", 1, request_type="patient_upsert")])
    repo.mark_accepted(
        "cmd-P-2-1",
        {"accepted": True, "core_response": {"eventSeq": 11}},
        visual_cooldown_seconds=4,
    )
    assert repo.get("cmd-P-2-1")["status"] == "accepted_unobserved"
    observe(repo, 11, "P-2")
    assert repo.get("cmd-P-2-1")["status"] == "observed"

    conn = db.connect()
    try:
        conn.execute(
            "UPDATE fullview_sync_outbox SET accepted_at=? WHERE command_id=?",
            (iso_offset(-31), "cmd-P-2-1"),
        )
        conn.commit()
    finally:
        conn.close()


def test_admission_is_global_but_later_patient_movements_do_not_block_each_other(tmp_path):
    db, repo = make_repo(tmp_path)
    repo.enqueue_batch(
        [
            command("P-1", "E-1", 1, request_type="patient_upsert"),
            command(
                "P-1",
                "E-1",
                2,
                request_type="movement_request",
                event_id="OP_ARRIVAL_TO_TRIAGE",
            ),
        ]
    )
    repo.enqueue_batch(
        [
            command("P-2", "E-2", 1, request_type="patient_upsert"),
            command(
                "P-2",
                "E-2",
                2,
                request_type="movement_request",
                event_id="OP_ARRIVAL_TO_TRIAGE",
            ),
        ]
    )
    client = EventClient(
        send_responses=[
            {"accepted": True, "core_response": {"eventSeq": 1}},
            {"accepted": True, "core_response": {"eventSeq": 2}},
            {"accepted": True, "core_response": {"eventSeq": 3}},
            {"accepted": True, "core_response": {"eventSeq": 4}},
        ]
    )
    worker = FullviewSyncWorker(
        repo=repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
        admission_gap_seconds=4,
    )

    assert worker.tick() is True
    assert worker.tick() is False
    observe(repo, 1, "P-1")
    assert worker.tick() is False
    expire_visual_hold(db, "cmd-P-1-1")

    assert worker.tick() is True
    assert repo.get("cmd-P-1-2")["status"] == "accepted_unobserved"
    assert worker.tick() is True
    observe(repo, 3, "P-2")
    expire_visual_hold(db, "cmd-P-2-1")

    assert worker.tick() is True
    assert repo.get("cmd-P-2-2")["status"] == "accepted_unobserved"


def test_twenty_concurrent_admissions_are_observed_one_at_a_time(tmp_path):
    db, repo = make_repo(tmp_path)
    patient_ids = [f"P-{index:02d}" for index in range(20)]
    for patient_id in patient_ids:
        repo.enqueue_batch(
            [command(patient_id, f"E-{patient_id}", 1, request_type="patient_upsert")]
        )
    client = EventClient(
        send_responses=[
            {"accepted": True, "core_response": {"eventSeq": index}}
            for index in range(1, 21)
        ]
    )
    worker = FullviewSyncWorker(
        repo=repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
        admission_gap_seconds=4,
    )

    admitted = []
    for event_seq in range(1, 21):
        assert worker.tick() is True
        patient_id = client.sent[-1][1]["patient_id"]
        admitted.append(patient_id)
        assert worker.tick() is False
        observe(repo, event_seq, patient_id)
        expire_visual_hold(db, f"cmd-{patient_id}-1")

    assert len(admitted) == len(set(admitted)) == 20
    assert set(admitted) == set(patient_ids)
    assert worker.tick() is False
    assert repo.get_status_counts() == {"observed": 20}


def test_observe_timeout_stops_only_that_patient_and_is_manually_retryable(tmp_path):
    db, repo = make_repo(tmp_path)
    repo.enqueue_batch([command("P-1", "E-1", 1, request_type="patient_upsert")])
    repo.mark_accepted(
        "cmd-P-1-1",
        {"accepted": True, "core_response": {"eventSeq": 21}},
    )
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE fullview_sync_outbox SET accepted_at=? WHERE command_id=?",
            (iso_offset(-31), "cmd-P-1-1"),
        )
        conn.commit()
    finally:
        conn.close()

    assert repo.mark_observe_timeouts(30) == 1
    assert repo.get("cmd-P-1-1")["status"] == "observe_timeout"
    assert repo.get_next_ready() is None
    assert repo.retry("cmd-P-1-1")["status"] == "pending"


def test_cleanup_waits_for_visual_idle_and_uses_serial_scheduler(tmp_path):
    db, repo = make_repo(tmp_path)
    repo.enqueue_batch([command("P-1", "E-1", 1, request_type="patient_upsert")])
    observe(repo, 31, "P-1")
    repo.mark_accepted(
        "cmd-P-1-1",
        {"accepted": True, "core_response": {"eventSeq": 31}},
        visual_cooldown_seconds=30,
    )
    repo.enqueue_cleanup_patients(["P-1"])
    client = EventClient()
    listener = FullviewEventListener(
        repo=repo,
        client=client,
        enabled=True,
        interval_seconds=0.1,
        observe_timeout_seconds=30,
        cleanup_idle_seconds=3,
    )

    assert listener.cleanup_tick() is False
    expire_visual_hold(db, "cmd-P-1-1")
    assert listener.cleanup_tick() is False

    conn = db.connect()
    try:
        conn.execute(
            "UPDATE fullview_listener_state SET last_movement_observed_at=? WHERE id=1",
            (iso_offset(-4),),
        )
        conn.commit()
    finally:
        conn.close()

    assert listener.cleanup_tick() is True
    assert client.deleted == ["P-1"]
    assert repo.cleanup_status(["P-1"]) == {"P-1": "deleted"}
