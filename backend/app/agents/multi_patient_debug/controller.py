from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.agents.npc_patient.debug_state import NpcPatientDebugState
from app.agents.npc_patient.profile import NpcPatientProfile, list_profiles
from app.agents.npc_patient.runner import NpcPatientRunner
from app.agents.patient_agent.debug_state import PatientAgentDebugState
from app.agents.patient_agent.runner import PatientAgentDebugRunner
from app.services.department_assignment import resolve_assigned_department_for_visit
from app.services.patient_flow_engine import FlowDecisionEngine, FlowExecutor
from app.schemas.multi_patient_debug import (
    MultiPatientDebugPatientSnapshot,
    MultiPatientDebugSnapshot,
    MultiPatientMode,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


StateLike = NpcPatientDebugState | PatientAgentDebugState


@dataclass
class _PatientSlot:
    npc_id: str
    mode: MultiPatientMode
    state: StateLike
    profile: NpcPatientProfile | None
    next_step_at: datetime


class MultiPatientDebugController:
    def __init__(self, container: dict):
        self._legacy_runner = NpcPatientRunner(container)
        self._intelligent_runner = PatientAgentDebugRunner(container)
        self._department_runtime_service = container.get("department_runtime_service")
        self._flow_engine = container.get("flow_decision_engine") or FlowDecisionEngine()
        self._flow_executor = container.get("flow_executor") or FlowExecutor()

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._running = False
        self._mode: MultiPatientMode = "intelligent_agent"
        self._spawn_interval_seconds = 5.0
        self._step_interval_seconds = 2.0
        self._max_active_patients = 3

        self._next_spawn_at: datetime | None = None
        self._last_spawn_at: str | None = None
        self._last_tick_at: str | None = None
        self._last_error: str | None = None

        self._total_spawned = 0
        self._slots: list[_PatientSlot] = []

    def start(
        self,
        *,
        mode: MultiPatientMode,
        spawn_interval_seconds: float,
        step_interval_seconds: float,
        max_active_patients: int,
    ) -> MultiPatientDebugSnapshot:
        with self._lock:
            if self._running:
                raise RuntimeError("multi patient debug already running")
            self._running = True
            self._mode = mode
            self._spawn_interval_seconds = max(0.0, float(spawn_interval_seconds))
            self._step_interval_seconds = max(0.1, float(step_interval_seconds))
            self._max_active_patients = max(1, min(10, int(max_active_patients)))
            self._slots = []
            self._total_spawned = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            self._next_spawn_at = now_utc()
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        self._ensure_thread_running()
        return self.get_snapshot()

    def stop(self) -> MultiPatientDebugSnapshot:
        with self._lock:
            self._running = False
        self._stop_background_thread()
        return self.get_snapshot()

    def reset(self) -> MultiPatientDebugSnapshot:
        self._stop_background_thread()
        with self._lock:
            self._running = False
            self._slots = []
            self._total_spawned = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            self._next_spawn_at = None
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        return self.get_snapshot()

    def get_snapshot(self) -> MultiPatientDebugSnapshot:
        with self._lock:
            patients = [self._to_patient_snapshot(slot) for slot in self._slots]
            active_count = sum(1 for slot in self._slots if not slot.state.finished)
            return MultiPatientDebugSnapshot(
                running=self._running,
                mode=self._mode,
                spawn_interval_seconds=self._spawn_interval_seconds,
                step_interval_seconds=self._step_interval_seconds,
                max_active_patients=self._max_active_patients,
                total_spawned=self._total_spawned,
                active_count=active_count,
                last_spawn_at=self._last_spawn_at,
                last_tick_at=self._last_tick_at,
                last_error=self._last_error,
                patients=patients,
            )

    def tick_once(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._last_tick_at = now_iso()
            self._spawn_if_due()
            self._step_due_patients()

    def shutdown(self) -> None:
        with self._lock:
            self._running = False
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
            name="multi-patient-debug",
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
        if len(self._slots) >= self._max_active_patients:
            return
        now = now_utc()
        if self._next_spawn_at and now < self._next_spawn_at:
            return
        npc_id = f"MULTI-NPC-{self._total_spawned + 1:03d}"
        try:
            slot = self._spawn_slot(npc_id)
        except Exception as exc:
            self._last_error = str(exc)
            return
        self._slots.append(slot)
        self._total_spawned += 1
        self._last_spawn_at = now.isoformat()
        self._next_spawn_at = now + timedelta(seconds=self._spawn_interval_seconds)
        self._sync_runtime_for_slot(slot)

    def _spawn_slot(self, npc_id: str) -> _PatientSlot:
        now = now_utc()
        if self._mode == "legacy_template":
            profile = random.choice(list_profiles())
            state = self._legacy_runner.spawn(profile)
            state.npc_id = npc_id
            return _PatientSlot(
                npc_id=npc_id,
                mode="legacy_template",
                state=state,
                profile=profile,
                next_step_at=now + timedelta(seconds=self._step_interval_seconds),
            )
        state = self._intelligent_runner.spawn(seed=f"{npc_id}-{random.randint(1000, 9999)}")
        state.npc_id = npc_id
        return _PatientSlot(
            npc_id=npc_id,
            mode="intelligent_agent",
            state=state,
            profile=None,
            next_step_at=now + timedelta(seconds=self._step_interval_seconds),
        )

    def _step_due_patients(self) -> None:
        now = now_utc()
        due = [slot for slot in self._slots if not slot.state.finished and now >= slot.next_step_at]
        random.shuffle(due)
        for slot in due:
            try:
                self._step_slot(slot)
            except Exception as exc:
                slot.state.last_error = str(exc)
                slot.state.status = "error"
                slot.state.finished = True
                self._last_error = str(exc)
            self._sync_runtime_for_slot(slot)
            slot.next_step_at = now + timedelta(seconds=self._step_interval_seconds)

    def _step_slot(self, slot: _PatientSlot) -> None:
        visit_row = None
        patient_row = None
        assigned_department_id = None
        if slot.mode == "legacy_template":
            if slot.profile is None:
                raise RuntimeError("legacy slot missing profile")
            visit_row = self._legacy_runner._get_visit_row(slot.state)  # noqa: SLF001
            patient_row = self._legacy_runner.patient_repo.get(slot.state.patient_id)
            if visit_row:
                assigned_department_id = resolve_assigned_department_for_visit(visit_row, patient_row)["id"]
            context = self._legacy_runner.build_context(slot.state)
            planned, decision = self._flow_engine.decide_with_plan(
                assigned_department_id=assigned_department_id,
                runner_context=context,
            )
            result = self._flow_executor.execute_legacy(
                runner=self._legacy_runner,
                state=slot.state,
                profile=slot.profile,
                planned=planned,
                decision=decision,
            )
            if not result.ok:
                slot.state.status = "idle"
                slot.state.last_error = result.error
            return
        visit_row = self._intelligent_runner._get_visit_row(slot.state)  # noqa: SLF001
        patient_row = self._intelligent_runner.patient_repo.get(slot.state.patient_id)
        if visit_row:
            assigned_department_id = resolve_assigned_department_for_visit(visit_row, patient_row)["id"]
        context = self._intelligent_runner.build_context(slot.state)
        planned, decision = self._flow_engine.decide_with_plan(
            assigned_department_id=assigned_department_id,
            runner_context=context,
        )
        result = self._flow_executor.execute_intelligent(
            runner=self._intelligent_runner,
            state=slot.state,
            planned=planned,
            decision=decision,
        )
        if not result.ok:
            slot.state.status = "idle"
            slot.state.last_error = result.error

    def _to_patient_snapshot(self, slot: _PatientSlot) -> MultiPatientDebugPatientSnapshot:
        profile_id = slot.profile.profile_id if slot.profile else None
        case_summary = slot.state.case_summary if isinstance(slot.state, PatientAgentDebugState) else None
        return MultiPatientDebugPatientSnapshot(
            npc_id=slot.npc_id,
            mode=slot.mode,
            profile_id=profile_id,
            patient_id=slot.state.patient_id,
            encounter_id=slot.state.encounter_id,
            visit_state=slot.state.visit_state,
            patient_lifecycle_state=slot.state.patient_lifecycle_state,
            phase=slot.state.phase,
            status=slot.state.status,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue=slot.state.current_dialogue,
            last_action=slot.state.last_action,
            last_error=slot.state.last_error,
            step_count=slot.state.step_count,
            finished=slot.state.finished,
            case_summary=case_summary,
        )

    def _sync_runtime_for_slot(self, slot: _PatientSlot) -> None:
        if not self._department_runtime_service:
            return
        current_dialogue = slot.state.current_dialogue
        if hasattr(current_dialogue, "model_dump"):
            current_dialogue_payload = current_dialogue.model_dump()
        else:
            current_dialogue_payload = current_dialogue or {}
        self._department_runtime_service.sync_patient_runtime(
            patient_id=slot.state.patient_id,
            visit_id=slot.state.encounter_id,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue_preview=current_dialogue_payload.get("message"),
            last_transition_action=slot.state.last_action,
            transition_version=now_iso(),
        )
