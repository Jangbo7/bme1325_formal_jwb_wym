from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from app.integrations.fullview import FullviewClientError


RETRYABLE_REASON_CODES = {
    "ROOM_NOT_FOUND",
    "RULE_NOT_FOUND",
    "BED_UNAVAILABLE",
    "ICU_BED_UNAVAILABLE",
    "WARD_BED_UNAVAILABLE",
    "NO_AVAILABLE_BED",
    "OUTPATIENT_SLOT_UNAVAILABLE",
    "TARGET_STILL_AVAILABLE",
    "ESCORT_UNAVAILABLE",
    "RESOURCE_BLOCKED",
}

RESOURCE_WAIT_REASON_CODES = {
    "BED_UNAVAILABLE",
    "ICU_BED_UNAVAILABLE",
    "WARD_BED_UNAVAILABLE",
    "NO_AVAILABLE_BED",
    "OUTPATIENT_SLOT_UNAVAILABLE",
    "TARGET_STILL_AVAILABLE",
    "ESCORT_UNAVAILABLE",
    "RESOURCE_BLOCKED",
}

logger = logging.getLogger(__name__)

VISUAL_COOLDOWN_SECONDS_BY_EVENT = {
    "OP_TRIAGE_TO_REGISTRATION": 4.0,
    "OP_REGISTRATION_TO_TARGET_QUEUE": 8.0,
    "OP_CURRENT_TO_TARGET_DOOR_QUEUE": 4.0,
    "OP_TARGET_DOOR_QUEUE_ADVANCE": 2.5,
    "OP_CONSULT_TO_PAYMENT": 5.0,
    "OP_PAYMENT_TO_LAB": 4.0,
    "OP_LAB_RETURN_TO_WAITING": 4.0,
    "OP_CURRENT_TO_PROCEDURE_QUEUE": 4.0,
    "OP_PROCEDURE_RETURN_TO_TARGET_QUEUE": 4.0,
    "OP_CONSULT_TO_PHARMACY": 5.0,
    "OP_REFERRAL_TO_REGISTRATION": 5.0,
    "OP_TO_WARD_MOVE": 12.0,
    "OP_TO_ICU_MOVE": 10.0,
    "TRANSFER_OP_TO_ED": 8.0,
    "OP_PATIENT_EXIT_HOSPITAL": 5.0,
}


class FullviewSyncWorker:
    def __init__(
        self,
        *,
        repo,
        client,
        enabled: bool,
        poll_interval_seconds: float,
        max_attempts: int,
        visual_cooldown_multiplier: float = 1.0,
        admission_gap_seconds: float = 4.0,
    ):
        self.repo = repo
        self.client = client
        self.enabled = enabled
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.visual_cooldown_multiplier = max(
            1.0,
            float(visual_cooldown_multiplier),
        )
        self.admission_gap_seconds = max(0.0, float(admission_gap_seconds))
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_loop_error: str | None = None
        self.last_loop_error_at: str | None = None

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self.repo.recover_sending()
        self.repo.retry_configuration_failures()
        self.repo.retry_recoverable_failures()
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="fullview-sync",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def wake(self) -> None:
        self._wake_event.set()

    def status(self) -> dict:
        return {
            "enabled": bool(self.enabled),
            "running": bool(self._thread and self._thread.is_alive()),
            "last_loop_error": self.last_loop_error,
            "last_loop_error_at": self.last_loop_error_at,
        }

    def tick(self) -> bool:
        command = self.repo.get_next_ready()
        if command is None:
            return False
        self.repo.mark_sending(command["command_id"])
        attempt_count = int(command.get("attempt_count") or 0) + 1
        idempotency_key = command["idempotency_key"]
        if (
            command.get("status") == "retryable"
            and command.get("reason_code") in RESOURCE_WAIT_REASON_CODES
        ):
            # Fullview caches rejected idempotent responses. A resource retry
            # must use a new key so availability is evaluated again.
            idempotency_key = f"{idempotency_key}-attempt-{attempt_count}"
        try:
            response = self.client.send(
                command["request_type"],
                command["payload"],
                idempotency_key,
            )
        except FullviewClientError as exc:
            self._retry_or_dead_letter(
                command,
                attempt_count=attempt_count,
                reason_code="FULLVIEW_UNAVAILABLE",
                error=str(exc),
            )
            return True
        except Exception as exc:
            self._retry_or_dead_letter(
                command,
                attempt_count=attempt_count,
                reason_code="FULLVIEW_CLIENT_ERROR",
                error=str(exc),
            )
            return True

        if response.get("accepted"):
            self.repo.mark_accepted(
                command["command_id"],
                response,
                visual_cooldown_seconds=(
                    self._visual_cooldown_seconds(command, response)
                    * self.visual_cooldown_multiplier
                    if command.get("request_type") != "patient_upsert"
                    else self.admission_gap_seconds
                ),
            )
            return True

        reason_code = str(response.get("reason_code") or "REQUEST_REJECTED")
        error = str(response.get("message") or "Fullview rejected the request")
        if (
            command.get("request_type") == "discharge_request"
            and reason_code == "REQUEST_TYPE_NOT_ENABLED"
        ):
            self.repo.mark_cleanup_pending(
                command["command_id"],
                attempt_count=attempt_count,
                response=response,
            )
            return True
        if reason_code in RETRYABLE_REASON_CODES:
            self._retry_or_dead_letter(
                command,
                attempt_count=attempt_count,
                reason_code=reason_code,
                error=error,
                response=response,
            )
        else:
            self.repo.mark_blocked(
                command["command_id"],
                attempt_count=attempt_count,
                reason_code=reason_code,
                error=error,
                response=response,
            )
        return True

    @staticmethod
    def _visual_cooldown_seconds(command: dict, response: dict) -> float:
        request_type = command.get("request_type")
        if request_type not in {
            "patient_upsert",
            "movement_request",
            "transfer_request",
            "discharge_request",
        }:
            return 0.0
        core = response.get("core_response") or {}
        animation = core.get("animation_plan") or core.get("animationPlan") or {}
        if not animation:
            return 0.0
        if request_type == "patient_upsert":
            return 3.0
        event_id = str(command.get("event_id") or "")
        return VISUAL_COOLDOWN_SECONDS_BY_EVENT.get(event_id, 4.0)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            processed = False
            try:
                processed = self.tick()
            except Exception as exc:
                self.last_loop_error = f"{type(exc).__name__}: {exc}"
                self.last_loop_error_at = datetime.now(timezone.utc).isoformat()
                logger.exception("Fullview sync worker loop failed")
                processed = False
            if processed:
                continue
            self._wake_event.wait(self.poll_interval_seconds)
            self._wake_event.clear()

    def _retry_or_dead_letter(
        self,
        command: dict,
        *,
        attempt_count: int,
        reason_code: str,
        error: str,
        response: dict | None = None,
    ) -> None:
        if reason_code in RESOURCE_WAIT_REASON_CODES:
            next_attempt_at = (
                datetime.now(timezone.utc) + timedelta(seconds=2)
            ).isoformat()
            self.repo.mark_retryable(
                command["command_id"],
                attempt_count=attempt_count,
                next_attempt_at=next_attempt_at,
                reason_code=reason_code,
                error=error,
                response=response,
            )
            return
        if attempt_count >= self.max_attempts:
            self.repo.mark_dead_letter(
                command["command_id"],
                attempt_count=attempt_count,
                reason_code=reason_code,
                error=error,
                response=response,
            )
            return
        delay_seconds = min(300, 2 ** min(attempt_count, 8))
        next_attempt_at = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ).isoformat()
        self.repo.mark_retryable(
            command["command_id"],
            attempt_count=attempt_count,
            next_attempt_at=next_attempt_at,
            reason_code=reason_code,
            error=error,
            response=response,
        )

class FullviewEventListener:
    def __init__(
        self,
        *,
        repo,
        client,
        enabled: bool,
        interval_seconds: float,
        observe_timeout_seconds: float,
        cleanup_idle_seconds: float,
        worker=None,
    ):
        self.repo = repo
        self.client = client
        self.enabled = bool(enabled)
        self.interval_seconds = max(0.1, float(interval_seconds))
        self.observe_timeout_seconds = max(1.0, float(observe_timeout_seconds))
        self.cleanup_idle_seconds = max(0.0, float(cleanup_idle_seconds))
        self.worker = worker
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_loop_error: str | None = None
        self.last_loop_error_at: str | None = None

    def start(self) -> None:
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self.repo.prepare_restart_cleanup()
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="fullview-event-listener",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def wake(self) -> None:
        self._wake_event.set()

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": bool(self._thread and self._thread.is_alive()),
            "cursor": self.repo.get_listener_cursor(),
            "last_loop_error": self.last_loop_error,
            "last_loop_error_at": self.last_loop_error_at,
        }

    def tick(self) -> bool:
        processed = False
        cursor = self.repo.get_listener_cursor()
        while True:
            events = self.client.fetch_events(cursor, limit=200)
            if not events:
                break
            for event in sorted(
                events,
                key=lambda item: int(item.get("eventSeq") or item.get("event_seq") or 0),
            ):
                self.repo.observe_event(event)
                cursor = max(
                    cursor,
                    int(event.get("eventSeq") or event.get("event_seq") or 0),
                )
                processed = True
            if len(events) < 200:
                break
        timed_out = self.repo.mark_observe_timeouts(self.observe_timeout_seconds)
        cleaned = self.cleanup_tick()
        if processed and self.worker is not None:
            self.worker.wake()
        return processed or bool(timed_out) or cleaned

    def cleanup_tick(self) -> bool:
        item = self.repo.claim_cleanup(self.cleanup_idle_seconds)
        if item is None:
            return False
        patient_id = item["patient_id"]
        try:
            response = self.client.delete_patient(patient_id)
            reason_code = response.get("reasonCode") or response.get("reason_code")
            accepted = bool(response.get("accepted") or reason_code == "PATIENT_NOT_FOUND")
            self.repo.finish_cleanup(
                patient_id,
                accepted=accepted,
                error=None if accepted else str(
                    response.get("message") or reason_code or "patient delete rejected"
                ),
            )
        except Exception as exc:
            self.repo.finish_cleanup(patient_id, accepted=False, error=str(exc))
        if self.worker is not None:
            self.worker.wake()
        return True

    def drain_cleanup(self, patient_ids: list[str], *, timeout_seconds: float = 15.0) -> dict:
        self.repo.enqueue_cleanup_patients(patient_ids)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=max(0.1, timeout_seconds))
        while datetime.now(timezone.utc) < deadline:
            statuses = self.repo.cleanup_status(patient_ids)
            if all(statuses.get(patient_id) == "deleted" for patient_id in patient_ids):
                return statuses
            self.tick()
            self._stop_event.wait(min(self.interval_seconds, 0.25))
        return self.repo.cleanup_status(patient_ids)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.tick()
                self.last_loop_error = None
                self.last_loop_error_at = None
            except Exception as exc:
                self.last_loop_error = f"{type(exc).__name__}: {exc}"
                self.last_loop_error_at = datetime.now(timezone.utc).isoformat()
                logger.exception("Fullview event listener loop failed")
                processed = False
            if processed:
                continue
            self._wake_event.wait(self.interval_seconds)
            self._wake_event.clear()


class FullviewSyncSubscriber:
    def __init__(self, mapping_service, worker):
        self.mapping_service = mapping_service
        self.worker = worker

    def handle_visit_state_changed(self, payload: dict) -> None:
        self.mapping_service.handle_visit_state_changed(payload)
        self.worker.wake()

    def handle_encounter_opened(self, payload: dict) -> None:
        self.mapping_service.handle_encounter_opened(payload)
        self.worker.wake()
