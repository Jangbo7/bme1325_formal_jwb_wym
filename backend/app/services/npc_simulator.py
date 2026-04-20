from __future__ import annotations

from datetime import datetime, timezone
import threading
import uuid

from app.events.types import PATIENT_STATE_CHANGED, QUEUE_TICKET_CALLED, VISIT_STATE_CHANGED
from app.schemas.common import (
    InternalMedicineDialogueState,
    PatientLifecycleState,
    QueueTicketStatus,
    TriageDialogueState,
    VisitLifecycleState,
)


SIMULATED_PATIENT_ID_PREFIX = "P-NPC-"
REGISTER_QUEUE_DEPARTMENT_ID = "doctor_entry"
REGISTER_QUEUE_DEPARTMENT_NAME = "Doctor Entry"
TERMINAL_PATIENT_STATES = {
    PatientLifecycleState.COMPLETED.value,
    PatientLifecycleState.CANCELLED.value,
    PatientLifecycleState.ERROR.value,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class NpcPatientSimulator:
    """Background simulator that periodically spawns and advances synthetic patients."""

    archetypes = [
        {
            "id": "mild_respiratory",
            "display_name": "Mild Respiratory",
            "age": 26,
            "symptom_tags": ["cough", "sore_throat"],
            "target_department": "General Medicine",
            "priority": "L",
            "triage_level": 4,
        },
        {
            "id": "fever_screening",
            "display_name": "Fever Screening",
            "age": 41,
            "symptom_tags": ["fever", "fatigue"],
            "target_department": "Fever Clinic",
            "priority": "M",
            "triage_level": 3,
        },
        {
            "id": "abdominal_pain",
            "display_name": "Abdominal Pain",
            "age": 58,
            "symptom_tags": ["abdominal_pain", "nausea"],
            "target_department": "General Medicine",
            "priority": "M",
            "triage_level": 3,
        },
    ]

    def __init__(
        self,
        *,
        patient_repo,
        visit_repo,
        queue_repo,
        session_repo,
        patient_state_machine,
        visit_state_machine,
        bus,
        enabled: bool,
        tick_interval_seconds: float,
        spawn_interval_seconds: float,
        max_active_patients: int,
        queue_wait_seconds: float,
        consult_seconds: float,
    ):
        self.patient_repo = patient_repo
        self.visit_repo = visit_repo
        self.queue_repo = queue_repo
        self.session_repo = session_repo
        self.patient_state_machine = patient_state_machine
        self.visit_state_machine = visit_state_machine
        self.bus = bus

        self.enabled = enabled
        self.tick_interval_seconds = max(0.5, tick_interval_seconds)
        self.spawn_interval_seconds = max(0.0, spawn_interval_seconds)
        self.max_active_patients = max(1, max_active_patients)
        self.queue_wait_seconds = max(0.0, queue_wait_seconds)
        self.consult_seconds = max(0.0, consult_seconds)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_spawn_at: datetime | None = None
        self._next_archetype_index = 0

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="npc-simulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.tick_interval_seconds):
            try:
                self.tick()
            except Exception:
                # Simulator should never crash the backend runtime.
                continue

    def tick(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._spawn_if_needed()
            for patient_row in self._list_active_simulated_patients():
                self._advance_patient(patient_row)

    def count_active_simulated_patients(self) -> int:
        return len(self._list_active_simulated_patients())

    def _is_simulated_patient(self, patient_id: str) -> bool:
        return str(patient_id).startswith(SIMULATED_PATIENT_ID_PREFIX)

    def _list_active_simulated_patients(self) -> list[dict]:
        rows = self.patient_repo.list()
        return [
            row
            for row in rows
            if self._is_simulated_patient(row.get("id"))
            and row.get("lifecycle_state") not in TERMINAL_PATIENT_STATES
        ]

    def _spawn_if_needed(self) -> None:
        active = self._list_active_simulated_patients()
        if len(active) >= self.max_active_patients:
            return

        now = datetime.now(timezone.utc)
        if self._last_spawn_at:
            elapsed = (now - self._last_spawn_at).total_seconds()
            if elapsed < self.spawn_interval_seconds:
                return

        self._spawn_one_patient()
        self._last_spawn_at = now

    def _spawn_one_patient(self) -> None:
        patient_id = self._build_next_patient_id()
        archetype = self.archetypes[self._next_archetype_index % len(self.archetypes)]
        self._next_archetype_index += 1

        triage_session_id = f"session-npc-{uuid.uuid4().hex[:8]}"
        visit_data = {
            "is_simulated": True,
            "simulator": {
                "archetype_id": archetype["id"],
                "display_name": archetype["display_name"],
                "age": archetype["age"],
                "symptom_tags": archetype["symptom_tags"],
                "target_department": archetype["target_department"],
            },
            "triage_session_id": triage_session_id,
        }

        visit_row = self.visit_repo.create(
            patient_id=patient_id,
            state=VisitLifecycleState.TRIAGED,
            current_node="triage_done",
            current_department=archetype["target_department"],
            active_agent_type="triage",
            data=visit_data,
        )

        triage_note = (
            f"Simulated archetype={archetype['id']}; age={archetype['age']}; "
            f"symptoms={','.join(archetype['symptom_tags'])}; "
            f"target_department={archetype['target_department']}"
        )

        self.patient_repo.save_view(
            {
                "id": patient_id,
                "name": f"NPC {archetype['display_name']} {patient_id[-3:]}",
                "lifecycle_state": PatientLifecycleState.TRIAGED.value,
                "state": self.patient_state_machine.label_for(PatientLifecycleState.TRIAGED),
                "priority": archetype["priority"],
                "location": "Lobby",
                "updated_at": now_iso(),
                "triage": {
                    "level": archetype["triage_level"],
                    "note": triage_note,
                },
                "session_id": triage_session_id,
                "visit_id": visit_row["id"],
            }
        )

        self.session_repo.create_or_update(
            triage_session_id,
            patient_id,
            TriageDialogueState.TRIAGED.value,
            agent_type="triage",
            visit_id=visit_row["id"],
        )

        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": visit_row["id"],
                "patient_id": patient_id,
                "state": VisitLifecycleState.TRIAGED.value,
                "event": "simulator_spawned",
            },
        )

    def _build_next_patient_id(self) -> str:
        max_index = 0
        for row in self.patient_repo.list():
            patient_id = row.get("id") or ""
            if not self._is_simulated_patient(patient_id):
                continue
            suffix = patient_id.replace(SIMULATED_PATIENT_ID_PREFIX, "", 1)
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))
        return f"{SIMULATED_PATIENT_ID_PREFIX}{max_index + 1:03d}"

    def _advance_patient(self, patient_row: dict) -> None:
        visit_id = patient_row.get("visit_id")
        if not visit_id:
            return

        visit_row = self.visit_repo.get(visit_id)
        if not visit_row:
            return

        patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
        visit_state = VisitLifecycleState(visit_row["state"])

        if patient_state == PatientLifecycleState.TRIAGED and visit_state == VisitLifecycleState.TRIAGED:
            self._register_visit(patient_row, visit_row)
            return

        if patient_state == PatientLifecycleState.QUEUED and visit_state == VisitLifecycleState.REGISTERED:
            self._progress_queue_wait(patient_row, visit_row)
            return

        if patient_state == PatientLifecycleState.CALLED and visit_state == VisitLifecycleState.WAITING_CONSULTATION:
            self._enter_consultation(patient_row, visit_row)
            return

        if patient_state == PatientLifecycleState.IN_CONSULTATION and visit_state == VisitLifecycleState.IN_CONSULTATION:
            self._finish_consultation(patient_row, visit_row)

    def _register_visit(self, patient_row: dict, visit_row: dict) -> None:
        visit_data = self._get_visit_data(visit_row)
        visit_data["registration_completed_at"] = now_iso()
        self._transition_visit(
            visit_row,
            "register_completed",
            current_node="registration_queue",
            current_department=REGISTER_QUEUE_DEPARTMENT_NAME,
            active_agent_type=None,
            data=visit_data,
        )

        self.queue_repo.create_ticket(
            patient_id=patient_row["id"],
            department_id=REGISTER_QUEUE_DEPARTMENT_ID,
            department_name=REGISTER_QUEUE_DEPARTMENT_NAME,
            visit_id=visit_row["id"],
        )

        next_state = self.patient_state_machine.transition(
            PatientLifecycleState(patient_row["lifecycle_state"]),
            "queue_created",
        )
        self._update_patient_state(
            patient_row["id"],
            next_state,
            location=REGISTER_QUEUE_DEPARTMENT_NAME,
            visit_id=visit_row["id"],
        )

    def _progress_queue_wait(self, patient_row: dict, visit_row: dict) -> None:
        visit_data = self._get_visit_data(visit_row)
        registered_at = parse_iso(visit_data.get("registration_completed_at")) or parse_iso(visit_row.get("updated_at"))
        if not registered_at:
            return

        elapsed = (datetime.now(timezone.utc) - registered_at).total_seconds()
        if elapsed < self.queue_wait_seconds:
            return

        ticket = self.queue_repo.get_active_ticket_for_patient(patient_row["id"], visit_id=visit_row["id"])
        if ticket and ticket.get("status") == QueueTicketStatus.WAITING.value:
            ticket = self.queue_repo.mark_called(ticket["id"]) or ticket
            self.bus.publish(
                QUEUE_TICKET_CALLED,
                {
                    "patient_id": patient_row["id"],
                    "visit_id": visit_row["id"],
                    "ticket": ticket,
                },
            )

        next_state = self.patient_state_machine.transition(
            PatientLifecycleState(patient_row["lifecycle_state"]),
            "ticket_called",
        )
        self._update_patient_state(
            patient_row["id"],
            next_state,
            location=REGISTER_QUEUE_DEPARTMENT_NAME,
            visit_id=visit_row["id"],
        )

        self._transition_visit(
            visit_row,
            "queue_wait_elapsed",
            current_node="doctor_entry_gate",
            current_department=REGISTER_QUEUE_DEPARTMENT_NAME,
            active_agent_type=None,
            data=visit_data,
        )

    def _enter_consultation(self, patient_row: dict, visit_row: dict) -> None:
        ticket = self.queue_repo.get_active_ticket_for_patient(patient_row["id"], visit_id=visit_row["id"])
        if not ticket or ticket.get("status") != QueueTicketStatus.CALLED.value:
            return

        self.queue_repo.mark_completed(ticket["id"])

        next_state = self.patient_state_machine.transition(
            PatientLifecycleState(patient_row["lifecycle_state"]),
            "start_consultation",
        )

        visit_data = self._get_visit_data(visit_row)
        visit_data["consultation_started_at"] = now_iso()

        internal_session_id = visit_data.get("internal_medicine_session_id")
        if not internal_session_id:
            internal_session_id = f"im-session-npc-{uuid.uuid4().hex[:8]}"
            self.session_repo.create_or_update(
                internal_session_id,
                patient_row["id"],
                InternalMedicineDialogueState.COLLECTING_INFO.value,
                agent_type="internal_medicine",
                visit_id=visit_row["id"],
            )
            visit_data["internal_medicine_session_id"] = internal_session_id

        self._update_patient_state(
            patient_row["id"],
            next_state,
            location="Consultation",
            visit_id=visit_row["id"],
            session_id=internal_session_id,
        )

        self._transition_visit(
            visit_row,
            "start_consultation",
            current_node="consultation_room",
            current_department="Consultation",
            active_agent_type="internal_medicine",
            data=visit_data,
        )

    def _finish_consultation(self, patient_row: dict, visit_row: dict) -> None:
        visit_data = self._get_visit_data(visit_row)
        started_at = parse_iso(visit_data.get("consultation_started_at")) or parse_iso(visit_row.get("updated_at"))
        if not started_at:
            return

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        if elapsed < self.consult_seconds:
            return

        next_state = self.patient_state_machine.transition(
            PatientLifecycleState(patient_row["lifecycle_state"]),
            "finish",
        )
        self._update_patient_state(
            patient_row["id"],
            next_state,
            location="Completed",
            visit_id=visit_row["id"],
        )

        self._transition_visit(
            visit_row,
            "complete_visit",
            current_node="completed",
            current_department="Completed",
            active_agent_type=None,
            data=visit_data,
        )

    def _transition_visit(
        self,
        visit_row: dict,
        event: str,
        *,
        current_node: str | None,
        current_department: str | None,
        active_agent_type: str | None,
        data: dict,
    ) -> dict:
        current_state = VisitLifecycleState(visit_row["state"])
        next_state = self.visit_state_machine.transition(current_state, event)
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            state=next_state.value,
            current_node=current_node if current_node is not None else visit_row.get("current_node"),
            current_department=current_department if current_department is not None else visit_row.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            data=data,
        )
        self.bus.publish(
            VISIT_STATE_CHANGED,
            {
                "visit_id": updated["id"],
                "patient_id": updated["patient_id"],
                "state": updated["state"],
                "event": event,
            },
        )
        return updated

    def _update_patient_state(
        self,
        patient_id: str,
        lifecycle_state: PatientLifecycleState,
        *,
        location: str,
        visit_id: str,
        session_id: str | None = None,
    ) -> dict:
        updated = self.patient_repo.update_patient(
            patient_id,
            lifecycle_state=lifecycle_state.value,
            state=self.patient_state_machine.label_for(lifecycle_state),
            location=location,
            visit_id=visit_id,
            session_id=session_id,
        )
        self.bus.publish(
            PATIENT_STATE_CHANGED,
            {
                "patient_id": patient_id,
                "lifecycle_state": lifecycle_state.value,
            },
        )
        return updated

    @staticmethod
    def _get_visit_data(visit_row: dict) -> dict:
        payload = visit_row.get("data_json")
        if not payload:
            return {}
        try:
            import json

            return json.loads(payload)
        except Exception:
            return {}
