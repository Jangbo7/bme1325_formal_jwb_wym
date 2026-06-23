from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from app.departments.registry import list_departments
from app.schemas.department_runtime import DepartmentRuntimeSummaryView
from app.schemas.runtime_console import (
    RuntimeConsoleDepartmentConfig,
    RuntimeConsoleDepartmentView,
    RuntimeConsoleEvent,
    RuntimeConsoleGlobalConfig,
    RuntimeConsoleSession,
    RuntimeConsoleSnapshot,
    RuntimeIssueSummary,
)
from app.services.department_capabilities import get_department_capability


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeConsoleService:
    def __init__(
        self,
        *,
        repo,
        department_runtime_service,
        fullview_client=None,
        fullview_sync_repo=None,
        fullview_event_listener=None,
        fullview_sync_enabled: bool = False,
        fullview_step_gate_enabled: bool = False,
    ):
        self.repo = repo
        self.department_runtime_service = department_runtime_service
        self.fullview_client = fullview_client
        self.fullview_sync_repo = fullview_sync_repo
        self.fullview_event_listener = fullview_event_listener
        self.fullview_sync_enabled = bool(fullview_sync_enabled)
        self.fullview_step_gate_enabled = bool(
            fullview_sync_enabled and fullview_step_gate_enabled
        )

    def prepare_local_runtime_reset(self, session_id: str | None = None) -> dict:
        patient_ids = set(self.repo.list_spawned_patient_ids(session_id))
        if self.fullview_sync_repo is not None:
            patient_ids.update(self.fullview_sync_repo.list_managed_patient_ids())
        patient_ids.update(self._list_remote_backend_patient_ids())
        patient_ids = sorted(patient_ids)
        skipped_commands = 0
        if patient_ids and self.fullview_sync_repo is not None:
            skipped_commands = self.fullview_sync_repo.skip_unfinished_for_patients(
                patient_ids,
                reason="runtime console reset or backend restart",
            )
        return {
            "session_id": session_id,
            "patient_ids": patient_ids,
            "skipped_commands": skipped_commands,
        }

    def _list_remote_backend_patient_ids(self) -> set[str]:
        if not self.fullview_sync_enabled or self.fullview_client is None:
            return set()
        fetch_snapshot = getattr(self.fullview_client, "fetch_snapshot", None)
        if fetch_snapshot is None:
            return set()
        try:
            snapshot = fetch_snapshot()
        except Exception:
            return set()
        patient_ids = set()
        for patient in snapshot.get("patients") or []:
            if not isinstance(patient, dict):
                continue
            clinical = patient.get("clinical") or {}
            summary = clinical.get("summary") or {}
            if (
                summary.get("source") == "outpatient_backend"
                or clinical.get("producer") == "groupA.outpatient"
            ):
                patient_id = (
                    patient.get("patientId")
                    or patient.get("patient_id")
                    or patient.get("id")
                )
                if patient_id:
                    patient_ids.add(str(patient_id))
        return patient_ids

    def cleanup_fullview_patients(
        self,
        patient_ids: list[str],
        *,
        session_id: str | None = None,
        skipped_commands: int = 0,
    ) -> dict:
        result = {
            "session_id": session_id,
            "patient_count": len(patient_ids),
            "deleted": [],
            "failed": [],
            "skipped_commands": skipped_commands,
        }
        if not self.fullview_sync_enabled:
            return result
        if self.fullview_event_listener is None:
            result["failed"] = [
                {"patient_id": patient_id, "error": "Fullview cleanup scheduler unavailable"}
                for patient_id in patient_ids
            ]
            return result
        statuses = self.fullview_event_listener.drain_cleanup(patient_ids)
        for patient_id in patient_ids:
            if statuses.get(patient_id) == "deleted":
                result["deleted"].append(patient_id)
            else:
                result["failed"].append(
                    {
                        "patient_id": patient_id,
                        "error": f"cleanup status: {statuses.get(patient_id, 'missing')}",
                    }
                )
        return result

    def cleanup_runtime_patients(
        self,
        session_id: str | None = None,
        *,
        reset_local: bool = False,
    ) -> dict:
        if reset_local:
            plan = self.prepare_local_runtime_reset(session_id)
            patient_ids = plan["patient_ids"]
            skipped_commands = int(plan["skipped_commands"])
        else:
            patient_ids = self.repo.list_spawned_patient_ids(session_id)
            skipped_commands = 0
            if patient_ids and self.fullview_sync_repo is not None:
                skipped_commands = self.fullview_sync_repo.skip_unfinished_for_patients(
                    patient_ids,
                    reason="runtime console reset or backend restart",
                )
        result = self.cleanup_fullview_patients(
            patient_ids,
            session_id=session_id,
            skipped_commands=skipped_commands,
        )
        if reset_local:
            self.repo.db.reset_runtime_data()
        return result

    def cleanup_stale_fullview_patients(self) -> dict:
        patient_ids = set(self._list_remote_backend_patient_ids())
        if self.fullview_sync_repo is not None:
            patient_ids.update(self.fullview_sync_repo.list_managed_patient_ids())
        resolved = sorted(patient_ids)
        skipped_commands = 0
        if resolved and self.fullview_sync_repo is not None:
            skipped_commands = self.fullview_sync_repo.skip_unfinished_for_patients(
                resolved,
                reason="new runtime session stale Fullview cleanup",
            )
        return self.cleanup_fullview_patients(
            resolved,
            skipped_commands=skipped_commands,
        )

    def default_global_config(self) -> RuntimeConsoleGlobalConfig:
        return RuntimeConsoleGlobalConfig(
            fullview_step_gate_enabled=self.fullview_step_gate_enabled,
        )

    def default_department_configs(self) -> list[RuntimeConsoleDepartmentConfig]:
        configs: list[RuntimeConsoleDepartmentConfig] = []
        for department in list_departments(include_legacy=False):
            capability = get_department_capability(department["id"])
            configs.append(
                RuntimeConsoleDepartmentConfig(
                    department_id=department["id"],
                    department_name=department["label"],
                    enabled=True,
                    spawn_weight=1.0,
                    allow_agent_patients=capability.department_agent_enabled,
                    allow_script_patients=capability.supports_scripted_fallback,
                    updated_at=now_iso(),
                )
            )
        return configs

    def get_latest_session(self) -> RuntimeConsoleSession | None:
        return self.repo.get_latest_session()

    def get_global_config(self, session_id: str | None) -> RuntimeConsoleGlobalConfig:
        if not session_id:
            return self.default_global_config()
        return self.repo.get_global_config(session_id) or self.default_global_config()

    def get_department_configs(self, session_id: str | None) -> list[RuntimeConsoleDepartmentConfig]:
        if not session_id:
            return self.default_department_configs()
        configs = self.repo.list_department_configs(session_id)
        return configs or self.default_department_configs()

    def create_session(
        self,
        *,
        global_config: RuntimeConsoleGlobalConfig,
        department_configs: list[RuntimeConsoleDepartmentConfig] | None,
    ) -> tuple[RuntimeConsoleSession, list[RuntimeConsoleDepartmentConfig]]:
        session = self.repo.create_session(status="running", global_config=global_config)
        configs = department_configs or self.default_department_configs()
        persisted = self.repo.replace_department_configs(session.session_id or "", configs)
        return session, persisted

    def update_global_config(self, session_id: str, global_config: RuntimeConsoleGlobalConfig) -> RuntimeConsoleGlobalConfig:
        return self.repo.update_global_config(session_id, global_config)

    def update_department_configs(
        self,
        session_id: str,
        department_configs: list[RuntimeConsoleDepartmentConfig],
    ) -> list[RuntimeConsoleDepartmentConfig]:
        return self.repo.replace_department_configs(session_id, department_configs)

    def record_event(
        self,
        *,
        session_id: str | None,
        severity: str,
        category: str,
        event_type: str,
        message: str,
        subject_type: str,
        subject_id: str,
        department_id: str | None = None,
        patient_id: str | None = None,
        npc_id: str | None = None,
        payload: dict | None = None,
    ) -> RuntimeConsoleEvent | None:
        if not session_id:
            return None
        event = RuntimeConsoleEvent(
            event_id=f"runtime-event-{uuid.uuid4().hex}",
            session_id=session_id,
            occurred_at=now_iso(),
            severity=severity,
            category=category,
            event_type=event_type,
            message=message,
            subject_type=subject_type,
            subject_id=subject_id,
            department_id=department_id,
            patient_id=patient_id,
            npc_id=npc_id,
            payload=payload or {},
        )
        return self.repo.append_event(event)

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
        return self.repo.list_events(
            session_id=session_id,
            severity=severity,
            category=category,
            subject_type=subject_type,
            subject_id=subject_id,
            limit=limit,
        )

    def build_snapshot(self, *, supervisor, runtime_snapshot=None) -> RuntimeConsoleSnapshot:
        session = supervisor.get_runtime_session()
        session_id = session.session_id
        global_config = self.get_global_config(session_id)
        department_configs = self.get_department_configs(session_id)
        hospital_snapshot = runtime_snapshot or self.department_runtime_service.build_hospital_runtime_snapshot(
            supervisor.get_snapshot()
        )
        patients = []
        for department in hospital_snapshot.departments:
            patients.extend(department.patients)
        patients.extend(hospital_snapshot.unassigned_patients)

        config_by_department = {item.department_id: item for item in department_configs}
        recent_events = self.list_events(session_id=session_id, limit=120) if session_id else []
        recent_issue_summaries = self._aggregate_issue_events(recent_events)
        current_issues = self._build_current_issues(patients)
        issue_counts_by_department = defaultdict(int)
        for issue in recent_issue_summaries:
            if issue.department_id:
                issue_counts_by_department[issue.department_id] += issue.occurrence_count

        departments: list[RuntimeConsoleDepartmentView] = []
        for department in hospital_snapshot.departments:
            config = config_by_department.get(department.department_id) or RuntimeConsoleDepartmentConfig(
                department_id=department.department_id,
                department_name=department.department_name,
                enabled=True,
                spawn_weight=1.0,
                allow_agent_patients=department.department_agent_enabled,
                allow_script_patients=True,
            )
            blocked_patients = sum(
                1
                for patient in department.patients
                if patient.blocking is not None or (patient.last_error and not patient.finished)
            )
            departments.append(
                RuntimeConsoleDepartmentView(
                    department_id=department.department_id,
                    department_name=department.department_name,
                    config=config,
                    department_agent_enabled=department.department_agent_enabled,
                    department_capability_class=department.department_capability_class,
                    department_gate_capacity=department.department_gate_capacity,
                    summary=department.summary,
                    doctor_slots=department.doctor_slots,
                    rooms=department.rooms,
                    patients=department.patients,
                    blocked_patients=blocked_patients,
                    recent_issue_count=issue_counts_by_department.get(department.department_id, 0),
                )
            )

        severity_counts = defaultdict(int)
        category_counts = defaultdict(int)
        for issue in current_issues:
            severity_counts[issue.severity] += issue.occurrence_count
            category_counts[issue.category] += issue.occurrence_count

        targets = supervisor.get_runtime_mix_targets()
        return RuntimeConsoleSnapshot(
            session=session,
            global_config=global_config,
            department_configs=department_configs,
            active_agent_target=targets["agent"],
            active_script_target=targets["script"],
            active_agent_count=targets["active_agent_count"],
            active_script_count=targets["active_script_count"],
            total_spawned=hospital_snapshot.total_spawned,
            active_count=hospital_snapshot.active_count,
            last_spawn_at=hospital_snapshot.last_spawn_at,
            last_tick_at=hospital_snapshot.last_tick_at,
            last_error=hospital_snapshot.last_error,
            nodes=[item.model_dump() for item in hospital_snapshot.nodes],
            departments=departments,
            patients=sorted(patients, key=lambda item: item.updated_at, reverse=True),
            current_issues=current_issues,
            recent_issues=recent_issue_summaries[:30],
            recent_events=recent_events[:50],
            severity_counts=dict(severity_counts),
            category_counts=dict(category_counts),
        )

    def _aggregate_issue_events(self, events: list[RuntimeConsoleEvent]) -> list[RuntimeIssueSummary]:
        grouped: dict[str, RuntimeIssueSummary] = {}
        for event in events:
            if event.severity == "info":
                continue
            issue_key = "|".join(
                [
                    event.category,
                    event.event_type,
                    event.subject_type,
                    event.subject_id,
                    event.department_id or "",
                    event.patient_id or "",
                ]
            )
            existing = grouped.get(issue_key)
            if existing is None:
                grouped[issue_key] = RuntimeIssueSummary(
                    issue_key=issue_key,
                    severity=event.severity,
                    category=event.category,
                    subject_type=event.subject_type,
                    subject_id=event.subject_id,
                    department_id=event.department_id,
                    patient_id=event.patient_id,
                    npc_id=event.npc_id,
                    latest_message=event.message,
                    occurrence_count=1,
                    last_occurred_at=event.occurred_at,
                    current=False,
                )
                continue
            existing.occurrence_count += 1
            if event.occurred_at > existing.last_occurred_at:
                existing.last_occurred_at = event.occurred_at
                existing.latest_message = event.message
                existing.severity = event.severity
        return sorted(grouped.values(), key=lambda item: item.last_occurred_at, reverse=True)

    def _build_current_issues(self, patients: list) -> list[RuntimeIssueSummary]:
        issues: list[RuntimeIssueSummary] = []
        now = now_iso()
        for patient in patients:
            if patient.latest_consultation_llm_error:
                issues.append(
                    RuntimeIssueSummary(
                        issue_key=f"llm-error|{patient.patient_id}",
                        severity="error",
                        category="llm",
                        subject_type="patient",
                        subject_id=patient.patient_id,
                        department_id=patient.assigned_department_id,
                        patient_id=patient.patient_id,
                        npc_id=patient.npc_id,
                        latest_message=patient.latest_consultation_llm_error,
                        last_occurred_at=patient.updated_at or now,
                    )
                )
            elif patient.latest_consultation_response_source == "fallback":
                issues.append(
                    RuntimeIssueSummary(
                        issue_key=f"llm-fallback|{patient.patient_id}",
                        severity="warning",
                        category="llm",
                        subject_type="patient",
                        subject_id=patient.patient_id,
                        department_id=patient.assigned_department_id,
                        patient_id=patient.patient_id,
                        npc_id=patient.npc_id,
                        latest_message="consultation used fallback response",
                        last_occurred_at=patient.updated_at or now,
                    )
                )
            if patient.blocking is not None:
                issues.append(
                    RuntimeIssueSummary(
                        issue_key=f"capacity|{patient.patient_id}",
                        severity="warning",
                        category="capacity",
                        subject_type="patient",
                        subject_id=patient.patient_id,
                        department_id=patient.assigned_department_id,
                        patient_id=patient.patient_id,
                        npc_id=patient.npc_id,
                        latest_message=patient.blocking.message or patient.last_error or "patient blocked",
                        last_occurred_at=patient.updated_at or now,
                    )
                )
            if patient.last_error and (
                patient.visit_state == "error" or patient.patient_lifecycle_state == "error"
            ):
                issues.append(
                    RuntimeIssueSummary(
                        issue_key=f"validation|{patient.patient_id}",
                        severity="error",
                        category="validation",
                        subject_type="patient",
                        subject_id=patient.patient_id,
                        department_id=patient.assigned_department_id,
                        patient_id=patient.patient_id,
                        npc_id=patient.npc_id,
                        latest_message=patient.last_error,
                        last_occurred_at=patient.updated_at or now,
                    )
                )
        return issues

    @staticmethod
    def empty_department_summary(department_id: str, department_name: str) -> DepartmentRuntimeSummaryView:
        return DepartmentRuntimeSummaryView(
            department_id=department_id,
            department_name=department_name,
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
