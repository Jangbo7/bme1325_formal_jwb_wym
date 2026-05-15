from __future__ import annotations

from app.agents.npc_patient.profile import get_profile
from app.agents.npc_patient.runner import NpcPatientRunner
from app.schemas.npc_debug import NpcDebugSnapshot


class NpcPatientDebugController:
    def __init__(self, container: dict):
        self.runner = NpcPatientRunner(container)
        self.medical_record_repo = container.get("medical_record_repo")
        self._active_state = None

    def spawn(self, profile_id: str) -> NpcDebugSnapshot:
        if self._active_state is not None:
            raise RuntimeError("npc debug session already active")
        profile = get_profile(profile_id)
        self._active_state = self.runner.spawn(profile)
        return self._active_state.to_snapshot()

    def step(self) -> NpcDebugSnapshot:
        if self._active_state is None:
            raise LookupError("npc debug session not found")
        profile = get_profile(self._active_state.profile_id)
        try:
            self.runner.step(self._active_state, profile)
        except Exception as exc:
            self._active_state.last_error = str(exc)
            raise
        return self._active_state.to_snapshot()

    def get_snapshot(self) -> NpcDebugSnapshot | None:
        if self._active_state is None:
            return None
        return self._active_state.to_snapshot()

    def reset(self) -> None:
        self._active_state = None

    def get_medical_record(self) -> dict | None:
        if self._active_state is None or not self._active_state.encounter_id or not self.medical_record_repo:
            return None
        return self.medical_record_repo.get_visit_timeline(self._active_state.encounter_id)
