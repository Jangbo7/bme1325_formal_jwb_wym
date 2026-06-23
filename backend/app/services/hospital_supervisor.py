from __future__ import annotations

import json
import math
import queue
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.api.contract import ContractError, map_exception
from app.agents.npc_patient.debug_state import NpcPatientDebugState
from app.agents.npc_patient.profile import NpcPatientProfile, list_profiles
from app.agents.npc_patient.runner import NpcPatientRunner
from app.agents.patient_agent.debug_state import PatientAgentDebugState
from app.agents.patient_agent.runner import PatientAgentDebugRunner
from app.departments.registry import list_departments
from app.schemas.multi_patient_debug import (
    MultiPatientDebugPatientSnapshot,
    MultiPatientDebugSnapshot,
    MultiPatientMode,
)
from app.schemas.runtime_console import (
    RuntimeConsoleDepartmentConfig,
    RuntimeConsoleGlobalConfig,
    RuntimeConsoleSession,
)
from app.services.department_capabilities import (
    get_department_capability,
    list_departments_for_mode,
)
from app.services.department_assignment import resolve_assigned_department_for_visit
from app.services.debug_department_policy import should_lock_department_for_debug
from app.services.department_resources import (
    get_department_resource_config,
    list_department_resource_configs,
    resolve_room_for_visit_state,
    stable_doctor_slot_for_patient,
)
from app.services.disposition import is_outpatient_flow_finished, should_stop_outpatient_automation
from app.services.patient_flow_engine import FlowDecisionEngine, FlowExecutor
from app.services.runtime_projection import derive_runtime_projection


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


StateLike = NpcPatientDebugState | PatientAgentDebugState
RunnerKind = Literal["legacy", "intelligent"]


@dataclass
class _PatientSlot:
    npc_id: str
    mode: MultiPatientMode
    runner_kind: RunnerKind
    patient_source: Literal["scripted", "generated"]
    llm_mode: str
    llm_sampled_probability: float | None
    state: StateLike
    profile: NpcPatientProfile | None
    next_step_at: datetime
    last_step_at: datetime | None = None
    current_node_id: str | None = None
    target_node_id: str | None = None
    assigned_department_id: str | None = None
    assigned_department_name: str | None = None
    generation_hint_department_id: str | None = None
    generation_hint_department_name: str | None = None
    department_agent_enabled: bool = False
    department_capability_class: str | None = None
    assigned_doctor_slot_id: str | None = None
    assigned_doctor_slot_name: str | None = None
    current_room_node_id: str | None = None
    current_room_name: str | None = None
    room_type: str | None = None
    last_progress_signature: str | None = None
    unchanged_step_count: int = 0
    last_progress_at: datetime | None = None
    last_consultation_response_source: str | None = None
    last_consultation_llm_error: str | None = None
    fullview_waiting_command_id: str | None = None
    fullview_waiting_status: str | None = None
    fullview_waiting_reason_code: str | None = None
    fullview_waiting_error: str | None = None


class HospitalSupervisor:
    """Engine-driven hospital-wide scheduler used by both debug and runtime snapshots."""

    def __init__(self, container: dict):
        self._legacy_runner = NpcPatientRunner(container)
        self._intelligent_runner = PatientAgentDebugRunner(container)
        self._department_runtime_service = container.get("department_runtime_service")
        self._runtime_console_service = container.get("runtime_console_service")
        self._medical_record_card_service = container.get("medical_record_card_service")
        self._fullview_sync_repo = container.get("fullview_sync_repo")
        self._fullview_step_gate_available = bool(container.get("fullview_sync_enabled"))
        self._fullview_step_gate_enabled = bool(container.get("fullview_step_gate_enabled"))
        self._flow_engine = container.get("flow_decision_engine") or FlowDecisionEngine()
        self._flow_executor = container.get("flow_executor") or FlowExecutor()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._control_queue: queue.Queue[str] = queue.Queue()
        self._control_thread: threading.Thread | None = None
        self._urgent_step_pause = threading.Event()

        self._running = False
        self._mode: MultiPatientMode = "intelligent_agent"
        self._spawn_interval_seconds = 5.0
        self._step_interval_seconds = 2.0
        self._max_active_patients = 20
        self._llm_probability: float | None = None

        self._next_spawn_at: datetime | None = None
        self._last_spawn_at: str | None = None
        self._last_tick_at: str | None = None
        self._last_error: str | None = None

        self._total_spawned = 0
        self._dispatch_count = 0
        self._blocked_count = 0
        self._slots: list[_PatientSlot] = []
        self._spawned_by_department: dict[str, int] = {}
        self._default_department_ids = list_departments_for_mode("department_mixed")
        self._department_ids = list(self._default_department_ids)
        self._round_robin_index = 0
        self._runtime_console_mode = False
        self._runtime_session_id: str | None = None
        self._runtime_status = "idle"
        self._runtime_started_at: str | None = None
        self._runtime_ended_at: str | None = None
        self._runtime_updated_at: str | None = None
        self._spawn_paused = False
        self._step_paused = False
        self._drain_mode = False
        self._runtime_global_config = RuntimeConsoleGlobalConfig()
        self._runtime_department_configs: dict[str, RuntimeConsoleDepartmentConfig] = {}
        self._next_spawn_at_by_kind: dict[RunnerKind, datetime | None] = {
            "legacy": None,
            "intelligent": None,
        }

        self._supervisor_mode = "engine_driven"
        self._fairness_policy = "oldest_due_first"
        self._node_capacities = self._build_node_capacities()
        self._node_step_delays = {
            "testing": 1.0,
            "payment": 0.5,
            "pharmacy": 0.5,
        }
        self._max_steps_per_tick = 8
        self._fullview_spawn_backpressure_limit = 4

    def start(
        self,
        *,
        mode: MultiPatientMode,
        spawn_interval_seconds: float,
        step_interval_seconds: float,
        max_active_patients: int | None,
        llm_probability: float | None = None,
    ) -> MultiPatientDebugSnapshot:
        with self._lock:
            if self._running:
                raise RuntimeError("multi patient debug already running")
            self._running = True
            self._runtime_console_mode = False
            self._runtime_session_id = None
            self._runtime_status = "idle"
            self._runtime_started_at = None
            self._runtime_ended_at = None
            self._runtime_updated_at = None
            self._spawn_paused = False
            self._step_paused = False
            self._drain_mode = False
            self._runtime_department_configs = {}
            self._runtime_global_config = RuntimeConsoleGlobalConfig()
            self._mode = mode
            self._spawn_interval_seconds = max(0.0, float(spawn_interval_seconds))
            self._step_interval_seconds = max(0.1, float(step_interval_seconds))
            resolved_max = 20 if max_active_patients is None else int(max_active_patients)
            self._max_active_patients = max(1, resolved_max)
            self._llm_probability = llm_probability
            self._slots = []
            self._spawned_by_department = {}
            self._round_robin_index = 0
            self._total_spawned = 0
            self._dispatch_count = 0
            self._blocked_count = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            self._next_spawn_at = now_utc()
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        self._ensure_thread_running()
        return self.get_snapshot()

    def start_runtime_console(
        self,
        *,
        session_id: str,
        global_config: RuntimeConsoleGlobalConfig,
        department_configs: list[RuntimeConsoleDepartmentConfig],
    ) -> MultiPatientDebugSnapshot:
        with self._lock:
            if self._running:
                raise RuntimeError("runtime console already running")
            self._running = True
            self._runtime_console_mode = True
            self._mode = "department_mixed"
            self._runtime_session_id = session_id
            self._runtime_status = "running"
            self._runtime_started_at = now_iso()
            self._runtime_ended_at = None
            self._runtime_updated_at = self._runtime_started_at
            self._spawn_paused = False
            self._step_paused = False
            self._drain_mode = False
            self._urgent_step_pause.clear()
            self._apply_runtime_console_global_config(global_config)
            self._apply_runtime_console_department_configs(department_configs)
            self._slots = []
            self._spawned_by_department = {}
            self._round_robin_index = 0
            self._total_spawned = 0
            self._dispatch_count = 0
            self._blocked_count = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            now = now_utc()
            self._next_spawn_at = None
            self._next_spawn_at_by_kind = {
                "legacy": now,
                "intelligent": now,
            }
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        self._record_runtime_event(
            severity="info",
            category="lifecycle",
            event_type="session_started",
            message="runtime console session started",
            subject_type="system",
            subject_id=session_id,
            payload={"global_config": global_config.model_dump()},
        )
        self._ensure_thread_running()
        return self.get_snapshot()

    def stop(self) -> MultiPatientDebugSnapshot:
        with self._lock:
            self._running = False
            if self._runtime_console_mode:
                self._runtime_status = "stopped"
                self._runtime_ended_at = now_iso()
                self._runtime_updated_at = self._runtime_ended_at
                self._sync_runtime_session_record()
        self._stop_background_thread()
        if self._runtime_console_mode:
            self._record_runtime_event(
                severity="info",
                category="lifecycle",
                event_type="session_stopped",
                message="runtime console session stopped",
                subject_type="system",
                subject_id=self._runtime_session_id or "runtime-console",
            )
            if self._runtime_console_service:
                self._runtime_console_service.cleanup_runtime_patients(
                    self._runtime_session_id,
                    reset_local=False,
                )
        return self.get_snapshot()

    def reset(self) -> MultiPatientDebugSnapshot:
        self._stop_background_thread()
        with self._lock:
            self._running = False
            runtime_console_mode = self._runtime_console_mode
            runtime_session_id = self._runtime_session_id
            self._slots = []
            self._total_spawned = 0
            self._dispatch_count = 0
            self._blocked_count = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            self._next_spawn_at = None
            self._next_spawn_at_by_kind = {
                "legacy": None,
                "intelligent": None,
            }
            self._llm_probability = None
            self._runtime_console_mode = False
            self._runtime_session_id = None
            self._runtime_status = "idle"
            self._runtime_started_at = None
            self._runtime_ended_at = None
            self._runtime_updated_at = None
            self._spawn_paused = False
            self._step_paused = False
            self._drain_mode = False
            self._runtime_department_configs = {}
            self._runtime_global_config = RuntimeConsoleGlobalConfig()
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        if runtime_console_mode:
            self._record_runtime_event(
                severity="info",
                category="lifecycle",
                event_type="session_reset",
                message="runtime console session reset",
                subject_type="system",
                subject_id=runtime_session_id or "runtime-console",
            )
            if self._runtime_console_service:
                self._runtime_console_service.cleanup_runtime_patients(
                    runtime_session_id,
                    reset_local=True,
                )
        self._urgent_step_pause.clear()
        return self.get_snapshot()

    def get_snapshot(self) -> MultiPatientDebugSnapshot:
        with self._lock:
            patients = [self._to_patient_snapshot(slot) for slot in self._slots]
            active_count = sum(1 for slot in self._slots if not self._slot_is_inactive(slot))
            currently_blocked_patients = sum(
                1
                for slot in self._slots
                if not self._slot_is_inactive(slot)
                and (
                    slot.state.status in {"blocked", "waiting_capacity"}
                    or slot.fullview_waiting_command_id is not None
                )
            )
            active_by_department: dict[str, int] = {}
            for slot in self._slots:
                if self._slot_is_inactive(slot) or not slot.assigned_department_id:
                    continue
                active_by_department[slot.assigned_department_id] = active_by_department.get(slot.assigned_department_id, 0) + 1
            return MultiPatientDebugSnapshot(
                running=self._running,
                mode=self._mode,
                spawn_interval_seconds=self._spawn_interval_seconds,
                step_interval_seconds=self._step_interval_seconds,
                max_active_patients=self._max_active_patients,
                llm_probability=self._llm_probability,
                total_spawned=self._total_spawned,
                active_count=active_count,
                last_spawn_at=self._last_spawn_at,
                last_tick_at=self._last_tick_at,
                last_error=self._last_error,
                supervisor_mode=self._supervisor_mode,
                fairness_policy=self._fairness_policy,
                node_capacities=dict(self._node_capacities),
                node_step_delays=dict(self._node_step_delays),
                dispatch_count=self._dispatch_count,
                blocked_count=self._blocked_count,
                currently_blocked_patients=currently_blocked_patients,
                department_coverage=dict(self._spawned_by_department),
                active_by_department=active_by_department,
                patients=patients,
            )

    def get_runtime_session(self) -> RuntimeConsoleSession:
        with self._lock:
            return RuntimeConsoleSession(
                session_id=self._runtime_session_id,
                status=self._runtime_status,
                running=self._running,
                spawn_paused=self._spawn_paused,
                step_paused=self._step_paused,
                drain_mode=self._drain_mode,
                mode="runtime_console",
                started_at=self._runtime_started_at,
                ended_at=self._runtime_ended_at,
                updated_at=self._runtime_updated_at,
            )

    def get_runtime_mix_targets(self) -> dict[str, int]:
        with self._lock:
            return self._runtime_mix_targets_locked()

    def update_runtime_console_global_config(self, global_config: RuntimeConsoleGlobalConfig) -> None:
        with self._lock:
            self._apply_runtime_console_global_config(global_config)
        self._record_runtime_event(
            severity="info",
            category="lifecycle",
            event_type="global_config_updated",
            message="runtime console global config updated",
            subject_type="system",
            subject_id=self._runtime_session_id or "runtime-console",
            payload={"global_config": global_config.model_dump()},
        )

    def set_fullview_step_gate_enabled(self, enabled: bool) -> RuntimeConsoleGlobalConfig:
        with self._lock:
            self._runtime_global_config = self._runtime_global_config.model_copy(
                update={"fullview_step_gate_enabled": bool(enabled)}
            )
            self._fullview_step_gate_enabled = bool(
                self._fullview_step_gate_available and enabled
            )
            if self._fullview_sync_repo is not None:
                self._fullview_sync_repo.set_visual_cooldown_enabled(
                    self._fullview_step_gate_enabled
                )
            self._runtime_updated_at = now_iso()
            self._sync_runtime_session_record()
            return self._runtime_global_config

    def get_fullview_step_gate_status(self) -> dict:
        with self._lock:
            return {
                "available": self._fullview_step_gate_available,
                "enabled": self._fullview_step_gate_enabled,
                "visual_cooldown_enabled": bool(
                    self._fullview_sync_repo
                    and self._fullview_sync_repo.visual_cooldown_enabled
                ),
            }

    def update_runtime_console_department_configs(
        self,
        department_configs: list[RuntimeConsoleDepartmentConfig],
    ) -> None:
        with self._lock:
            self._apply_runtime_console_department_configs(department_configs)
        self._record_runtime_event(
            severity="info",
            category="lifecycle",
            event_type="department_config_updated",
            message="runtime console department config updated",
            subject_type="system",
            subject_id=self._runtime_session_id or "runtime-console",
            payload={"department_count": len(department_configs)},
        )

    def request_runtime_console_command(self, command: str) -> None:
        if command not in {"pause_spawn", "pause_step", "resume", "drain", "stop", "reset", "refresh"}:
            raise RuntimeError(f"unsupported runtime console command: {command}")
        if command in {"pause_step", "drain", "stop", "reset"}:
            self._urgent_step_pause.set()
        # These flags are intentionally set before queueing so pause commands
        # take effect immediately without waiting for an in-progress step lock.
        if command in {"pause_spawn", "drain"}:
            self._spawn_paused = True
        if command == "pause_step":
            self._step_paused = True
        if command == "drain":
            self._drain_mode = True
        self._ensure_control_thread_running()
        self._control_queue.put(command)

    def _ensure_control_thread_running(self) -> None:
        if self._control_thread and self._control_thread.is_alive():
            return
        self._control_thread = threading.Thread(
            target=self._run_control_loop,
            name="hospital-supervisor-control",
            daemon=True,
        )
        self._control_thread.start()

    def _run_control_loop(self) -> None:
        while True:
            command = self._control_queue.get()
            try:
                self.runtime_console_command(command)
            except Exception as exc:
                self._last_error = self._format_exception(exc)
            finally:
                self._control_queue.task_done()

    def runtime_console_command(self, command: str) -> MultiPatientDebugSnapshot:
        should_refresh_only = False
        with self._lock:
            session_id = self._runtime_session_id or "runtime-console"
            if command == "pause_spawn":
                self._spawn_paused = True
            elif command == "pause_step":
                self._step_paused = True
            elif command == "resume":
                self._spawn_paused = False
                self._step_paused = False
                self._drain_mode = False
                self._urgent_step_pause.clear()
            elif command == "drain":
                self._drain_mode = True
                self._spawn_paused = True
            elif command == "stop":
                self._running = False
            elif command == "refresh":
                should_refresh_only = True
            elif command == "reset":
                pass
            else:
                raise RuntimeError(f"unsupported runtime console command: {command}")
            if should_refresh_only:
                pass
            self._runtime_status = self._derive_runtime_status_locked()
            self._runtime_updated_at = now_iso()
            if command == "stop":
                self._runtime_ended_at = self._runtime_updated_at
            self._sync_runtime_session_record()
        if should_refresh_only:
            return self.get_snapshot()
        if command == "reset":
            return self.reset()
        if command == "stop":
            return self.stop()
        self._record_runtime_event(
            severity="info",
            category="lifecycle",
            event_type=f"command_{command}",
            message=f"runtime console command: {command}",
            subject_type="system",
            subject_id=session_id,
        )
        return self.get_snapshot()

    def tick_once(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._last_tick_at = now_iso()
            if not self._spawn_paused:
                self._spawn_if_due()
            if not self._step_paused:
                self._step_due_patients()
            if self._runtime_console_mode and self._drain_mode and self._active_slot_count_locked() == 0:
                self._running = False
                self._runtime_status = "stopped"
                self._runtime_ended_at = now_iso()
                self._runtime_updated_at = self._runtime_ended_at
                self._sync_runtime_session_record()

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
            if self._runtime_console_mode:
                self._runtime_status = "stopped"
                self._runtime_ended_at = now_iso()
                self._runtime_updated_at = self._runtime_ended_at
                self._sync_runtime_session_record()
        self._stop_background_thread()

    def _stop_background_thread(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def _ensure_thread_running(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="hospital-supervisor",
            daemon=True,
        )
        self._thread.start()

    def _run_loop(self) -> None:
        while not self._stop_event.wait(0.5):
            try:
                self.tick_once()
            except Exception:
                continue

    def _spawn_if_due(self) -> None:
        if self._runtime_console_mode:
            self._spawn_if_due_runtime_console()
            return
        active_slots = [slot for slot in self._slots if not self._slot_is_inactive(slot)]
        if len(active_slots) >= self._max_active_patients:
            return
        now = now_utc()
        if self._next_spawn_at and now < self._next_spawn_at:
            return
        npc_id = f"MULTI-NPC-{self._total_spawned + 1:03d}"
        try:
            slot = self._spawn_slot(npc_id)
        except Exception as exc:
            self._last_error = self._format_exception(exc)
            return
        self._slots.append(slot)
        self._total_spawned += 1
        self._last_spawn_at = now.isoformat()
        self._next_spawn_at = now + timedelta(seconds=self._spawn_interval_seconds)
        self._sync_runtime_for_slot(slot)

    def _spawn_if_due_runtime_console(self) -> None:
        if self._active_slot_count_locked() >= self._max_active_patients:
            return
        if self._fullview_spawn_backpressure_reached():
            return
        now = now_utc()
        due_kinds = [
            kind
            for kind, due_at in self._next_spawn_at_by_kind.items()
            if due_at is not None and now >= due_at
        ]
        due_kinds.sort(key=lambda kind: self._next_spawn_at_by_kind[kind] or now)
        for kind in due_kinds:
            if self._urgent_step_pause.is_set():
                break
            if self._active_slot_count_locked() >= self._max_active_patients:
                break
            if not self._should_spawn_runtime_kind(kind):
                self._next_spawn_at_by_kind[kind] = now + timedelta(seconds=self._spawn_interval_for_kind(kind))
                continue
            npc_id = f"MULTI-NPC-{self._total_spawned + 1:03d}"
            try:
                slot = self._spawn_slot_runtime_console(npc_id=npc_id, runner_kind=kind, now=now)
            except Exception as exc:
                message = self._format_exception(exc)
                self._last_error = message
                self._record_runtime_event(
                    severity="warning",
                    category="spawn",
                    event_type="spawn_skipped",
                    message=message,
                    subject_type="system",
                    subject_id=self._runtime_session_id or "runtime-console",
                    payload={"runner_kind": kind},
                )
                self._next_spawn_at_by_kind[kind] = now + timedelta(seconds=self._spawn_interval_for_kind(kind))
                continue
            self._slots.append(slot)
            self._total_spawned += 1
            self._last_spawn_at = now.isoformat()
            self._next_spawn_at_by_kind[kind] = now + timedelta(seconds=self._spawn_interval_for_kind(kind))
            self._sync_runtime_for_slot(slot)
            self._record_runtime_event(
                severity="info",
                category="spawn",
                event_type="spawn_succeeded",
                message=f"spawned {kind} patient for {slot.generation_hint_department_id}",
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.generation_hint_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
                payload={
                    "runner_kind": kind,
                    "department_id": slot.generation_hint_department_id,
                },
            )

    def _spawn_slot(self, npc_id: str) -> _PatientSlot:
        now = now_utc()
        target_department_id = self._next_department_for_spawn()
        capability = get_department_capability(target_department_id)
        if self._mode == "legacy_template":
            return self._spawn_legacy_slot(
                npc_id=npc_id,
                slot_mode="legacy_template",
                target_department_id=target_department_id,
                llm_mode="offline",
                llm_sampled_probability=None,
                now=now,
            )

        if self._mode == "legacy_probabilistic_llm":
            sampled_probability = float(self._llm_probability or 0.0)
            if random.random() < sampled_probability:
                return self._spawn_intelligent_slot(
                    npc_id=npc_id,
                    slot_mode="legacy_probabilistic_llm",
                    target_department_id=target_department_id,
                    now=now,
                    preassign_department=False,
                    llm_sampled_probability=sampled_probability,
                )
            return self._spawn_legacy_slot(
                npc_id=npc_id,
                slot_mode="legacy_probabilistic_llm",
                target_department_id=target_department_id,
                llm_mode="offline",
                llm_sampled_probability=sampled_probability,
                now=now,
            )

        if self._mode == "intelligent_agent":
            if not capability.department_agent_enabled:
                raise RuntimeError(f"department {target_department_id} is not eligible for intelligent mode")
            return self._spawn_intelligent_slot(
                npc_id=npc_id,
                slot_mode="intelligent_agent",
                target_department_id=target_department_id,
                now=now,
            )

        if capability.department_agent_enabled:
            return self._spawn_intelligent_slot(
                npc_id=npc_id,
                slot_mode="department_mixed",
                target_department_id=target_department_id,
                now=now,
            )
        if capability.supports_scripted_fallback:
            return self._spawn_legacy_slot(
                npc_id=npc_id,
                slot_mode="department_mixed",
                target_department_id=target_department_id,
                llm_mode="offline",
                llm_sampled_probability=None,
                now=now,
            )
        raise RuntimeError(f"department {target_department_id} cannot be spawned in mode {self._mode}")

    def _spawn_slot_runtime_console(
        self,
        *,
        npc_id: str,
        runner_kind: RunnerKind,
        now: datetime,
    ) -> _PatientSlot:
        target_department_id = self._next_department_for_runtime_spawn(runner_kind)
        if runner_kind == "intelligent":
            return self._spawn_intelligent_slot(
                npc_id=npc_id,
                slot_mode="department_mixed",
                target_department_id=target_department_id,
                now=now,
            )
        return self._spawn_legacy_slot(
            npc_id=npc_id,
            slot_mode="department_mixed",
            target_department_id=target_department_id,
            llm_mode="offline",
            llm_sampled_probability=None,
            now=now,
        )

    def _spawn_legacy_slot(
        self,
        *,
        npc_id: str,
        slot_mode: MultiPatientMode,
        target_department_id: str,
        llm_mode: str,
        llm_sampled_probability: float | None,
        now: datetime,
    ) -> _PatientSlot:
        profile_pool = list_profiles(target_department_id) or list_profiles()
        profile = random.choice(profile_pool)
        state = self._legacy_runner.spawn(profile)
        state.npc_id = npc_id
        slot = _PatientSlot(
            npc_id=npc_id,
            mode=slot_mode,
            runner_kind="legacy",
            patient_source="scripted",
            llm_mode=llm_mode,
            llm_sampled_probability=llm_sampled_probability,
            state=state,
            profile=profile,
            next_step_at=now + timedelta(seconds=self._step_interval_for_kind("legacy")),
            generation_hint_department_id=target_department_id,
            generation_hint_department_name=self._department_name(target_department_id),
        )
        state.mode = slot_mode
        self._assign_slot_department(
            slot,
            profile.target_department_id,
            profile.target_department_name,
            increment_coverage=True,
            update_visit_assignment=True,
            lock_debug_department=True,
        )
        return slot

    def _spawn_intelligent_slot(
        self,
        *,
        npc_id: str,
        slot_mode: MultiPatientMode,
        target_department_id: str,
        now: datetime,
        preassign_department: bool = True,
        llm_sampled_probability: float | None = None,
    ) -> _PatientSlot:
        state = self._intelligent_runner.spawn(
            seed=f"{npc_id}-{target_department_id}-{random.randint(1000, 9999)}",
            department_id=target_department_id,
        )
        state.npc_id = npc_id
        state.mode = slot_mode
        assigned_department_name = self._department_name(target_department_id)
        slot = _PatientSlot(
            npc_id=npc_id,
            mode=slot_mode,
            runner_kind="intelligent",
            patient_source="generated",
            llm_mode="online",
            llm_sampled_probability=llm_sampled_probability,
            state=state,
            profile=None,
            next_step_at=now + timedelta(seconds=self._step_interval_for_kind("intelligent")),
            generation_hint_department_id=target_department_id,
            generation_hint_department_name=assigned_department_name,
        )
        self._spawned_by_department[target_department_id] = self._spawned_by_department.get(target_department_id, 0) + 1
        if preassign_department:
            self._assign_slot_department(
                slot,
                target_department_id,
                assigned_department_name,
                increment_coverage=False,
                update_visit_assignment=True,
                lock_debug_department=False,
            )
        return slot

    def _step_due_patients(self) -> None:
        now = now_utc()
        due_slots = [slot for slot in self._slots if not self._slot_is_inactive(slot) and now >= slot.next_step_at]
        due_slots.sort(
            key=lambda slot: (
                slot.next_step_at,
                slot.last_step_at or datetime.fromtimestamp(0, tz=timezone.utc),
                slot.state.step_count,
                slot.npc_id,
            )
        )
        dispatch_budget: dict[str, int] = {}
        stepped_count = 0
        # Scan all due slots so a Fullview-gated patient cannot starve patients
        # behind it. Actual patient work remains bounded because a step may
        # invoke an LLM while the supervisor lock is held.
        for slot in due_slots:
            if self._urgent_step_pause.is_set():
                break
            blocker = self._fullview_step_gate_blocker(slot)
            if blocker is not None:
                self._defer_for_fullview(slot, blocker, now)
                self._sync_runtime_for_slot(slot)
                self._evaluate_runtime_console_slot(slot)
                continue
            if stepped_count >= self._max_steps_per_tick:
                break
            self._release_fullview_gate(slot)
            try:
                node_id = self._decide_and_step(slot, dispatch_budget, now)
                slot.last_step_at = now
                slot.current_node_id = node_id
                stepped_count += 1
            except Exception as exc:
                slot.state.last_error = self._format_exception(exc)
                slot.state.status = "error"
                self._last_error = self._format_exception(exc)
                stepped_count += 1
                self._record_runtime_event(
                    severity="error",
                    category="validation",
                    event_type="step_failed",
                    message=slot.state.last_error,
                    subject_type="patient",
                    subject_id=slot.state.patient_id,
                    department_id=slot.assigned_department_id,
                    patient_id=slot.state.patient_id,
                    npc_id=slot.npc_id,
                )
            self._sync_runtime_for_slot(slot)
            self._evaluate_runtime_console_slot(slot)

    def _fullview_spawn_backpressure_reached(self) -> bool:
        if not self._fullview_step_gate_enabled or self._fullview_sync_repo is None:
            return False
        visual_backlog_patients = (
            self._fullview_sync_repo.get_visual_backlog_patient_count()
        )
        return visual_backlog_patients >= self._fullview_spawn_backpressure_limit

    def _fullview_step_gate_blocker(self, slot: _PatientSlot) -> dict | None:
        if not self._fullview_step_gate_enabled or self._fullview_sync_repo is None:
            return None
        encounter_id = str(slot.state.encounter_id or "").strip()
        if not encounter_id:
            return None
        return self._fullview_sync_repo.get_step_gate_blocker(encounter_id)

    def _defer_for_fullview(self, slot: _PatientSlot, blocker: dict, now: datetime) -> None:
        command_id = str(blocker.get("command_id") or "")
        command_status = str(blocker.get("status") or "pending")
        reason_code = str(blocker.get("reason_code") or "") or None
        slot.fullview_waiting_status = command_status
        slot.fullview_waiting_reason_code = reason_code
        slot.fullview_waiting_error = str(blocker.get("last_error") or "") or None
        slot.next_step_at = now + timedelta(
            seconds=max(0.2, min(1.0, self._step_interval_for_kind(slot.runner_kind)))
        )
        if slot.fullview_waiting_command_id == command_id:
            return
        slot.fullview_waiting_command_id = command_id
        self._blocked_count += 1
        waiting_reason = (
            "visual cooldown"
            if command_status == "accepted"
            else f"command {command_status}"
        )
        is_terminal_failure = command_status in {"blocked", "dead_letter"}
        is_capacity_wait = reason_code in {
            "BED_UNAVAILABLE",
            "ICU_BED_UNAVAILABLE",
            "WARD_BED_UNAVAILABLE",
            "NO_AVAILABLE_BED",
            "OUTPATIENT_SLOT_UNAVAILABLE",
            "RESOURCE_BLOCKED",
        }
        self._record_runtime_event(
            severity="error" if is_terminal_failure else ("warning" if is_capacity_wait else "info"),
            category="capacity" if is_capacity_wait else "scheduling",
            event_type="waiting_fullview",
            message=(
                f"waiting for Fullview {waiting_reason}: {command_id}"
            ),
            subject_type="patient",
            subject_id=slot.state.patient_id,
            department_id=slot.assigned_department_id,
            patient_id=slot.state.patient_id,
            npc_id=slot.npc_id,
            payload={
                "command_id": command_id,
                "command_status": command_status,
                "event_id": blocker.get("event_id"),
                "reason_code": blocker.get("reason_code"),
                "visual_ready_at": blocker.get("visual_ready_at"),
            },
        )

    def _release_fullview_gate(self, slot: _PatientSlot) -> None:
        if slot.fullview_waiting_command_id is None:
            return
        command_id = slot.fullview_waiting_command_id
        slot.fullview_waiting_command_id = None
        slot.fullview_waiting_status = None
        slot.fullview_waiting_reason_code = None
        slot.fullview_waiting_error = None
        self._record_runtime_event(
            severity="info",
            category="scheduling",
            event_type="fullview_accepted",
            message=f"Fullview command accepted; resuming patient step: {command_id}",
            subject_type="patient",
            subject_id=slot.state.patient_id,
            department_id=slot.assigned_department_id,
            patient_id=slot.state.patient_id,
            npc_id=slot.npc_id,
            payload={"command_id": command_id},
        )

    def _decide_and_step(self, slot: _PatientSlot, dispatch_budget: dict[str, int], now: datetime) -> str | None:
        if slot.runner_kind == "legacy":
            if slot.profile is None:
                raise RuntimeError("legacy slot missing profile")
            runner = self._legacy_runner
        else:
            runner = self._intelligent_runner

        visit_row = runner._get_visit_row(slot.state)  # noqa: SLF001
        patient_row = runner.patient_repo.get(slot.state.patient_id)
        self._refresh_slot_department_from_visit(slot, visit_row)
        assigned_department_id = self._resolved_assigned_department_id(slot, visit_row, patient_row)

        context = runner.build_context(slot.state)
        planned, decision = self._flow_engine.decide_with_plan(
            assigned_department_id=assigned_department_id,
            runner_context=context,
        )
        if decision.next_action in {"enter_round1_consult", "enter_round2_consult"}:
            self._assign_available_consultation_slot(slot, dispatch_budget)
        target_node = self._resolve_target_node_for_slot(
            slot,
            visit_state=context.visit_state,
            next_action=decision.next_action,
            default_target_node=decision.target_node or assigned_department_id or "triage",
        )
        slot.target_node_id = target_node
        if decision.next_action != "complete_visit" and not self._can_dispatch_to_node(
            target_node,
            dispatch_budget,
            slot=slot,
        ):
            self._blocked_count += 1
            slot.state.status = "waiting_capacity"
            slot.state.last_error = f"node capacity reached: {target_node}"
            slot.next_step_at = now + timedelta(seconds=max(0.5, self._step_interval_for_kind(slot.runner_kind) / 2))
            self._record_runtime_event(
                severity="warning",
                category="capacity",
                event_type="capacity_block",
                message=slot.state.last_error,
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
                payload={"target_node_id": target_node},
            )
            return slot.current_node_id or target_node

        if slot.runner_kind == "legacy":
            result = self._flow_executor.execute_legacy(
                runner=self._legacy_runner,
                state=slot.state,
                profile=slot.profile,
                planned=planned,
                decision=decision,
                force_offline_llm=slot.llm_mode == "offline",
            )
        else:
            result = self._flow_executor.execute_intelligent(
                runner=self._intelligent_runner,
                state=slot.state,
                planned=planned,
                decision=decision,
            )
        if not result.ok:
            self._blocked_count += 1
            slot.state.status = "blocked"
            slot.state.last_error = result.error
            slot.next_step_at = now + timedelta(seconds=max(0.5, self._step_interval_for_kind(slot.runner_kind) / 2))
            self._record_runtime_event(
                severity="warning",
                category="scheduling",
                event_type="step_blocked",
                message=result.error or "step blocked",
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
            )
            return slot.current_node_id or target_node

        if decision.next_action != "complete_visit":
            dispatch_budget[target_node] = dispatch_budget.get(target_node, 0) + 1
        self._dispatch_count += 1
        updated_visit_row = runner._get_visit_row(slot.state)  # noqa: SLF001
        self._refresh_slot_department_from_visit(slot, updated_visit_row)
        visit_data = {}
        if updated_visit_row is not None:
            visit_data = runner._decode_visit_data(updated_visit_row)  # noqa: SLF001
        if is_outpatient_flow_finished(slot.state.visit_state, visit_data):
            slot.state.finished = True
            slot.state.phase = "finished"
            slot.state.status = slot.state.visit_state or "finished"
            slot.state.clear_dialogue()
        slot.state.last_error = None
        slot.next_step_at = now + timedelta(seconds=self._next_delay_for_node(slot, target_node))
        self._record_runtime_event(
            severity="info",
            category="scheduling",
            event_type="step_succeeded",
            message=f"patient stepped to {target_node}",
            subject_type="patient",
            subject_id=slot.state.patient_id,
            department_id=slot.assigned_department_id,
            patient_id=slot.state.patient_id,
            npc_id=slot.npc_id,
            payload={"target_node_id": target_node, "visit_state": slot.state.visit_state},
        )
        return target_node

    def _can_dispatch_to_node(
        self,
        node_id: str,
        dispatch_budget: dict[str, int],
        *,
        slot: _PatientSlot,
    ) -> bool:
        capacity = self._node_capacities.get(node_id, self._node_capacities.get("*", 1))
        if slot.current_room_node_id == node_id:
            return True
        occupied = sum(
            1
            for other in self._slots
            if other is not slot
            and not self._slot_is_inactive(other)
            and other.current_room_node_id == node_id
        )
        return occupied + dispatch_budget.get(node_id, 0) < capacity

    def _assign_available_consultation_slot(
        self,
        slot: _PatientSlot,
        dispatch_budget: dict[str, int],
    ) -> None:
        config = get_department_resource_config(slot.assigned_department_id)
        if config is None:
            return
        candidates = []
        for doctor_slot in config.doctor_slots:
            occupied = sum(
                1
                for other in self._slots
                if other is not slot
                and not self._slot_is_inactive(other)
                and other.current_room_node_id == doctor_slot.room_node_id
            )
            reserved = dispatch_budget.get(doctor_slot.room_node_id, 0)
            if occupied + reserved < doctor_slot.capacity:
                candidates.append((occupied + reserved, doctor_slot.slot_id, doctor_slot))
        if not candidates:
            return
        _, _, doctor_slot = min(candidates)
        slot.assigned_doctor_slot_id = doctor_slot.slot_id
        slot.assigned_doctor_slot_name = doctor_slot.label

    def _next_delay_for_node(self, slot: _PatientSlot, node_id: str) -> float:
        default_step_interval = self._step_interval_for_kind(slot.runner_kind)
        return max(0.1, float(self._node_step_delays.get(node_id, default_step_interval)))

    def _build_node_capacities(self) -> dict[str, int]:
        capacities = {"*": 1, "triage": 8, "testing": 2, "payment": 2, "pharmacy": 2}
        for config in list_department_resource_configs():
            capacities[config.department_id] = config.department_gate_capacity
            for room in config.room_nodes:
                capacities[room.node_id] = room.capacity
        return capacities

    def _to_patient_snapshot(self, slot: _PatientSlot) -> MultiPatientDebugPatientSnapshot:
        profile_id = slot.profile.profile_id if slot.profile else None
        case_summary = slot.state.case_summary if isinstance(slot.state, PatientAgentDebugState) else None
        visit_row = None
        visit_data = {}
        if slot.state.encounter_id:
            runner = self._legacy_runner if slot.runner_kind == "legacy" else self._intelligent_runner
            visit_row = runner.visit_repo.get(slot.state.encounter_id)
            if visit_row is not None:
                visit_data = runner._decode_visit_data(visit_row)  # noqa: SLF001
        runtime_row = (
            self._department_runtime_service.runtime_repo.get_patient_runtime(
                slot.state.patient_id,
                slot.state.encounter_id,
            )
            if self._department_runtime_service and slot.state.patient_id and slot.state.encounter_id
            else None
        )
        consultation_observability = (
            self._department_runtime_service.get_latest_consultation_observability(
                patient_id=slot.state.patient_id,
                visit_id=slot.state.encounter_id,
            )
            if self._department_runtime_service and slot.state.patient_id and slot.state.encounter_id
            else {
                "latest_consultation_response_source": None,
                "latest_consultation_llm_error": None,
            }
        )
        if case_summary is None and slot.profile is not None:
            case_summary = {
                "name": slot.profile.name,
                "age": slot.profile.age,
                "sex": slot.profile.sex,
                "chief_complaint": slot.profile.chief_complaint,
                "symptoms": slot.profile.symptoms,
            }
        effective_status = (
            "waiting_fullview"
            if slot.fullview_waiting_command_id is not None
            else slot.state.status
        )
        effective_error = slot.fullview_waiting_error or slot.state.last_error
        projection = derive_runtime_projection(
            assigned_department_id=slot.assigned_department_id,
            assigned_department_name=slot.assigned_department_name,
            assigned_doctor_slot_id=slot.assigned_doctor_slot_id,
            assigned_doctor_slot_name=slot.assigned_doctor_slot_name,
            current_node_id=slot.current_node_id,
            current_room_node_id=slot.current_room_node_id,
            current_room_name=slot.current_room_name,
            room_type=slot.room_type,
            target_node_id=slot.target_node_id,
            visit_state=slot.state.visit_state,
            patient_lifecycle_state=slot.state.patient_lifecycle_state,
            department_status=(runtime_row or {}).get("department_status") or (runtime_row or {}).get("department_flow_status"),
            department_round=(runtime_row or {}).get("department_round"),
            phase=slot.state.phase,
            status=effective_status,
            finished=slot.state.finished,
            last_error=effective_error,
        )
        if slot.state.encounter_id and self._medical_record_card_service is not None:
            medical_record_card = self._medical_record_card_service.get_card_for_visit(
                slot.state.encounter_id,
                hide_until_finished=True,
            )
        else:
            medical_record_card = (
                self._medical_record_card_service.build_pending_view()
                if self._medical_record_card_service is not None
                else {}
            )
        return MultiPatientDebugPatientSnapshot(
            npc_id=slot.npc_id,
            mode=slot.mode,
            execution_runner_kind=slot.runner_kind,
            patient_source=slot.patient_source,
            department_agent_enabled=slot.department_agent_enabled,
            department_capability_class=slot.department_capability_class or "script_only",
            llm_mode=slot.llm_mode,
            llm_probability=slot.llm_sampled_probability,
            profile_id=profile_id,
            patient_id=slot.state.patient_id,
            encounter_id=slot.state.encounter_id,
            visit_state=slot.state.visit_state,
            patient_lifecycle_state=slot.state.patient_lifecycle_state,
            primary_disposition=visit_data.get("primary_disposition"),
            disposition=dict(visit_data.get("disposition") or {}),
            outpatient_flow_finished=is_outpatient_flow_finished(slot.state.visit_state, visit_data),
            outpatient_finished_at=visit_data.get("outpatient_finished_at"),
            rare_event_profile=dict(
                visit_data.get("rare_event_profile")
                or (case_summary or {}).get("rare_event_profile")
                or {}
            ),
            rare_event_triggered_by=visit_data.get("rare_event_triggered_by") or (case_summary or {}).get("rare_event_triggered_by"),
            rare_event_type=visit_data.get("rare_event_type") or (case_summary or {}).get("rare_event_type"),
            rare_event_seed=visit_data.get("rare_event_seed") or (case_summary or {}).get("rare_event_seed"),
            report_acuity_level=((visit_data.get("simulated_report") or {}).get("report_summary") or {}).get("acuity_level"),
            report_cross_specialty_clues=list(
                (((visit_data.get("simulated_report") or {}).get("report_summary") or {}).get("cross_specialty_clues") or [])
            ),
            recommended_department=visit_data.get("recommended_department"),
            recommended_department_reason=visit_data.get("recommended_department_reason"),
            requires_new_registration=bool(visit_data.get("requires_new_registration", False)),
            carry_forward_summary=dict(visit_data.get("carry_forward_summary") or {}),
            medical_record_card=medical_record_card,
            assigned_department_id=slot.assigned_department_id,
            assigned_department_name=slot.assigned_department_name,
            generation_hint_department_id=slot.generation_hint_department_id,
            generation_hint_department_name=slot.generation_hint_department_name,
            assigned_doctor_slot_id=slot.assigned_doctor_slot_id,
            assigned_doctor_slot_name=slot.assigned_doctor_slot_name,
            phase=slot.state.phase,
            status=effective_status,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue=slot.state.current_dialogue,
            last_action=slot.state.last_action,
            last_error=effective_error,
            step_count=slot.state.step_count,
            finished=slot.state.finished,
            case_summary=case_summary,
            current_node_id=slot.current_node_id,
            current_room_node_id=slot.current_room_node_id,
            current_room_name=slot.current_room_name,
            room_type=slot.room_type,
            target_node_id=slot.target_node_id,
            display_stage=projection["display_stage"],
            dispatch_state=projection["dispatch_state"],
            consultation_round=projection["consultation_round"],
            blocking=projection["blocking"],
            resource_assignment=projection["resource_assignment"],
            latest_consultation_response_source=consultation_observability["latest_consultation_response_source"],
            latest_consultation_llm_error=consultation_observability["latest_consultation_llm_error"],
            next_step_at=slot.next_step_at.isoformat(),
        )

    def _assign_slot_department(
        self,
        slot: _PatientSlot,
        department_id: str,
        department_name: str,
        *,
        increment_coverage: bool,
        update_visit_assignment: bool,
        lock_debug_department: bool,
    ) -> None:
        slot.assigned_department_id = department_id
        slot.assigned_department_name = department_name
        capability = get_department_capability(department_id)
        slot.department_agent_enabled = capability.department_agent_enabled
        slot.department_capability_class = capability.department_capability_class
        doctor_slot = stable_doctor_slot_for_patient(department_id, slot.state.patient_id)
        if doctor_slot is not None:
            slot.assigned_doctor_slot_id = doctor_slot.slot_id
            slot.assigned_doctor_slot_name = doctor_slot.label
        else:
            slot.assigned_doctor_slot_id = None
            slot.assigned_doctor_slot_name = None
        if increment_coverage:
            self._spawned_by_department[department_id] = self._spawned_by_department.get(department_id, 0) + 1
        if update_visit_assignment and slot.state.encounter_id:
            if slot.runner_kind == "legacy":
                visit_repo = self._legacy_runner.visit_repo
            else:
                visit_repo = self._intelligent_runner.visit_repo
            visit_row = visit_repo.get(slot.state.encounter_id)
            visit_data = {}
            if visit_row and visit_row.get("data_json"):
                try:
                    visit_data = json.loads(visit_row["data_json"])
                except Exception:
                    visit_data = {}
            if lock_debug_department and should_lock_department_for_debug(mode=slot.mode, department_id=department_id):
                visit_data.update(
                    {
                        "debug_department_locked_by_mode": True,
                        "debug_spawn_department_id": department_id,
                        "debug_spawn_department_name": department_name,
                    }
                )
            visit_repo.update_visit(
                slot.state.encounter_id,
                assigned_department_id=department_id,
                assigned_department_name=department_name,
                data=visit_data,
            )

    def _department_name(self, department_id: str) -> str:
        for item in list_departments(include_legacy=False):
            if item["id"] == department_id:
                return item["label"]
        return "Internal Medicine"

    def _next_department_for_spawn(self) -> str:
        department_ids = self._effective_department_ids_for_mode()
        # First pass guarantees at least one spawned patient for each formal department.
        for department_id in department_ids:
            if self._spawned_by_department.get(department_id, 0) == 0:
                return department_id
        if not department_ids:
            raise RuntimeError(f"no eligible departments configured for mode {self._mode}")
        department_id = department_ids[self._round_robin_index % len(department_ids)]
        self._round_robin_index += 1
        return department_id

    def _effective_department_ids_for_mode(self) -> list[str]:
        allowed = set(list_departments_for_mode(self._mode))
        return [department_id for department_id in self._department_ids if department_id in allowed]

    def _spawn_interval_for_kind(self, runner_kind: RunnerKind) -> float:
        if self._runtime_console_mode:
            if runner_kind == "intelligent":
                return max(0.0, float(self._runtime_global_config.agent_spawn_interval_seconds))
            return max(0.0, float(self._runtime_global_config.script_spawn_interval_seconds))
        return max(0.0, float(self._spawn_interval_seconds))

    def _step_interval_for_kind(self, runner_kind: RunnerKind) -> float:
        if self._runtime_console_mode:
            if runner_kind == "intelligent":
                return max(0.1, float(self._runtime_global_config.agent_step_interval_seconds))
            return max(0.1, float(self._runtime_global_config.script_step_interval_seconds))
        return max(0.1, float(self._step_interval_seconds))

    def _apply_runtime_console_global_config(self, global_config: RuntimeConsoleGlobalConfig) -> None:
        self._runtime_global_config = global_config
        self._fullview_step_gate_enabled = bool(
            self._fullview_step_gate_available
            and global_config.fullview_step_gate_enabled
        )
        if self._fullview_sync_repo is not None:
            self._fullview_sync_repo.set_visual_cooldown_enabled(
                self._fullview_step_gate_enabled
            )
        self._max_active_patients = int(global_config.max_active_patients)
        self._spawn_interval_seconds = min(
            float(global_config.agent_spawn_interval_seconds),
            float(global_config.script_spawn_interval_seconds),
        )
        self._step_interval_seconds = min(
            float(global_config.agent_step_interval_seconds),
            float(global_config.script_step_interval_seconds),
        )
        self._runtime_updated_at = now_iso()
        self._sync_runtime_session_record()

    def _apply_runtime_console_department_configs(
        self,
        department_configs: list[RuntimeConsoleDepartmentConfig],
    ) -> None:
        self._runtime_department_configs = {
            item.department_id: item
            for item in department_configs
        }
        self._runtime_updated_at = now_iso()
        self._sync_runtime_session_record()

    def _derive_runtime_status_locked(self) -> str:
        if not self._running:
            return "stopped"
        if self._drain_mode:
            return "draining"
        if self._spawn_paused or self._step_paused:
            return "paused"
        return "running"

    def _sync_runtime_session_record(self) -> None:
        if not self._runtime_console_mode or not self._runtime_console_service or not self._runtime_session_id:
            return
        self._runtime_console_service.repo.update_session(
            self._runtime_session_id,
            status=self._runtime_status,
            running=1 if self._running else 0,
            spawn_paused=1 if self._spawn_paused else 0,
            step_paused=1 if self._step_paused else 0,
            drain_mode=1 if self._drain_mode else 0,
            started_at=self._runtime_started_at,
            ended_at=self._runtime_ended_at,
            updated_at=self._runtime_updated_at or now_iso(),
            global_config_json=self._runtime_console_service.repo.db.encode_json(
                self._runtime_global_config.model_dump()
            ),
        )

    def _record_runtime_event(
        self,
        *,
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
    ) -> None:
        if not self._runtime_console_mode or not self._runtime_console_service:
            return
        self._runtime_console_service.record_event(
            session_id=self._runtime_session_id,
            severity=severity,
            category=category,
            event_type=event_type,
            message=message,
            subject_type=subject_type,
            subject_id=subject_id,
            department_id=department_id,
            patient_id=patient_id,
            npc_id=npc_id,
            payload=payload,
        )

    def _evaluate_runtime_console_slot(self, slot: _PatientSlot) -> None:
        if not self._runtime_console_mode:
            return
        snapshot = self._to_patient_snapshot(slot)
        signature = "|".join(
            [
                str(snapshot.visit_state or ""),
                str(snapshot.display_stage or ""),
                str(snapshot.dispatch_state or ""),
            ]
        )
        if not snapshot.display_stage or not snapshot.dispatch_state:
            self._record_runtime_event(
                severity="error",
                category="validation",
                event_type="invalid_state",
                message="runtime projection missing display stage or dispatch state",
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
            )
        if slot.generation_hint_department_id and snapshot.assigned_department_id and slot.generation_hint_department_id != snapshot.assigned_department_id:
            self._record_runtime_event(
                severity="warning",
                category="department",
                event_type="department_mismatch",
                message=(
                    f"generation hint {slot.generation_hint_department_id} differs from assigned "
                    f"{snapshot.assigned_department_id}"
                ),
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=snapshot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
            )
        if snapshot.latest_consultation_response_source == "fallback" and slot.last_consultation_response_source != "fallback":
            self._record_runtime_event(
                severity="warning",
                category="llm",
                event_type="llm_fallback",
                message="consultation used fallback response",
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
            )
        if snapshot.latest_consultation_llm_error and snapshot.latest_consultation_llm_error != slot.last_consultation_llm_error:
            self._record_runtime_event(
                severity="error",
                category="llm",
                event_type="llm_error",
                message=snapshot.latest_consultation_llm_error,
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
            )
        if signature == slot.last_progress_signature and not self._slot_is_inactive(slot):
            slot.unchanged_step_count += 1
        else:
            slot.unchanged_step_count = 0
            slot.last_progress_signature = signature
            slot.last_progress_at = now_utc()
        if slot.unchanged_step_count in {3, 6}:
            self._record_runtime_event(
                severity="warning" if slot.unchanged_step_count == 3 else "error",
                category="stuck",
                event_type="stuck_patient",
                message=f"patient made no progress for {slot.unchanged_step_count} consecutive steps",
                subject_type="patient",
                subject_id=slot.state.patient_id,
                department_id=slot.assigned_department_id,
                patient_id=slot.state.patient_id,
                npc_id=slot.npc_id,
                payload={"unchanged_step_count": slot.unchanged_step_count},
            )
        slot.last_consultation_response_source = snapshot.latest_consultation_response_source
        slot.last_consultation_llm_error = snapshot.latest_consultation_llm_error

    def _next_department_for_runtime_spawn(self, runner_kind: RunnerKind) -> str:
        configs = list(self._runtime_department_configs.values())
        candidates: list[tuple[RuntimeConsoleDepartmentConfig, float]] = []
        for config in configs:
            if not config.enabled or config.spawn_weight <= 0:
                continue
            capability = get_department_capability(config.department_id)
            if runner_kind == "intelligent":
                if not config.allow_agent_patients or not capability.department_agent_enabled:
                    continue
            else:
                if not config.allow_script_patients or not capability.supports_scripted_fallback:
                    continue
            candidates.append((config, float(config.spawn_weight)))
        if not candidates:
            raise RuntimeError(f"no eligible departments configured for {runner_kind} patients")
        total_weight = sum(weight for _config, weight in candidates)
        sample = random.uniform(0.0, total_weight)
        upto = 0.0
        for config, weight in candidates:
            upto += weight
            if sample <= upto:
                return config.department_id
        return candidates[-1][0].department_id

    def _active_slot_count_locked(self) -> int:
        return sum(1 for slot in self._slots if not self._slot_is_inactive(slot))

    def _slot_is_inactive(self, slot: _PatientSlot) -> bool:
        if slot.state.finished:
            return True
        if slot.state.status == "error":
            return True
        visit_data = {}
        if slot.state.encounter_id:
            runner = self._legacy_runner if slot.runner_kind == "legacy" else self._intelligent_runner
            visit_row = runner.visit_repo.get(slot.state.encounter_id)
            if visit_row is not None:
                visit_data = runner._decode_visit_data(visit_row)  # noqa: SLF001
        return should_stop_outpatient_automation(slot.state.visit_state, visit_data)

    def _runtime_mix_targets_locked(self) -> dict[str, int]:
        active_agent_count = sum(
            1
            for slot in self._slots
            if not self._slot_is_inactive(slot) and slot.runner_kind == "intelligent"
        )
        active_script_count = sum(
            1
            for slot in self._slots
            if not self._slot_is_inactive(slot) and slot.runner_kind == "legacy"
        )
        agent_target = min(
            self._max_active_patients,
            max(0, int(round(self._max_active_patients * self._runtime_global_config.active_agent_ratio))),
        )
        script_target = max(0, self._max_active_patients - agent_target)
        return {
            "agent": agent_target,
            "script": script_target,
            "active_agent_count": active_agent_count,
            "active_script_count": active_script_count,
        }

    def _should_spawn_runtime_kind(self, runner_kind: RunnerKind) -> bool:
        counts = self._runtime_mix_targets_locked()
        kind_key = "agent" if runner_kind == "intelligent" else "script"
        other_key = "script" if kind_key == "agent" else "agent"
        active_count = counts["active_agent_count"] + counts["active_script_count"]
        if active_count >= self._max_active_patients:
            return False
        current_kind = counts["active_agent_count"] if kind_key == "agent" else counts["active_script_count"]
        current_other = counts["active_script_count"] if kind_key == "agent" else counts["active_agent_count"]
        if current_kind < counts[kind_key]:
            return True
        if current_other < counts[other_key]:
            return False
        return True

    @staticmethod
    def _format_exception(exc: Exception) -> str:
        if isinstance(exc, ContractError):
            code, message, details, _status = map_exception(exc)
            if details is None:
                return f"{code}: {message}"
            try:
                details_text = json.dumps(details, ensure_ascii=False, sort_keys=True)
            except Exception:
                details_text = str(details)
            return f"{code}: {message} | details={details_text}"
        return str(exc)

    def _sync_runtime_for_slot(self, slot: _PatientSlot) -> None:
        if not self._department_runtime_service:
            return
        current_dialogue = slot.state.current_dialogue
        if hasattr(current_dialogue, "model_dump"):
            current_dialogue_payload = current_dialogue.model_dump()
        else:
            current_dialogue_payload = current_dialogue or {}
        runtime_row = self._department_runtime_service.sync_patient_runtime(
            patient_id=slot.state.patient_id,
            visit_id=slot.state.encounter_id,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue_preview=current_dialogue_payload.get("message"),
            target_node_id=slot.target_node_id,
            execution_runner_kind=slot.runner_kind,
            patient_source=slot.patient_source,
            generation_hint_department_id=slot.generation_hint_department_id,
            generation_hint_department_name=slot.generation_hint_department_name,
            department_agent_enabled=slot.department_agent_enabled,
            department_capability_class=slot.department_capability_class,
            assigned_doctor_slot_id=slot.assigned_doctor_slot_id,
            assigned_doctor_slot_name=slot.assigned_doctor_slot_name,
            last_transition_action=slot.state.last_action,
            transition_version=now_iso(),
            allow_unassigned_department=(
                slot.patient_source == "generated" and not slot.assigned_department_id
            ),
        )
        if runtime_row:
            slot.department_agent_enabled = bool(runtime_row.get("department_agent_enabled"))
            slot.department_capability_class = runtime_row.get("department_capability_class")
            slot.assigned_doctor_slot_id = runtime_row.get("assigned_doctor_slot_id")
            slot.assigned_doctor_slot_name = runtime_row.get("assigned_doctor_slot_name")
            slot.current_node_id = runtime_row.get("current_node_id")
            slot.current_room_node_id = runtime_row.get("current_room_node_id")
            slot.current_room_name = runtime_row.get("current_room_name")
            slot.room_type = runtime_row.get("room_type")

    def _resolve_target_node_for_slot(
        self,
        slot: _PatientSlot,
        *,
        visit_state: str | None,
        next_action: str | None,
        default_target_node: str,
    ) -> str:
        department_id = slot.assigned_department_id
        if not department_id:
            return default_target_node
        if next_action in {"enter_round1_consult", "enter_round2_consult"}:
            consult_room = resolve_room_for_visit_state(
                department_id,
                "in_consultation",
                assigned_doctor_slot_id=slot.assigned_doctor_slot_id,
            )
            if consult_room is not None:
                return consult_room.node_id
        room = resolve_room_for_visit_state(
            department_id,
            visit_state,
            assigned_doctor_slot_id=slot.assigned_doctor_slot_id,
        )
        if room is not None and default_target_node in {department_id, "outpatient_procedure"}:
            return room.node_id
        return default_target_node

    def _resolved_assigned_department_id(
        self,
        slot: _PatientSlot,
        visit_row: dict | None,
        patient_row: dict | None,
    ) -> str | None:
        if slot.patient_source == "generated" and visit_row:
            assigned_id = str(visit_row.get("assigned_department_id") or "").strip()
            assigned_name = str(visit_row.get("assigned_department_name") or "").strip()
            if assigned_id and assigned_name:
                return assigned_id
            return slot.assigned_department_id
        if visit_row:
            return resolve_assigned_department_for_visit(visit_row, patient_row)["id"]
        return slot.assigned_department_id

    def _refresh_slot_department_from_visit(self, slot: _PatientSlot, visit_row: dict | None) -> None:
        if not visit_row:
            return
        assigned_id = str(visit_row.get("assigned_department_id") or "").strip()
        assigned_name = str(visit_row.get("assigned_department_name") or "").strip()
        if not assigned_id or not assigned_name:
            # Keep the spawn-time department as a provisional routing hint until
            # triage writes the authoritative visit assignment.
            return
        if (
            slot.assigned_department_id == assigned_id
            and slot.assigned_department_name == assigned_name
        ):
            return
        self._assign_slot_department(
            slot,
            assigned_id,
            assigned_name,
            increment_coverage=False,
            update_visit_assignment=False,
            lock_debug_department=False,
        )
