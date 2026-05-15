from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MedicalRecordRepository:
    def __init__(self, db):
        self.db = db

    def get_by_visit(self, visit_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT * FROM medical_records WHERE visit_id = ?",
                (visit_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create(self, *, patient_id: str, visit_id: str) -> dict:
        record_id = f"MR-{uuid.uuid4().hex[:12]}"
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO medical_records (id, patient_id, visit_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record_id, patient_id, visit_id, timestamp, timestamp),
            )
            conn.commit()
            return self.get_by_visit(visit_id)
        finally:
            conn.close()

    def get_or_create(self, *, patient_id: str, visit_id: str) -> dict:
        row = self.get_by_visit(visit_id)
        if row:
            return row
        return self.create(patient_id=patient_id, visit_id=visit_id)

    def append_entry(
        self,
        *,
        patient_id: str,
        visit_id: str,
        phase: str,
        entry_type: str,
        actor: str,
        title: str,
        content_text: str,
        content: dict | None = None,
    ) -> dict:
        record = self.get_or_create(patient_id=patient_id, visit_id=visit_id)
        timestamp = now_iso()
        content_json = Database.encode_json(content or {})
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                INSERT INTO medical_record_entries
                (record_id, patient_id, visit_id, phase, entry_type, actor, title, content_text, content_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    patient_id,
                    visit_id,
                    phase,
                    entry_type,
                    actor,
                    title,
                    content_text,
                    content_json,
                    timestamp,
                ),
            )
            conn.execute(
                "UPDATE medical_records SET updated_at = ? WHERE id = ?",
                (timestamp, record["id"]),
            )
            conn.commit()
            return {
                "id": cursor.lastrowid,
                "record_id": record["id"],
                "patient_id": patient_id,
                "visit_id": visit_id,
                "phase": phase,
                "entry_type": entry_type,
                "actor": actor,
                "title": title,
                "content_text": content_text,
                "content_json": content_json,
                "created_at": timestamp,
            }
        finally:
            conn.close()

    def list_entries_by_visit(self, visit_id: str, *, limit: int = 200) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM medical_record_entries
                WHERE visit_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (visit_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_recent_visit_ids_by_patient(
        self,
        patient_id: str,
        *,
        exclude_visit_id: str | None = None,
        limit: int = 3,
    ) -> list[str]:
        conn = self.db.connect()
        try:
            if exclude_visit_id:
                rows = conn.execute(
                    """
                    SELECT visit_id FROM medical_records
                    WHERE patient_id = ? AND visit_id != ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (patient_id, exclude_visit_id, max(1, int(limit))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT visit_id FROM medical_records
                    WHERE patient_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (patient_id, max(1, int(limit))),
                ).fetchall()
            return [str(row["visit_id"]) for row in rows if row.get("visit_id")]
        finally:
            conn.close()

    @staticmethod
    def _decode_entry(row: dict) -> dict:
        payload = row.get("content_json")
        content = {}
        if payload:
            try:
                content = json.loads(payload)
            except Exception:
                content = {}
        return {
            "entry_id": row["id"],
            "record_id": row["record_id"],
            "patient_id": row["patient_id"],
            "visit_id": row["visit_id"],
            "phase": row["phase"],
            "entry_type": row["entry_type"],
            "actor": row["actor"],
            "title": row["title"],
            "content_text": row["content_text"],
            "content": content,
            "created_at": row["created_at"],
        }

    def get_visit_timeline(self, visit_id: str) -> dict | None:
        record = self.get_by_visit(visit_id)
        if not record:
            return None
        entries = [self._decode_entry(row) for row in self.list_entries_by_visit(visit_id)]
        summary = {
            "record_id": record["id"],
            "patient_id": record["patient_id"],
            "visit_id": record["visit_id"],
            "entry_count": len(entries),
            "latest_entry_type": entries[-1]["entry_type"] if entries else None,
            "latest_phase": entries[-1]["phase"] if entries else None,
            "updated_at": record["updated_at"],
        }
        return {
            "summary": summary,
            "entries": entries,
        }
