from dataclasses import dataclass, field
from enum import Enum

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
        row = {
            "id": session_id,
            "patient_id": patient_id,
            "visit_id": visit_id,
            "agent_type": agent_type,
            "dialogue_state": dialogue_state,
        }
        self.rows[session_id] = row
        return row

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


class FakeDepartmentService(DepartmentAgentRuntime):
    def __init__(self, *, counters: dict, llm_settings: dict | None = None):
        self.counters = counters
        config = build_fake_config(counters)
        graph = DepartmentAgentGraph(service=None, dialogue_state_machine=FakeDialogueStateMachine(), config=config)
        super().__init__(
            config=config,
            llm_settings=llm_settings or {},
            patient_repo=DummyPatientRepo(),
            session_repo=DummySessionRepo(),
            memory_repo=DummyMemoryRepo(),
            queue_repo=DummyQueueRepo(),
            visit_repo=None,
            dialogue_state_machine=FakeDialogueStateMachine(),
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

    def after_persist_result(self, **kwargs) -> None:
        self.counters["after_persist"] += 1


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
        return ["high-risk"] if "severe" in " ".join(symptoms).lower() else []

    def build_missing_fields(shared_memory: dict):
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
        return build_missing_fields(shared_memory)

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
        counters["retrieve_rules"] += 1
        return [{"id": "fake-rule", "title": "Fake rule", "source": "unit-test"}]

    def fallback_result(payload: dict):
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
        counters["validate_result"] += 1
        result = dict(fallback)
        result["complete"] = True
        result["tests_suggested"] = []
        result["medication_or_action"] = ["rest"]
        result["red_flags"] = []
        result["patient_plan"] = "follow plan"
        result["source"] = "fallback-validated" if llm_result is None else "llm"
        return result

    def build_initial_message(shared_memory: dict, progress: FakeProgress):
        counters["build_initial_message"] += 1
        return "initial follow-up"

    def build_follow_up_question(field_name: str, shared_memory: dict, **kwargs):
        counters["build_follow_up_question"] += 1
        return f"please provide {field_name}"

    def build_follow_up_llm_messages(shared_memory: dict, message: str, missing_fields: list[str], **kwargs):
        counters["build_follow_up_llm_messages"] += 1
        return [
            {"role": "system", "content": "followup system"},
            {"role": "user", "content": f"message={message},missing={missing_fields}"},
        ]

    def build_transition_follow_up_question(shared_memory: dict):
        counters["build_transition_follow_up_question"] += 1
        return "please clarify"

    def build_final_message(result: dict, *, message_type: str = "final"):
        counters["build_final_message"] += 1
        return f"{message_type}:{result['source']}"

    def build_system_prompt():
        return "system prompt"

    def build_user_prompt(shared_memory: dict, message: str, missing_fields: list[str], **kwargs):
        counters["build_user_prompt"] += 1
        return f"user prompt:{message}:{','.join(missing_fields)}"

    def final_result_changed(previous: dict | None, current: dict | None):
        return (previous or {}) != (current or {})

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
        build_follow_up_llm_messages=build_follow_up_llm_messages,
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
    )


def test_department_agent_runtime_create_session_enters_followup():
    counters = {
        "retrieve_rules": 0,
        "fallback_result": 0,
        "validate_result": 0,
        "build_initial_message": 0,
        "build_follow_up_question": 0,
        "build_follow_up_llm_messages": 0,
        "build_transition_follow_up_question": 0,
        "build_final_message": 0,
        "build_user_prompt": 0,
        "after_persist": 0,
    }
    service = FakeDepartmentService(counters=counters)

    response = service.create_session(
        {
            "patient_id": "patient-1",
            "session_id": "fake-session-1",
            "visit_id": "visit-1",
            "name": "Patient One",
        }
    )

    assert response["dialogue"]["status"] == FakeDialogueState.AWAITING.value
    assert response["dialogue"]["message_type"] == "followup"
    assert response["dialogue"]["assistant_message"] == "initial follow-up"
    assert counters["build_initial_message"] == 1
    assert counters["retrieve_rules"] == 1
    assert counters["fallback_result"] == 1
    assert counters["after_persist"] == 1


def test_department_agent_runtime_continue_session_uses_fallback_and_hooks():
    counters = {
        "retrieve_rules": 0,
        "fallback_result": 0,
        "validate_result": 0,
        "build_initial_message": 0,
        "build_follow_up_question": 0,
        "build_follow_up_llm_messages": 0,
        "build_transition_follow_up_question": 0,
        "build_final_message": 0,
        "build_user_prompt": 0,
        "after_persist": 0,
    }
    service = FakeDepartmentService(counters=counters)
    service.create_session(
        {
            "patient_id": "patient-2",
            "session_id": "fake-session-2",
            "visit_id": "visit-2",
            "name": "Patient Two",
        }
    )

    response = service.continue_session(
        "fake-session-2",
        {
            "patient_id": "patient-2",
            "visit_id": "visit-2",
            "name": "Patient Two",
            "message": "I had cough since yesterday and no allergies.",
        },
    )

    assert response["dialogue"]["status"] == FakeDialogueState.COMPLETED.value
    assert response["dialogue"]["message_type"] == "final"
    assert response["dialogue"]["final_result"]["source"] == "fallback-validated"
    assert response["dialogue"]["assistant_message"] == "final:fallback-validated"
    assert counters["validate_result"] == 1
    assert counters["build_final_message"] == 1
    assert counters["after_persist"] == 2
    session_memory = service.memory_repo.get_agent_session_memory("fake-session-2", "patient-2", agent_type="fake_department")
    assert session_memory["latest_extraction"]["onset_time"] == "yesterday"
    assert len(service.session_repo.list_turns("fake-session-2")) == 3


def test_department_agent_runtime_continue_session_followup_prefers_llm_when_available():
    counters = {
        "retrieve_rules": 0,
        "fallback_result": 0,
        "validate_result": 0,
        "build_initial_message": 0,
        "build_follow_up_question": 0,
        "build_follow_up_llm_messages": 0,
        "build_transition_follow_up_question": 0,
        "build_final_message": 0,
        "build_user_prompt": 0,
        "after_persist": 0,
    }
    service = FakeDepartmentService(
        counters=counters,
        llm_settings={"api_key": "mock-key", "endpoint": "https://example.invalid", "model": "mock-model"},
    )
    service.create_session(
        {
            "patient_id": "patient-3",
            "session_id": "fake-session-3",
            "visit_id": "visit-3",
            "name": "Patient Three",
        }
    )

    service.request_follow_up_message_from_llm = lambda *args, **kwargs: "llm follow-up question"

    response = service.continue_session(
        "fake-session-3",
        {
            "patient_id": "patient-3",
            "visit_id": "visit-3",
            "name": "Patient Three",
            "message": "I have cough.",
        },
    )

    assert response["dialogue"]["status"] == FakeDialogueState.AWAITING.value
    assert response["dialogue"]["message_type"] == "followup"
    assert response["dialogue"]["assistant_message"] == "llm follow-up question"
    assert counters["build_follow_up_question"] == 0
    assert counters["build_transition_follow_up_question"] == 0


def test_department_agent_runtime_continue_session_followup_falls_back_when_llm_unavailable():
    counters = {
        "retrieve_rules": 0,
        "fallback_result": 0,
        "validate_result": 0,
        "build_initial_message": 0,
        "build_follow_up_question": 0,
        "build_follow_up_llm_messages": 0,
        "build_transition_follow_up_question": 0,
        "build_final_message": 0,
        "build_user_prompt": 0,
        "after_persist": 0,
    }
    service = FakeDepartmentService(counters=counters, llm_settings={})
    service.create_session(
        {
            "patient_id": "patient-4",
            "session_id": "fake-session-4",
            "visit_id": "visit-4",
            "name": "Patient Four",
        }
    )

    response = service.continue_session(
        "fake-session-4",
        {
            "patient_id": "patient-4",
            "visit_id": "visit-4",
            "name": "Patient Four",
            "message": "I have cough.",
        },
    )

    assert response["dialogue"]["status"] == FakeDialogueState.AWAITING.value
    assert response["dialogue"]["message_type"] == "followup"
    assert response["dialogue"]["assistant_message"] == "please provide onset_time"
    assert counters["build_follow_up_question"] == 1
