from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.internal_medicine.rules import retrieve_relevant_internal_medicine_rules, rule_based_internal_medicine
from app.agents.interactive_debug.controllers import (
    _BaseAgentDebugController,
    _deep_diff,
    _latest_reply,
    _to_transcript,
)
from app.agents.interactive_debug.presets import get_internal_medicine_presets, get_surgery_presets
from app.agents.surgery.prompts import build_consultation_system_prompt as build_surgery_system_prompt
from app.agents.surgery.rules import retrieve_relevant_surgery_rules, rule_based_surgery
from app.schemas.agent_debug import AgentDebugSnapshot, AgentDebugTrace
from app.schemas.common import PatientLifecycleState, VisitLifecycleState


DoctorPresetLoader = Callable[[], list[dict]]
DoctorPreloadAdapter = Callable[["_BaseDoctorAgentDebugController", "DoctorDebugAgentConfig", dict], dict[str, Any]]
DoctorTraceBuilder = Callable[
    ["_BaseDoctorAgentDebugController", "DoctorDebugAgentConfig", dict, str, str, str, dict, dict, dict, dict],
    dict[str, Any],
]


@dataclass(frozen=True)
class DoctorDebugAgentConfig:
    agent_type: str
    department_id: str
    label: str
    service_container_key: str
    preset_loader: DoctorPresetLoader
    preload_adapter: DoctorPreloadAdapter
    trace_builder: DoctorTraceBuilder
    supports_round2: bool = False
    default_visit_state: str = VisitLifecycleState.IN_CONSULTATION.value
    default_patient_lifecycle_state: str = PatientLifecycleState.IN_CONSULTATION.value


class DoctorDebugRegistry:
    def __init__(self):
        self._configs: dict[str, DoctorDebugAgentConfig] = {}

    def register(self, config: DoctorDebugAgentConfig) -> None:
        self._configs[config.agent_type] = config

    def get(self, agent_type: str) -> DoctorDebugAgentConfig:
        config = self._configs.get(agent_type)
        if config is None:
            raise KeyError(agent_type)
        return config

    def list_available(self) -> list[DoctorDebugAgentConfig]:
        return list(self._configs.values())


class _BaseDoctorAgentDebugController(_BaseAgentDebugController):
    agent_type = "doctor"

    def __init__(self, deps: dict, registry: DoctorDebugRegistry):
        super().__init__(deps)
        self.registry = registry
        self._current_by_agent: dict[str, dict[str, Any]] = {}
        for config in registry.list_available():
            if config.service_container_key in deps:
                setattr(self, config.service_container_key, deps[config.service_container_key])

    def list_registered_agents(self) -> list[DoctorDebugAgentConfig]:
        return self.registry.list_available()

    def list_available_agents(self) -> list[dict[str, Any]]:
        available = []
        for config in self.registry.list_available():
            if self._get_service(config) is None:
                continue
            available.append(
                {
                    "agent_type": config.agent_type,
                    "department_id": config.department_id,
                    "label": config.label,
                }
            )
        return available

    def get_presets(self, agent_type: str) -> list[dict]:
        return deepcopy(self.registry.get(agent_type).preset_loader())

    def preload(self, agent_type: str, *, preset_id: str | None = None, payload: dict | None = None) -> AgentDebugSnapshot:
        config = self.registry.get(agent_type)
        self._require_service(config)
        resolved = self._resolve_payload(config, preset_id=preset_id, payload=payload)
        current = self._apply_preload(config, deepcopy(resolved))
        self._current_by_agent[agent_type] = current
        return self._build_snapshot_for(config, current)

    def message(self, agent_type: str, message: str) -> AgentDebugSnapshot:
        config = self.registry.get(agent_type)
        current = self._current_by_agent.get(agent_type)
        if not current:
            raise LookupError("debug session not found")
        self._handle_message(config, current, message)
        return self._build_snapshot_for(config, current)

    def get_snapshot(self, agent_type: str) -> AgentDebugSnapshot | None:
        current = self._current_by_agent.get(agent_type)
        if not current:
            return None
        return self._build_snapshot_for(self.registry.get(agent_type), current)

    def reset(self, agent_type: str) -> None:
        self._current_by_agent.pop(agent_type, None)

    def _resolve_payload(self, config: DoctorDebugAgentConfig, *, preset_id: str | None, payload: dict | None) -> dict:
        if payload:
            return deepcopy(payload)
        presets = self.get_presets(config.agent_type)
        if preset_id:
            for preset in presets:
                if preset["preset_id"] == preset_id:
                    return deepcopy(preset["payload"])
            raise KeyError(preset_id)
        if not presets:
            raise KeyError("no presets configured")
        return deepcopy(presets[0]["payload"])

    def _apply_preload(self, config: DoctorDebugAgentConfig, payload: dict) -> dict[str, Any]:
        service = self._require_service(config)
        preload_plan = config.preload_adapter(self, config, payload)
        debug_session_id, patient_id, session_id = self._seed_patient_visit(
            payload,
            visit_state=str(preload_plan["visit_state"]),
            patient_state=str(preload_plan["patient_state"]),
            active_agent_type=config.agent_type,
            visit_data=preload_plan.get("visit_data"),
        )
        visit = self.visit_repo.get_active_by_patient(patient_id)
        assert visit is not None
        self._save_shared_memory_from_payload(patient_id=patient_id, payload=payload)
        self._save_medical_record_entries(
            patient_id=patient_id,
            visit_id=visit["id"],
            entries=list(preload_plan.get("medical_record_entries") or []),
        )
        before_memory: dict[str, Any] = {}
        response = service.create_session(
            {
                "patient_id": patient_id,
                "visit_id": visit["id"],
                "session_id": session_id,
                "name": payload.get("patient_profile", {}).get("name") or patient_id,
                "age": payload.get("patient_profile", {}).get("age"),
                "sex": payload.get("patient_profile", {}).get("sex"),
                "allergies": payload.get("patient_profile", {}).get("allergies") or [],
                "chronic_conditions": payload.get("patient_profile", {}).get("chronic_conditions") or [],
                "chief_complaint": payload.get("chief_complaint") or "",
                "symptoms": payload.get("symptoms") or "",
                "onset_time": payload.get("onset_time"),
                "vitals": payload.get("vitals") or {},
                **dict(preload_plan.get("request_overrides") or {}),
            }
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, payload.get("patient_profile", {}).get("name") or patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=config.agent_type)
        trace = config.trace_builder(
            self,
            config,
            payload,
            patient_id,
            visit["id"],
            session_id,
            before_memory,
            after_memory,
            response,
            private_memory,
        )
        return {
            "debug_session_id": debug_session_id,
            "agent_type": config.agent_type,
            "department_id": config.department_id,
            "agent_label": config.label,
            "patient_id": patient_id,
            "visit_id": visit["id"],
            "session_id": session_id,
            "preload_summary": preload_plan.get("preload_summary") or {},
            "trace": trace,
            "last_error": None,
        }

    def _handle_message(self, config: DoctorDebugAgentConfig, current: dict[str, Any], message: str) -> None:
        service = self._require_service(config)
        patient_id = current["patient_id"]
        session_id = current["session_id"]
        visit_id = current["visit_id"]
        before_memory = deepcopy(self.memory_repo.get_shared_memory(patient_id, patient_id))
        response = service.continue_session(
            session_id,
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "message": message,
                "name": self.patient_repo.get(patient_id)["name"],
            },
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type=config.agent_type)
        payload = {
            "message": message,
            "patient_profile": {"name": self.patient_repo.get(patient_id)["name"]},
        }
        current["trace"] = config.trace_builder(
            self,
            config,
            payload,
            patient_id,
            visit_id,
            session_id,
            before_memory,
            after_memory,
            response,
            private_memory,
        )
        current["last_error"] = None

    def _build_snapshot_for(self, config: DoctorDebugAgentConfig, current: dict[str, Any]) -> AgentDebugSnapshot:
        visit = self.visit_repo.get(current["visit_id"])
        patient = self.patient_repo.get(current["patient_id"])
        turns = self.session_repo.list_turns(current["session_id"], limit=200)
        timeline = self.medical_record_repo.get_visit_timeline(current["visit_id"])
        return AgentDebugSnapshot(
            debug_session_id=current["debug_session_id"],
            agent_type=config.agent_type,
            department_id=config.department_id,
            agent_label=config.label,
            patient_id=current["patient_id"],
            visit_id=current["visit_id"],
            session_id=current["session_id"],
            visit_state=visit.get("state") if visit else None,
            patient_lifecycle_state=patient.get("lifecycle_state") if patient else None,
            preload_summary=current.get("preload_summary") or {},
            transcript=_to_transcript(turns),
            latest_reply=_latest_reply(turns),
            trace=AgentDebugTrace.model_validate(current.get("trace") or {}),
            medical_record_summary=(timeline or {}).get("summary"),
            last_error=current.get("last_error"),
        )

    def _get_service(self, config: DoctorDebugAgentConfig):
        return self.__dict__.get(config.service_container_key) or getattr(self, config.service_container_key, None)

    def _require_service(self, config: DoctorDebugAgentConfig):
        service = self._get_service(config)
        if service is None:
            raise RuntimeError(f"debug service unavailable for agent '{config.agent_type}'")
        return service


class DoctorAgentDebugController(_BaseDoctorAgentDebugController):
    pass


class FixedDoctorDebugController:
    def __init__(self, doctor_controller: DoctorAgentDebugController, agent_type: str):
        self.doctor_controller = doctor_controller
        self.fixed_agent_type = agent_type

    def get_presets(self) -> list[dict]:
        return self.doctor_controller.get_presets(self.fixed_agent_type)

    def preload(self, *, preset_id: str | None = None, payload: dict | None = None) -> AgentDebugSnapshot:
        return self.doctor_controller.preload(self.fixed_agent_type, preset_id=preset_id, payload=payload)

    def message(self, message: str) -> AgentDebugSnapshot:
        return self.doctor_controller.message(self.fixed_agent_type, message)

    def get_snapshot(self) -> AgentDebugSnapshot | None:
        return self.doctor_controller.get_snapshot(self.fixed_agent_type)

    def reset(self) -> None:
        self.doctor_controller.reset(self.fixed_agent_type)


def _default_doctor_preload_adapter(
    controller: _BaseDoctorAgentDebugController,
    config: DoctorDebugAgentConfig,
    payload: dict,
) -> dict[str, Any]:
    del controller
    visit_state = payload.get("visit_state") or config.default_visit_state
    patient_state = payload.get("patient_lifecycle_state") or config.default_patient_lifecycle_state
    return {
        "visit_state": visit_state,
        "patient_state": patient_state,
        "visit_data": {},
        "medical_record_entries": payload.get("medical_record_entries") or [],
        "request_overrides": {},
        "preload_summary": {
            "chief_complaint": payload.get("chief_complaint"),
            "consultation_round": payload.get("consultation_round") or 1,
            "visit_state": visit_state,
        },
    }


def _internal_medicine_preload_adapter(
    controller: _BaseDoctorAgentDebugController,
    config: DoctorDebugAgentConfig,
    payload: dict,
) -> dict[str, Any]:
    plan = _default_doctor_preload_adapter(controller, config, payload)
    if payload.get("simulated_report"):
        plan["visit_data"] = {"simulated_report": deepcopy(payload["simulated_report"])}
    plan["request_overrides"] = {"debug_read_historical_records": True}
    return plan


def _build_internal_medicine_trace(
    controller: _BaseDoctorAgentDebugController,
    config: DoctorDebugAgentConfig,
    payload: dict,
    patient_id: str,
    visit_id: str,
    session_id: str,
    before_memory: dict,
    after_memory: dict,
    response: dict,
    private_memory: dict,
) -> dict[str, Any]:
    service = controller._require_service(config)
    merged_payload = service.build_merged_payload(
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "name": controller.patient_repo.get(patient_id)["name"],
            "message": payload.get("message") or "",
            "chief_complaint": payload.get("chief_complaint"),
            "symptoms": payload.get("symptoms"),
            "onset_time": payload.get("onset_time"),
            "vitals": payload.get("vitals") or {},
            "allergies": payload.get("patient_profile", {}).get("allergies") or [],
            "chronic_conditions": payload.get("patient_profile", {}).get("chronic_conditions") or [],
        },
        after_memory,
        private_memory,
    )
    rules = retrieve_relevant_internal_medicine_rules(merged_payload, top_k=3)
    fallback = rule_based_internal_medicine(merged_payload)
    messages = service.build_consultation_llm_messages(
        merged_payload,
        after_memory,
        (response.get("dialogue") or {}).get("missing_fields") or [],
        historical_records_template=merged_payload.get("historical_records_template"),
        previous_final_result=private_memory.get("final_result") if isinstance(private_memory.get("final_result"), dict) else {},
        post_final_reassessment=bool((response.get("dialogue") or {}).get("message_type") in {"final_update", "final_no_change"}),
    )
    dialogue = response.get("dialogue") or {}
    return {
        "merged_payload": merged_payload,
        "system_prompt": messages[0].get("content") if len(messages) > 1 else None,
        "user_prompt": messages[-1].get("content") if messages else None,
        "rag_query": {
            "chief_complaint": merged_payload.get("chief_complaint"),
            "symptoms": merged_payload.get("symptoms"),
            "historical_records": bool(merged_payload.get("historical_records_template")),
            "simulated_report": merged_payload.get("simulated_report"),
        },
        "rag_hits": rules,
        "parsed_result": {
            "final_result": dialogue.get("final_result") or {},
            "missing_fields": list(dialogue.get("missing_fields") or []),
            "question_focus": dialogue.get("question_focus"),
            "message_type": dialogue.get("message_type"),
        },
        "fallback_reason": None if service.llm_settings.get("api_key") else "llm_unavailable",
        "memory_delta": {
            "shared_memory": _deep_diff(before_memory, after_memory),
        },
        "extra": {
            "historical_records_template": private_memory.get("historical_records_template") or {},
            "fallback_result": fallback,
        },
    }


def _build_surgery_trace(
    controller: _BaseDoctorAgentDebugController,
    config: DoctorDebugAgentConfig,
    payload: dict,
    patient_id: str,
    visit_id: str,
    session_id: str,
    before_memory: dict,
    after_memory: dict,
    response: dict,
    private_memory: dict,
) -> dict[str, Any]:
    service = controller._require_service(config)
    merged_payload = service.build_merged_payload(
        {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "name": controller.patient_repo.get(patient_id)["name"],
            "message": payload.get("message") or "",
            "chief_complaint": payload.get("chief_complaint"),
            "symptoms": payload.get("symptoms"),
            "onset_time": payload.get("onset_time"),
            "vitals": payload.get("vitals") or {},
            "allergies": payload.get("patient_profile", {}).get("allergies") or [],
            "chronic_conditions": payload.get("patient_profile", {}).get("chronic_conditions") or [],
        },
        after_memory,
        private_memory,
    )
    rules = retrieve_relevant_surgery_rules(merged_payload, top_k=3)
    fallback = rule_based_surgery(merged_payload)
    messages = service.build_consultation_llm_messages(
        merged_payload,
        after_memory,
        (response.get("dialogue") or {}).get("missing_fields") or [],
        historical_records_template=merged_payload.get("historical_records_template"),
        previous_final_result=private_memory.get("final_result") if isinstance(private_memory.get("final_result"), dict) else {},
        post_final_reassessment=bool((response.get("dialogue") or {}).get("message_type") in {"final_update", "final_no_change"}),
    )
    dialogue = response.get("dialogue") or {}
    return {
        "merged_payload": merged_payload,
        "system_prompt": messages[0].get("content") if len(messages) > 1 else build_surgery_system_prompt(),
        "user_prompt": messages[-1].get("content") if messages else None,
        "rag_query": {
            "chief_complaint": merged_payload.get("chief_complaint"),
            "symptoms": merged_payload.get("symptoms"),
            "historical_records": bool(merged_payload.get("historical_records_template")),
            "simulated_report": merged_payload.get("simulated_report"),
        },
        "rag_hits": rules,
        "parsed_result": {
            "final_result": dialogue.get("final_result") or {},
            "missing_fields": list(dialogue.get("missing_fields") or []),
            "question_focus": dialogue.get("question_focus"),
            "message_type": dialogue.get("message_type"),
        },
        "fallback_reason": None if service.llm_settings.get("api_key") else "llm_unavailable",
        "memory_delta": {
            "shared_memory": _deep_diff(before_memory, after_memory),
        },
        "extra": {
            "historical_records_template": private_memory.get("historical_records_template") or {},
            "fallback_result": fallback,
        },
    }


def build_default_doctor_debug_registry() -> DoctorDebugRegistry:
    registry = DoctorDebugRegistry()
    registry.register(
        DoctorDebugAgentConfig(
            agent_type="internal_medicine",
            department_id="internal",
            label="Internal Medicine Agent Debug",
            service_container_key="internal_medicine_service",
            preset_loader=get_internal_medicine_presets,
            preload_adapter=_internal_medicine_preload_adapter,
            trace_builder=_build_internal_medicine_trace,
            supports_round2=True,
        )
    )
    registry.register(
        DoctorDebugAgentConfig(
            agent_type="surgery",
            department_id="surgery",
            label="Surgery Agent Debug",
            service_container_key="surgery_service",
            preset_loader=get_surgery_presets,
            preload_adapter=_default_doctor_preload_adapter,
            trace_builder=_build_surgery_trace,
            supports_round2=False,
        )
    )
    return registry
