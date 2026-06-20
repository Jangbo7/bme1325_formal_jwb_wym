from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


PATIENT_ID_RE = re.compile(r"^P-[0-9a-f]{8}$")
ENCOUNTER_ID_RE = re.compile(r"^E-[0-9]{14}-[0-9a-f]{4}$")

DEPARTMENT_ROOMS = {
    "internal": ("R-OP-INTERNAL", "R-OP-INTERNAL-B"),
    "surgery": ("R-OP-SURGERY", "R-OP-SURGERY-B"),
    "pediatrics": ("R-OP-PEDIATRICS",),
    "fever": ("R-OP-FEVER",),
    "obgyn": ("R-OP-OBGYN",),
    "ophthalmology": ("R-OP-OPHTHALMOLOGY",),
    "ent": ("R-OP-ENT",),
    "dentistry": ("R-OP-DENTISTRY",),
    "dermatology": ("R-OP-DERMATOLOGY",),
    "psychiatry": ("R-OP-PSYCHIATRY",),
    "rehabilitation": ("R-OP-REHABILITATION",),
    "pain": ("R-OP-PAIN",),
}

DEPARTMENT_QUEUES = {
    "internal": "R-OP-QUEUE-INTERNAL",
    "surgery": "R-OP-QUEUE-SURGERY",
    "pediatrics": "R-OP-QUEUE-PEDIATRICS",
    "fever": "R-OP-QUEUE-FEVER",
    "obgyn": "R-OP-QUEUE-OBGYN",
    "ophthalmology": "R-OP-QUEUE-OPHTHALMOLOGY",
    "ent": "R-OP-QUEUE-ENT",
    "dentistry": "R-OP-QUEUE-DENTISTRY",
    "dermatology": "R-OP-QUEUE-DERMATOLOGY",
    "psychiatry": "R-OP-QUEUE-PSYCHIATRY",
    "rehabilitation": "R-OP-QUEUE-REHABILITATION",
    "pain": "R-OP-QUEUE-PAIN",
    "testing": "R-OP-QUEUE-DIAGNOSTIC",
}

EVENT_ALIASES = {
    "triage_completed": "triage_complete",
    "register_completed": "register_complete",
    "queue_wait_elapsed": "call_patient",
    "start_consultation": "start_initial_consultation",
    "ready_payment": "request_medical_payment",
}

NO_MOVEMENT_EVENTS = {
    "pay_test",
    "pay_medical",
    "plan_disposition",
    "results_ready",
    "queue_second_consultation",
    "choose_outpatient_treatment",
    "choose_followup_booking",
    "cancel",
    "mark_error",
}


@dataclass(frozen=True, slots=True)
class MovementSpec:
    request_type: str
    event_id: str
    target_kind: str
    to_department_id: str | None = None


MOVEMENT_SPECS = {
    "begin_triage": MovementSpec("movement_request", "OP_ARRIVAL_TO_TRIAGE", "triage"),
    "begin_registration": MovementSpec("movement_request", "OP_TRIAGE_TO_REGISTRATION", "registration"),
    "register_complete": MovementSpec("movement_request", "OP_REGISTRATION_TO_TARGET_QUEUE", "department_queue"),
    "call_patient": MovementSpec("movement_request", "OP_CURRENT_TO_TARGET_DOOR_QUEUE", "department_queue"),
    "start_initial_consultation": MovementSpec("movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "consult_room"),
    "request_test_payment": MovementSpec("movement_request", "OP_CONSULT_TO_PAYMENT", "payment"),
    "start_exam": MovementSpec("movement_request", "OP_PAYMENT_TO_LAB", "lab"),
    "finish_exam": MovementSpec("movement_request", "OP_LAB_RETURN_TO_WAITING", "department_queue"),
    "order_outpatient_procedure": MovementSpec("movement_request", "OP_CURRENT_TO_PROCEDURE_QUEUE", "procedure_queue"),
    "start_outpatient_procedure": MovementSpec("movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "procedure_room"),
    "finish_outpatient_procedure": MovementSpec(
        "movement_request",
        "OP_PROCEDURE_RETURN_TO_TARGET_QUEUE",
        "department_queue",
    ),
    "start_second_consultation": MovementSpec("movement_request", "OP_TARGET_DOOR_QUEUE_ADVANCE", "consult_room"),
    "request_medical_payment": MovementSpec("movement_request", "OP_CONSULT_TO_PAYMENT", "payment"),
    "choose_pharmacy": MovementSpec("movement_request", "OP_CONSULT_TO_PHARMACY", "pharmacy"),
    "choose_referral": MovementSpec("movement_request", "OP_REFERRAL_TO_REGISTRATION", "registration"),
    "route_to_emergency": MovementSpec(
        "transfer_request",
        "TRANSFER_OP_TO_ED",
        "emergency",
        "emergency",
    ),
    "route_to_icu_rescue": MovementSpec(
        "transfer_request",
        "OP_TO_ICU_MOVE",
        "icu",
        "icu",
    ),
    "admit_patient": MovementSpec(
        "transfer_request",
        "OP_TO_WARD_MOVE",
        "ward",
        "ward",
    ),
    "complete_visit": MovementSpec("discharge_request", "OP_PATIENT_EXIT_HOSPITAL", "exit"),
    "dispense_medication": MovementSpec("discharge_request", "OP_PATIENT_EXIT_HOSPITAL", "exit"),
}


def normalize_transition_event(value: str | None) -> str:
    event = str(value or "").strip()
    while event.startswith("orchestration."):
        event = event.removeprefix("orchestration.")
    return EVENT_ALIASES.get(event, event)


class FullviewMappingService:
    def __init__(
        self,
        *,
        visit_repo,
        patient_repo,
        department_runtime_repo,
        sync_repo,
        discharge_linger_seconds: float = 0.0,
    ):
        self.visit_repo = visit_repo
        self.patient_repo = patient_repo
        self.department_runtime_repo = department_runtime_repo
        self.sync_repo = sync_repo
        self.discharge_linger_seconds = max(
            0.0,
            float(discharge_linger_seconds),
        )

    def handle_encounter_opened(self, payload: dict) -> None:
        visit_id = str(payload.get("encounter_id") or payload.get("visit_id") or "")
        patient_id = str(payload.get("patient_id") or "")
        if not PATIENT_ID_RE.fullmatch(patient_id) or not ENCOUNTER_ID_RE.fullmatch(visit_id):
            return
        visit = self.visit_repo.get(visit_id)
        patient = self.patient_repo.get(patient_id)
        if not visit or not patient:
            return
        runtime = self.department_runtime_repo.get_patient_runtime(patient_id, visit_id) or {}
        commands = self._bootstrap_commands(
            visit,
            patient,
            runtime,
            "encounter_opened",
        )
        self._assign_sequence_and_ids(visit, "encounter_opened", commands)
        self.sync_repo.enqueue_batch(commands)

    def handle_visit_state_changed(self, payload: dict) -> None:
        visit_id = str(payload.get("visit_id") or "")
        patient_id = str(payload.get("patient_id") or "")
        if not PATIENT_ID_RE.fullmatch(patient_id) or not ENCOUNTER_ID_RE.fullmatch(visit_id):
            return
        visit = self.visit_repo.get(visit_id)
        patient = self.patient_repo.get(patient_id)
        if not visit or not patient:
            return
        event = normalize_transition_event(payload.get("event"))
        if not event:
            return
        runtime = self.department_runtime_repo.get_patient_runtime(patient_id, visit_id) or {}
        if event in {"cancel", "mark_error"}:
            self.sync_repo.mark_local_status(
                patient_id=patient_id,
                encounter_id=visit_id,
                status="error",
                event_id=event,
                error=f"outpatient transition entered {event}",
            )
            return
        if event in NO_MOVEMENT_EVENTS:
            return
        if event == "triage_complete":
            commands = self._bootstrap_commands(visit, patient, runtime, event)
            self._assign_sequence_and_ids(visit, event, commands)
            self.sync_repo.enqueue_batch(commands)
            return
        spec = MOVEMENT_SPECS.get(event)
        if spec is None:
            return

        assigned_department_id = str(
            visit.get("assigned_department_id")
            or runtime.get("assigned_department_id")
            or ""
        ).strip()
        if assigned_department_id and not visit.get("assigned_department_id"):
            visit = {
                **visit,
                "assigned_department_id": assigned_department_id,
                "assigned_department_name": runtime.get("assigned_department_name"),
            }
        if spec.target_kind in {"department_queue", "consult_room"} and assigned_department_id not in DEPARTMENT_QUEUES:
            self.sync_repo.mark_local_status(
                patient_id=patient_id,
                encounter_id=visit_id,
                status="configuration_error",
                event_id=event,
                error="assigned department is missing or unsupported for Fullview routing",
            )
            return

        commands = self._bootstrap_commands(visit, patient, runtime, event)
        if event == "register_complete" and self._known_room(visit, runtime) != "R-OP-REGISTRATION":
            commands.append(
                {
                    "request_type": "movement_request",
                    "event_id": "OP_TRIAGE_TO_REGISTRATION",
                    "payload": {
                        "patient_id": patient["id"],
                        "encounter_id": visit["id"],
                        "event_id": "OP_TRIAGE_TO_REGISTRATION",
                        "from_room_id": "R-OP-TRIAGE",
                        "to_room_id": "R-OP-REGISTRATION",
                        "reason": "register_complete compatibility bridge",
                        "summary": {
                            "source": "outpatient_backend",
                            "transition_event": event,
                            "compatibility_bridge": True,
                        },
                    },
                }
            )
        movement = self._movement_command(visit, patient, runtime, event, spec)
        if movement is not None:
            commands.append(movement)
        self._assign_sequence_and_ids(visit, event, commands)
        self.sync_repo.enqueue_batch(commands)

    def _bootstrap_commands(
        self,
        visit: dict,
        patient: dict,
        runtime: dict,
        event: str,
    ) -> list[dict]:
        encounter_id = visit["id"]
        commands = []
        if not self.sync_repo.has_request_type(encounter_id, "patient_upsert"):
            room_id = self._bootstrap_room(visit, runtime, event)
            registration_profile = self._visit_data(visit).get("registration_profile") or {}
            commands.append(
                {
                    "request_type": "patient_upsert",
                    "event_id": None,
                    "payload": {
                        "patient_id": patient["id"],
                        "encounter_id": encounter_id,
                        "name": patient.get("name") or "Unknown Patient",
                        "gender": registration_profile.get("sex") or "unknown",
                        "age": registration_profile.get("age"),
                        "room_id": room_id,
                        "status": "ARRIVED",
                        "summary": {
                            "source": "outpatient_backend",
                            "visit_state": visit.get("state"),
                            "priority": patient.get("priority"),
                        },
                    },
                }
            )
        return commands

    def _movement_command(
        self,
        visit: dict,
        patient: dict,
        runtime: dict,
        event: str,
        spec: MovementSpec,
    ) -> dict | None:
        from_room = self._current_room(visit, runtime, event)
        target_room = self._target_room(visit, runtime, spec.target_kind)
        if event == "call_patient" and from_room == target_room:
            return None

        payload = {
            "patient_id": patient["id"],
            "encounter_id": visit["id"],
            "event_id": spec.event_id,
            "reason": event,
            "summary": {
                "source": "outpatient_backend",
                "transition_event": event,
                "visit_state": visit.get("state"),
            },
        }
        if spec.request_type == "discharge_request":
            if self.discharge_linger_seconds > 0:
                payload["summary"]["visual_linger_seconds"] = (
                    self.discharge_linger_seconds
                )
            return {
                "request_type": spec.request_type,
                "event_id": spec.event_id,
                "payload": payload,
                "next_attempt_at": (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=self.discharge_linger_seconds)
                ).isoformat(),
            }

        payload["from_room_id"] = from_room
        payload["to_room_id"] = target_room
        if spec.request_type == "transfer_request":
            payload["to_department_id"] = spec.to_department_id
            payload["requested_resources"] = {
                "bed_type": (spec.to_department_id or "").upper(),
                "monitor": spec.to_department_id == "icu",
            }
        return {
            "request_type": spec.request_type,
            "event_id": spec.event_id,
            "payload": payload,
        }

    def _assign_sequence_and_ids(self, visit: dict, event: str, commands: list[dict]) -> None:
        sequence = self.sync_repo.next_sequence(visit["id"])
        transition_version = visit.get("updated_at") or ""
        for offset, command in enumerate(commands):
            identity = {
                "encounter_id": visit["id"],
                "transition_version": transition_version,
                "event": event,
                "request_type": command["request_type"],
                "event_id": command.get("event_id"),
                "payload": command["payload"],
            }
            digest = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            command_id = f"fv-{digest[:32]}"
            command.update(
                {
                    "command_id": command_id,
                    "transition_key": digest,
                    "patient_id": visit["patient_id"],
                    "encounter_id": visit["id"],
                    "sequence_no": sequence + offset,
                    "idempotency_key": command_id,
                }
            )

    def _current_room(self, visit: dict, runtime: dict, event: str) -> str:
        fixed_sources = {
            "begin_triage": "outside",
            "begin_registration": "R-OP-TRIAGE",
            "register_complete": "R-OP-REGISTRATION",
            "start_exam": "R-OP-PAYMENT",
            "finish_exam": "R-OP-LAB",
            "start_outpatient_procedure": "R-OP-QUEUE-SURGERY",
            "finish_outpatient_procedure": "R-OP-SURGERY-PROCEDURE",
        }
        if event in fixed_sources:
            return fixed_sources[event]
        known_room = self._known_room(visit, runtime)
        return known_room or self._bootstrap_room(visit, runtime, event)

    def _known_room(self, visit: dict, runtime: dict) -> str | None:
        projection = self.sync_repo.get_projection(visit["patient_id"], visit["id"]) or {}
        projected = projection.get("current_room_id")
        if projected:
            return str(projected)
        planned = self.sync_repo.get_latest_planned_room(visit["id"])
        if planned:
            return planned
        node_room = self._room_from_node(
            visit.get("current_node"),
            visit.get("assigned_department_id"),
            runtime,
        )
        return node_room

    def _target_room(self, visit: dict, runtime: dict, kind: str) -> str:
        if kind == "triage":
            return "R-OP-TRIAGE"
        if kind == "registration":
            return "R-OP-REGISTRATION"
        if kind == "payment":
            return "R-OP-PAYMENT"
        if kind == "lab":
            return "R-OP-LAB"
        if kind == "pharmacy":
            return "R-OP-PHARMACY"
        if kind == "procedure_queue":
            return "R-OP-QUEUE-SURGERY"
        if kind == "procedure_room":
            return "R-OP-SURGERY-PROCEDURE"
        if kind == "department_queue":
            return self._department_queue(visit.get("assigned_department_id"))
        if kind == "consult_room":
            return self._consult_room(visit.get("assigned_department_id"), runtime)
        if kind == "emergency":
            return "R-ED-HANDOFF"
        if kind == "icu":
            return "R-ICU-ADMISSION"
        if kind == "ward":
            return "R-WARD-WARD-ADMISSION"
        if kind == "exit":
            return "exit"
        raise ValueError(f"unsupported Fullview target kind: {kind}")

    def _bootstrap_room(self, visit: dict, runtime: dict, event: str) -> str:
        if event == "begin_triage":
            return "R-OP-REGISTRATION"
        node_room = self._room_from_node(
            visit.get("current_node"),
            visit.get("assigned_department_id"),
            runtime,
        )
        if node_room:
            return node_room
        state = str(visit.get("state") or "")
        if state in {"in_triage", "triaged", "triaging"}:
            return "R-OP-TRIAGE"
        if state in {"registration_pending"}:
            return "R-OP-REGISTRATION"
        if state in {"registered", "waiting_consultation", "waiting_second_consultation", "waiting_return_consultation", "results_ready"}:
            return self._department_queue(visit.get("assigned_department_id"))
        if state in {"in_consultation", "in_second_consultation", "diagnosis_finalized", "waiting_test"}:
            return self._consult_room(visit.get("assigned_department_id"), runtime)
        if state in {"waiting_payment", "waiting_test_payment", "test_payment_completed", "medical_payment_completed", "disposition_pending"}:
            return "R-OP-PAYMENT"
        if state == "in_test":
            return "R-OP-LAB"
        if state in {"waiting_outpatient_procedure"}:
            return "R-OP-QUEUE-SURGERY"
        if state == "in_outpatient_procedure":
            return "R-OP-SURGERY-PROCEDURE"
        if state == "waiting_pharmacy":
            return "R-OP-PHARMACY"
        return "R-OP-REGISTRATION"

    @staticmethod
    def _department_queue(department_id: str | None) -> str:
        return DEPARTMENT_QUEUES.get(str(department_id or ""), "R-OP-OUTPATIENT-WAITING")

    @staticmethod
    def _consult_room(department_id: str | None, runtime: dict) -> str:
        department = str(department_id or "")
        rooms = DEPARTMENT_ROOMS.get(department)
        if not rooms:
            return "R-OP-CONSULTATION-A"
        slot_id = str(runtime.get("assigned_doctor_slot_id") or "")
        if slot_id.endswith("_2") and len(rooms) > 1:
            return rooms[1]
        current_room_node = str(runtime.get("current_room_node_id") or "")
        if current_room_node.endswith("_2") and len(rooms) > 1:
            return rooms[1]
        return rooms[0]

    def _room_from_node(
        self,
        node_id: str | None,
        department_id: str | None,
        runtime: dict,
    ) -> str | None:
        node = str(node_id or "")
        direct = {
            "triage": "R-OP-TRIAGE",
            "triage_done": "R-OP-TRIAGE",
            "registration": "R-OP-REGISTRATION",
            "registration_queue": "R-OP-REGISTRATION",
            "payment": "R-OP-PAYMENT",
            "payment_wait": "R-OP-PAYMENT",
            "testing": "R-OP-LAB",
            "pharmacy": "R-OP-PHARMACY",
            "pharmacy_wait": "R-OP-PHARMACY",
            "outpatient_procedure_wait": "R-OP-QUEUE-SURGERY",
            "outpatient_procedure_room": "R-OP-SURGERY-PROCEDURE",
            "surgery_outpatient_procedure_room": "R-OP-SURGERY-PROCEDURE",
        }
        if node in direct:
            return direct[node]
        if node.endswith("_queue_gate") or node in DEPARTMENT_QUEUES:
            return self._department_queue(department_id)
        if "consult_room" in node or node.endswith("_consultation_room"):
            room_runtime = dict(runtime)
            if node.endswith("_2"):
                room_runtime["current_room_node_id"] = node
            return self._consult_room(department_id, room_runtime)
        return None

    @staticmethod
    def _visit_data(visit: dict) -> dict:
        try:
            return json.loads(visit.get("data_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
