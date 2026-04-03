from datetime import datetime, timezone

from app.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_or_update(self, session_id: str, patient_id: str, dialogue_state: str, agent_type: str = "triage") -> dict:
        timestamp = now_iso()
        conn = self.db.connect()
        try:
            existing = conn.execute("SELECT id FROM triage_sessions WHERE id = ?", (session_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE triage_sessions
                    SET patient_id = ?, dialogue_state = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (patient_id, dialogue_state, timestamp, session_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO triage_sessions (id, patient_id, agent_type, dialogue_state, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, patient_id, agent_type, dialogue_state, timestamp, timestamp),
                )
            conn.commit()
            return self.get(session_id)
        finally:
            conn.close()

    def update_state(self, session_id: str, dialogue_state: str) -> dict:
        conn = self.db.connect()
        try:
            conn.execute(
                "UPDATE triage_sessions SET dialogue_state = ?, updated_at = ? WHERE id = ?",
                (dialogue_state, now_iso(), session_id),
            )
            conn.commit()
            return self.get(session_id)
        finally:
            conn.close()

    def get(self, session_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM triage_sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def append_turn(self, session_id: str, patient_id: str, role: str, content: str, timestamp: str, metadata: dict | None = None) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO session_turns (session_id, patient_id, role, content, timestamp, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, patient_id, role, content, timestamp, Database.encode_json(metadata or {})),
            )
            conn.commit()
        finally:
            conn.close()

    def list_turns(self, session_id: str, limit: int = 8) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT role, content, timestamp, metadata_json
                FROM session_turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
            ordered = list(reversed(rows))
            return [
                {
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                    "metadata": Database.decode_json(row["metadata_json"], {}),
                }
                for row in ordered
            ]
        finally:
            conn.close()
