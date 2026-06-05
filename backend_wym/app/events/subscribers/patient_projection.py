from app.domain.patient.state_machine import PatientStateMachine
from app.repositories.patients import PatientRepository
from app.schemas.common import PatientLifecycleState


class PatientProjectionSubscriber:
    def __init__(self, patient_repo: PatientRepository, patient_state_machine: PatientStateMachine):
        self.patient_repo = patient_repo
        self.patient_state_machine = patient_state_machine

    def handle_state_changed(self, payload: dict) -> None:
        patient = self.patient_repo.get(payload["patient_id"])
        if not patient:
            return
        lifecycle_state = PatientLifecycleState(payload["lifecycle_state"])
        self.patient_repo.update_patient(
            payload["patient_id"],
            state=self.patient_state_machine.label_for(lifecycle_state),
        )
