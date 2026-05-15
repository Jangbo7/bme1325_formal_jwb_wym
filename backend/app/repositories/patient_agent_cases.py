from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatientAgentCaseRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        *,
        patient_id: str,
        mode: str,
        case_payload: dict,
        visit_id: str | None = None,
        status: str = "generated",
    ) -> dict:
        case_id = f"PAC-{uuid.uuid4().hex[:12]}"
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO patient_agent_cases (id, patient_id, visit_id, mode, status, case_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    patient_id,
                    visit_id,
                    mode,
                    status,
                    Database.encode_json(case_payload),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return self.get(case_id)
        finally:
            conn.close()

    def get(self, case_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM patient_agent_cases WHERE id = ?", (case_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_by_patient(self, patient_id: str, *, mode: str | None = None) -> dict | None:
        conn = self.db.connect()
        try:
            if mode:
                row = conn.execute(
                    """
                    SELECT * FROM patient_agent_cases
                    WHERE patient_id = ? AND mode = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (patient_id, mode),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM patient_agent_cases
                    WHERE patient_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (patient_id,),
                ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_by_visit(self, visit_id: str, *, mode: str | None = None) -> dict | None:
        conn = self.db.connect()
        try:
            if mode:
                row = conn.execute(
                    """
                    SELECT * FROM patient_agent_cases
                    WHERE visit_id = ? AND mode = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (visit_id, mode),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM patient_agent_cases
                    WHERE visit_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (visit_id,),
                ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def update(self, case_id: str, **kwargs) -> dict:
        existing = self.get(case_id)
        if not existing:
            raise KeyError(case_id)
        payload = {
            "patient_id": kwargs.get("patient_id", existing["patient_id"]),
            "visit_id": kwargs.get("visit_id", existing["visit_id"]),
            "mode": kwargs.get("mode", existing["mode"]),
            "status": kwargs.get("status", existing["status"]),
            "case_json": Database.encode_json(kwargs.get("case_payload", Database.decode_json(existing["case_json"], {}))),
            "updated_at": kwargs.get("updated_at", now_iso()),
        }
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE patient_agent_cases
                SET patient_id = ?, visit_id = ?, mode = ?, status = ?, case_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["patient_id"],
                    payload["visit_id"],
                    payload["mode"],
                    payload["status"],
                    payload["case_json"],
                    payload["updated_at"],
                    case_id,
                ),
            )
            conn.commit()
            return self.get(case_id)
        finally:
            conn.close()
