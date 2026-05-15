from __future__ import annotations

from app.agents.patient_agent.runner import PatientAgentDebugRunner
from app.schemas.patient_agent_debug import PatientAgentDebugSnapshot


class PatientAgentDebugController:
    def __init__(self, container: dict):
        self.runner = PatientAgentDebugRunner(container)
        self.medical_record_repo = container.get("medical_record_repo")
        self._active_state = None

    def spawn(self, seed: str | None = None) -> PatientAgentDebugSnapshot:
        if self._active_state is not None:
            raise RuntimeError("patient agent debug session already active")
        self._active_state = self.runner.spawn(seed=seed)
        return self._active_state.to_snapshot()

    def step(self) -> PatientAgentDebugSnapshot:
        if self._active_state is None:
            raise LookupError("patient agent debug session not found")
        self.runner.step(self._active_state)
        return self._active_state.to_snapshot()

    def get_snapshot(self) -> PatientAgentDebugSnapshot | None:
        if self._active_state is None:
            return None
        return self._active_state.to_snapshot()

    def reset(self) -> None:
        self._active_state = None

    def get_medical_record(self) -> dict | None:
        if self._active_state is None or not self._active_state.encounter_id or not self.medical_record_repo:
            return None
        return self.medical_record_repo.get_visit_timeline(self._active_state.encounter_id)
