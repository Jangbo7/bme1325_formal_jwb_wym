from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.agents.internal_medicine.prompts import build_consultation_system_prompt, build_consultation_user_prompt
from app.agents.internal_medicine.rules import retrieve_relevant_internal_medicine_rules, rule_based_internal_medicine
from app.agents.patient_agent.prompt_builder import build_reply_messages
from app.agents.patient_agent.schemas import PatientCaseCard, PatientReplyContext
from app.agents.triage.prompts import build_follow_up_system_prompt, build_follow_up_user_prompt
from app.agents.triage.rules import retrieve_relevant_rules, rule_based_triage
from app.agents.interactive_debug.presets import (
    get_internal_medicine_presets,
    get_patient_agent_presets,
    get_triage_presets,
)
from app.schemas.agent_debug import AgentDebugReply, AgentDebugSnapshot, AgentDebugTrace, AgentDebugTranscriptEntry
from app.schemas.common import PatientLifecycleState, TriageDialogueState, VisitLifecycleState
from app.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_diff(before: Any, after: Any) -> dict[str, Any]:
    if before == after:
        return {}
    if isinstance(before, dict) and isinstance(after, dict):
        diff: dict[str, Any] = {}
        keys = sorted(set(before.keys()) | set(after.keys()))
        for key in keys:
            child = _deep_diff(before.get(key), after.get(key))
            if child != {}:
                diff[key] = child
        return diff
    return {"before": before, "after": after}


def _to_transcript(turns: list[dict]) -> list[AgentDebugTranscriptEntry]:
    return [
        AgentDebugTranscriptEntry(
            role=str(turn.get("role") or ""),
            content=str(turn.get("content") or ""),
            timestamp=turn.get("timestamp"),
            metadata=turn.get("metadata") or {},
        )
        for turn in turns
    ]


def _latest_reply(turns: list[dict]) -> AgentDebugReply | None:
    for turn in reversed(turns):
        if turn.get("role") == "assistant":
            return AgentDebugReply(
                role="assistant",
                content=str(turn.get("content") or ""),
                timestamp=turn.get("timestamp"),
            )
    return None


class _BaseAgentDebugController:
    agent_type: str

    def __init__(self, deps: dict):
        self.patient_repo = deps["patient_repo"]
        self.session_repo = deps["session_repo"]
        self.memory_repo = deps["memory_repo"]
        self.visit_repo = deps["visit_repo"]
        self.medical_record_repo = deps["medical_record_repo"]
        self.patient_agent_case_repo = deps.get("patient_agent_case_repo")
        self.triage_service = deps.get("triage_service")
        self.internal_medicine_service = deps.get("internal_medicine_service")
        self.patient_agent_service = deps.get("patient_agent_service")
        self._current: dict[str, Any] | None = None

    def reset(self) -> None:
        self._current = None

    def get_snapshot(self) -> AgentDebugSnapshot | None:
        if not self._current:
            return None
        return self._build_snapshot()

    def get_presets(self) -> list[dict]:
        raise NotImplementedError

    def preload(self, *, preset_id: str | None = None, payload: dict | None = None) -> AgentDebugSnapshot:
        resolved = self._resolve_payload(preset_id=preset_id, payload=payload)
        self._current = self._apply_preload(deepcopy(resolved))
        return self._build_snapshot()

    def message(self, message: str) -> AgentDebugSnapshot:
        if not self._current:
            raise LookupError("debug session not found")
        self._handle_message(message)
        return self._build_snapshot()

    def _resolve_payload(self, *, preset_id: str | None, payload: dict | None) -> dict:
        if payload:
            return deepcopy(payload)
        if preset_id:
            for preset in self.get_presets():
                if preset["preset_id"] == preset_id:
                    return deepcopy(preset["payload"])
            raise KeyError(preset_id)
        presets = self.get_presets()
        if not presets:
            raise KeyError("no presets configured")
        return deepcopy(presets[0]["payload"])

    def _new_ids(self) -> tuple[str, str, str]:
        token = uuid.uuid4().hex[:8]
        return (
            f"DBG-{self.agent_type}-{token}",
            f"P-{token.upper()}",
            f"{self.agent_type}-session-{token}",
        )

    def _seed_patient_visit(self, payload: dict, *, visit_state: str, patient_state: str, active_agent_type: str | None, visit_data: dict | None = None) -> tuple[str, str, str]:
        debug_session_id, patient_id, session_id = self._new_ids()
        profile = payload.get("patient_profile") or {}
        name = profile.get("name") or patient_id
        self.patient_repo.upsert_basic(patient_id, name)
        visit = self.visit_repo.create(
            patient_id=patient_id,
            state=VisitLifecycleState(visit_state),
            current_node=self._node_for_visit_state(visit_state),
            current_department=self._department_for_visit_state(visit_state),
            active_agent_type=active_agent_type,
            data=visit_data or {},
        )
        self.patient_repo.update_patient(
            patient_id,
            name=name,
            lifecycle_state=patient_state,
            location=self._department_for_visit_state(visit_state) or "Lobby",
            visit_id=visit["id"],
            session_id=session_id,
        )
        return debug_session_id, patient_id, session_id

    @staticmethod
    def _node_for_visit_state(visit_state: str) -> str:
        mapping = {
            VisitLifecycleState.IN_CONSULTATION.value: "consultation",
            VisitLifecycleState.IN_SECOND_CONSULTATION.value: "consultation",
            VisitLifecycleState.WAITING_TEST.value: "diagnostic_wait",
            VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value: "outpatient_procedure_wait",
            VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value: "outpatient_procedure_room",
            VisitLifecycleState.RESULTS_READY.value: "results_ready",
            VisitLifecycleState.ARRIVED.value: "lobby",
            VisitLifecycleState.TRIAGING.value: "triage",
        }
        return mapping.get(visit_state, "debug")

    @staticmethod
    def _department_for_visit_state(visit_state: str) -> str | None:
        mapping = {
            VisitLifecycleState.IN_CONSULTATION.value: "Consultation",
            VisitLifecycleState.IN_SECOND_CONSULTATION.value: "Consultation",
            VisitLifecycleState.WAITING_TEST.value: "Auxiliary Diagnostic Center",
            VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value: "Outpatient Procedure",
            VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value: "Outpatient Procedure",
            VisitLifecycleState.RESULTS_READY.value: "Auxiliary Diagnostic Center",
            VisitLifecycleState.TRIAGING.value: "Triage",
            VisitLifecycleState.ARRIVED.value: "Lobby",
        }
        return mapping.get(visit_state)

    def _save_shared_memory_from_payload(self, *, patient_id: str, payload: dict) -> None:
        shared_memory = deepcopy(payload.get("shared_memory") or {})
        shared_memory["patient_id"] = patient_id
        profile = shared_memory.setdefault("profile", {})
        patient_profile = payload.get("patient_profile") or {}
        profile.setdefault("name", patient_profile.get("name") or patient_id)
        profile.setdefault("age", patient_profile.get("age"))
        profile.setdefault("sex", patient_profile.get("sex"))
        profile.setdefault("allergies", list(patient_profile.get("allergies") or []))
        profile.setdefault("allergy_status", "known" if patient_profile.get("allergies") is not None else "unknown")
        profile.setdefault("chronic_conditions", list(patient_profile.get("chronic_conditions") or []))
        profile.setdefault("baseline_risk_flags", [])
        clinical = shared_memory.setdefault("clinical_memory", {})
        clinical.setdefault("chief_complaint", payload.get("chief_complaint") or "")
        symptom_text = payload.get("symptoms") or ""
        if isinstance(symptom_text, str):
            symptoms = [part.strip() for part in symptom_text.split(",") if part.strip()]
        else:
            symptoms = list(symptom_text or [])
        clinical.setdefault("symptoms", symptoms)
        clinical.setdefault("onset_time", payload.get("onset_time"))
        clinical.setdefault("vitals", deepcopy(payload.get("vitals") or {}))
        clinical.setdefault("risk_flags", [])
        clinical.setdefault("last_department", None)
        clinical.setdefault("last_triage_level", None)
        self.memory_repo.save_shared_memory(patient_id, shared_memory)

    def _save_medical_record_entries(self, *, patient_id: str, visit_id: str, entries: list[dict]) -> None:
        for entry in entries:
            self.medical_record_repo.append_entry(
                patient_id=patient_id,
                visit_id=visit_id,
                phase=entry["phase"],
                entry_type=entry["entry_type"],
                actor=entry.get("actor") or "system",
                title=entry["title"],
                content_text=entry["content_text"],
                content=entry.get("content") or {},
            )

    def _build_snapshot(self) -> AgentDebugSnapshot:
        assert self._current is not None
        visit = self.visit_repo.get(self._current["visit_id"])
        patient = self.patient_repo.get(self._current["patient_id"])
        turns = self.session_repo.list_turns(self._current["session_id"], limit=200)
        timeline = self.medical_record_repo.get_visit_timeline(self._current["visit_id"])
        return AgentDebugSnapshot(
            debug_session_id=self._current["debug_session_id"],
            agent_type=self.agent_type,  # type: ignore[arg-type]
            patient_id=self._current["patient_id"],
            visit_id=self._current["visit_id"],
            session_id=self._current["session_id"],
            visit_state=visit.get("state") if visit else None,
            patient_lifecycle_state=patient.get("lifecycle_state") if patient else None,
            preload_summary=self._current.get("preload_summary") or {},
            transcript=_to_transcript(turns),
            latest_reply=_latest_reply(turns),
            trace=AgentDebugTrace.model_validate(self._current.get("trace") or {}),
            medical_record_summary=(timeline or {}).get("summary"),
            last_error=self._current.get("last_error"),
        )


class TriageAgentDebugController(_BaseAgentDebugController):
    agent_type = "triage"

    def get_presets(self) -> list[dict]:
        return get_triage_presets()

    def _apply_preload(self, payload: dict) -> dict:
        debug_session_id, patient_id, session_id = self._seed_patient_visit(
            payload,
            visit_state=VisitLifecycleState.ARRIVED.value,
            patient_state=PatientLifecycleState.UNTRIAGED.value,
            active_agent_type=None,
        )
        visit = self.visit_repo.get_active_by_patient(patient_id)
        assert visit is not None
        self._save_shared_memory_from_payload(patient_id=patient_id, payload=payload)
        before_memory = {}
        response = self.triage_service.create_session(
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
            }
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, payload.get("patient_profile", {}).get("name") or patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="triage")
        trace = self._build_trace(
            payload=payload,
            patient_id=patient_id,
            visit_id=visit["id"],
            session_id=session_id,
            before_memory=before_memory,
            after_memory=after_memory,
            response=response,
            private_memory=private_memory,
        )
        return {
            "debug_session_id": debug_session_id,
            "patient_id": patient_id,
            "visit_id": visit["id"],
            "session_id": session_id,
            "preload_summary": {
                "preset_label": payload.get("patient_profile", {}).get("name"),
                "chief_complaint": payload.get("chief_complaint"),
                "symptoms": payload.get("symptoms"),
            },
            "trace": trace,
            "last_error": None,
        }

    def _handle_message(self, message: str) -> None:
        assert self._current is not None
        patient_id = self._current["patient_id"]
        session_id = self._current["session_id"]
        visit_id = self._current["visit_id"]
        before_memory = deepcopy(self.memory_repo.get_shared_memory(patient_id, patient_id))
        response = self.triage_service.continue_session(
            session_id,
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "message": message,
                "name": self.patient_repo.get(patient_id)["name"],
            },
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="triage")
        payload = {
            "chief_complaint": before_memory.get("clinical_memory", {}).get("chief_complaint"),
            "symptoms": message,
            "message": message,
            "patient_profile": {"name": self.patient_repo.get(patient_id)["name"]},
        }
        self._current["trace"] = self._build_trace(
            payload=payload,
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            before_memory=before_memory,
            after_memory=after_memory,
            response=response,
            private_memory=private_memory,
        )
        self._current["last_error"] = None

    def _build_trace(self, *, payload: dict, patient_id: str, visit_id: str, session_id: str, before_memory: dict, after_memory: dict, response, private_memory: dict) -> dict:
        merged_payload = self.triage_service.build_merged_payload(
            {
                "patient_id": patient_id,
                "name": self.patient_repo.get(patient_id)["name"],
                "chief_complaint": payload.get("chief_complaint"),
                "symptoms": payload.get("symptoms"),
                "message": payload.get("message"),
                "onset_time": payload.get("onset_time"),
                "vitals": payload.get("vitals") or {},
                "allergies": payload.get("patient_profile", {}).get("allergies") or [],
                "chronic_conditions": payload.get("patient_profile", {}).get("chronic_conditions") or [],
            },
            after_memory,
        )
        memory_context = self.triage_service.prepare_context(
            {
                "patient_id": patient_id,
                "name": self.patient_repo.get(patient_id)["name"],
                "chief_complaint": payload.get("chief_complaint"),
                "symptoms": payload.get("symptoms"),
                "message": payload.get("message"),
                "onset_time": payload.get("onset_time"),
                "vitals": payload.get("vitals") or {},
                "allergies": payload.get("patient_profile", {}).get("allergies") or [],
                "chronic_conditions": payload.get("patient_profile", {}).get("chronic_conditions") or [],
            },
            session_id,
            TriageDialogueState(self.triage_service.session_repo.get(session_id)["dialogue_state"]),
        )
        # Use repo-backed values for the actual trace payload.
        retrieved_rules = retrieve_relevant_rules(merged_payload, top_k=3)
        fallback = rule_based_triage(merged_payload)
        final_result = {
            "triage_level": (response.get("patient") or {}).get("triage", {}).get("level"),
            "priority": (response.get("patient") or {}).get("priority"),
            "department": (response.get("patient") or {}).get("location"),
            "note": (response.get("patient") or {}).get("triage", {}).get("note"),
        }
        dialogue = response.get("dialogue") or {}
        system_prompt = None
        user_prompt = None
        if dialogue and dialogue.get("message_type") == "followup" and dialogue.get("missing_fields"):
            system_prompt = build_follow_up_system_prompt()
            user_prompt = build_follow_up_user_prompt(
                triage_result=final_result,
                missing_fields=list(dialogue.get("missing_fields") or []),
                patient_summary=after_memory,
                turns=self.session_repo.list_turns(session_id),
                risk_flags=after_memory.get("clinical_memory", {}).get("risk_flags") or [],
                last_question_focus=private_memory.get("last_question_focus"),
                last_question_text=private_memory.get("last_question_text"),
                asked_fields_history=private_memory.get("asked_fields_history") or [],
                recommendation_changed=bool(private_memory.get("recommendation_changed")),
            )
        else:
            triage_messages = self.triage_service.build_triage_llm_messages(merged_payload, retrieved_rules, memory_context)
            system_prompt = triage_messages[0].get("content") if len(triage_messages) > 1 else None
            user_prompt = triage_messages[-1].get("content") if triage_messages else None
        fallback_reason = None
        if not self.triage_service.llm_settings.get("api_key"):
            fallback_reason = "llm_unavailable"
        elif dialogue and dialogue.get("message_type") == "followup":
            fallback_reason = "followup_prompt_path"
        return {
            "merged_payload": merged_payload,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "rag_query": {
                "symptoms": merged_payload.get("symptoms"),
                "chief_complaint": merged_payload.get("chief_complaint"),
                "risk_flags": after_memory.get("clinical_memory", {}).get("risk_flags") or [],
            },
            "rag_hits": retrieved_rules,
            "parsed_result": {
                "triage_result": final_result,
                "dialogue_state": dialogue.get("status"),
                "missing_fields": list(dialogue.get("missing_fields") or []),
                "latest_extraction": private_memory.get("latest_extraction") or {},
            },
            "fallback_reason": fallback_reason,
            "memory_delta": {
                "shared_memory": _deep_diff(before_memory, after_memory),
            },
            "extra": {
                "fallback_result": fallback,
                "question_focus": dialogue.get("question_focus"),
            },
        }


class InternalMedicineAgentDebugController(_BaseAgentDebugController):
    agent_type = "internal_medicine"

    def get_presets(self) -> list[dict]:
        return get_internal_medicine_presets()

    def _apply_preload(self, payload: dict) -> dict:
        visit_state = payload.get("visit_state") or VisitLifecycleState.IN_CONSULTATION.value
        patient_state = payload.get("patient_lifecycle_state") or PatientLifecycleState.IN_CONSULTATION.value
        visit_data = {}
        if payload.get("simulated_report"):
            visit_data["simulated_report"] = deepcopy(payload["simulated_report"])
        debug_session_id, patient_id, session_id = self._seed_patient_visit(
            payload,
            visit_state=visit_state,
            patient_state=patient_state,
            active_agent_type="internal_medicine",
            visit_data=visit_data,
        )
        visit = self.visit_repo.get_active_by_patient(patient_id)
        assert visit is not None
        self._save_shared_memory_from_payload(patient_id=patient_id, payload=payload)
        self._save_medical_record_entries(patient_id=patient_id, visit_id=visit["id"], entries=payload.get("medical_record_entries") or [])
        before_memory = {}
        response = self.internal_medicine_service.create_session(
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
                "debug_read_historical_records": True,
            }
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, payload.get("patient_profile", {}).get("name") or patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="internal_medicine")
        trace = self._build_trace(
            payload=payload,
            patient_id=patient_id,
            visit_id=visit["id"],
            session_id=session_id,
            before_memory=before_memory,
            after_memory=after_memory,
            response=response,
            private_memory=private_memory,
        )
        return {
            "debug_session_id": debug_session_id,
            "patient_id": patient_id,
            "visit_id": visit["id"],
            "session_id": session_id,
            "preload_summary": {
                "chief_complaint": payload.get("chief_complaint"),
                "consultation_round": payload.get("consultation_round") or 1,
                "visit_state": visit_state,
            },
            "trace": trace,
            "last_error": None,
        }

    def _handle_message(self, message: str) -> None:
        assert self._current is not None
        patient_id = self._current["patient_id"]
        session_id = self._current["session_id"]
        visit_id = self._current["visit_id"]
        before_memory = deepcopy(self.memory_repo.get_shared_memory(patient_id, patient_id))
        response = self.internal_medicine_service.continue_session(
            session_id,
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "message": message,
                "name": self.patient_repo.get(patient_id)["name"],
            },
        )
        after_memory = self.memory_repo.get_shared_memory(patient_id, patient_id)
        private_memory = self.memory_repo.get_agent_session_memory(session_id, patient_id, agent_type="internal_medicine")
        payload = {
            "message": message,
            "patient_profile": {"name": self.patient_repo.get(patient_id)["name"]},
        }
        self._current["trace"] = self._build_trace(
            payload=payload,
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            before_memory=before_memory,
            after_memory=after_memory,
            response=response,
            private_memory=private_memory,
        )
        self._current["last_error"] = None

    def _build_trace(self, *, payload: dict, patient_id: str, visit_id: str, session_id: str, before_memory: dict, after_memory: dict, response, private_memory: dict) -> dict:
        merged_payload = self.internal_medicine_service.build_merged_payload(
            {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "name": self.patient_repo.get(patient_id)["name"],
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
        dialogue = response.get("dialogue") or {}
        message_type = dialogue.get("message_type")
        if message_type in {"answer_only", "answer_with_guidance"}:
            messages = self.internal_medicine_service.build_post_final_answer_llm_messages(
                merged_payload,
                after_memory,
                private_memory.get("final_result") if isinstance(private_memory.get("final_result"), dict) else {},
                previous_final_result=private_memory.get("final_result") if isinstance(private_memory.get("final_result"), dict) else {},
                response_mode=dialogue.get("response_mode") or message_type,
                policy_runtime_context=None,
            )
        else:
            messages = self.internal_medicine_service.build_consultation_llm_messages(
                merged_payload,
                after_memory,
                dialogue.get("missing_fields") or [],
                historical_records_template=merged_payload.get("historical_records_template"),
                previous_final_result=private_memory.get("final_result") if isinstance(private_memory.get("final_result"), dict) else {},
                post_final_reassessment=bool(message_type in {"final_update", "final_no_change"}),
            )
        llm_diagnostics = dict(private_memory.get("llm_diagnostics") or {})
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
                "response_mode": dialogue.get("response_mode"),
                "judgment_changed": bool(dialogue.get("judgment_changed", False)),
                "judgment_action": dialogue.get("judgment_action"),
                "answer_source": dialogue.get("answer_source"),
                "llm_response_kind": dialogue.get("llm_response_kind"),
                "update_reason": dialogue.get("update_reason"),
                "result_changed_fields": list(dialogue.get("result_changed_fields") or []),
                "reassessment_intent": dialogue.get("reassessment_intent"),
                "reply_rendering_mode": dialogue.get("reply_rendering_mode"),
            },
            "fallback_reason": llm_diagnostics.get("llm_error") or (None if self.internal_medicine_service.llm_settings.get("api_key") else "llm_unavailable"),
            "llm_attempted": bool(llm_diagnostics.get("llm_attempted")),
            "llm_succeeded": bool(llm_diagnostics.get("llm_succeeded")),
            "llm_error": llm_diagnostics.get("llm_error"),
            "response_source": llm_diagnostics.get("response_source"),
            "response_mode": dialogue.get("response_mode"),
            "judgment_changed": bool(dialogue.get("judgment_changed", False)),
            "judgment_action": dialogue.get("judgment_action"),
            "answer_source": dialogue.get("answer_source"),
            "llm_response_kind": dialogue.get("llm_response_kind"),
            "patient_reply_source": dialogue.get("patient_reply_source"),
            "structured_result": dialogue.get("final_result") or {},
            "patient_reply": dialogue.get("assistant_message"),
            "update_reason": dialogue.get("update_reason"),
            "result_changed_fields": list(dialogue.get("result_changed_fields") or []),
            "reassessment_intent": dialogue.get("reassessment_intent"),
            "reply_rendering_mode": dialogue.get("reply_rendering_mode"),
            "memory_delta": {
                "shared_memory": _deep_diff(before_memory, after_memory),
            },
            "extra": {
                "historical_records_template": private_memory.get("historical_records_template") or {},
                "fallback_result": fallback,
            },
        }


class PatientAgentChatDebugController(_BaseAgentDebugController):
    agent_type = "patient_agent"

    def get_presets(self) -> list[dict]:
        return get_patient_agent_presets()

    def _apply_preload(self, payload: dict) -> dict:
        debug_session_id, patient_id, session_id = self._seed_patient_visit(
            payload,
            visit_state=VisitLifecycleState.IN_CONSULTATION.value,
            patient_state=PatientLifecycleState.IN_CONSULTATION.value,
            active_agent_type=None,
        )
        visit = self.visit_repo.get_active_by_patient(patient_id)
        assert visit is not None
        profile = payload.get("case_card", {}).get("patient_profile") or payload.get("patient_profile") or {}
        self.patient_repo.update_patient(
            patient_id,
            name=profile.get("name") or patient_id,
            visit_id=visit["id"],
            session_id=session_id,
        )
        case_payload = deepcopy(payload.get("case_card") or {})
        case_payload["patient_profile"]["name"] = profile.get("name") or patient_id
        row = self.patient_agent_case_repo.create(
            patient_id=patient_id,
            visit_id=visit["id"],
            mode="intelligent_agent",
            case_payload=case_payload,
            status="active",
        )
        for turn in payload.get("recent_turns") or []:
            self.session_repo.append_turn(
                session_id,
                patient_id,
                turn.get("role") or "assistant",
                turn.get("content") or "",
                turn.get("timestamp") or now_iso(),
                metadata=turn.get("metadata") or {},
            )
        for entry in payload.get("medical_record_excerpt") or []:
            self.medical_record_repo.append_entry(
                patient_id=patient_id,
                visit_id=visit["id"],
                phase=entry.get("phase") or "history",
                entry_type=entry.get("entry_type") or "history_note",
                actor=entry.get("actor") or "system",
                title=entry.get("title") or "Imported Debug Entry",
                content_text=entry.get("content_text") or "",
                content=entry.get("content") or {},
            )
        trace = self._build_trace(
            patient_id=patient_id,
            visit_id=visit["id"],
            session_id=session_id,
            payload=payload,
            case_payload=case_payload,
            before_turns=[],
        )
        return {
            "debug_session_id": debug_session_id,
            "patient_id": patient_id,
            "visit_id": visit["id"],
            "session_id": session_id,
            "case_id": row["id"],
            "phase": payload.get("phase") or "internal_medicine_round1",
            "preload_summary": {
                "phase": payload.get("phase") or "internal_medicine_round1",
                "case_id": case_payload.get("case_id"),
                "chief_complaint": case_payload.get("chief_complaint"),
            },
            "trace": trace,
            "last_error": None,
        }

    def _handle_message(self, message: str) -> None:
        assert self._current is not None
        patient_id = self._current["patient_id"]
        visit_id = self._current["visit_id"]
        session_id = self._current["session_id"]
        before_turns = self.session_repo.list_turns(session_id, limit=200)
        self.session_repo.append_turn(session_id, patient_id, "user", message, now_iso(), metadata={"speaker": "clinician"})
        reply = self.patient_agent_service.build_patient_reply(
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            phase=self._current.get("phase") or "internal_medicine_round1",
            recent_question=message,
        )
        self.session_repo.append_turn(session_id, patient_id, "assistant", reply["message"], now_iso(), metadata={"speaker": "patient_agent"})
        case_row = self.patient_agent_case_repo.get_latest_by_visit(visit_id)
        case_payload = Database.decode_json(case_row.get("case_json"), {}) if case_row else {}
        self._current["trace"] = self._build_trace(
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            payload={
                "phase": self._current.get("phase") or "internal_medicine_round1",
                "recent_question": message,
            },
            case_payload=case_payload,
            before_turns=before_turns,
        )
        self._current["last_error"] = None

    def _build_trace(self, *, patient_id: str, visit_id: str, session_id: str, payload: dict, case_payload: dict, before_turns: list[dict]) -> dict:
        case_card = PatientCaseCard.model_validate(case_payload)
        timeline = self.medical_record_repo.get_visit_timeline(visit_id) or {"entries": []}
        entries = list(timeline.get("entries") or [])
        known_test_results = [entry for entry in entries if entry.get("entry_type") == "test_result_note"]
        context = PatientReplyContext(
            phase=payload.get("phase") or "internal_medicine_round1",
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            recent_question=payload.get("recent_question") or "",
            recent_turns=self.session_repo.list_turns(session_id, limit=8),
            known_test_results=known_test_results,
            medical_record_excerpt=entries[-3:],
        )
        decision = self.patient_agent_service.agent.policy.decide(case_card, context)
        messages = build_reply_messages(
            case_card=case_card,
            context=context,
            decision=decision,
            constraints=self.patient_agent_service.agent.rag_context.build_reply_constraints(),
        )
        turns = self.session_repo.list_turns(session_id, limit=200)
        latest = _latest_reply(turns)
        return {
            "merged_payload": {
                "case_card": case_card.model_dump(),
                "reply_context": context.model_dump(),
                "policy_decision": decision.model_dump(),
            },
            "system_prompt": messages[0].get("content") if len(messages) > 1 else None,
            "user_prompt": messages[-1].get("content") if messages else None,
            "rag_query": {
                "phase": context.phase,
                "recent_question": context.recent_question,
                "known_test_results_count": len(context.known_test_results),
            },
            "rag_hits": [
                {"source": "reply_constraints", "content": self.patient_agent_service.agent.rag_context.build_reply_constraints()},
                {
                    "source": "case_constraints",
                    "content": self.patient_agent_service.agent.rag_context.build_case_constraints(),
                },
            ],
            "parsed_result": {
                "case_summary": self.patient_agent_service.summarize_case_for_debug(case_card),
                "policy_state": decision.model_dump(),
                "latest_message": latest.content if latest else "",
            },
            "fallback_reason": None if self.patient_agent_service.agent.llm_settings.get("api_key") else "patient_agent_llm_unavailable",
            "memory_delta": {
                "transcript": {
                    "before_count": len(before_turns),
                    "after_count": len(turns),
                }
            },
            "extra": {
                "used_facts_hint": list(decision.allowed_fact_keys),
                "rag_context_shell": self.patient_agent_service.agent.rag_context.build_reply_constraints(),
            },
        }
