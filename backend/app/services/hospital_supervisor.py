from __future__ import annotations

import json
import random
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
from app.services.department_assignment import resolve_assigned_department_for_visit
from app.services.patient_flow_engine import FlowDecisionEngine, FlowExecutor


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


StateLike = NpcPatientDebugState | PatientAgentDebugState


@dataclass
class _PatientSlot:
    npc_id: str
    mode: MultiPatientMode
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


class HospitalSupervisor:
    """Engine-driven hospital-wide scheduler used by both debug and runtime snapshots."""

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
        self._department_ids = [item["id"] for item in list_departments(include_legacy=False)]
        self._round_robin_index = 0

        self._supervisor_mode = "engine_driven"
        self._fairness_policy = "oldest_due_first"
        self._node_capacities = self._build_node_capacities()
        self._node_step_delays = {
            "testing": 1.0,
            "payment": 0.5,
            "pharmacy": 0.5,
        }

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
            self._dispatch_count = 0
            self._blocked_count = 0
            self._last_error = None
            self._last_spawn_at = None
            self._last_tick_at = None
            self._next_spawn_at = None
            self._llm_probability = None
            if self._department_runtime_service:
                self._department_runtime_service.clear_all()
        return self.get_snapshot()

    def get_snapshot(self) -> MultiPatientDebugSnapshot:
        with self._lock:
            patients = [self._to_patient_snapshot(slot) for slot in self._slots]
            active_count = sum(1 for slot in self._slots if not slot.state.finished)
            active_by_department: dict[str, int] = {}
            for slot in self._slots:
                if slot.state.finished or not slot.assigned_department_id:
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
                department_coverage=dict(self._spawned_by_department),
                active_by_department=active_by_department,
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
        active_slots = [slot for slot in self._slots if not slot.state.finished]
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

    def _spawn_slot(self, npc_id: str) -> _PatientSlot:
        now = now_utc()
        target_department_id = self._next_department_for_spawn()
        if self._mode == "legacy_template":
            llm_mode = "offline"
            profile_pool = list_profiles(target_department_id) or list_profiles()
            profile = random.choice(profile_pool)
            state = self._legacy_runner.spawn(profile)
            state.npc_id = npc_id
            slot = _PatientSlot(
                npc_id=npc_id,
                mode="legacy_template",
                llm_mode=llm_mode,
                llm_sampled_probability=None,
                state=state,
                profile=profile,
                next_step_at=now + timedelta(seconds=self._step_interval_seconds),
            )
            self._assign_slot_department(slot, profile.target_department_id, profile.target_department_name)
            return slot

        if self._mode == "legacy_probabilistic_llm":
            sampled_probability = float(self._llm_probability or 0.0)
            llm_mode = "online" if random.random() < sampled_probability else "offline"
            profile_pool = list_profiles(target_department_id) or list_profiles()
            profile = random.choice(profile_pool)
            state = self._legacy_runner.spawn(profile)
            state.npc_id = npc_id
            slot = _PatientSlot(
                npc_id=npc_id,
                mode="legacy_probabilistic_llm",
                llm_mode=llm_mode,
                llm_sampled_probability=sampled_probability,
                state=state,
                profile=profile,
                next_step_at=now + timedelta(seconds=self._step_interval_seconds),
            )
            self._assign_slot_department(slot, profile.target_department_id, profile.target_department_name)
            return slot

        if self._mode == "department_mixed" and target_department_id != "internal":
            profile_pool = list_profiles(target_department_id) or list_profiles()
            profile = random.choice(profile_pool)
            state = self._legacy_runner.spawn(profile)
            state.npc_id = npc_id
            slot = _PatientSlot(
                npc_id=npc_id,
                mode="legacy_template",
                llm_mode="online",
                llm_sampled_probability=None,
                state=state,
                profile=profile,
                next_step_at=now + timedelta(seconds=self._step_interval_seconds),
            )
            self._assign_slot_department(slot, profile.target_department_id, profile.target_department_name)
            return slot

        state = self._intelligent_runner.spawn(seed=f"{npc_id}-{target_department_id}-{random.randint(1000, 9999)}")
        state.npc_id = npc_id
        assigned_department_name = self._department_name(target_department_id)
        slot = _PatientSlot(
            npc_id=npc_id,
            mode="intelligent_agent",
            llm_mode="online",
            llm_sampled_probability=None,
            state=state,
            profile=None,
            next_step_at=now + timedelta(seconds=self._step_interval_seconds),
        )
        self._assign_slot_department(slot, target_department_id, assigned_department_name)
        return slot

    def _step_due_patients(self) -> None:
        now = now_utc()
        due_slots = [slot for slot in self._slots if not slot.state.finished and now >= slot.next_step_at]
        due_slots.sort(
            key=lambda slot: (
                slot.next_step_at,
                slot.last_step_at or datetime.fromtimestamp(0, tz=timezone.utc),
                slot.state.step_count,
                slot.npc_id,
            )
        )
        dispatch_budget: dict[str, int] = {}
        for slot in due_slots:
            try:
                node_id = self._decide_and_step(slot, dispatch_budget, now)
                slot.last_step_at = now
                slot.current_node_id = node_id
            except Exception as exc:
                slot.state.last_error = self._format_exception(exc)
                slot.state.status = "error"
                slot.state.finished = True
                self._last_error = self._format_exception(exc)
            self._sync_runtime_for_slot(slot)

    def _decide_and_step(self, slot: _PatientSlot, dispatch_budget: dict[str, int], now: datetime) -> str | None:
        if slot.mode == "legacy_template":
            if slot.profile is None:
                raise RuntimeError("legacy slot missing profile")
            runner = self._legacy_runner
        else:
            runner = self._intelligent_runner

        visit_row = runner._get_visit_row(slot.state)  # noqa: SLF001
        patient_row = runner.patient_repo.get(slot.state.patient_id)
        assigned_department_id = None
        if visit_row:
            assigned_department_id = resolve_assigned_department_for_visit(visit_row, patient_row)["id"]

        context = runner.build_context(slot.state)
        planned, decision = self._flow_engine.decide_with_plan(
            assigned_department_id=assigned_department_id,
            runner_context=context,
        )
        slot.target_node_id = decision.target_node
        target_node = decision.target_node or assigned_department_id or "internal"
        if not self._can_dispatch_to_node(target_node, dispatch_budget):
            self._blocked_count += 1
            slot.state.status = "waiting_capacity"
            slot.state.last_error = f"node capacity reached: {target_node}"
            slot.next_step_at = now + timedelta(seconds=max(0.5, self._step_interval_seconds / 2))
            return slot.current_node_id or target_node

        if slot.mode == "legacy_template":
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
            slot.next_step_at = now + timedelta(seconds=max(0.5, self._step_interval_seconds / 2))
            return slot.current_node_id or target_node

        dispatch_budget[target_node] = dispatch_budget.get(target_node, 0) + 1
        self._dispatch_count += 1
        slot.state.last_error = None
        slot.next_step_at = now + timedelta(seconds=self._next_delay_for_node(target_node))
        return target_node

    def _can_dispatch_to_node(self, node_id: str, dispatch_budget: dict[str, int]) -> bool:
        capacity = self._node_capacities.get(node_id, self._node_capacities.get("*", 1))
        return dispatch_budget.get(node_id, 0) < capacity

    def _next_delay_for_node(self, node_id: str) -> float:
        return max(0.1, float(self._node_step_delays.get(node_id, self._step_interval_seconds)))

    def _build_node_capacities(self) -> dict[str, int]:
        capacities = {"*": 1, "testing": 2, "payment": 2, "pharmacy": 2}
        for department in list_departments(include_legacy=False):
            capacities[department["id"]] = 1
        return capacities

    def _to_patient_snapshot(self, slot: _PatientSlot) -> MultiPatientDebugPatientSnapshot:
        profile_id = slot.profile.profile_id if slot.profile else None
        case_summary = slot.state.case_summary if isinstance(slot.state, PatientAgentDebugState) else None
        return MultiPatientDebugPatientSnapshot(
            npc_id=slot.npc_id,
            mode=slot.mode,
            llm_mode=slot.llm_mode,
            llm_probability=slot.llm_sampled_probability,
            profile_id=profile_id,
            patient_id=slot.state.patient_id,
            encounter_id=slot.state.encounter_id,
            visit_state=slot.state.visit_state,
            patient_lifecycle_state=slot.state.patient_lifecycle_state,
            assigned_department_id=slot.assigned_department_id,
            assigned_department_name=slot.assigned_department_name,
            phase=slot.state.phase,
            status=slot.state.status,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue=slot.state.current_dialogue,
            last_action=slot.state.last_action,
            last_error=slot.state.last_error,
            step_count=slot.state.step_count,
            finished=slot.state.finished,
            case_summary=case_summary,
            current_node_id=slot.current_node_id,
            target_node_id=slot.target_node_id,
            next_step_at=slot.next_step_at.isoformat(),
        )

    def _assign_slot_department(self, slot: _PatientSlot, department_id: str, department_name: str) -> None:
        slot.assigned_department_id = department_id
        slot.assigned_department_name = department_name
        self._spawned_by_department[department_id] = self._spawned_by_department.get(department_id, 0) + 1
        if slot.state.encounter_id:
            if slot.mode == "legacy_template":
                visit_repo = self._legacy_runner.visit_repo
            else:
                visit_repo = self._intelligent_runner.visit_repo
            visit_repo.update_visit(
                slot.state.encounter_id,
                assigned_department_id=department_id,
                assigned_department_name=department_name,
            )

    def _department_name(self, department_id: str) -> str:
        for item in list_departments(include_legacy=False):
            if item["id"] == department_id:
                return item["label"]
        return "General Medicine"

    def _next_department_for_spawn(self) -> str:
        # First pass guarantees at least one spawned patient for each formal department.
        for department_id in self._department_ids:
            if self._spawned_by_department.get(department_id, 0) == 0:
                return department_id
        if not self._department_ids:
            return "internal"
        department_id = self._department_ids[self._round_robin_index % len(self._department_ids)]
        self._round_robin_index += 1
        return department_id

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
        self._department_runtime_service.sync_patient_runtime(
            patient_id=slot.state.patient_id,
            visit_id=slot.state.encounter_id,
            current_counterparty=slot.state.current_counterparty,
            current_dialogue_preview=current_dialogue_payload.get("message"),
            current_node_id=slot.current_node_id,
            target_node_id=slot.target_node_id,
            last_transition_action=slot.state.last_action,
            transition_version=now_iso(),
        )
