from __future__ import annotations


class DepartmentRuntimeProjector:
    def __init__(self, runtime_service):
        self.runtime_service = runtime_service

    def handle_triage_completed(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def handle_patient_state_changed(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def handle_visit_state_changed(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def handle_queue_ticket_created(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def handle_queue_ticket_called(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def handle_queue_ticket_completed(self, payload: dict) -> None:
        self._sync_from_payload(payload)

    def _sync_from_payload(self, payload: dict) -> None:
        patient_id = payload.get("patient_id")
        if not patient_id:
            return
        self.runtime_service.sync_patient_runtime(
            patient_id=patient_id,
            visit_id=payload.get("visit_id"),
        )
