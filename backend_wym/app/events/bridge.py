from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.events.types import (
    ENCOUNTER_OPENED,
    ENCOUNTER_TRANSFERRED,
    TRIAGE_COMPLETED,
    VISIT_STATE_CHANGED,
)


logger = logging.getLogger(__name__)
CN_TZ = timezone(timedelta(hours=8))


class RedisMirrorPublisher:
    def __init__(
        self,
        *,
        enabled: bool,
        host: str,
        port: int,
        db: int,
        password: str | None,
        channel_prefix: str,
        durable_stream_enabled: bool,
        durable_stream_key: str,
    ):
        self.enabled = enabled
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.channel_prefix = channel_prefix
        self.durable_stream_enabled = durable_stream_enabled
        self.durable_stream_key = durable_stream_key
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        if not self.enabled:
            return None
        with self._client_lock:
            if self._client is False:
                return None
            if self._client is not None:
                return self._client
            try:
                import redis  # type: ignore

                self._client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    decode_responses=True,
                )
            except Exception as exc:
                logger.warning("redis mirror unavailable: %s", exc)
                self._client = False
            return self._client if self._client is not False else None

    def publish(self, event_type: str, envelope: dict) -> None:
        client = self._get_client()
        if client is None:
            return
        payload = json.dumps(envelope, ensure_ascii=False)
        channel = f"{self.channel_prefix}.{event_type}"
        try:
            client.publish(channel, payload)
            if self.durable_stream_enabled and event_type in {
                "patient.transferred",
                "patient.admitted",
                "patient.discharged",
                "vital.critical",
                "alert.raised",
            }:
                client.xadd(self.durable_stream_key, {"payload": payload}, maxlen=100_000)
        except Exception as exc:
            logger.warning("redis mirror publish failed: %s", exc)


class HospitalEventBridge:
    def __init__(self, *, producer: str, redis_publisher: RedisMirrorPublisher):
        self.producer = producer
        self.redis_publisher = redis_publisher
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers = [q for q in self._subscribers if q is not subscriber]

    def handle_internal_event(self, event_name: str, payload: dict) -> None:
        mapped_events = self._map_internal_event(event_name, payload)
        if not mapped_events:
            return
        for event_type, normalized_data in mapped_events:
            patient_id = normalized_data.get("patient_id") or payload.get("patient_id")
            if not patient_id:
                continue
            encounter_id = (
                normalized_data.get("encounter_id")
                or payload.get("encounter_id")
                or payload.get("visit_id")
            )
            envelope = self._build_envelope(
                event_type=event_type,
                patient_id=patient_id,
                encounter_id=encounter_id,
                data=normalized_data.get("data", {}),
                correlation_id=payload.get("correlation_id"),
            )
            self._fanout(envelope)
            self.redis_publisher.publish(event_type, envelope)

    def _fanout(self, envelope: dict) -> None:
        dead: list[queue.Queue] = []
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(envelope)
            except queue.Full:
                dead.append(subscriber)
        if dead:
            with self._lock:
                self._subscribers = [q for q in self._subscribers if q not in dead]

    def _build_envelope(
        self,
        *,
        event_type: str,
        patient_id: str,
        encounter_id: str | None,
        data: dict,
        correlation_id: str | None,
    ) -> dict:
        event_id = f"evt_{uuid.uuid4().hex[:26].upper()}"
        occurred_at = datetime.now(CN_TZ).isoformat(timespec="milliseconds")
        return {
            "event_id": event_id,
            "event_type": event_type,
            "schema_version": "1.0",
            "occurred_at": occurred_at,
            "producer": self.producer,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "correlation_id": correlation_id or event_id,
            "data": data,
        }

    @staticmethod
    def _map_internal_event(event_name: str, payload: dict) -> list[tuple[str, dict]]:
        mapped: list[tuple[str, dict]] = []
        if event_name == ENCOUNTER_OPENED:
            mapped.append(
                (
                    "encounter.opened",
                    {
                        "patient_id": payload.get("patient_id"),
                        "encounter_id": payload.get("encounter_id"),
                        "data": {
                            "state": payload.get("state"),
                            "department": payload.get("department"),
                        },
                    },
                )
            )
            mapped.append(
                (
                    "patient.arrived",
                    {
                        "patient_id": payload.get("patient_id"),
                        "encounter_id": payload.get("encounter_id"),
                        "data": {"location": payload.get("department") or "lobby"},
                    },
                )
            )
            return mapped

        if event_name == ENCOUNTER_TRANSFERRED:
            mapped.append(
                (
                    "patient.transferred",
                    {
                        "patient_id": payload.get("patient_id"),
                        "encounter_id": payload.get("encounter_id"),
                        "data": {
                            "from_group": payload.get("from_group"),
                            "to_group": payload.get("to_group"),
                            "reason": payload.get("reason"),
                            "ctas_level": payload.get("ctas_level"),
                            "status": payload.get("status"),
                        },
                    },
                )
            )
            return mapped

        if event_name == TRIAGE_COMPLETED:
            mapped.append(
                (
                    "patient.triaged",
                    {
                        "patient_id": payload.get("patient_id"),
                        "encounter_id": payload.get("visit_id"),
                        "data": {
                            "department": payload.get("department"),
                            "priority": payload.get("priority"),
                        },
                    },
                )
            )
            if payload.get("department"):
                mapped.append(
                    (
                        "patient.routed",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {
                                "target_department": payload.get("department"),
                                "priority": payload.get("priority"),
                                "source": "triage",
                            },
                        },
                    )
                )
            return mapped

        if event_name == VISIT_STATE_CHANGED:
            event = payload.get("event")
            if event in {"route_to_emergency", "route_to_icu_rescue"}:
                mapped.append(
                    (
                        "patient.transferred",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {
                                "from_group": payload.get("from_group") or "OUT",
                                "to_group": payload.get("to_group") or ("ICU" if event == "route_to_icu_rescue" else "ED"),
                                "reason": payload.get("reason") or "triage_high_risk_placeholder_route",
                                "ctas_level": f"L{payload.get('triage_level')}" if payload.get("triage_level") else None,
                                "status": "accepted",
                                "placeholder": bool(payload.get("placeholder", False)),
                            },
                        },
                    )
                )
                return mapped
            if event == "register_completed":
                mapped.append(
                    (
                        "patient.registered",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {"state": payload.get("state")},
                        },
                    )
                )
                mapped.append(
                    (
                        "patient.routed",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {"target_department": "doctor_entry", "source": "registration"},
                        },
                    )
                )
                return mapped
            if event == "start_consultation":
                mapped.append(
                    (
                        "encounter.consultation_started",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {"state": payload.get("state")},
                        },
                    )
                )
                return mapped
            if event == "consultation_completed":
                mapped.append(
                    (
                        "encounter.consultation_completed",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {"state": payload.get("state")},
                        },
                    )
                )
                return mapped
            state = (payload.get("state") or "").lower()
            if state in {"completed", "cancelled", "error"}:
                mapped.append(
                    (
                        "encounter.closed",
                        {
                            "patient_id": payload.get("patient_id"),
                            "encounter_id": payload.get("visit_id"),
                            "data": {"state": state, "reason": event},
                        },
                    )
                )
                return mapped
        return mapped
