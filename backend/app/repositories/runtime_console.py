from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.schemas.runtime_console import (
    RuntimeConsoleDepartmentConfig,
    RuntimeConsoleEvent,
    RuntimeConsoleGlobalConfig,
    RuntimeConsoleSession,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeConsoleRepository:
    def __init__(self, db):
        self.db = db

    def create_session(
        self,
        *,
        status: str,
        global_config: RuntimeConsoleGlobalConfig,
    ) -> RuntimeConsoleSession:
        session_id = f"runtime-session-{uuid.uuid4().hex}"
        now = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO runtime_console_sessions (
                    session_id, status, running, spawn_paused, step_paused, drain_mode,
                    mode, started_at, ended_at, updated_at, global_config_json
                )
                VALUES (?, ?, ?, 0, 0, 0, 'runtime_console', ?, NULL, ?, ?)
                """,
                (
                    session_id,
                    status,
                    1 if status in {"running", "paused", "draining"} else 0,
                    now,
                    now,
                    self.db.encode_json(global_config.model_dump()),
                ),
            )
            conn.commit()
            session = self.get_session(session_id)
            if session is None:
                raise RuntimeError("failed to create runtime console session")
            return session
        finally:
            conn.close()

    def update_session(self, session_id: str, **fields) -> RuntimeConsoleSession | None:
        if not fields:
            return self.get_session(session_id)
        payload = dict(fields)
        payload["updated_at"] = payload.get("updated_at") or now_iso()
        assignments = ", ".join(f"{key} = ?" for key in payload)
        conn = self.db.connect()
        try:
            conn.execute(
                f"UPDATE runtime_console_sessions SET {assignments} WHERE session_id = ?",
                (*payload.values(), session_id),
            )
            conn.commit()
            return self.get_session(session_id)
        finally:
            conn.close()

    def get_session(self, session_id: str) -> RuntimeConsoleSession | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT session_id, status, running, spawn_paused, step_paused, drain_mode,
                       mode, started_at, ended_at, updated_at
                FROM runtime_console_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            payload = dict(row)
            payload["running"] = bool(payload.get("running"))
            payload["spawn_paused"] = bool(payload.get("spawn_paused"))
            payload["step_paused"] = bool(payload.get("step_paused"))
            payload["drain_mode"] = bool(payload.get("drain_mode"))
            return RuntimeConsoleSession(**payload)
        finally:
            conn.close()

    def get_latest_session(self) -> RuntimeConsoleSession | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT session_id
                FROM runtime_console_sessions
                ORDER BY started_at DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            return self.get_session(str(row["session_id"]))
        finally:
            conn.close()

    def get_global_config(self, session_id: str) -> RuntimeConsoleGlobalConfig | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT global_config_json FROM runtime_console_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return RuntimeConsoleGlobalConfig(**self.db.decode_json(row["global_config_json"], {}))
        finally:
            conn.close()

    def update_global_config(self, session_id: str, global_config: RuntimeConsoleGlobalConfig) -> RuntimeConsoleGlobalConfig:
        self.update_session(
            session_id,
            global_config_json=self.db.encode_json(global_config.model_dump()),
        )
        resolved = self.get_global_config(session_id)
        if resolved is None:
            raise RuntimeError("runtime console session config missing after update")
        return resolved

    def replace_department_configs(
        self,
        session_id: str,
        department_configs: list[RuntimeConsoleDepartmentConfig],
    ) -> list[RuntimeConsoleDepartmentConfig]:
        conn = self.db.connect()
        now = now_iso()
        try:
            conn.execute(
                "DELETE FROM runtime_console_department_configs WHERE session_id = ?",
                (session_id,),
            )
            for config in department_configs:
                conn.execute(
                    """
                    INSERT INTO runtime_console_department_configs (
                        session_id, department_id, department_name, enabled, spawn_weight,
                        allow_agent_patients, allow_script_patients, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        config.department_id,
                        config.department_name,
                        1 if config.enabled else 0,
                        float(config.spawn_weight),
                        1 if config.allow_agent_patients else 0,
                        1 if config.allow_script_patients else 0,
                        now,
                    ),
                )
            conn.commit()
            return self.list_department_configs(session_id)
        finally:
            conn.close()

    def list_department_configs(self, session_id: str) -> list[RuntimeConsoleDepartmentConfig]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT department_id, department_name, enabled, spawn_weight,
                       allow_agent_patients, allow_script_patients, updated_at
                FROM runtime_console_department_configs
                WHERE session_id = ?
                ORDER BY department_id ASC
                """,
                (session_id,),
            ).fetchall()
            configs: list[RuntimeConsoleDepartmentConfig] = []
            for row in rows:
                payload = dict(row)
                payload["enabled"] = bool(payload.get("enabled"))
                payload["allow_agent_patients"] = bool(payload.get("allow_agent_patients"))
                payload["allow_script_patients"] = bool(payload.get("allow_script_patients"))
                configs.append(RuntimeConsoleDepartmentConfig(**payload))
            return configs
        finally:
            conn.close()

    def append_event(self, event: RuntimeConsoleEvent) -> RuntimeConsoleEvent:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO runtime_console_events (
                    event_id, session_id, occurred_at, severity, category, event_type, message,
                    subject_type, subject_id, department_id, patient_id, npc_id, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.occurred_at,
                    event.severity,
                    event.category,
                    event.event_type,
                    event.message,
                    event.subject_type,
                    event.subject_id,
                    event.department_id,
                    event.patient_id,
                    event.npc_id,
                    self.db.encode_json(event.payload),
                ),
            )
            conn.commit()
            return event
        finally:
            conn.close()

    def list_events(
        self,
        *,
        session_id: str,
        severity: str | None = None,
        category: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        limit: int = 200,
    ) -> list[RuntimeConsoleEvent]:
        clauses = ["session_id = ?"]
        params: list[object] = [session_id]
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if subject_type:
            clauses.append("subject_type = ?")
            params.append(subject_type)
        if subject_id:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        params.append(int(limit))
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"""
                SELECT *
                FROM runtime_console_events
                WHERE {" AND ".join(clauses)}
                ORDER BY occurred_at DESC, event_id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            return [self._to_event(dict(row)) for row in rows]
        finally:
            conn.close()

    def list_spawned_patient_ids(self, session_id: str | None = None) -> list[str]:
        clauses = ["event_type = 'spawn_succeeded'", "patient_id IS NOT NULL"]
        params: list[object] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        conn = self.db.connect()
        try:
            rows = conn.execute(
                f"""
                SELECT DISTINCT patient_id
                FROM runtime_console_events
                WHERE {" AND ".join(clauses)}
                ORDER BY patient_id ASC
                """,
                tuple(params),
            ).fetchall()
            return [str(row["patient_id"]) for row in rows if row["patient_id"]]
        finally:
            conn.close()

    @staticmethod
    def _to_event(payload: dict) -> RuntimeConsoleEvent:
        json_payload = payload.pop("payload_json", None)
        payload["payload"] = {} if json_payload in {None, ""} else json.loads(json_payload)
        return RuntimeConsoleEvent(**payload)
