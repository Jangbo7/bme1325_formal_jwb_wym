from datetime import datetime, timezone

from app.database import Database
from app.domain.identifiers import generate_encounter_id
from app.schemas.common import VisitLifecycleState
from app.schemas.visit import VisitView
from app.services.disposition import is_outpatient_flow_finished


TERMINAL_VISIT_STATES = {
    VisitLifecycleState.COMPLETED.value,
    VisitLifecycleState.ERROR.value,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VisitRepository:
    def __init__(self, db):
        self.db = db

    def create(
        self,
        patient_id: str,
        state: VisitLifecycleState = VisitLifecycleState.ARRIVED,
        assigned_department_id: str | None = None,
        assigned_department_name: str | None = None,
        current_node: str | None = "lobby",
        current_department: str | None = None,
        active_agent_type: str | None = None,
        data: dict | None = None,
    ) -> dict:
        visit_id = generate_encounter_id()
        timestamp = now_iso()
        payload = {
            "id": visit_id,
            "patient_id": patient_id,
            "state": state.value,
            "assigned_department_id": assigned_department_id,
            "assigned_department_name": assigned_department_name,
            "current_node": current_node,
            "current_department": current_department,
            "active_agent_type": active_agent_type,
            "data_json": Database.encode_json(data or {}),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO visits (
                    id, patient_id, state, assigned_department_id, assigned_department_name,
                    current_node, current_department, active_agent_type, data_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
            return self.get(visit_id)
        finally:
            conn.close()

    def get(self, visit_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_active_by_patient(self, patient_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT * FROM visits
                WHERE patient_id = ? AND state NOT IN (?, ?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (patient_id, VisitLifecycleState.COMPLETED.value, VisitLifecycleState.ERROR.value),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_or_get_active(self, patient_id: str) -> dict:
        active = self.get_active_by_patient(patient_id)
        if active:
            return active
        return self.create(patient_id=patient_id)

    def update_visit(self, visit_id: str, **kwargs) -> dict:
        existing = self.get(visit_id)
        if not existing:
            raise KeyError(visit_id)
        payload = {
            "id": existing["id"],
            "patient_id": kwargs.get("patient_id", existing["patient_id"]),
            "state": kwargs.get("state", existing["state"]),
            "assigned_department_id": (
                kwargs.get("assigned_department_id")
                if kwargs.get("assigned_department_id") is not None
                else existing.get("assigned_department_id")
            ),
            "assigned_department_name": (
                kwargs.get("assigned_department_name")
                if kwargs.get("assigned_department_name") is not None
                else existing.get("assigned_department_name")
            ),
            "current_node": kwargs.get("current_node", existing["current_node"]),
            "current_department": kwargs.get("current_department", existing["current_department"]),
            "active_agent_type": kwargs.get("active_agent_type", existing["active_agent_type"]),
            "data_json": Database.encode_json(kwargs.get("data", Database.decode_json(existing.get("data_json"), {}))),
            "created_at": existing["created_at"],
            "updated_at": kwargs.get("updated_at", now_iso()),
        }
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE visits
                SET patient_id = ?, state = ?, assigned_department_id = ?, assigned_department_name = ?,
                    current_node = ?, current_department = ?, active_agent_type = ?, data_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["patient_id"],
                    payload["state"],
                    payload["assigned_department_id"],
                    payload["assigned_department_name"],
                    payload["current_node"],
                    payload["current_department"],
                    payload["active_agent_type"],
                    payload["data_json"],
                    payload["updated_at"],
                    visit_id,
                ),
            )
            conn.commit()
            return self.get(visit_id)
        finally:
            conn.close()

    def update_openemr_encounter_id(self, visit_id: str, openemr_encounter_id: str | None) -> dict:
        conn = self.db.connect()
        try:
            conn.execute(
                "UPDATE visits SET openemr_encounter_id = ?, updated_at = ? WHERE id = ?",
                (openemr_encounter_id, now_iso(), visit_id),
            )
            conn.commit()
            return self.get(visit_id)
        finally:
            conn.close()

    def set_emr_sync_status(
        self,
        visit_id: str,
        *,
        status: str,
        error: str | None = None,
        synced_at: str | None = None,
    ) -> dict:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                UPDATE visits
                SET emr_sync_status = ?, emr_sync_error = ?, emr_synced_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error, synced_at, now_iso(), visit_id),
            )
            conn.commit()
            return self.get(visit_id)
        finally:
            conn.close()

    def get_visit_data(self, visit_id: str) -> dict:
        row = self.get(visit_id)
        if not row:
            raise KeyError(visit_id)
        return Database.decode_json(row.get("data_json"), {})

    def set_openemr_sync_ref(self, visit_id: str, key: str, external_id: str | None) -> dict:
        if key not in {"triage_note_id", "internal_medicine_note_id", "test_report_id"}:
            raise ValueError("unsupported openemr sync key")
        row = self.get(visit_id)
        if not row:
            raise KeyError(visit_id)
        data = Database.decode_json(row.get("data_json"), {})
        openemr_sync = data.get("openemr_sync")
        if not isinstance(openemr_sync, dict):
            openemr_sync = {}
        openemr_sync[key] = external_id
        data["openemr_sync"] = openemr_sync
        return self.update_visit(visit_id, data=data)

    def to_view(self, row: dict) -> VisitView:
        visit_data = Database.decode_json(row.get("data_json"), {})
        return VisitView(
            id=row["id"],
            encounter_id=row["id"],
            patient_id=row["patient_id"],
            state=VisitLifecycleState(row["state"]),
            assigned_department_id=row.get("assigned_department_id"),
            assigned_department_name=row.get("assigned_department_name"),
            current_node=row.get("current_node"),
            current_department=row.get("current_department"),
            active_agent_type=row.get("active_agent_type"),
            primary_disposition=visit_data.get("primary_disposition"),
            disposition=dict(visit_data.get("disposition") or {}),
            outpatient_flow_finished=is_outpatient_flow_finished(row.get("state"), visit_data),
            outpatient_finished_at=visit_data.get("outpatient_finished_at"),
            data=visit_data,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
