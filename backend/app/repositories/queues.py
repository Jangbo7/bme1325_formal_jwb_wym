import uuid
from datetime import datetime, timezone

from app.schemas.common import QueueTicketStatus
from app.schemas.queue import QueueTicketView, QueueView


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueueRepository:
    def __init__(self, db):
        self.db = db

    def get_active_ticket_for_patient(self, patient_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM queue_tickets
                WHERE patient_id = ? AND status IN (?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (patient_id, QueueTicketStatus.WAITING.value, QueueTicketStatus.CALLED.value),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_ticket(self, patient_id: str, department_id: str, department_name: str) -> dict:
        existing = self.get_active_ticket_for_patient(patient_id)
        if existing:
            return existing
        conn = self.db.connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(number), 0) AS max_number FROM queue_tickets WHERE department_id = ?",
                (department_id,),
            ).fetchone()
            next_number = int(row["max_number"]) + 1
            timestamp = now_iso()
            payload = {
                "id": f"QT-{uuid.uuid4().hex[:8]}",
                "patient_id": patient_id,
                "department_id": department_id,
                "department_name": department_name,
                "number": next_number,
                "status": QueueTicketStatus.WAITING.value,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            conn.execute(
                """
                INSERT INTO queue_tickets (id, patient_id, department_id, department_name, number, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
            return payload
        finally:
            conn.close()

    def list_views(self) -> list[QueueView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM queue_tickets ORDER BY department_id ASC, number ASC"
            ).fetchall()
            grouped = {}
            for row in rows:
                ticket = QueueTicketView(**dict(row))
                group = grouped.setdefault(
                    row["department_id"],
                    {
                        "department_id": row["department_id"],
                        "department_name": row["department_name"],
                        "waiting": [],
                        "called": None,
                    },
                )
                if row["status"] == QueueTicketStatus.WAITING.value:
                    group["waiting"].append(ticket)
                elif row["status"] == QueueTicketStatus.CALLED.value:
                    group["called"] = ticket
            return [QueueView(**group) for group in grouped.values()]
        finally:
            conn.close()
