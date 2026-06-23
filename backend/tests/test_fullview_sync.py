from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database import Database
from app.repositories.fullview_sync import FullviewSyncRepository
from app.repositories.patients import PatientRepository
from app.repositories.visits import VisitRepository
from app.schemas.common import VisitLifecycleState
from app.services.fullview_mapping import FullviewMappingService, normalize_transition_event
from app.services.fullview_sync import FullviewEventListener, FullviewSyncWorker


class RuntimeRepoStub:
    def __init__(self, runtime: dict | None = None):
        self.runtime = runtime or {}

    def get_patient_runtime(self, patient_id: str, visit_id: str):
        return dict(self.runtime)


class FakeFullviewClient:
    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls = []

    def send(self, request_type: str, payload: dict, idempotency_key: str):
        self.calls.append((request_type, payload, idempotency_key))
        return self.responses.pop(0)


class FakeDischargeFallbackClient(FakeFullviewClient):
    def __init__(self, responses: list[dict], delete_response: dict):
        super().__init__(responses)
        self.delete_response = delete_response
        self.deleted_patient_ids = []

    def delete_patient(self, patient_id: str):
        self.deleted_patient_ids.append(patient_id)
        return self.delete_response


@pytest.fixture
def sync_context(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'fullview-sync.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    patient_id = "P-a1b2c3d4"
    patient_repo.upsert_basic(patient_id, "Mapping Patient")
    visit_repo = VisitRepository(db)
    visit = visit_repo.create(
        patient_id=patient_id,
        state=VisitLifecycleState.IN_CONSULTATION,
        assigned_department_id="internal",
        assigned_department_name="Internal Medicine",
        current_node="internal_consult_room_1",
        current_department="Internal Medicine",
    )
    sync_repo = FullviewSyncRepository(db)
    return db, patient_repo, visit_repo, sync_repo, patient_id, visit


def build_mapping(sync_context, runtime=None):
    _, patient_repo, visit_repo, sync_repo, _, _ = sync_context
    return FullviewMappingService(
        visit_repo=visit_repo,
        patient_repo=patient_repo,
        department_runtime_repo=RuntimeRepoStub(runtime),
        sync_repo=sync_repo,
    )


def publish(mapping, visit, patient_id, event):
    mapping.handle_visit_state_changed(
        {
            "visit_id": visit["id"],
            "patient_id": patient_id,
            "state": visit["state"],
            "event": event,
        }
    )


def publish_encounter_opened(mapping, visit, patient_id):
    mapping.handle_encounter_opened(
        {
            "encounter_id": visit["id"],
            "patient_id": patient_id,
            "state": visit["state"],
        }
    )


def last_command(sync_repo, encounter_id):
    return sync_repo.list_for_encounter(encounter_id)[-1]


def accept_and_observe(sync_repo, command, *, cooldown=0.0, event_seq=None):
    seq = int(event_seq or command["sequence_no"])
    sync_repo.mark_accepted(
        command["command_id"],
        {"accepted": True, "core_response": {"eventSeq": seq}},
        visual_cooldown_seconds=cooldown,
    )
    sync_repo.observe_event(
        {
            "eventSeq": seq,
            "eventType": "patient.moved",
            "eventId": command.get("event_id"),
            "patientId": command["patient_id"],
            "animationPlan": {
                "patientId": command["patient_id"],
                "toRoomId": command["payload"].get("to_room_id")
                or command["payload"].get("room_id"),
            },
        }
    )


def test_normalizes_orchestration_prefix_and_legacy_alias():
    assert normalize_transition_event("orchestration.register_completed") == "register_complete"
    assert normalize_transition_event("orchestration.orchestration.ready_payment") == "request_medical_payment"


def test_encounter_opened_bootstraps_patient_at_arrival(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.ARRIVED.value,
        current_node="lobby",
    )
    mapping = build_mapping(sync_context)

    publish_encounter_opened(mapping, visit, patient_id)

    commands = sync_repo.list_for_encounter(visit["id"])
    assert [item["request_type"] for item in commands] == ["patient_upsert"]
    assert commands[0]["payload"]["status"] == "ARRIVED"
    assert commands[0]["payload"]["room_id"] == "R-OP-REGISTRATION"


def test_begin_triage_reuses_arrival_bootstrap(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish_encounter_opened(mapping, visit, patient_id)

    publish(mapping, visit, patient_id, "begin_triage")

    commands = sync_repo.list_for_encounter(visit["id"])
    assert [item["request_type"] for item in commands].count("patient_upsert") == 1
    assert [item["request_type"] for item in commands].count("encounter_open") == 0
    assert commands[-1]["event_id"] == "OP_ARRIVAL_TO_TRIAGE"


def test_triage_complete_bootstraps_patient_without_movement(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.TRIAGED.value,
        current_node="triage_done",
    )
    mapping = build_mapping(sync_context)

    publish(mapping, visit, patient_id, "triage_completed")

    commands = sync_repo.list_for_encounter(visit["id"])
    assert [item["request_type"] for item in commands] == ["patient_upsert"]
    assert commands[0]["payload"]["room_id"] == "R-OP-TRIAGE"


def test_direct_register_complete_bridges_triage_to_registration(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.REGISTERED.value,
        current_node="triage_done",
    )
    mapping = build_mapping(sync_context)

    publish(mapping, visit, patient_id, "register_completed")

    commands = sync_repo.list_for_encounter(visit["id"])
    assert [item["event_id"] for item in commands[-2:]] == [
        "OP_TRIAGE_TO_REGISTRATION",
        "OP_REGISTRATION_TO_TARGET_QUEUE",
    ]


@pytest.mark.parametrize(
    ("event", "request_type", "event_id", "target_room"),
    [
        ("begin_triage", "movement_request", "OP_ARRIVAL_TO_TRIAGE", "R-OP-TRIAGE"),
        ("begin_registration", "movement_request", "OP_TRIAGE_TO_REGISTRATION", "R-OP-REGISTRATION"),
        ("register_complete", "movement_request", "OP_REGISTRATION_TO_TARGET_QUEUE", "R-OP-QUEUE-INTERNAL"),
        ("start_initial_consultation", "movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "R-OP-INTERNAL"),
        ("request_test_payment", "movement_request", "OP_CONSULT_TO_PAYMENT", "R-OP-PAYMENT"),
        ("start_exam", "movement_request", "OP_PAYMENT_TO_LAB", "R-OP-LAB"),
        ("finish_exam", "movement_request", "OP_LAB_RETURN_TO_WAITING", "R-OP-QUEUE-INTERNAL"),
        ("order_outpatient_procedure", "movement_request", "OP_CURRENT_TO_PROCEDURE_QUEUE", "R-OP-QUEUE-SURGERY"),
        ("start_outpatient_procedure", "movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "R-OP-SURGERY-PROCEDURE"),
        ("finish_outpatient_procedure", "movement_request", "OP_PROCEDURE_RETURN_TO_TARGET_QUEUE", "R-OP-QUEUE-INTERNAL"),
        ("start_second_consultation", "movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "R-OP-INTERNAL"),
        ("request_medical_payment", "movement_request", "OP_CONSULT_TO_PAYMENT", "R-OP-PAYMENT"),
        ("choose_pharmacy", "movement_request", "OP_CONSULT_TO_PHARMACY", "R-OP-PHARMACY"),
        ("choose_referral", "movement_request", "OP_REFERRAL_TO_REGISTRATION", "R-OP-REGISTRATION"),
        ("route_to_emergency", "transfer_request", "TRANSFER_OP_TO_ED", "R-ED-HANDOFF"),
        ("route_to_icu_rescue", "transfer_request", "OP_TO_ICU_MOVE", "R-ICU-ADMISSION"),
        ("admit_patient", "transfer_request", "OP_TO_WARD_MOVE", "R-WARD-WARD-ADMISSION"),
    ],
)
def test_maps_transition_to_fullview_request(
    tmp_path,
    event,
    request_type,
    event_id,
    target_room,
):
    db = Database(f"sqlite:///{tmp_path / f'{event}.db'}")
    db.init_schema()
    patient_repo = PatientRepository(db)
    patient_id = "P-a1b2c3d4"
    patient_repo.upsert_basic(patient_id, "Mapping Patient")
    visit_repo = VisitRepository(db)
    visit = visit_repo.create(
        patient_id=patient_id,
        state=VisitLifecycleState.IN_CONSULTATION,
        assigned_department_id="internal",
        assigned_department_name="Internal Medicine",
        current_node="internal_consult_room_1",
        current_department="Internal Medicine",
    )
    sync_repo = FullviewSyncRepository(db)
    mapping = FullviewMappingService(
        visit_repo=visit_repo,
        patient_repo=patient_repo,
        department_runtime_repo=RuntimeRepoStub(),
        sync_repo=sync_repo,
    )

    publish(mapping, visit, patient_id, f"orchestration.{event}")

    commands = sync_repo.list_for_encounter(visit["id"])
    assert commands[0]["request_type"] == "patient_upsert"
    command = commands[-1]
    assert command["request_type"] == request_type
    assert command["event_id"] == event_id
    assert command["payload"]["to_room_id"] == target_room


@pytest.mark.parametrize("event", ["complete_visit", "dispense_medication"])
def test_completion_maps_to_discharge(sync_context, event):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)

    publish(mapping, visit, patient_id, event)

    command = last_command(sync_repo, visit["id"])
    assert command["request_type"] == "discharge_request"
    assert command["event_id"] == "OP_PATIENT_EXIT_HOSPITAL"
    assert "from_room_id" not in command["payload"]


def test_completion_delays_discharge_for_visual_linger(sync_context):
    _, patient_repo, visit_repo, sync_repo, patient_id, visit = sync_context
    mapping = FullviewMappingService(
        visit_repo=visit_repo,
        patient_repo=patient_repo,
        department_runtime_repo=RuntimeRepoStub(),
        sync_repo=sync_repo,
        discharge_linger_seconds=30,
    )

    publish(mapping, visit, patient_id, "complete_visit")

    command = last_command(sync_repo, visit["id"])
    assert command["request_type"] == "discharge_request"
    assert command["payload"]["summary"]["visual_linger_seconds"] == 30
    assert command["next_attempt_at"] > command["created_at"]


@pytest.mark.parametrize(
    "event",
    [
        "pay_test",
        "pay_medical",
        "plan_disposition",
        "results_ready",
        "choose_outpatient_treatment",
        "choose_followup_booking",
    ],
)
def test_state_only_events_do_not_enqueue(sync_context, event):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)

    publish(mapping, visit, patient_id, event)

    assert sync_repo.list_for_encounter(visit["id"]) == []


@pytest.mark.parametrize("event", ["cancel", "mark_error"])
def test_error_events_preserve_room_and_record_error_projection(sync_context, event):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    sync_repo.mark_local_status(
        patient_id=patient_id,
        encounter_id=visit["id"],
        status="accepted",
        event_id="previous",
        error=None,
    )
    conn = sync_repo.db.connect()
    try:
        conn.execute(
            """
            UPDATE fullview_patient_projection
            SET current_room_id='R-OP-INTERNAL'
            WHERE patient_id=? AND encounter_id=?
            """,
            (patient_id, visit["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    publish(mapping, visit, patient_id, event)

    assert sync_repo.list_for_encounter(visit["id"]) == []
    projection = sync_repo.get_projection(patient_id, visit["id"])
    assert projection["current_room_id"] == "R-OP-INTERNAL"
    assert projection["sync_status"] == "error"
    assert projection["last_event_id"] == event


def test_resolves_second_internal_room_from_doctor_slot(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(
        sync_context,
        {"assigned_doctor_slot_id": "internal_doctor_slot_2"},
    )

    publish(mapping, visit, patient_id, "start_initial_consultation")

    command = last_command(sync_repo, visit["id"])
    assert command["payload"]["to_room_id"] == "R-OP-INTERNAL-B"


def test_call_patient_skips_when_already_planned_in_target_queue(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "register_complete")
    before = len(sync_repo.list_for_encounter(visit["id"]))

    publish(mapping, visit, patient_id, "call_patient")

    assert len(sync_repo.list_for_encounter(visit["id"])) == before


def test_worker_sends_in_sequence_and_updates_projection(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])
    client = FakeFullviewClient(
        [
            {"accepted": True, "trace_id": "trc-1", "core_response": {"eventSeq": 1}},
            {
                "accepted": True,
                "trace_id": "trc-3",
                "core_response": {
                    "eventSeq": 2,
                    "animationPlan": {"toRoomId": "R-OP-REGISTRATION"},
                },
            },
        ]
    )
    worker = FullviewSyncWorker(
        repo=sync_repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
    )

    assert worker.tick() is True
    sync_repo.observe_event(
        {"eventSeq": 1, "patientId": patient_id, "animationPlan": {"toRoomId": "R-OP-TRIAGE"}}
    )
    command = sync_repo.get(commands[0]["command_id"])
    conn = sync_repo.db.connect()
    conn.execute(
        "UPDATE fullview_sync_outbox SET visual_ready_at=? WHERE command_id=?",
        ("2000-01-01T00:00:00+00:00", command["command_id"]),
    )
    conn.commit()
    conn.close()
    assert worker.tick() is True
    sync_repo.observe_event(
        {"eventSeq": 2, "patientId": patient_id, "animationPlan": {"toRoomId": "R-OP-REGISTRATION"}}
    )

    assert [call[0] for call in client.calls] == [
        "patient_upsert",
        "movement_request",
    ]
    assert all(sync_repo.get(item["command_id"])["status"] == "observed" for item in commands)
    projection = sync_repo.get_projection(patient_id, visit["id"])
    assert projection["current_room_id"] == "R-OP-REGISTRATION"
    assert projection["last_event_seq"] == 2


def test_worker_retries_capacity_and_blocks_contract_error(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])
    for command in commands[:-1]:
        accept_and_observe(sync_repo, command)
    movement = commands[-1]

    retry_worker = FullviewSyncWorker(
        repo=sync_repo,
        client=FakeFullviewClient(
            [
                {
                    "accepted": False,
                    "reason_code": "OUTPATIENT_SLOT_UNAVAILABLE",
                    "message": "busy",
                    "core_response": {},
                }
            ]
        ),
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
    )
    assert retry_worker.tick() is True
    retried = sync_repo.get(movement["command_id"])
    assert retried["status"] == "retryable"
    assert retried["attempt_count"] == 1

    sync_repo.retry(movement["command_id"])
    blocked_worker = FullviewSyncWorker(
        repo=sync_repo,
        client=FakeFullviewClient(
            [
                {
                    "accepted": False,
                    "reason_code": "RULE_NOT_ALLOWED_FOR_DEPARTMENT",
                    "message": "not enabled",
                    "core_response": {},
                }
            ]
        ),
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
    )
    assert blocked_worker.tick() is True
    blocked = sync_repo.get(movement["command_id"])
    assert blocked["status"] == "blocked"
    assert blocked["reason_code"] == "RULE_NOT_ALLOWED_FOR_DEPARTMENT"


def test_capacity_wait_never_becomes_dead_letter(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])
    for command in commands[:-1]:
        accept_and_observe(sync_repo, command)
    movement = commands[-1]
    worker = FullviewSyncWorker(
        repo=sync_repo,
        client=FakeFullviewClient(
            [
                {
                    "accepted": False,
                    "reason_code": "OUTPATIENT_SLOT_UNAVAILABLE",
                    "message": "busy",
                    "core_response": {},
                }
            ]
        ),
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=1,
    )

    assert worker.tick() is True

    waiting = sync_repo.get(movement["command_id"])
    assert waiting["status"] == "retryable"
    assert waiting["attempt_count"] == 1


def test_discharge_request_falls_back_to_backend_patient_delete(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "complete_visit")
    commands = sync_repo.list_for_encounter(visit["id"])
    for command in commands[:-1]:
        accept_and_observe(sync_repo, command)
    discharge = commands[-1]
    client = FakeDischargeFallbackClient(
        [
            {
                "accepted": False,
                "reason_code": "REQUEST_TYPE_NOT_ENABLED",
                "message": "not enabled",
                "core_response": {},
            }
        ],
        {"accepted": True, "eventSeq": 91},
    )
    worker = FullviewSyncWorker(
        repo=sync_repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=2,
    )

    assert worker.tick() is True

    completed = sync_repo.get(discharge["command_id"])
    assert completed["status"] == "cleanup_pending"
    assert client.deleted_patient_ids == []
    assert sync_repo.cleanup_status([patient_id]) == {
        patient_id: "cleanup_pending"
    }


def test_startup_recovery_requeues_capacity_and_discharge_compatibility_failures(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    capacity_command = sync_repo.list_for_encounter(visit["id"])[0]
    sync_repo.mark_dead_letter(
        capacity_command["command_id"],
        attempt_count=8,
        reason_code="OUTPATIENT_SLOT_UNAVAILABLE",
        error="busy",
    )

    assert sync_repo.retry_recoverable_failures() == 1
    assert sync_repo.get(capacity_command["command_id"])["status"] == "pending"


def test_delivery_backlog_counts_only_actionable_commands(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])

    assert sync_repo.get_delivery_backlog_count() == len(commands)

    accept_and_observe(sync_repo, commands[0])
    assert sync_repo.get_delivery_backlog_count() == len(commands) - 1


def test_visual_backlog_counts_patients_not_commands(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")

    assert sync_repo.get_delivery_backlog_count() == 2
    assert sync_repo.get_visual_backlog_patient_count() == 1


def test_visual_backlog_includes_accepted_cooldown(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])
    sync_repo.set_visual_cooldown_enabled(True)
    for command in commands:
        accept_and_observe(sync_repo, command, cooldown=30)

    assert sync_repo.get_delivery_backlog_count() == 0
    assert sync_repo.get_visual_backlog_patient_count() == 1


def test_recover_sending_after_restart(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    command = sync_repo.list_for_encounter(visit["id"])[0]
    sync_repo.mark_sending(command["command_id"])

    sync_repo.recover_sending()

    recovered = sync_repo.get(command["command_id"])
    assert recovered["status"] == "retryable"
    assert recovered["next_attempt_at"] <= datetime.now(timezone.utc).isoformat()

def test_runtime_cleanup_skips_unfinished_patient_commands(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.TRIAGED.value,
        current_node="triage_done",
    )
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "triage_completed")

    changed = sync_repo.skip_unfinished_for_patients(
        [patient_id],
        reason="runtime reset test",
    )

    commands = sync_repo.list_for_encounter(visit["id"])
    assert changed == 1
    assert [command["status"] for command in commands] == ["skipped"]
    assert all(command["reason_code"] == "RUNTIME_RESET" for command in commands)
def test_configuration_failures_retry_after_catalog_repair(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    command = sync_repo.list_for_encounter(visit["id"])[0]
    sync_repo.mark_blocked(
        command["command_id"],
        attempt_count=1,
        reason_code="ROOM_NOT_FOUND",
        error="room missing",
    )

    assert sync_repo.retry_configuration_failures() == 1
    recovered = sync_repo.get(command["command_id"])
    assert recovered["status"] == "pending"
    assert recovered["attempt_count"] == 0


def test_encounter_status_exposes_predecessor_blocking(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_registration")
    commands = sync_repo.list_for_encounter(visit["id"])
    sync_repo.mark_blocked(
        commands[0]["command_id"],
        attempt_count=1,
        reason_code="ROOM_NOT_FOUND",
        error="room missing",
    )

    status = sync_repo.get_encounter_sync_status(visit["id"])

    assert status["blocking_command"]["command_id"] == commands[0]["command_id"]
    assert status["commands"][1]["blocked_by_command_id"] == commands[0]["command_id"]


def test_missing_department_marks_configuration_error_without_generic_fallback(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        assigned_department_id="unassigned",
        assigned_department_name="Unassigned",
    )
    mapping = build_mapping(sync_context, {"assigned_department_id": "unassigned"})

    publish(mapping, visit, patient_id, "register_complete")

    assert sync_repo.list_for_encounter(visit["id"]) == []
    projection = sync_repo.get_projection(patient_id, visit["id"])
    assert projection["sync_status"] == "configuration_error"
    assert "assigned department" in projection["last_error"]


def test_step_gate_blocker_clears_only_after_all_commands_are_accepted(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.TRIAGED.value,
        current_node="triage_done",
    )
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "triage_completed")
    commands = sync_repo.list_for_encounter(visit["id"])

    blocker = sync_repo.get_step_gate_blocker(visit["id"])
    assert blocker["command_id"] == commands[0]["command_id"]
    assert blocker["status"] == "pending"

    accept_and_observe(sync_repo, commands[0])
    assert sync_repo.get_step_gate_blocker(visit["id"]) is None


def test_visual_cooldown_blocks_visual_queue_but_not_business_step_gate(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.TRIAGED.value,
        current_node="triage_done",
    )
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_triage")
    commands = sync_repo.list_for_encounter(visit["id"])
    sync_repo.set_visual_cooldown_enabled(True)

    for command in commands:
        accept_and_observe(sync_repo, command, cooldown=30)

    assert sync_repo.get_next_ready() is None
    assert sync_repo.get_step_gate_blocker(visit["id"]) is None

    assert all(command["status"] == "observed" for command in sync_repo.list_for_encounter(visit["id"]))


def test_resource_retry_uses_new_idempotency_key(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_triage")
    command = sync_repo.list_for_encounter(visit["id"])[0]
    client = FakeFullviewClient(
        [
            {
                "accepted": False,
                "reason_code": "OUTPATIENT_SLOT_UNAVAILABLE",
                "message": "busy",
            },
            {"accepted": True, "core_response": {"eventSeq": 2}},
        ]
    )
    worker = FullviewSyncWorker(
        repo=sync_repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
    )

    assert worker.tick() is True
    first_key = client.calls[0][2]
    conn = sync_repo.db.connect()
    conn.execute(
        "UPDATE fullview_sync_outbox SET next_attempt_at=? WHERE command_id=?",
        ("2000-01-01T00:00:00+00:00", command["command_id"]),
    )
    conn.commit()
    conn.close()
    assert worker.tick() is True
    second_key = client.calls[1][2]

    assert first_key == command["idempotency_key"]
    assert second_key == f"{command['idempotency_key']}-attempt-2"


def test_worker_assigns_event_specific_visual_cooldown():
    command = {
        "request_type": "movement_request",
        "event_id": "OP_REGISTRATION_TO_TARGET_QUEUE",
    }
    response = {
        "core_response": {
            "animation_plan": {
                "from_room_id": "R-OP-REGISTRATION",
                "to_room_id": "R-OP-QUEUE-INTERNAL",
            }
        }
    }

    assert FullviewSyncWorker._visual_cooldown_seconds(command, response) == 8.0


def test_worker_assigns_patient_upsert_visual_cooldown():
    command = {"request_type": "patient_upsert", "event_id": None}
    response = {
        "core_response": {
            "animation_plan": {
                "kind": "patient-upsert",
                "to_room_id": "R-OP-REGISTRATION",
            }
        }
    }

    assert FullviewSyncWorker._visual_cooldown_seconds(command, response) == 3.0


def test_worker_applies_visual_cooldown_multiplier(sync_context):
    _, _, _, sync_repo, patient_id, visit = sync_context
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "begin_triage")
    commands = sync_repo.list_for_encounter(visit["id"])
    client = FakeFullviewClient(
        [
            {"accepted": True, "core_response": {"eventSeq": 1}},
            {
                "accepted": True,
                "core_response": {
                    "eventSeq": 2,
                    "animation_plan": {
                        "from_room_id": "outside",
                        "to_room_id": "R-OP-TRIAGE",
                    }
                },
            },
        ]
    )
    worker = FullviewSyncWorker(
        repo=sync_repo,
        client=client,
        enabled=True,
        poll_interval_seconds=0.1,
        max_attempts=3,
        visual_cooldown_multiplier=2,
    )

    assert worker.tick() is True
    sync_repo.observe_event(
        {"eventSeq": 1, "patientId": patient_id, "animationPlan": {"toRoomId": "R-OP-REGISTRATION"}}
    )
    conn = sync_repo.db.connect()
    conn.execute(
        "UPDATE fullview_sync_outbox SET visual_ready_at=? WHERE command_id=?",
        ("2000-01-01T00:00:00+00:00", commands[0]["command_id"]),
    )
    conn.commit()
    conn.close()
    assert worker.tick() is True
    sync_repo.observe_event(
        {"eventSeq": 2, "patientId": patient_id, "animationPlan": {"toRoomId": "R-OP-TRIAGE"}}
    )

    movement = sync_repo.get(commands[-1]["command_id"])
    ready_at = datetime.fromisoformat(movement["visual_ready_at"])
    observed_at = datetime.fromisoformat(movement["observed_at"])
    assert (ready_at - observed_at).total_seconds() >= 7.9


def test_register_bridge_batch_waits_for_first_movement_visual_cooldown(sync_context):
    _, _, visit_repo, sync_repo, patient_id, visit = sync_context
    visit = visit_repo.update_visit(
        visit["id"],
        state=VisitLifecycleState.REGISTERED.value,
        current_node="registered",
    )
    mapping = build_mapping(sync_context)
    publish(mapping, visit, patient_id, "register_complete")
    commands = sync_repo.list_for_encounter(visit["id"])
    bridge = next(
        command
        for command in commands
        if command["event_id"] == "OP_TRIAGE_TO_REGISTRATION"
    )
    queue_move = next(
        command
        for command in commands
        if command["event_id"] == "OP_REGISTRATION_TO_TARGET_QUEUE"
    )
    sync_repo.set_visual_cooldown_enabled(True)

    for command in commands:
        if command["sequence_no"] >= bridge["sequence_no"]:
            break
        accept_and_observe(sync_repo, command)
    assert sync_repo.get_next_ready()["command_id"] == bridge["command_id"]

    sync_repo.mark_accepted(
        bridge["command_id"],
        {
            "accepted": True,
            "core_response": {
                "eventSeq": bridge["sequence_no"],
                "animation_plan": {
                    "from_room_id": "R-OP-TRIAGE",
                    "to_room_id": "R-OP-REGISTRATION",
                }
            },
        },
        visual_cooldown_seconds=30,
    )
    sync_repo.observe_event(
        {
            "eventSeq": bridge["sequence_no"],
            "patientId": patient_id,
            "animationPlan": {"toRoomId": "R-OP-REGISTRATION"},
        }
    )

    assert sync_repo.get_next_ready() is None
    assert sync_repo.get_step_gate_blocker(visit["id"])["command_id"] == queue_move["command_id"]

    sync_repo.mark_accepted(
        bridge["command_id"],
        {
            "accepted": True,
            "core_response": {"eventSeq": bridge["sequence_no"]},
        },
        visual_cooldown_seconds=0,
    )
    assert sync_repo.get_next_ready()["command_id"] == queue_move["command_id"]
