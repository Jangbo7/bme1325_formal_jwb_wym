from __future__ import annotations

from datetime import datetime, timezone

from app.database import Database
from app.schemas.common import PatientLifecycleState, VisitLifecycleState
from app.schemas.patient import DialogueSummary, EvidenceItem, PatientView, QueueTicketRef, TriageSummary


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatientRepository:
    def __init__(self, db: Database):
        self.db = db
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        if self.get("P-self") is None:
            self.upsert_basic("P-self", "You (Player)")
        if self.get("P-102") is None:
            self.save_view(
                {
                    "id": "P-102",
                    "name": "Wang Ayi",
                    "lifecycle_state": PatientLifecycleState.QUEUED.value,
                    "state": "Queued",
                    "priority": "M",
                    "location": "Consultation",
                    "updated_at": now_iso(),
                    "triage": {"level": 3, "note": "Waiting for consultation."},
                    "session_id": None,
                    "visit_id": None,
                }
            )
        if self.get("P-203") is None:
            self.save_view(
                {
                    "id": "P-203",
                    "name": "Li Xiansheng",
                    "lifecycle_state": PatientLifecycleState.IN_CONSULTATION.value,
                    "state": "In Consultation",
                    "priority": "H",
                    "location": "Consultation",
                    "updated_at": now_iso(),
                    "triage": {"level": 2, "note": "High-priority patient."},
                    "session_id": None,
                    "visit_id": None,
                }
            )

    def upsert_basic(self, patient_id: str, name: str) -> None:
        existing = self.get(patient_id)
        if existing:
            return
        self.save_view(
            {
                "id": patient_id,
                "name": name,
                "lifecycle_state": PatientLifecycleState.UNTRIAGED.value,
                "state": "Untriaged",
                "priority": "-",
                "location": "Lobby",
                "updated_at": now_iso(),
                "triage": {"level": None, "note": ""},
                "session_id": None,
                "visit_id": None,
            }
        )

    def save_view(self, payload: dict) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO patients (id, name, lifecycle_state, display_state, priority, location, updated_at, triage_level, triage_note, session_id, visit_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    lifecycle_state=excluded.lifecycle_state,
                    display_state=excluded.display_state,
                    priority=excluded.priority,
                    location=excluded.location,
                    updated_at=excluded.updated_at,
                    triage_level=excluded.triage_level,
                    triage_note=excluded.triage_note,
                    session_id=excluded.session_id,
                    visit_id=excluded.visit_id
                """,
                (
                    payload["id"],
                    payload["name"],
                    payload["lifecycle_state"],
                    payload["state"],
                    payload["priority"],
                    payload["location"],
                    payload["updated_at"],
                    payload["triage"]["level"],
                    payload["triage"]["note"],
                    payload.get("session_id"),
                    payload.get("visit_id"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, patient_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list(self) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute("SELECT * FROM patients ORDER BY updated_at DESC").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_patient(self, patient_id: str, **kwargs) -> dict:
        existing = self.get(patient_id)
        if not existing:
            raise KeyError(patient_id)
        payload = {
            "id": existing["id"],
            "name": kwargs.get("name", existing["name"]),
            "lifecycle_state": kwargs.get("lifecycle_state", existing["lifecycle_state"]),
            "state": kwargs.get("state", existing["display_state"]),
            "priority": kwargs.get("priority", existing["priority"]),
            "location": kwargs.get("location", existing["location"]),
            "updated_at": kwargs.get("updated_at", now_iso()),
            "triage": {
                "level": kwargs.get("triage_level", existing["triage_level"]),
                "note": kwargs.get("triage_note", existing["triage_note"] or ""),
            },
            "session_id": kwargs.get("session_id", existing["session_id"]),
            "visit_id": kwargs.get("visit_id", existing.get("visit_id")),
        }
        self.save_view(payload)
        return self.get(patient_id)

    def to_view(
        self,
        patient_row: dict,
        dialogue: dict | None = None,
        evidence: list[dict] | None = None,
        queue_ticket: dict | None = None,
        visit_row: dict | None = None,
    ) -> PatientView:
        visit_id = patient_row.get("visit_id")
        visit_state = None
        if visit_row:
            visit_id = visit_row.get("id")
            state_value = visit_row.get("state")
            visit_state = VisitLifecycleState(state_value) if state_value else None

        return PatientView(
            id=patient_row["id"],
            name=patient_row["name"],
            lifecycle_state=PatientLifecycleState(patient_row["lifecycle_state"]),
            state=patient_row["display_state"],
            priority=patient_row["priority"],
            location=patient_row["location"],
            updated_at=patient_row["updated_at"],
            session_id=patient_row.get("session_id"),
            visit_id=visit_id,
            visit_state=visit_state,
            triage=TriageSummary(level=patient_row["triage_level"], note=patient_row["triage_note"] or ""),
            dialogue=DialogueSummary(**dialogue) if dialogue else None,
            triage_evidence=[EvidenceItem(**item) for item in (evidence or [])],
            queue_ticket=QueueTicketRef(**queue_ticket) if queue_ticket else None,
        )
