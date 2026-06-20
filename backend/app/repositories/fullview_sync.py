from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FullviewSyncRepository:
    def __init__(self, db):
        self.db = db
        self.visual_cooldown_enabled = False
        self.admission_gap_seconds = 4.0

    def set_visual_cooldown_enabled(self, enabled: bool) -> None:
        self.visual_cooldown_enabled = bool(enabled)

    def set_admission_gap_seconds(self, seconds: float) -> None:
        self.admission_gap_seconds = max(0.0, float(seconds))

    def enqueue_batch(self, commands: list[dict]) -> list[dict]:
        if not commands:
            return []
        encounter_ids = {str(command["encounter_id"]) for command in commands}
        if len(encounter_ids) != 1:
            raise ValueError("Fullview command batches must belong to one encounter")
        encounter_id = next(iter(encounter_ids))
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) AS value FROM fullview_sync_outbox WHERE encounter_id=?",
                (encounter_id,),
            ).fetchone()
            next_sequence = int(row["value"]) + 1
            for command in commands:
                existing = conn.execute(
                    """
                    SELECT command_id FROM fullview_sync_outbox
                    WHERE command_id=? OR transition_key=? OR idempotency_key=?
                    LIMIT 1
                    """,
                    (
                        command["command_id"],
                        command["transition_key"],
                        command["idempotency_key"],
                    ),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    """
                    INSERT INTO fullview_sync_outbox (
                        command_id, transition_key, patient_id, encounter_id, sequence_no,
                        request_type, event_id, payload_json, idempotency_key, status,
                        attempt_count, next_attempt_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                    """,
                    (
                        command["command_id"],
                        command["transition_key"],
                        command["patient_id"],
                        command["encounter_id"],
                        next_sequence,
                        command["request_type"],
                        command.get("event_id"),
                        json.dumps(command["payload"], ensure_ascii=False, sort_keys=True),
                        command["idempotency_key"],
                        command.get("next_attempt_at") or now_iso(),
                        command.get("created_at") or now_iso(),
                        command.get("updated_at") or now_iso(),
                    ),
                )
                next_sequence += 1
            conn.commit()
            return self.list_for_encounter(encounter_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_projection(self, patient_id: str, encounter_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM fullview_patient_projection
                WHERE patient_id = ? AND encounter_id = ?
                """,
                (patient_id, encounter_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_planned_room(self, encounter_id: str) -> str | None:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT payload_json FROM fullview_sync_outbox
                WHERE encounter_id=? AND status NOT IN ('blocked', 'dead_letter', 'skipped')
                ORDER BY sequence_no DESC
                LIMIT 10
                """,
                (encounter_id,),
            ).fetchall()
            for row in rows:
                target = json.loads(row["payload_json"] or "{}").get("to_room_id")
                if target and target != "exit":
                    return str(target)
            return None
        finally:
            conn.close()

    def get_step_gate_blocker(self, encounter_id: str) -> dict | None:
        """Return the first Fullview command not yet accepted or skipped."""
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT command_id, patient_id, encounter_id, sequence_no, request_type,
                       event_id, status, reason_code, last_error, visual_ready_at, updated_at
                FROM fullview_sync_outbox
                WHERE encounter_id=?
                  AND (
                    status NOT IN ('observed', 'cleanup_complete', 'skipped')
                    OR (
                      ?=1
                      AND status='observed'
                      AND visual_ready_at IS NOT NULL
                      AND visual_ready_at > ?
                    )
                  )
                ORDER BY sequence_no ASC
                LIMIT 1
                """,
                (encounter_id, 1 if self.visual_cooldown_enabled else 0, timestamp),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def mark_local_status(
        self,
        *,
        patient_id: str,
        encounter_id: str,
        status: str,
        event_id: str,
        error: str | None,
    ) -> None:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO fullview_patient_projection (
                    patient_id, encounter_id, current_room_id, sync_status,
                    last_command_id, last_event_id, last_event_seq, last_error, updated_at
                )
                VALUES (?, ?, NULL, ?, NULL, ?, NULL, ?, ?)
                ON CONFLICT(patient_id, encounter_id) DO UPDATE SET
                    sync_status=excluded.sync_status,
                    last_event_id=excluded.last_event_id,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (patient_id, encounter_id, status, event_id, error, timestamp),
            )
            conn.commit()
        finally:
            conn.close()

    def get_next_ready(self, now: str | None = None) -> dict | None:
        timestamp = now or now_iso()
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT candidate.*
                FROM fullview_sync_outbox candidate
                WHERE candidate.status IN ('pending', 'retryable')
                  AND candidate.next_attempt_at <= ?
                  AND NOT EXISTS (
                    SELECT 1
                    FROM fullview_sync_outbox earlier
                    WHERE earlier.encounter_id = candidate.encounter_id
                      AND earlier.sequence_no < candidate.sequence_no
                      AND (
                        earlier.status NOT IN ('observed', 'cleanup_complete', 'skipped')
                        OR (
                          earlier.status='observed'
                          AND earlier.visual_ready_at IS NOT NULL
                          AND earlier.visual_ready_at > ?
                        )
                      )
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM fullview_listener_state state
                    WHERE state.id=1
                      AND state.cleanup_barrier_until IS NOT NULL
                      AND state.cleanup_barrier_until > ?
                  )
                  AND (
                    candidate.request_type <> 'patient_upsert'
                    OR NOT EXISTS (
                      SELECT 1
                      FROM fullview_sync_outbox admission
                      WHERE admission.request_type='patient_upsert'
                        AND admission.command_id <> candidate.command_id
                        AND (
                          admission.status IN ('sending', 'accepted_unobserved')
                          OR (
                            admission.status='observed'
                            AND admission.visual_ready_at IS NOT NULL
                            AND admission.visual_ready_at > ?
                          )
                        )
                    )
                  )
                ORDER BY candidate.created_at ASC, candidate.sequence_no ASC
                LIMIT 1
                """,
                (
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            ).fetchone()
            return self._decode_row(row) if row else None
        finally:
            conn.close()

    def mark_sending(self, command_id: str) -> None:
        self._update_status(command_id, status="sending")

    def mark_accepted(
        self,
        command_id: str,
        response: dict,
        *,
        visual_cooldown_seconds: float = 0.0,
    ) -> None:
        row = self.get(command_id)
        if not row:
            return
        core = response.get("core_response") or {}
        event_seq = core.get("event_seq") or core.get("eventSeq")
        payload = row["payload"]
        target_room = (
            (core.get("animation_plan") or {}).get("to_room_id")
            or (core.get("animationPlan") or {}).get("toRoomId")
            or payload.get("to_room_id")
            or payload.get("room_id")
        )
        if target_room == "exit":
            target_room = None
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            observed = conn.execute(
                """
                SELECT observed_at FROM fullview_observed_events
                WHERE event_seq=? AND patient_id=?
                """,
                (event_seq, row["patient_id"]),
            ).fetchone() if event_seq is not None else None
            observed_at = observed["observed_at"] if observed else None
            status = "observed" if observed_at else "accepted_unobserved"
            observe_status = "observed" if observed_at else "pending"
            visual_ready_at = (
                (
                    datetime.fromisoformat(observed_at)
                    + timedelta(seconds=max(0.0, float(visual_cooldown_seconds)))
                ).isoformat()
                if observed_at
                else None
            )
            conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status=?, response_json=?, event_seq=?, trace_id=?,
                    reason_code=NULL, last_error=NULL, accepted_at=?,
                    observed_at=?, observe_status=?, visual_cooldown_seconds=?,
                    visual_ready_at=?, updated_at=?
                WHERE command_id=?
                """,
                (
                    status,
                    json.dumps(response, ensure_ascii=False),
                    event_seq,
                    response.get("trace_id"),
                    timestamp,
                    observed_at,
                    observe_status,
                    max(0.0, float(visual_cooldown_seconds)),
                    visual_ready_at,
                    timestamp,
                    command_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO fullview_patient_projection (
                    patient_id, encounter_id, current_room_id, sync_status,
                    last_command_id, last_event_id, last_event_seq, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                ON CONFLICT(patient_id, encounter_id) DO UPDATE SET
                    current_room_id=CASE
                        WHEN excluded.last_event_id='OP_PATIENT_EXIT_HOSPITAL' THEN NULL
                        ELSE COALESCE(excluded.current_room_id, fullview_patient_projection.current_room_id)
                    END,
                    sync_status=excluded.sync_status,
                    last_command_id=excluded.last_command_id,
                    last_event_id=excluded.last_event_id,
                    last_event_seq=excluded.last_event_seq,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    row["patient_id"],
                    row["encounter_id"],
                    target_room,
                    status,
                    command_id,
                    row.get("event_id"),
                    event_seq,
                    timestamp,
                ),
            )
            conn.commit()
            return
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_retryable(
        self,
        command_id: str,
        *,
        attempt_count: int,
        next_attempt_at: str,
        reason_code: str | None,
        error: str,
        response: dict | None = None,
    ) -> None:
        self._mark_failed(
            command_id,
            status="retryable",
            attempt_count=attempt_count,
            next_attempt_at=next_attempt_at,
            reason_code=reason_code,
            error=error,
            response=response,
        )

    def mark_blocked(
        self,
        command_id: str,
        *,
        attempt_count: int,
        reason_code: str | None,
        error: str,
        response: dict | None = None,
    ) -> None:
        self._mark_failed(
            command_id,
            status="blocked",
            attempt_count=attempt_count,
            next_attempt_at=now_iso(),
            reason_code=reason_code,
            error=error,
            response=response,
        )

    def mark_dead_letter(
        self,
        command_id: str,
        *,
        attempt_count: int,
        reason_code: str | None,
        error: str,
        response: dict | None = None,
    ) -> None:
        self._mark_failed(
            command_id,
            status="dead_letter",
            attempt_count=attempt_count,
            next_attempt_at=now_iso(),
            reason_code=reason_code,
            error=error,
            response=response,
        )

    def retry(self, command_id: str) -> dict | None:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='pending', next_attempt_at=?, last_error=NULL,
                    reason_code=NULL, updated_at=?
                WHERE command_id=? AND status IN (
                    'blocked', 'dead_letter', 'retryable', 'observe_timeout'
                )
                """,
                (timestamp, timestamp, command_id),
            )
            conn.commit()
            return self.get(command_id)
        finally:
            conn.close()

    def recover_sending(self) -> None:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='retryable', next_attempt_at=?, updated_at=?
                WHERE status='sending'
                """,
                (timestamp, timestamp),
            )
            conn.commit()
        finally:
            conn.close()

    def get_listener_cursor(self) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT last_event_seq FROM fullview_listener_state WHERE id=1"
            ).fetchone()
            return int(row["last_event_seq"] or 0) if row else 0
        finally:
            conn.close()

    def observe_event(self, event: dict) -> bool:
        event_seq = int(event.get("eventSeq") or event.get("event_seq") or 0)
        if event_seq <= 0:
            return False
        patient_id = event.get("patientId") or event.get("patient_id")
        event_type = event.get("eventType") or event.get("event_type")
        event_id = event.get("eventId") or event.get("event_id")
        occurred_at = event.get("occurredAt") or event.get("occurred_at")
        animation = event.get("animationPlan") or event.get("animation_plan") or {}
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO fullview_observed_events (
                    event_seq, patient_id, event_type, event_id, payload_json,
                    occurred_at, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_seq,
                    patient_id,
                    event_type,
                    event_id,
                    json.dumps(event, ensure_ascii=False),
                    occurred_at,
                    timestamp,
                ),
            )
            inserted = bool(cursor.rowcount)
            if inserted:
                command = conn.execute(
                    """
                    SELECT * FROM fullview_sync_outbox
                    WHERE event_seq=? AND patient_id=?
                    LIMIT 1
                    """,
                    (event_seq, patient_id),
                ).fetchone()
                if command and command["status"] == "accepted_unobserved":
                    cooldown = max(0.0, float(command["visual_cooldown_seconds"] or 0))
                    ready_at = (
                        datetime.fromisoformat(timestamp) + timedelta(seconds=cooldown)
                    ).isoformat()
                    conn.execute(
                        """
                        UPDATE fullview_sync_outbox
                        SET status='observed', observed_at=?, observe_status='observed',
                            visual_ready_at=?, last_error=NULL, reason_code=NULL,
                            updated_at=?
                        WHERE command_id=?
                        """,
                        (timestamp, ready_at, timestamp, command["command_id"]),
                    )
                    conn.execute(
                        """
                        UPDATE fullview_patient_projection
                        SET sync_status='observed', last_event_seq=?,
                            last_error=NULL, updated_at=?
                        WHERE patient_id=? AND encounter_id=?
                        """,
                        (
                            event_seq,
                            timestamp,
                            command["patient_id"],
                            command["encounter_id"],
                        ),
                    )
            movement_observed_at = None
            if patient_id and animation and event_type not in {"patient.deleted", "PATIENT_DELETE"}:
                movement_observed_at = timestamp
            conn.execute(
                """
                UPDATE fullview_listener_state
                SET last_event_seq=MAX(last_event_seq, ?),
                    last_event_at=?,
                    last_movement_observed_at=COALESCE(?, last_movement_observed_at),
                    updated_at=?
                WHERE id=1
                """,
                (event_seq, timestamp, movement_observed_at, timestamp),
            )
            conn.commit()
            return inserted
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_observe_timeouts(self, timeout_seconds: float) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max(1.0, float(timeout_seconds)))
        ).isoformat()
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='observe_timeout', observe_status='timeout',
                    reason_code='EVENT_NOT_OBSERVED',
                    last_error='Fullview accepted the command but its event was not observed',
                    updated_at=?
                WHERE status='accepted_unobserved'
                  AND accepted_at IS NOT NULL
                  AND accepted_at <= ?
                """,
                (timestamp, cutoff),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def mark_cleanup_pending(
        self,
        command_id: str,
        *,
        attempt_count: int,
        response: dict,
    ) -> None:
        row = self.get(command_id)
        if not row:
            return
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='cleanup_pending', attempt_count=?, response_json=?,
                    reason_code='REQUEST_TYPE_NOT_ENABLED',
                    last_error=NULL, observe_status='not_applicable', updated_at=?
                WHERE command_id=?
                """,
                (
                    attempt_count,
                    json.dumps(response, ensure_ascii=False),
                    timestamp,
                    command_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO fullview_cleanup_queue (
                    patient_id, encounter_id, command_id, status, attempt_count,
                    next_attempt_at, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, 'cleanup_pending', 0, ?, NULL, ?, ?)
                ON CONFLICT(patient_id) DO UPDATE SET
                    encounter_id=excluded.encounter_id,
                    command_id=excluded.command_id,
                    status='cleanup_pending',
                    next_attempt_at=excluded.next_attempt_at,
                    last_error=NULL,
                    updated_at=excluded.updated_at
                """,
                (
                    row["patient_id"],
                    row["encounter_id"],
                    command_id,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def enqueue_cleanup_patients(self, patient_ids: list[str]) -> int:
        resolved = sorted({str(item) for item in patient_ids if item})
        if not resolved:
            return 0
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            for patient_id in resolved:
                command = conn.execute(
                    """
                    SELECT encounter_id, command_id
                    FROM fullview_sync_outbox
                    WHERE patient_id=?
                    ORDER BY sequence_no DESC LIMIT 1
                    """,
                    (patient_id,),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO fullview_cleanup_queue (
                        patient_id, encounter_id, command_id, status, attempt_count,
                        next_attempt_at, last_error, created_at, updated_at
                    ) VALUES (?, ?, ?, 'cleanup_pending', 0, ?, NULL, ?, ?)
                    ON CONFLICT(patient_id) DO UPDATE SET
                        status='cleanup_pending', next_attempt_at=excluded.next_attempt_at,
                        last_error=NULL, updated_at=excluded.updated_at
                    """,
                    (
                        patient_id,
                        command["encounter_id"] if command else None,
                        command["command_id"] if command else None,
                        timestamp,
                        timestamp,
                        timestamp,
                    ),
                )
            conn.commit()
            return len(resolved)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def claim_cleanup(self, idle_seconds: float) -> dict | None:
        timestamp = now_iso()
        idle_cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max(0.0, float(idle_seconds)))
        ).isoformat()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            unsafe = conn.execute(
                """
                SELECT 1
                WHERE EXISTS (
                    SELECT 1 FROM fullview_sync_outbox
                    WHERE status IN (
                        'sending', 'accepted_unobserved', 'observe_timeout'
                    )
                )
                OR EXISTS (
                    SELECT 1 FROM fullview_sync_outbox
                    WHERE status='observed'
                      AND visual_ready_at IS NOT NULL
                      AND visual_ready_at > ?
                )
                OR EXISTS (
                    SELECT 1 FROM fullview_listener_state
                    WHERE id=1
                      AND (
                        (last_movement_observed_at IS NOT NULL
                         AND last_movement_observed_at > ?)
                        OR (cleanup_barrier_until IS NOT NULL
                            AND cleanup_barrier_until > ?)
                      )
                )
                """,
                (timestamp, idle_cutoff, timestamp),
            ).fetchone()
            if unsafe:
                conn.rollback()
                return None
            row = conn.execute(
                """
                SELECT * FROM fullview_cleanup_queue
                WHERE status IN ('cleanup_pending', 'retryable')
                  AND next_attempt_at <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (timestamp,),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            barrier_until = (
                datetime.now(timezone.utc) + timedelta(seconds=0.25)
            ).isoformat()
            conn.execute(
                """
                UPDATE fullview_cleanup_queue
                SET status='deleting', updated_at=?
                WHERE patient_id=?
                """,
                (timestamp, row["patient_id"]),
            )
            conn.execute(
                """
                UPDATE fullview_listener_state
                SET cleanup_barrier_until=?, updated_at=? WHERE id=1
                """,
                (barrier_until, timestamp),
            )
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finish_cleanup(
        self,
        patient_id: str,
        *,
        accepted: bool,
        error: str | None = None,
    ) -> None:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM fullview_cleanup_queue WHERE patient_id=?",
                (patient_id,),
            ).fetchone()
            if not row:
                conn.rollback()
                return
            if accepted:
                conn.execute(
                    """
                    UPDATE fullview_cleanup_queue
                    SET status='deleted', last_error=NULL, updated_at=?
                    WHERE patient_id=?
                    """,
                    (timestamp, patient_id),
                )
                if row["command_id"]:
                    conn.execute(
                        """
                        UPDATE fullview_sync_outbox
                        SET status='cleanup_complete', observe_status='not_applicable',
                            visual_ready_at=?, last_error=NULL, reason_code=NULL,
                            updated_at=?
                        WHERE command_id=?
                        """,
                        (timestamp, timestamp, row["command_id"]),
                    )
            else:
                attempts = int(row["attempt_count"] or 0) + 1
                next_attempt = (
                    datetime.now(timezone.utc) + timedelta(seconds=min(30, 2 ** min(attempts, 5)))
                ).isoformat()
                conn.execute(
                    """
                    UPDATE fullview_cleanup_queue
                    SET status='retryable', attempt_count=?, next_attempt_at=?,
                        last_error=?, updated_at=?
                    WHERE patient_id=?
                    """,
                    (attempts, next_attempt, error, timestamp, patient_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def cleanup_status(self, patient_ids: list[str] | None = None) -> dict[str, str]:
        conn = self.db.connect()
        try:
            if patient_ids:
                ids = sorted({str(item) for item in patient_ids if item})
                placeholders = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"SELECT patient_id, status FROM fullview_cleanup_queue WHERE patient_id IN ({placeholders})",
                    ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT patient_id, status FROM fullview_cleanup_queue"
                ).fetchall()
            return {str(row["patient_id"]): str(row["status"]) for row in rows}
        finally:
            conn.close()

    def retry_configuration_failures(self) -> int:
        """Retry commands that may succeed after a Fullview catalog migration."""
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='pending', attempt_count=0, next_attempt_at=?,
                    last_error=NULL, updated_at=?
                WHERE status IN ('blocked', 'dead_letter', 'retryable')
                  AND reason_code IN ('ROOM_NOT_FOUND', 'RULE_NOT_FOUND')
                """,
                (timestamp, timestamp),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def retry_recoverable_failures(self) -> int:
        """Recover waits that should not remain terminal after a restart or upgrade."""
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='pending', attempt_count=0, next_attempt_at=?,
                    last_error=NULL, updated_at=?
                WHERE status IN ('blocked', 'dead_letter', 'retryable')
                  AND (
                    reason_code IN (
                      'BED_UNAVAILABLE', 'ICU_BED_UNAVAILABLE',
                      'WARD_BED_UNAVAILABLE', 'NO_AVAILABLE_BED',
                      'OUTPATIENT_SLOT_UNAVAILABLE', 'TARGET_STILL_AVAILABLE',
                      'ESCORT_UNAVAILABLE', 'RESOURCE_BLOCKED'
                    )
                    OR (
                      request_type='discharge_request'
                      AND reason_code='REQUEST_TYPE_NOT_ENABLED'
                    )
                  )
                """,
                (timestamp, timestamp),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def get(self, command_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM fullview_sync_outbox WHERE command_id=?",
                (command_id,),
            ).fetchone()
            return self._decode_row(row) if row else None
        finally:
            conn.close()

    def list_recent(self, limit: int = 100) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT candidate.*,
                       (
                           SELECT earlier.command_id
                           FROM fullview_sync_outbox earlier
                           WHERE earlier.encounter_id = candidate.encounter_id
                             AND earlier.sequence_no < candidate.sequence_no
                             AND earlier.status NOT IN ('observed', 'cleanup_complete', 'skipped')
                           ORDER BY earlier.sequence_no ASC
                           LIMIT 1
                       ) AS blocked_by_command_id
                FROM fullview_sync_outbox candidate
                ORDER BY candidate.created_at DESC, candidate.sequence_no DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
            return [self._decode_row(row) for row in rows]
        finally:
            conn.close()

    def get_status_counts(self) -> dict[str, int]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM fullview_sync_outbox
                GROUP BY status
                """
            ).fetchall()
            return {str(row["status"]): int(row["count"]) for row in rows}
        finally:
            conn.close()

    def get_delivery_backlog_count(self) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM fullview_sync_outbox
                WHERE status IN (
                    'pending', 'sending', 'retryable',
                    'accepted_unobserved', 'observe_timeout'
                )
                """
            ).fetchone()
            return int(row["count"] or 0)
        finally:
            conn.close()

    def get_visual_backlog_patient_count(self, now: str | None = None) -> int:
        """Count patients whose Fullview delivery or visual hold is unfinished."""
        timestamp = now or now_iso()
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT patient_id) AS count
                FROM fullview_sync_outbox
                WHERE status IN (
                    'pending', 'sending', 'retryable',
                    'accepted_unobserved', 'observe_timeout'
                )
                   OR (
                     status='observed'
                     AND visual_ready_at IS NOT NULL
                     AND visual_ready_at > ?
                   )
                """,
                (
                    timestamp,
                ),
            ).fetchone()
            return int(row["count"] or 0)
        finally:
            conn.close()

    def list_for_encounter(self, encounter_id: str) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT candidate.*,
                       (
                           SELECT earlier.command_id
                           FROM fullview_sync_outbox earlier
                           WHERE earlier.encounter_id = candidate.encounter_id
                             AND earlier.sequence_no < candidate.sequence_no
                             AND earlier.status NOT IN ('observed', 'cleanup_complete', 'skipped')
                           ORDER BY earlier.sequence_no ASC
                           LIMIT 1
                       ) AS blocked_by_command_id
                FROM fullview_sync_outbox candidate
                WHERE candidate.encounter_id=?
                ORDER BY candidate.sequence_no ASC
                """,
                (encounter_id,),
            ).fetchall()
            return [self._decode_row(row) for row in rows]
        finally:
            conn.close()

    def retry_encounter(self, encounter_id: str) -> int:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status='pending', attempt_count=0, next_attempt_at=?,
                    reason_code=NULL, last_error=NULL, updated_at=?
                WHERE encounter_id=?
                  AND status IN ('blocked', 'dead_letter', 'retryable', 'observe_timeout')
                """,
                (timestamp, timestamp, encounter_id),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def get_encounter_sync_status(self, encounter_id: str) -> dict:
        commands = self.list_for_encounter(encounter_id)
        counts: dict[str, int] = {}
        for command in commands:
            status = str(command.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        blocking = next(
            (
                command
                for command in commands
                if command.get("status") in {
                    "blocked", "dead_letter", "retryable", "sending",
                    "accepted_unobserved", "observe_timeout",
                }
            ),
            None,
        )
        patient_id = commands[0]["patient_id"] if commands else None
        projection = self.get_projection(patient_id, encounter_id) if patient_id else None
        return {
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "counts": counts,
            "blocking_command": blocking,
            "projection": projection,
            "commands": commands,
        }

    def next_sequence(self, encounter_id: str) -> int:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) AS value FROM fullview_sync_outbox WHERE encounter_id=?",
                (encounter_id,),
            ).fetchone()
            return int(row["value"]) + 1
        finally:
            conn.close()

    def has_request_type(self, encounter_id: str, request_type: str) -> bool:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT 1 FROM fullview_sync_outbox
                WHERE encounter_id=? AND request_type=?
                LIMIT 1
                """,
                (encounter_id, request_type),
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def skip_unfinished_for_patients(self, patient_ids: list[str], *, reason: str) -> int:
        resolved_ids = sorted({str(patient_id) for patient_id in patient_ids if patient_id})
        if not resolved_ids:
            return 0
        placeholders = ",".join("?" for _ in resolved_ids)
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                f"""
                UPDATE fullview_sync_outbox
                SET status='skipped', reason_code='RUNTIME_RESET', last_error=?, updated_at=?
                WHERE patient_id IN ({placeholders})
                  AND status IN (
                    'pending', 'retryable', 'sending', 'blocked', 'dead_letter',
                    'accepted_unobserved', 'observe_timeout'
                  )
                """,
                (reason, timestamp, *resolved_ids),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def list_managed_patient_ids(self) -> list[str]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT patient_id FROM fullview_sync_outbox
                UNION
                SELECT patient_id FROM fullview_patient_projection
                UNION
                SELECT patient_id FROM fullview_cleanup_queue
                ORDER BY patient_id
                """
            ).fetchall()
            return [str(row["patient_id"]) for row in rows if row["patient_id"]]
        finally:
            conn.close()

    def prepare_restart_cleanup(self) -> dict:
        patient_ids = self.list_managed_patient_ids()
        skipped = self.skip_unfinished_for_patients(
            patient_ids,
            reason="backend restart orphan cleanup",
        )
        queued = self.enqueue_cleanup_patients(patient_ids)
        return {
            "patient_ids": patient_ids,
            "skipped_commands": skipped,
            "queued_patients": queued,
        }

    def _mark_failed(
        self,
        command_id: str,
        *,
        status: str,
        attempt_count: int,
        next_attempt_at: str,
        reason_code: str | None,
        error: str,
        response: dict | None,
    ) -> None:
        row = self.get(command_id)
        if not row:
            return
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE fullview_sync_outbox
                SET status=?, attempt_count=?, next_attempt_at=?, reason_code=?,
                    last_error=?, response_json=?, updated_at=?
                WHERE command_id=?
                """,
                (
                    status,
                    attempt_count,
                    next_attempt_at,
                    reason_code,
                    error,
                    json.dumps(response or {}, ensure_ascii=False),
                    timestamp,
                    command_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO fullview_patient_projection (
                    patient_id, encounter_id, current_room_id, sync_status,
                    last_command_id, last_event_id, last_event_seq, last_error, updated_at
                )
                VALUES (?, ?, NULL, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(patient_id, encounter_id) DO UPDATE SET
                    sync_status=excluded.sync_status,
                    last_command_id=excluded.last_command_id,
                    last_event_id=excluded.last_event_id,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    row["patient_id"],
                    row["encounter_id"],
                    status,
                    command_id,
                    row.get("event_id"),
                    error,
                    timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_status(self, command_id: str, *, status: str) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                "UPDATE fullview_sync_outbox SET status=?, updated_at=? WHERE command_id=?",
                (status, now_iso(), command_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _decode_row(row) -> dict:
        payload = dict(row)
        payload["payload"] = json.loads(payload.pop("payload_json") or "{}")
        payload["response"] = json.loads(payload.pop("response_json") or "{}")
        return payload
