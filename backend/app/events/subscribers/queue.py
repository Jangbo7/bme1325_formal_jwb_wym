from app.departments.registry import map_department_from_triage
from app.domain.patient.state_machine import PatientStateMachine
from app.events.types import PATIENT_STATE_CHANGED, QUEUE_TICKET_CREATED
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.schemas.common import PatientLifecycleState


class QueueSubscriber:
    def __init__(self, patient_repo: PatientRepository, queue_repo: QueueRepository, patient_state_machine: PatientStateMachine, bus):
        self.patient_repo = patient_repo
        self.queue_repo = queue_repo
        self.patient_state_machine = patient_state_machine
        self.bus = bus

    def handle_triage_completed(self, payload: dict) -> None:
        patient_id = payload["patient_id"]
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return
        if patient["lifecycle_state"] not in {PatientLifecycleState.TRIAGED.value, PatientLifecycleState.QUEUED.value}:
            return
        department = map_department_from_triage(payload.get("department", ""), payload.get("priority", "M"))
        ticket = self.queue_repo.create_ticket(
            patient_id=patient_id,
            department_id=department["queue_department_id"],
            department_name=department["label"],
        )
        current_state = PatientLifecycleState(patient["lifecycle_state"])
        queued_state = current_state if current_state == PatientLifecycleState.QUEUED else self.patient_state_machine.transition(current_state, "queue_created")
        self.patient_repo.update_patient(
            patient_id,
            lifecycle_state=queued_state.value,
            location=department["label"],
        )
        self.bus.publish(
            PATIENT_STATE_CHANGED,
            {
                "patient_id": patient_id,
                "lifecycle_state": queued_state.value,
            },
        )
        self.bus.publish(
            QUEUE_TICKET_CREATED,
            {
                "patient_id": patient_id,
                "ticket": ticket,
            },
        )
