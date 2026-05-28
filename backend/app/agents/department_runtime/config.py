from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class DepartmentAgentConfig:
    agent_type: str
    session_prefix: str
    route_slug: str
    state_enum: type
    graph_state_cls: type
    working_memory_cls: type
    progress_from_dict: Callable[[dict | None], Any]
    progress_memory_key: str = "consultation_progress"
    min_patient_reply_count_before_complete: int = 0
    create_session_events: tuple[str, ...] = ("start", "evaluate")
    continue_session_event: str = "receive_reply"
    followup_events: tuple[str, ...] = ("need_followup", "wait_for_reply")
    complete_events: tuple[str, ...] = ("complete",)
    build_initial_message: Callable[[dict, Any], str] | None = None
    build_follow_up_question: Callable[..., str] | None = None
    build_follow_up_llm_messages: Callable[..., list[dict]] | None = None
    build_transition_follow_up_question: Callable[[dict], str] | None = None
    build_final_message: Callable[..., str] | None = None
    build_system_prompt: Callable[[], str] | None = None
    build_user_prompt: Callable[..., str] | None = None
    retrieve_rules: Callable[[dict, int], list[dict]] | None = None
    fallback_result: Callable[[dict], dict] | None = None
    validate_result: Callable[[dict | None, dict, dict], dict] | None = None
    extract_structured_updates: Callable[[str], dict] | None = None
    derive_risk_flags: Callable[[list[str], dict], list[str]] | None = None
    split_symptoms: Callable[[str], list[str]] | None = None
    merge_unique: Callable[[list | None, list | None], list] | None = None
    merge_vitals: Callable[[dict | None, dict | None], dict] | None = None
    build_missing_fields: Callable[[dict], list[str]] | None = None
    prioritize_missing_fields: Callable[..., list[str]] | None = None
    final_result_changed: Callable[[dict | None, dict | None], bool] | None = None
    policy_agent_scope: str | None = None
    policy_department_scope: str | None = None
    policy_registry_loader: Callable[[], Any] | None = None
    policy_phase_selector: Callable[..., str | None] | None = None
    policy_prompt_adapter: Callable[..., str] | None = None
    policy_validator: Callable[..., Any] | None = None
    policy_fallback_builder: Callable[..., dict] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
