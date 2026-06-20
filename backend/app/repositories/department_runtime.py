from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.department_runtime import DepartmentRuntimePatientView, DepartmentRuntimeSummaryView


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DepartmentRuntimeRepository:
    def __init__(self, db):
        self.db = db

    def clear_all(self) -> None:
        conn = self.db.connect()
        try:
            conn.execute("DELETE FROM department_patient_runtime")
            conn.execute("DELETE FROM department_runtime_summary")
            conn.commit()
        finally:
            conn.close()

    def upsert_patient_runtime(self, payload: dict) -> dict:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO department_patient_runtime (
                    patient_id, visit_id, assigned_department_id, assigned_department_name,
                    execution_runner_kind, department_agent_enabled, department_capability_class,
                    assigned_doctor_slot_id, assigned_doctor_slot_name,
                    queue_kind, department_status, department_round, department_flow_status,
                    queue_ticket_id, visit_state,
                    patient_lifecycle_state, active_agent_type, current_node, current_node_id,
                    current_room_node_id, current_room_name, room_type, target_node_id,
                    last_transition_action, transition_version,
                    current_counterparty, current_dialogue_preview, entered_department_at, updated_at,
                    source_of_truth_version, finished_at, phase, status, last_error, step_count, next_step_at
                )

                ON CONFLICT(patient_id, visit_id) DO UPDATE SET
                    assigned_department_id = excluded.assigned_department_id,
                    assigned_department_name = excluded.assigned_department_name,
                    execution_runner_kind = excluded.execution_runner_kind,
                    department_agent_enabled = excluded.department_agent_enabled,
                    department_capability_class = excluded.department_capability_class,
                    assigned_doctor_slot_id = excluded.assigned_doctor_slot_id,
                    assigned_doctor_slot_name = excluded.assigned_doctor_slot_name,
                    queue_kind = excluded.queue_kind,
                    department_status = excluded.department_status,
                    department_round = excluded.department_round,
                    department_flow_status = excluded.department_flow_status,
                    queue_ticket_id = excluded.queue_ticket_id,
                    visit_state = excluded.visit_state,
                    patient_lifecycle_state = excluded.patient_lifecycle_state,
                    active_agent_type = excluded.active_agent_type,
                    current_node = excluded.current_node,
                    current_node_id = excluded.current_node_id,
                    current_room_node_id = excluded.current_room_node_id,
                    current_room_name = excluded.current_room_name,
                    room_type = excluded.room_type,
                    target_node_id = excluded.target_node_id,
                    last_transition_action = excluded.last_transition_action,
                    transition_version = excluded.transition_version,
                    current_counterparty = excluded.current_counterparty,
                    current_dialogue_preview = excluded.current_dialogue_preview,
                    entered_department_at = COALESCE(department_patient_runtime.entered_department_at, excluded.entered_department_at),
                    updated_at = excluded.updated_at,
                    source_of_truth_version = excluded.source_of_truth_version,
                    finished_at = excluded.finished_at,
                    phase = excluded.phase,
                    status = excluded.status,
                    last_error = excluded.last_error,
                    step_count = excluded.step_count,
                    next_step_at = excluded.next_step_at
                """,
                (
                    payload["patient_id"],
                    payload["visit_id"],
                    payload["assigned_department_id"],
                    payload["assigned_department_name"],
                    payload.get("execution_runner_kind"),
                    1 if payload.get("department_agent_enabled") else 0,
                    payload.get("department_capability_class"),
                    payload.get("assigned_doctor_slot_id"),
                    payload.get("assigned_doctor_slot_name"),
                    payload.get("queue_kind"),
                    payload["department_status"],
                    payload.get("department_round") or "none",
                    payload["department_flow_status"],
                    payload.get("queue_ticket_id"),
                    payload.get("visit_state"),
                    payload.get("patient_lifecycle_state"),
                    payload.get("active_agent_type"),
                    payload.get("current_node"),
                    payload.get("current_node_id"),
                    payload.get("current_room_node_id"),
                    payload.get("current_room_name"),
                    payload.get("room_type"),
                    payload.get("target_node_id"),
                    payload.get("last_transition_action"),
                    payload.get("transition_version"),
                    payload.get("current_counterparty"),
                    payload.get("current_dialogue_preview"),
                    payload.get("entered_department_at"),
                    payload.get("updated_at") or now_iso(),
                    payload.get("source_of_truth_version"),
                    payload.get("finished_at"),
                    payload.get("phase"),
                    payload.get("status"),
                    payload.get("last_error"),
                    int(payload.get("step_count") or 0),
                    payload.get("next_step_at"),
                ),
            )
            conn.commit()
            return self.get_patient_runtime(payload["patient_id"], payload["visit_id"])
        finally:
            conn.close()

    def get_patient_runtime(self, patient_id: str, visit_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM department_patient_runtime
                WHERE patient_id = ? AND visit_id = ?
                """,
                (patient_id, visit_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_patient_runtimes(self) -> list[DepartmentRuntimePatientView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM department_patient_runtime
                ORDER BY assigned_department_id ASC, updated_at DESC
                """
            ).fetchall()
            normalized = []
            for row in rows:
                payload = dict(row)
                payload["department_status"] = payload.get("department_status") or payload.get("department_flow_status")
                payload["department_round"] = payload.get("department_round") or "none"
                payload["source_of_truth_version"] = payload.get("source_of_truth_version") or payload.get("updated_at")
                payload["transition_version"] = payload.get("transition_version") or payload.get("updated_at")
                normalized.append(DepartmentRuntimePatientView(**payload))
            return normalized
        finally:
            conn.close()

    def replace_summary(self, payload: dict) -> dict:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO department_runtime_summary (
                    department_id, department_name, active_count, pending_registration_count,
                    waiting_round1_count, waiting_round2_count,
                    called_round1_count, called_round2_count,
                    in_consultation_round1_count, in_consultation_round2_count,
                    waiting_count, called_count, in_consultation_count, in_test_count,
                    finished_count, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(department_id) DO UPDATE SET
                    department_name = excluded.department_name,
                    active_count = excluded.active_count,
                    pending_registration_count = excluded.pending_registration_count,
                    waiting_round1_count = excluded.waiting_round1_count,
                    waiting_round2_count = excluded.waiting_round2_count,
                    called_round1_count = excluded.called_round1_count,
                    called_round2_count = excluded.called_round2_count,
                    in_consultation_round1_count = excluded.in_consultation_round1_count,
                    in_consultation_round2_count = excluded.in_consultation_round2_count,
                    waiting_count = excluded.waiting_count,
                    called_count = excluded.called_count,
                    in_consultation_count = excluded.in_consultation_count,
                    in_test_count = excluded.in_test_count,
                    finished_count = excluded.finished_count,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["department_id"],
                    payload["department_name"],
                    payload["active_count"],
                    payload["pending_registration_count"],
                    payload["waiting_round1_count"],
                    payload["waiting_round2_count"],
                    payload["called_round1_count"],
                    payload["called_round2_count"],
                    payload["in_consultation_round1_count"],
                    payload["in_consultation_round2_count"],
                    payload["waiting_count"],
                    payload["called_count"],
                    payload["in_consultation_count"],
                    payload["in_test_count"],
                    payload["finished_count"],
                    payload.get("updated_at") or now_iso(),
                ),
            )
            conn.commit()
            return self.get_summary(payload["department_id"])
        finally:
            conn.close()

    def get_summary(self, department_id: str) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM department_runtime_summary
                WHERE department_id = ?
                """,
                (department_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_summaries(self) -> list[DepartmentRuntimeSummaryView]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM department_runtime_summary
                ORDER BY department_id ASC
                """
            ).fetchall()
            normalized = []
            for row in rows:
                payload = dict(row)
                payload["waiting_round1_count"] = payload.get("waiting_round1_count") or 0
                payload["waiting_round2_count"] = payload.get("waiting_round2_count") or 0
                payload["called_round1_count"] = payload.get("called_round1_count") or 0
                payload["called_round2_count"] = payload.get("called_round2_count") or 0
                payload["in_consultation_round1_count"] = payload.get("in_consultation_round1_count") or 0
                payload["in_consultation_round2_count"] = payload.get("in_consultation_round2_count") or 0
                normalized.append(DepartmentRuntimeSummaryView(**payload))
            return normalized
        finally:
            conn.close()
