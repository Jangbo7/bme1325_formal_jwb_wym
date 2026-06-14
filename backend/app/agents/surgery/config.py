from app.agents.department_runtime import DepartmentAgentConfig
from app.agents.surgery.policy import (
    adapt_surgery_policy_prompt,
    build_surgery_policy_fallback,
    load_surgery_policy_registry,
    select_surgery_policy_phase,
    validate_surgery_policy_snapshot,
)
from app.agents.surgery.patient_reply import build_patient_reply
from app.agents.surgery.post_final_answer import build_post_final_answer_llm_messages
from app.agents.surgery.prompts import (
    build_consultation_system_prompt,
    build_consultation_user_prompt,
    build_final_message,
    build_follow_up_llm_messages,
    build_follow_up_question,
    build_initial_message,
    build_transition_follow_up_question,
)
from app.agents.surgery.rules import (
    build_missing_fields,
    derive_risk_flags,
    extract_structured_updates,
    final_result_changed,
    merge_unique,
    merge_vitals,
    prioritize_missing_fields,
    retrieve_relevant_surgery_rules,
    rule_based_surgery,
    split_symptoms,
    validate_surgery_result,
)
from app.agents.surgery.state import SurgeryDialogueState, SurgeryGraphState, WorkingMemory
from app.agents.surgery.workflow import ConsultationProgress


def build_surgery_runtime_config() -> DepartmentAgentConfig:
    return DepartmentAgentConfig(
        agent_type="surgery",
        session_prefix="surgery-session-",
        route_slug="surgery",
        state_enum=SurgeryDialogueState,
        graph_state_cls=SurgeryGraphState,
        working_memory_cls=WorkingMemory,
        progress_from_dict=ConsultationProgress.from_dict,
        min_patient_reply_count_before_complete=2,
        create_session_events=("start", "evaluate"),
        continue_session_event="receive_reply",
        followup_events=("need_followup", "wait_for_reply"),
        complete_events=("complete", "plan_treatment", "approve"),
        build_initial_message=build_initial_message,
        build_follow_up_question=build_follow_up_question,
        build_follow_up_llm_messages=build_follow_up_llm_messages,
        build_transition_follow_up_question=build_transition_follow_up_question,
        build_post_final_answer_llm_messages=build_post_final_answer_llm_messages,
        build_final_message=build_final_message,
        build_patient_reply=build_patient_reply,
        build_system_prompt=build_consultation_system_prompt,
        build_user_prompt=build_consultation_user_prompt,
        retrieve_rules=retrieve_relevant_surgery_rules,
        fallback_result=rule_based_surgery,
        validate_result=validate_surgery_result,
        extract_structured_updates=extract_structured_updates,
        derive_risk_flags=derive_risk_flags,
        split_symptoms=split_symptoms,
        merge_unique=merge_unique,
        merge_vitals=merge_vitals,
        build_missing_fields=build_missing_fields,
        prioritize_missing_fields=prioritize_missing_fields,
        final_result_changed=final_result_changed,
        policy_agent_scope="surgery_agent",
        policy_department_scope="surgery",
        policy_registry_loader=load_surgery_policy_registry,
        policy_phase_selector=select_surgery_policy_phase,
        policy_prompt_adapter=adapt_surgery_policy_prompt,
        policy_validator=validate_surgery_policy_snapshot,
        policy_fallback_builder=build_surgery_policy_fallback,
        metadata={
            "policy_agent_role": "surgery_agent",
            "department_id": "surgery",
            "department_label": "Surgery",
        },
    )
