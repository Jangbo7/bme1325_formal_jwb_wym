from dataclasses import dataclass, field
from enum import Enum

from app.agents.clinical_policy import ClinicalPolicyCard, ClinicalPolicyRegistry, ClinicalPolicyValidatorResult
from app.agents.department_runtime import DepartmentAgentConfig, DepartmentAgentGraph, DepartmentAgentRuntime


class FakeDialogueState(str, Enum):
    IDLE = "idle"
    COLLECTING = "collecting"
    EVALUATING = "evaluating"
    NEEDS_FOLLOWUP = "needs_followup"
    AWAITING = "awaiting_patient_reply"
    COMPLETED = "completed"


class FakeDialogueStateMachine:
    _transitions = {
        FakeDialogueState.IDLE: {"start": FakeDialogueState.COLLECTING},
        FakeDialogueState.COLLECTING: {"evaluate": FakeDialogueState.EVALUATING},
        FakeDialogueState.EVALUATING: {
            "need_followup": FakeDialogueState.NEEDS_FOLLOWUP,
            "complete": FakeDialogueState.COMPLETED,
        },
        FakeDialogueState.NEEDS_FOLLOWUP: {"wait_for_reply": FakeDialogueState.AWAITING},
        FakeDialogueState.AWAITING: {"receive_reply": FakeDialogueState.EVALUATING},
        FakeDialogueState.COMPLETED: {"receive_reply": FakeDialogueState.EVALUATING},
    }

    def transition(self, current: FakeDialogueState, event: str) -> FakeDialogueState:
        next_state = self._transitions.get(current, {}).get(event)
        if next_state is None:
            raise ValueError(f"invalid transition {current} -> {event}")
        return next_state


@dataclass
class FakeProgress:
    followup_count: int = 0
    asked_fields_history: list[str] = field(default_factory=list)
    last_question_focus: str | None = None
    last_question_text: str = ""
    last_extracted_fields: list[str] = field(default_factory=list)
    patient_reply_count: int = 0
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "followup_count": self.followup_count,
            "asked_fields_history": list(self.asked_fields_history),
            "last_question_focus": self.last_question_focus,
            "last_question_text": self.last_question_text,
            "last_extracted_fields": list(self.last_extracted_fields),
            "patient_reply_count": self.patient_reply_count,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "FakeProgress":
        payload = data or {}
        return cls(
            followup_count=int(payload.get("followup_count", 0)),
            asked_fields_history=list(payload.get("asked_fields_history") or []),
            last_question_focus=payload.get("last_question_focus"),
            last_question_text=str(payload.get("last_question_text") or ""),
            last_extracted_fields=list(payload.get("last_extracted_fields") or []),
            patient_reply_count=int(payload.get("patient_reply_count", 0)),
            completed=bool(payload.get("completed", False)),
        )


@dataclass
class FakeGraphState:
    payload: dict
    patient_row: dict | None = None
    session_row: dict | None = None
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)
    merged_payload: dict = field(default_factory=dict)
    final_result: dict | None = None
    evidence: list[dict] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    assistant_message: dict = field(default_factory=dict)
    complete: bool = False
    dialogue_state: FakeDialogueState = FakeDialogueState.IDLE


@dataclass
class FakeWorkingMemory:
    short_term_turns: list[dict] = field(default_factory=list)
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
    consultation_progress: FakeProgress = field(default_factory=FakeProgress)


class DummyPatientRepo:
    def __init__(self):
        self.rows = {}

    def get(self, patient_id: str):
        return self.rows.get(patient_id)

    def update_patient(self, patient_id: str, **kwargs):
        row = dict(self.rows.get(patient_id) or {"id": patient_id, "name": patient_id, "priority": "M"})
        row.update(kwargs)
        self.rows[patient_id] = row
        return row


class DummySessionRepo:
    def __init__(self):
        self.rows = {}
        self.turns = {}

    def create_or_update(self, session_id: str, patient_id: str, dialogue_state: str, agent_type: str = "fake", visit_id: str | None = None):
        self.rows[session_id] = {
            "id": session_id,
            "patient_id": patient_id,
            "visit_id": visit_id,
            "agent_type": agent_type,
            "dialogue_state": dialogue_state,
        }
        return self.rows[session_id]

    def update_state(self, session_id: str, dialogue_state: str):
        self.rows[session_id]["dialogue_state"] = dialogue_state
        return self.rows[session_id]

    def get(self, session_id: str):
        return self.rows.get(session_id)

    def append_turn(self, session_id: str, patient_id: str, role: str, content: str, timestamp: str, metadata: dict | None = None):
        self.turns.setdefault(session_id, []).append(
            {
                "patient_id": patient_id,
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "metadata": metadata or {},
            }
        )

    def list_turns(self, session_id: str, limit: int = 8):
        return list(self.turns.get(session_id, []))[-limit:]


class DummyMemoryRepo:
    def __init__(self):
        self.shared = {}
        self.private = {}

    def get_shared_memory(self, patient_id: str, patient_name: str):
        self.shared.setdefault(
            patient_id,
            {
                "profile": {
                    "name": patient_name,
                    "allergies": [],
                    "allergy_status": "unknown",
                    "chronic_conditions": [],
                },
                "clinical_memory": {
                    "chief_complaint": None,
                    "symptoms": [],
                    "onset_time": None,
                    "vitals": {},
                    "risk_flags": [],
                },
            },
        )
        return self.shared[patient_id]

    def save_shared_memory(self, patient_id: str, payload: dict):
        self.shared[patient_id] = payload

    def get_agent_session_memory(self, session_id: str, patient_id: str, agent_type: str = "fake"):
        self.private.setdefault((session_id, patient_id, agent_type), {"agent_type": agent_type})
        return self.private[(session_id, patient_id, agent_type)]

    def save_agent_session_memory(self, session_id: str, patient_id: str, payload: dict, agent_type: str = "fake"):
        self.private[(session_id, patient_id, agent_type)] = payload


class DummyQueueRepo:
    def get_active_ticket_for_patient(self, *args, **kwargs):
        return None


class DummyBus:
    def __init__(self):
        self.events = []

    def publish(self, topic: str, payload: dict):
        self.events.append((topic, payload))


class FakePolicyService(DepartmentAgentRuntime):
    def __init__(self, counters: dict):
        self.counters = counters
        config = build_fake_config(counters)
        dialogue_state_machine = FakeDialogueStateMachine()
        graph = DepartmentAgentGraph(service=None, dialogue_state_machine=dialogue_state_machine, config=config)
        super().__init__(
            config=config,
            llm_settings={},
            patient_repo=DummyPatientRepo(),
            session_repo=DummySessionRepo(),
            memory_repo=DummyMemoryRepo(),
            queue_repo=DummyQueueRepo(),
            visit_repo=None,
            dialogue_state_machine=dialogue_state_machine,
            patient_state_machine=None,
            visit_state_machine=None,
            bus=DummyBus(),
            graph=graph,
        )
        self.graph.service = self

    def get_patient_view(self, patient_id: str):
        return {"id": patient_id, "visit_state": "in_consultation"}

    def prepare_create_session(self, payload: dict, session_id: str, dialogue_state):
        self.patient_repo.update_patient(payload["patient_id"], session_id=session_id, visit_id=payload.get("visit_id"))
        self.session_repo.create_or_update(
            session_id,
            payload["patient_id"],
            dialogue_state.value,
            agent_type=self.config.agent_type,
            visit_id=payload.get("visit_id"),
        )

    def validate_continue_session(self, session_id: str, payload: dict) -> dict:
        session_row = self.session_repo.get(session_id)
        if not session_row:
            raise ValueError("missing session")
        payload["patient_id"] = payload.get("patient_id") or session_row["patient_id"]
        return session_row

    def configure_private_memory_defaults(self, private_memory: dict, payload: dict) -> None:
        private_memory.setdefault("message_type", "followup")
        private_memory.setdefault("missing_fields", [])
        private_memory.setdefault("assistant_message", "")
        private_memory.setdefault("evidence", [])
        private_memory.setdefault("latest_extraction", {})
        private_memory.setdefault("latest_summary", {})
        private_memory.setdefault(self.config.progress_memory_key, {})
        private_memory.setdefault("final_result", {})
        private_memory.setdefault("consultation_round", 1)


def build_fake_policy_registry() -> ClinicalPolicyRegistry:
    card = ClinicalPolicyCard(
        id="fake_intake_policy",
        version="1",
        source_layer="unit_test",
        agent_scope="fake_agent",
        department_scope="fake_department",
        category="consultation_intake",
        retrieval_priority="high",
        authority_level="internal",
        safety_level="non_diagnostic",
        applicable_phase=("round1_initial_consultation",),
        keywords=("cough",),
        symptom_patterns=(),
        patient_constraints={},
        visit_constraints={},
        role_boundary="Collect intake information only.",
        collection_targets=(
            {"field": "chief_complaint", "required": True, "runtime_supported": True},
            {"field": "onset_time", "required": True, "runtime_supported": True},
            {"field": "allergies", "required": True, "runtime_supported": True},
        ),
        question_policy={"max_questions_per_turn": 3},
        red_flags=("chest pain",),
        forbidden_actions=("definitive_diagnosis",),
        allowed_outputs=("ask_follow_up", "summarize_case"),
        escalation_policy={"default_urgency": "routine", "red_flag_urgency": "urgent"},
        output_mode="policy_snapshot",
        output_schema_name="fake_round1_policy",
        required_fields=(
            "agent_role",
            "consultation_stage",
            "chief_complaint",
            "key_symptoms_collected",
            "missing_information",
            "red_flags",
            "urgency",
            "follow_up_questions",
            "patient_summary",
            "next_action",
        ),
        allowed_next_actions=("ask_follow_up", "summarize_case"),
    )
    return ClinicalPolicyRegistry(cards=[card])


def build_fake_config(counters: dict) -> DepartmentAgentConfig:
    def merge_unique(old_values, new_values):
        merged = list(old_values or [])
        for value in new_values or []:
            if value and value not in merged:
                merged.append(value)
        return merged

    def merge_vitals(old_vitals, new_vitals):
        merged = dict(old_vitals or {})
        merged.update({key: value for key, value in (new_vitals or {}).items() if value not in (None, "")})
        return merged

    def split_symptoms(text: str):
        return [part.strip() for part in str(text or "").split(",") if part.strip()]

    def derive_risk_flags(symptoms: list[str], vitals: dict):
        del vitals
        return ["high-risk"] if "severe" in " ".join(symptoms).lower() else []

    def build_missing_fields(shared_memory: dict, *, policy_runtime_context=None):
        counters["build_missing_fields"] += 1
        assert policy_runtime_context is not None
        missing = []
        clinical = shared_memory["clinical_memory"]
        profile = shared_memory["profile"]
        if not clinical.get("chief_complaint"):
            missing.append("chief_complaint")
        if not clinical.get("onset_time"):
            missing.append("onset_time")
        if profile.get("allergy_status") != "known":
            missing.append("allergies")
        return missing

    def prioritize_missing_fields(shared_memory: dict, **kwargs):
        counters["prioritize_missing_fields"] += 1
        assert kwargs.get("policy_runtime_context") is not None
        return build_missing_fields(shared_memory, policy_runtime_context=kwargs.get("policy_runtime_context"))

    def extract_structured_updates(message: str):
        lowered = message.lower()
        extracted = {
            "chief_complaint": "severe cough" if "cough" in lowered else None,
            "onset_time": "yesterday" if "yesterday" in lowered else None,
            "allergies": [] if "no allergies" in lowered else None,
            "allergy_status": "known" if "no allergies" in lowered else None,
            "symptoms": ["severe cough"] if "cough" in lowered else [],
            "extracted_fields": [],
        }
        for field in ("chief_complaint", "onset_time", "allergies", "symptoms"):
            value = extracted.get(field)
            if value not in (None, [], ""):
                extracted["extracted_fields"].append(field)
        return extracted

    def retrieve_rules(payload: dict, top_k: int = 3):
        del payload, top_k
        counters["retrieve_rules"] += 1
        return [{"id": "fake-rule", "title": "Fake rule", "source": "unit-test"}]

    def fallback_result(payload: dict):
        del payload
        counters["fallback_result"] += 1
        return {
            "department": "Fake Department",
            "priority": "M",
            "diagnosis_level": 1,
            "note": "fallback note",
            "test_required": False,
            "test_category": "none",
            "test_items": [],
            "test_reason": "",
        }

    def validate_result(llm_result: dict | None, fallback: dict, payload: dict):
        del llm_result, payload
        counters["validate_result"] += 1
        result = dict(fallback)
        result["complete"] = True
        result["tests_suggested"] = []
        result["medication_or_action"] = ["rest"]
        result["red_flags"] = []
        result["patient_plan"] = "follow plan"
        result["source"] = "fallback-validated"
        return result

    def build_initial_message(shared_memory: dict, progress: FakeProgress, *, policy_runtime_context=None):
        del shared_memory, progress
        counters["build_initial_message"] += 1
        assert policy_runtime_context is not None
        return "initial follow-up"

    def build_follow_up_question(field_name: str, shared_memory: dict, **kwargs):
        del shared_memory
        counters["build_follow_up_question"] += 1
        assert kwargs.get("policy_runtime_context") is not None
        return f"please provide {field_name}"

    def build_transition_follow_up_question(shared_memory: dict, **kwargs):
        del shared_memory
        counters["build_transition_follow_up_question"] += 1
        assert kwargs.get("policy_runtime_context") is not None
        return "please clarify"

    def build_final_message(result: dict, *, message_type: str = "final"):
        counters["build_final_message"] += 1
        return f"{message_type}:{result['source']}"

    def build_system_prompt(*, policy_prompt_context: str = "", policy_runtime_context=None):
        counters["build_system_prompt"] += 1
        assert policy_runtime_context is not None
        assert "fake_intake_policy" in policy_prompt_context
        return f"system prompt\n{policy_prompt_context}"

    def build_user_prompt(shared_memory: dict, message: str, missing_fields: list[str], **kwargs):
        del shared_memory, message, missing_fields
        counters["build_user_prompt"] += 1
        assert "fake_intake_policy" in kwargs.get("policy_prompt_context", "")
        return "user prompt"

    def final_result_changed(previous: dict | None, current: dict | None):
        return (previous or {}) != (current or {})

    def policy_registry_loader():
        counters["policy_registry_loader"] += 1
        return build_fake_policy_registry()

    def policy_phase_selector(payload: dict, shared_memory: dict, private_memory: dict, progress: FakeProgress, mode: str, **kwargs):
        del payload, shared_memory, private_memory, progress, mode, kwargs
        counters["policy_phase_selector"] += 1
        return "round1_initial_consultation"

    def policy_prompt_adapter(policy_runtime_context, policy_prompt_context: str, **kwargs):
        del kwargs
        counters["policy_prompt_adapter"] += 1
        return f"{policy_runtime_context.primary_card.id}\n{policy_prompt_context}"

    def policy_validator(snapshot: dict, policy_runtime_context, payload: dict, **kwargs):
        del snapshot, policy_runtime_context, payload, kwargs
        counters["policy_validator"] += 1
        return ClinicalPolicyValidatorResult(ok=True, normalized_output={})

    def policy_fallback_builder(*args, **kwargs):
        del args, kwargs
        counters["policy_fallback_builder"] += 1
        return {}

    return DepartmentAgentConfig(
        agent_type="fake_department",
        session_prefix="fake-session-",
        route_slug="fake-department",
        state_enum=FakeDialogueState,
        graph_state_cls=FakeGraphState,
        working_memory_cls=FakeWorkingMemory,
        progress_from_dict=FakeProgress.from_dict,
        min_patient_reply_count_before_complete=1,
        create_session_events=("start", "evaluate"),
        continue_session_event="receive_reply",
        followup_events=("need_followup", "wait_for_reply"),
        complete_events=("complete",),
        build_initial_message=build_initial_message,
        build_follow_up_question=build_follow_up_question,
        build_transition_follow_up_question=build_transition_follow_up_question,
        build_final_message=build_final_message,
        build_system_prompt=build_system_prompt,
        build_user_prompt=build_user_prompt,
        retrieve_rules=retrieve_rules,
        fallback_result=fallback_result,
        validate_result=validate_result,
        extract_structured_updates=extract_structured_updates,
        derive_risk_flags=derive_risk_flags,
        split_symptoms=split_symptoms,
        merge_unique=merge_unique,
        merge_vitals=merge_vitals,
        build_missing_fields=build_missing_fields,
        prioritize_missing_fields=prioritize_missing_fields,
        final_result_changed=final_result_changed,
        policy_agent_scope="fake_agent",
        policy_department_scope="fake_department",
        policy_registry_loader=policy_registry_loader,
        policy_phase_selector=policy_phase_selector,
        policy_prompt_adapter=policy_prompt_adapter,
        policy_validator=policy_validator,
        policy_fallback_builder=policy_fallback_builder,
    )


def test_department_agent_runtime_policy_hooks_are_used():
    counters = {
        "retrieve_rules": 0,
        "fallback_result": 0,
        "validate_result": 0,
        "build_initial_message": 0,
        "build_follow_up_question": 0,
        "build_transition_follow_up_question": 0,
        "build_final_message": 0,
        "build_system_prompt": 0,
        "build_user_prompt": 0,
        "build_missing_fields": 0,
        "prioritize_missing_fields": 0,
        "policy_registry_loader": 0,
        "policy_phase_selector": 0,
        "policy_prompt_adapter": 0,
        "policy_validator": 0,
        "policy_fallback_builder": 0,
    }
    service = FakePolicyService(counters)
    service.create_session(
        {
            "patient_id": "patient-1",
            "session_id": "fake-session-1",
            "visit_id": "visit-1",
            "name": "Patient One",
        }
    )

    response = service.continue_session(
        "fake-session-1",
        {
            "patient_id": "patient-1",
            "visit_id": "visit-1",
            "name": "Patient One",
            "message": "I had severe cough since yesterday and no allergies.",
        },
    )

    assert response["dialogue"]["status"] == FakeDialogueState.COMPLETED.value
    assert counters["policy_registry_loader"] == 1
    assert counters["policy_phase_selector"] >= 2
    assert counters["policy_prompt_adapter"] >= 1
    assert counters["policy_validator"] >= 2
    assert counters["build_system_prompt"] == 1
    assert counters["build_user_prompt"] == 1
    session_memory = service.memory_repo.get_agent_session_memory("fake-session-1", "patient-1", agent_type="fake_department")
    assert session_memory["latest_policy"]["card_id"] == "fake_intake_policy"
    assert session_memory["latest_policy"]["phase"] == "round1_initial_consultation"
