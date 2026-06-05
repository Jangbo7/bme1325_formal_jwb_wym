from __future__ import annotations

from datetime import datetime, timezone

from app.departments.registry import list_departments
from app.schemas.common import DepartmentFlowStatus, QueueTicketKind, QueueTicketStatus, VisitLifecycleState
from app.schemas.department_runtime import (
    DepartmentDoctorSlotRuntimeView,
    DepartmentRuntimeDepartmentView,
    DepartmentRuntimePatientView,
    DepartmentRoomRuntimeView,
    DepartmentRuntimeSnapshot,
    DepartmentRuntimeSummaryView,
)
from app.schemas.hospital_runtime import HospitalNodeRuntimeView, HospitalNodeSummary, HospitalRuntimeSnapshot
from app.services.department_capabilities import get_department_capability
from app.services.department_assignment import resolve_assigned_department_for_visit
from app.services.department_resources import (
    get_department_resource_config,
    get_doctor_slot_by_id,
    resolve_room_for_visit_state,
    stable_doctor_slot_for_patient,
)
from app.services.hospital_nodes import list_hospital_nodes


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FINISHED_VISIT_STATES = {
    VisitLifecycleState.WAITING_PAYMENT.value,
    VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
    VisitLifecycleState.DISPOSITION_PENDING.value,
    VisitLifecycleState.DISPOSITION_OUTPATIENT_TREATMENT.value,
    VisitLifecycleState.DISPOSITION_FOLLOWUP_BOOKING.value,
    VisitLifecycleState.DISPOSITION_REFERRAL.value,
    VisitLifecycleState.WAITING_PHARMACY.value,
    VisitLifecycleState.ADMITTED.value,
    VisitLifecycleState.TRANSFERRING.value,
    VisitLifecycleState.COMPLETED.value,
}

TEST_VISIT_STATES = {
    VisitLifecycleState.WAITING_TEST.value,
    VisitLifecycleState.WAITING_TEST_PAYMENT.value,
    VisitLifecycleState.TEST_PAYMENT_COMPLETED.value,
    VisitLifecycleState.IN_TEST.value,
    VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
    VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
    VisitLifecycleState.WAITING_RETURN_CONSULTATION.value,
    VisitLifecycleState.RESULTS_READY.value,
}


class DepartmentRuntimeService:
    def __init__(self, *, runtime_repo, patient_repo, visit_repo, queue_repo):
        self.runtime_repo = runtime_repo
        self.patient_repo = patient_repo
        self.visit_repo = visit_repo
        self.queue_repo = queue_repo

    def clear_all(self) -> None:
        self.runtime_repo.clear_all()

    def sync_patient_runtime(
        self,
        *,
        patient_id: str,
        visit_id: str | None = None,
        current_counterparty: str | None = None,
        current_dialogue_preview: str | None = None,
        current_node_id: str | None = None,
        target_node_id: str | None = None,
        execution_runner_kind: str | None = None,
        department_agent_enabled: bool | None = None,
        department_capability_class: str | None = None,
        assigned_doctor_slot_id: str | None = None,
        assigned_doctor_slot_name: str | None = None,
        current_room_node_id: str | None = None,
        current_room_name: str | None = None,
        room_type: str | None = None,
        last_transition_action: str | None = None,
        transition_version: str | None = None,
    ) -> dict | None:
        patient_row = self.patient_repo.get(patient_id)
        if not patient_row:
            return None
        resolved_visit_id = visit_id or patient_row.get("visit_id")
        if not resolved_visit_id:
            return None
        visit_row = self.visit_repo.get(resolved_visit_id)
        if not visit_row:
            return None

        assigned_department_id = visit_row.get("assigned_department_id")
        assigned_department_name = visit_row.get("assigned_department_name")
        if not assigned_department_id or not assigned_department_name:
            resolved = resolve_assigned_department_for_visit(visit_row, patient_row)
            visit_row = self.visit_repo.update_visit(
                resolved_visit_id,
                assigned_department_id=resolved["id"],
                assigned_department_name=resolved["label"],
            )
            assigned_department_id = visit_row.get("assigned_department_id")
            assigned_department_name = visit_row.get("assigned_department_name")
            if not assigned_department_id or not assigned_department_name:
                return None

        existing = self.runtime_repo.get_patient_runtime(patient_id, resolved_visit_id) or {}
        visit_state = visit_row.get("state")
        capability_info = self._resolve_department_capability_fields(
            department_id=assigned_department_id,
            existing=existing,
            execution_runner_kind=execution_runner_kind,
            department_agent_enabled=department_agent_enabled,
            department_capability_class=department_capability_class,
        )
        slot_info = self._resolve_doctor_slot_assignment(
            patient_id=patient_id,
            department_id=assigned_department_id,
            existing=existing,
            assigned_doctor_slot_id=assigned_doctor_slot_id,
            assigned_doctor_slot_name=assigned_doctor_slot_name,
        )
        room_info = self._resolve_room_assignment(
            department_id=assigned_department_id,
            visit_state=visit_state,
            assigned_doctor_slot_id=slot_info["slot_id"],
            current_room_node_id=current_room_node_id,
            current_room_name=current_room_name,
            room_type=room_type,
        )
        target_queue_kind = None
        if visit_state == VisitLifecycleState.IN_SECOND_CONSULTATION.value:
            target_queue_kind = QueueTicketKind.RETURN_CONSULTATION.value
        elif visit_state in {
            VisitLifecycleState.WAITING_CONSULTATION.value,
            VisitLifecycleState.IN_CONSULTATION.value,
            VisitLifecycleState.REGISTERED.value,
        }:
            target_queue_kind = QueueTicketKind.INITIAL_CONSULTATION.value
        ticket = self.queue_repo.get_active_ticket_for_patient(
            patient_id,
            visit_id=resolved_visit_id,
            queue_kind=target_queue_kind,
        )
        if not ticket:
            ticket = self.queue_repo.get_latest_ticket_for_patient(patient_id, visit_id=resolved_visit_id)

        flow_status, department_round, queue_kind = self._derive_flow_status(
            visit_state=visit_row.get("state"),
            patient_lifecycle_state=patient_row.get("lifecycle_state"),
            ticket=ticket,
        )
        previous_entered_at = existing.get("entered_department_at")
        entered_department_at = previous_entered_at or now_iso()
        if flow_status == DepartmentFlowStatus.ASSIGNED_PENDING_REGISTRATION.value:
            entered_department_at = None
        payload = {
            "patient_id": patient_id,
            "visit_id": resolved_visit_id,
            "assigned_department_id": assigned_department_id,
            "assigned_department_name": assigned_department_name,
            "execution_runner_kind": capability_info["execution_runner_kind"],
            "department_agent_enabled": capability_info["department_agent_enabled"],
            "department_capability_class": capability_info["department_capability_class"],
            "assigned_doctor_slot_id": slot_info["slot_id"],
            "assigned_doctor_slot_name": slot_info["slot_name"],
            "queue_kind": queue_kind or existing.get("queue_kind"),
            "department_status": flow_status,
            "department_round": department_round,
            "department_flow_status": flow_status,
            "queue_ticket_id": ticket.get("id") if ticket else existing.get("queue_ticket_id"),
            "visit_state": visit_row.get("state"),
            "patient_lifecycle_state": patient_row.get("lifecycle_state"),
            "active_agent_type": visit_row.get("active_agent_type"),
            "current_node": visit_row.get("current_node"),
            "current_node_id": current_node_id
            or room_info["node_id"]
            or self._node_for_visit_state(
                visit_row.get("state"),
                assigned_department_id,
                assigned_doctor_slot_id=slot_info["slot_id"],
            ),
            "current_room_node_id": room_info["node_id"],
            "current_room_name": room_info["name"],
            "room_type": room_info["room_type"],
            "target_node_id": target_node_id or existing.get("target_node_id"),
            "last_transition_action": last_transition_action or existing.get("last_transition_action"),
            "transition_version": transition_version or now_iso(),
            "current_counterparty": current_counterparty if current_counterparty is not None else existing.get("current_counterparty"),
            "current_dialogue_preview": (
                current_dialogue_preview if current_dialogue_preview is not None else existing.get("current_dialogue_preview")
            ),
            "entered_department_at": entered_department_at,
            "updated_at": now_iso(),
            "source_of_truth_version": now_iso(),
            "finished_at": now_iso() if flow_status == DepartmentFlowStatus.FINISHED.value else None,
        }
        runtime_row = self.runtime_repo.upsert_patient_runtime(payload)
        self.refresh_department_summary(assigned_department_id, assigned_department_name)
        return runtime_row

    def refresh_department_summary(self, department_id: str, department_name: str) -> dict:
        patient_rows = [
            row.model_dump()
            for row in self.runtime_repo.list_patient_runtimes()
            if row.assigned_department_id == department_id
        ]
        counts = {
            "active_count": 0,
            "pending_registration_count": 0,
            "waiting_round1_count": 0,
            "waiting_round2_count": 0,
            "called_round1_count": 0,
            "called_round2_count": 0,
            "in_consultation_round1_count": 0,
            "in_consultation_round2_count": 0,
            "waiting_count": 0,
            "called_count": 0,
            "in_consultation_count": 0,
            "in_test_count": 0,
            "finished_count": 0,
        }
        for row in patient_rows:
            status = row.get("department_status") or row["department_flow_status"]
            if status not in {
                DepartmentFlowStatus.FINISHED.value,
                DepartmentFlowStatus.CANCELLED.value,
                DepartmentFlowStatus.ERROR.value,
            }:
                counts["active_count"] += 1
            if status == DepartmentFlowStatus.ASSIGNED_PENDING_REGISTRATION.value:
                counts["pending_registration_count"] += 1
            elif status == DepartmentFlowStatus.WAITING_QUEUE_ROUND1.value:
                counts["waiting_round1_count"] += 1
                counts["waiting_count"] += 1
            elif status == DepartmentFlowStatus.WAITING_QUEUE_ROUND2.value:
                counts["waiting_round2_count"] += 1
                counts["waiting_count"] += 1
            elif status == DepartmentFlowStatus.CALLED_ROUND1.value:
                counts["called_round1_count"] += 1
                counts["called_count"] += 1
            elif status == DepartmentFlowStatus.CALLED_ROUND2.value:
                counts["called_round2_count"] += 1
                counts["called_count"] += 1
            elif status == DepartmentFlowStatus.IN_CONSULTATION_ROUND1.value:
                counts["in_consultation_round1_count"] += 1
                counts["in_consultation_count"] += 1
            elif status == DepartmentFlowStatus.IN_CONSULTATION_ROUND2.value:
                counts["in_consultation_round2_count"] += 1
                counts["in_consultation_count"] += 1
            elif status == DepartmentFlowStatus.IN_TEST.value:
                counts["in_test_count"] += 1
            elif status == DepartmentFlowStatus.FINISHED.value:
                counts["finished_count"] += 1
        payload = {
            "department_id": department_id,
            "department_name": department_name,
            **counts,
            "updated_at": now_iso(),
        }
        return self.runtime_repo.replace_summary(payload)

    def build_debug_snapshot(self, multi_snapshot) -> DepartmentRuntimeSnapshot:
        formal_departments = list_departments(include_legacy=False)
        runtime_rows = self.runtime_repo.list_patient_runtimes()
        controller_patients = {
            item.patient_id: item.model_dump()
            for item in multi_snapshot.patients
        }
        rows_by_department: dict[str, list[DepartmentRuntimePatientView]] = {}
        unassigned: list[DepartmentRuntimePatientView] = []

        for row in runtime_rows:
            merged = row.model_dump()
            overlay = controller_patients.get(row.patient_id)
            if overlay:
                merged["npc_id"] = overlay.get("npc_id")
                merged["last_action"] = overlay.get("last_action")
                merged["finished"] = overlay.get("finished", False)
                merged["execution_runner_kind"] = overlay.get("execution_runner_kind") or merged.get("execution_runner_kind")
                merged["department_agent_enabled"] = overlay.get("department_agent_enabled", merged.get("department_agent_enabled", False))
                merged["department_capability_class"] = overlay.get("department_capability_class") or merged.get("department_capability_class")
                merged["current_node_id"] = overlay.get("current_node_id") or merged.get("current_node_id")
                merged["target_node_id"] = overlay.get("target_node_id") or merged.get("target_node_id")
                merged["current_counterparty"] = overlay.get("current_counterparty") or merged.get("current_counterparty")
                merged["current_dialogue"] = overlay.get("current_dialogue")
                if overlay.get("current_dialogue"):
                    overlay_dialogue = overlay["current_dialogue"]
                    if hasattr(overlay_dialogue, "model_dump"):
                        overlay_dialogue = overlay_dialogue.model_dump()
                    merged["current_dialogue_preview"] = (overlay_dialogue or {}).get("message")
            patient_view = DepartmentRuntimePatientView(**merged)
            rows_by_department.setdefault(patient_view.assigned_department_id, []).append(patient_view)

        summaries = {item.department_id: item for item in self.runtime_repo.list_summaries()}
        departments: list[DepartmentRuntimeDepartmentView] = []
        for department in formal_departments:
            resource_summary = self._build_resource_summary(department["id"], rows_by_department.get(department["id"], []))
            capability = get_department_capability(department["id"])
            summary = summaries.get(department["id"]) or DepartmentRuntimeSummaryView(
                department_id=department["id"],
                department_name=department["label"],
                active_count=0,
                pending_registration_count=0,
                waiting_round1_count=0,
                waiting_round2_count=0,
                called_round1_count=0,
                called_round2_count=0,
                in_consultation_round1_count=0,
                in_consultation_round2_count=0,
                waiting_count=0,
                called_count=0,
                in_consultation_count=0,
                in_test_count=0,
                finished_count=0,
                updated_at=now_iso(),
            )
            patients = sorted(
                rows_by_department.pop(department["id"], []),
                key=lambda item: item.updated_at,
                reverse=True,
            )
            departments.append(
                DepartmentRuntimeDepartmentView(
                    department_id=department["id"],
                    department_name=department["label"],
                    department_agent_enabled=capability.department_agent_enabled,
                    department_capability_class=capability.department_capability_class,
                    summary=summary,
                    doctor_slots=resource_summary["doctor_slots"],
                    rooms=resource_summary["rooms"],
                    patients=patients,
                )
            )

        for remaining_rows in rows_by_department.values():
            unassigned.extend(remaining_rows)

        for patient_id, overlay in controller_patients.items():
            if any(row.patient_id == patient_id for row in unassigned):
                continue
            if any(patient_id == row.patient_id for department in departments for row in department.patients):
                continue
            unassigned.append(
                DepartmentRuntimePatientView(
                    patient_id=patient_id,
                    visit_id=overlay.get("encounter_id") or "",
                    assigned_department_id="unassigned",
                    assigned_department_name="Unassigned",
                    execution_runner_kind=overlay.get("execution_runner_kind"),
                    department_agent_enabled=overlay.get("department_agent_enabled", False),
                    department_capability_class=overlay.get("department_capability_class"),
                    queue_kind=None,
                    department_status="unassigned",
                    department_round="none",
                    department_flow_status="unassigned",
                    queue_ticket_id=None,
                    visit_state=overlay.get("visit_state"),
                    patient_lifecycle_state=overlay.get("patient_lifecycle_state"),
                    active_agent_type=None,
                    current_node=None,
                    current_node_id=overlay.get("current_node_id"),
                    target_node_id=overlay.get("target_node_id"),
                    last_transition_action=overlay.get("last_action"),
                    transition_version=now_iso(),
                    current_counterparty=overlay.get("current_counterparty"),
                    current_dialogue=overlay.get("current_dialogue"),
                    current_dialogue_preview=(overlay.get("current_dialogue") or {}).get("message"),
                    entered_department_at=None,
                    updated_at=now_iso(),
                    source_of_truth_version=now_iso(),
                    finished_at=None,
                    npc_id=overlay.get("npc_id"),
                    last_action=overlay.get("last_action"),
                    finished=overlay.get("finished", False),
                )
            )

        return DepartmentRuntimeSnapshot(
            running=multi_snapshot.running,
            mode=multi_snapshot.mode,
            spawn_interval_seconds=multi_snapshot.spawn_interval_seconds,
            step_interval_seconds=multi_snapshot.step_interval_seconds,
            max_active_patients=multi_snapshot.max_active_patients,
            total_spawned=multi_snapshot.total_spawned,
            active_count=multi_snapshot.active_count,
            last_spawn_at=multi_snapshot.last_spawn_at,
            last_tick_at=multi_snapshot.last_tick_at,
            last_error=multi_snapshot.last_error,
            supervisor_mode=multi_snapshot.supervisor_mode,
            fairness_policy=multi_snapshot.fairness_policy,
            node_capacities=multi_snapshot.node_capacities,
            node_step_delays=multi_snapshot.node_step_delays,
            dispatch_count=multi_snapshot.dispatch_count,
            blocked_count=multi_snapshot.blocked_count,
            formal_departments=formal_departments,
            departments=departments,
            unassigned_patients=sorted(unassigned, key=lambda item: item.updated_at, reverse=True),
        )

    def build_hospital_runtime_snapshot(self, multi_snapshot) -> HospitalRuntimeSnapshot:
        department_snapshot = self.build_debug_snapshot(multi_snapshot)
        nodes = list_hospital_nodes()
        rows: list[DepartmentRuntimePatientView] = []
        for department in department_snapshot.departments:
            rows.extend(department.patients)
        rows.extend(department_snapshot.unassigned_patients)

        grouped: dict[str, list[DepartmentRuntimePatientView]] = {}
        for row in rows:
            node_id = row.current_node_id or self._node_for_visit_state(
                row.visit_state,
                row.assigned_department_id,
                assigned_doctor_slot_id=row.assigned_doctor_slot_id,
            )
            grouped.setdefault(node_id or "unknown", []).append(row)

        node_views: list[HospitalNodeRuntimeView] = []
        for node in nodes:
            node_rows = sorted(grouped.get(node.node_id, []), key=lambda item: item.updated_at, reverse=True)
            waiting_count = sum(
                1
                for item in node_rows
                if (item.department_status or item.department_flow_status) in {
                    DepartmentFlowStatus.WAITING_QUEUE_ROUND1.value,
                    DepartmentFlowStatus.WAITING_QUEUE_ROUND2.value,
                }
            )
            called_count = sum(
                1
                for item in node_rows
                if (item.department_status or item.department_flow_status) in {
                    DepartmentFlowStatus.CALLED_ROUND1.value,
                    DepartmentFlowStatus.CALLED_ROUND2.value,
                }
            )
            in_consultation_count = sum(
                1
                for item in node_rows
                if (item.department_status or item.department_flow_status) in {
                    DepartmentFlowStatus.IN_CONSULTATION_ROUND1.value,
                    DepartmentFlowStatus.IN_CONSULTATION_ROUND2.value,
                }
            )
            in_test_count = sum(
                1
                for item in node_rows
                if (item.department_status or item.department_flow_status) == DepartmentFlowStatus.IN_TEST.value
            )
            finished_count = sum(
                1
                for item in node_rows
                if (item.department_status or item.department_flow_status) == DepartmentFlowStatus.FINISHED.value
            )
            node_views.append(
                HospitalNodeRuntimeView(
                    node=node,
                    summary=HospitalNodeSummary(
                        node_id=node.node_id,
                        node_name=node.name,
                        node_type=node.node_type,
                        active_count=sum(1 for item in node_rows if not item.finished),
                        waiting_count=waiting_count,
                        called_count=called_count,
                        in_consultation_count=in_consultation_count,
                        in_test_count=in_test_count,
                        finished_count=finished_count,
                        updated_at=now_iso(),
                    ),
                    patients=node_rows,
                )
            )
        return HospitalRuntimeSnapshot(
            running=multi_snapshot.running,
            mode=multi_snapshot.mode,
            spawn_interval_seconds=multi_snapshot.spawn_interval_seconds,
            step_interval_seconds=multi_snapshot.step_interval_seconds,
            max_active_patients=multi_snapshot.max_active_patients,
            total_spawned=multi_snapshot.total_spawned,
            active_count=multi_snapshot.active_count,
            last_spawn_at=multi_snapshot.last_spawn_at,
            last_tick_at=multi_snapshot.last_tick_at,
            last_error=multi_snapshot.last_error,
            supervisor_mode=multi_snapshot.supervisor_mode,
            fairness_policy=multi_snapshot.fairness_policy,
            node_capacities=multi_snapshot.node_capacities,
            node_step_delays=multi_snapshot.node_step_delays,
            dispatch_count=multi_snapshot.dispatch_count,
            blocked_count=multi_snapshot.blocked_count,
            nodes=node_views,
            departments=department_snapshot.departments,
            unassigned_patients=department_snapshot.unassigned_patients,
        )

    @staticmethod
    def _derive_flow_status(*, visit_state: str | None, patient_lifecycle_state: str | None, ticket: dict | None) -> tuple[str, str, str | None]:
        queue_kind = ticket.get("queue_kind") if ticket else None
        ticket_status = ticket.get("status") if ticket else None

        if patient_lifecycle_state == "cancelled" or visit_state == VisitLifecycleState.CANCELLED.value:
            return DepartmentFlowStatus.CANCELLED.value, "none", queue_kind
        if patient_lifecycle_state == "error" or visit_state == VisitLifecycleState.ERROR.value:
            return DepartmentFlowStatus.ERROR.value, "none", queue_kind
        if visit_state in FINISHED_VISIT_STATES:
            return DepartmentFlowStatus.FINISHED.value, "none", queue_kind
        if visit_state == VisitLifecycleState.IN_SECOND_CONSULTATION.value:
            return DepartmentFlowStatus.IN_CONSULTATION_ROUND2.value, "round2", QueueTicketKind.RETURN_CONSULTATION.value
        if visit_state in TEST_VISIT_STATES:
            round_name = "round2" if queue_kind == QueueTicketKind.RETURN_CONSULTATION.value else "round1"
            return DepartmentFlowStatus.IN_TEST.value, round_name, queue_kind
        if visit_state == VisitLifecycleState.IN_CONSULTATION.value:
            return DepartmentFlowStatus.IN_CONSULTATION_ROUND1.value, "round1", QueueTicketKind.INITIAL_CONSULTATION.value
        if ticket_status == QueueTicketStatus.CALLED.value and queue_kind == QueueTicketKind.RETURN_CONSULTATION.value:
            return DepartmentFlowStatus.CALLED_ROUND2.value, "round2", queue_kind
        if ticket_status == QueueTicketStatus.CALLED.value:
            return (
                DepartmentFlowStatus.CALLED_ROUND1.value,
                "round1",
                queue_kind or QueueTicketKind.INITIAL_CONSULTATION.value,
            )
        if ticket_status == QueueTicketStatus.WAITING.value and queue_kind == QueueTicketKind.RETURN_CONSULTATION.value:
            return DepartmentFlowStatus.WAITING_QUEUE_ROUND2.value, "round2", queue_kind
        if ticket_status == QueueTicketStatus.WAITING.value:
            return (
                DepartmentFlowStatus.WAITING_QUEUE_ROUND1.value,
                "round1",
                queue_kind or QueueTicketKind.INITIAL_CONSULTATION.value,
            )
        return DepartmentFlowStatus.ASSIGNED_PENDING_REGISTRATION.value, "none", queue_kind

    @staticmethod
    def _node_for_visit_state(
        visit_state: str | None,
        assigned_department_id: str | None,
        *,
        assigned_doctor_slot_id: str | None = None,
    ) -> str:
        department_id = assigned_department_id or "internal"
        room = resolve_room_for_visit_state(
            department_id,
            visit_state,
            assigned_doctor_slot_id=assigned_doctor_slot_id,
        )
        if room is not None:
            return room.node_id
        if visit_state in {
            VisitLifecycleState.ARRIVED.value,
            VisitLifecycleState.TRIAGING.value,
            VisitLifecycleState.WAITING_FOLLOWUP.value,
            VisitLifecycleState.TRIAGED.value,
            VisitLifecycleState.REGISTERED.value,
            VisitLifecycleState.WAITING_CONSULTATION.value,
            VisitLifecycleState.IN_CONSULTATION.value,
            VisitLifecycleState.WAITING_SECOND_CONSULTATION.value,
            VisitLifecycleState.IN_SECOND_CONSULTATION.value,
            VisitLifecycleState.RESULTS_READY.value,
        }:
            return department_id
        if visit_state in {
            VisitLifecycleState.WAITING_TEST.value,
            VisitLifecycleState.WAITING_TEST_PAYMENT.value,
            VisitLifecycleState.TEST_PAYMENT_COMPLETED.value,
            VisitLifecycleState.IN_TEST.value,
            VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
            VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
            VisitLifecycleState.WAITING_RETURN_CONSULTATION.value,
        }:
            return "testing"
        if visit_state in {
            VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
            VisitLifecycleState.WAITING_PAYMENT.value,
            VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
        }:
            return "payment"
        if visit_state == VisitLifecycleState.WAITING_PHARMACY.value:
            return "pharmacy"
        return department_id

    @staticmethod
    def _resolve_doctor_slot_assignment(
        *,
        patient_id: str,
        department_id: str,
        existing: dict,
        assigned_doctor_slot_id: str | None,
        assigned_doctor_slot_name: str | None,
    ) -> dict[str, str | None]:
        slot_id = assigned_doctor_slot_id or existing.get("assigned_doctor_slot_id")
        slot_name = assigned_doctor_slot_name or existing.get("assigned_doctor_slot_name")
        slot = get_doctor_slot_by_id(department_id, slot_id)
        if slot is None:
            slot = stable_doctor_slot_for_patient(department_id, patient_id)
        if slot is not None:
            slot_id = slot.slot_id
            slot_name = slot.label
        return {
            "slot_id": slot_id,
            "slot_name": slot_name,
        }

    @staticmethod
    def _resolve_department_capability_fields(
        *,
        department_id: str | None,
        existing: dict,
        execution_runner_kind: str | None,
        department_agent_enabled: bool | None,
        department_capability_class: str | None,
    ) -> dict[str, str | bool]:
        capability = get_department_capability(department_id)
        resolved_runner_kind = execution_runner_kind or existing.get("execution_runner_kind") or capability.preferred_runner_kind
        existing_agent_enabled = existing.get("department_agent_enabled")
        if department_agent_enabled is None:
            if existing_agent_enabled is None:
                resolved_agent_enabled = capability.department_agent_enabled
            else:
                resolved_agent_enabled = bool(existing_agent_enabled)
        else:
            resolved_agent_enabled = department_agent_enabled
        resolved_capability_class = (
            department_capability_class
            or existing.get("department_capability_class")
            or capability.department_capability_class
        )
        return {
            "execution_runner_kind": resolved_runner_kind,
            "department_agent_enabled": bool(resolved_agent_enabled),
            "department_capability_class": resolved_capability_class,
        }

    @staticmethod
    def _resolve_room_assignment(
        *,
        department_id: str,
        visit_state: str | None,
        assigned_doctor_slot_id: str | None,
        current_room_node_id: str | None,
        current_room_name: str | None,
        room_type: str | None,
    ) -> dict[str, str | None]:
        room = resolve_room_for_visit_state(
            department_id,
            visit_state,
            assigned_doctor_slot_id=assigned_doctor_slot_id,
        )
        if room is not None:
            return {
                "node_id": room.node_id,
                "name": room.name,
                "room_type": room.room_type,
            }
        return {
            "node_id": current_room_node_id,
            "name": current_room_name,
            "room_type": room_type,
        }

    @staticmethod
    def _build_resource_summary(department_id: str, patient_rows: list[DepartmentRuntimePatientView]) -> dict[str, list]:
        config = get_department_resource_config(department_id)
        if config is None:
            return {"doctor_slots": [], "rooms": []}

        doctor_slot_views: list[DepartmentDoctorSlotRuntimeView] = []
        for slot in config.doctor_slots:
            active_patients = [
                row.patient_id
                for row in patient_rows
                if not row.finished and row.assigned_doctor_slot_id == slot.slot_id
            ]
            doctor_slot_views.append(
                DepartmentDoctorSlotRuntimeView(
                    slot_id=slot.slot_id,
                    label=slot.label,
                    capacity=slot.capacity,
                    active_count=len(active_patients),
                    patient_ids=active_patients,
                )
            )

        room_views: list[DepartmentRoomRuntimeView] = []
        for room in config.room_nodes:
            active_patients = [
                row.patient_id
                for row in patient_rows
                if not row.finished and row.current_room_node_id == room.node_id
            ]
            room_views.append(
                DepartmentRoomRuntimeView(
                    node_id=room.node_id,
                    name=room.name,
                    room_type=room.room_type,
                    capacity=room.capacity,
                    active_count=len(active_patients),
                    patient_ids=active_patients,
                )
            )

        return {
            "doctor_slots": doctor_slot_views,
            "rooms": room_views,
        }
