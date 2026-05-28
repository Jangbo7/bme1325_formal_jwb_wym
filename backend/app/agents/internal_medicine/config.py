from app.agents.department_runtime import DepartmentAgentConfig
from app.agents.internal_medicine.policy import (
    adapt_internal_medicine_policy_prompt,
    build_internal_medicine_policy_fallback,
    load_internal_medicine_policy_registry,
    select_internal_medicine_policy_phase,
    validate_internal_medicine_policy_snapshot,
)
from app.agents.internal_medicine.prompts import (
    build_consultation_system_prompt,
    build_consultation_user_prompt,
    build_final_message,
    build_follow_up_question,
    build_initial_message,
    build_transition_follow_up_question,
)
from app.agents.internal_medicine.rules import (
    build_missing_fields,
    derive_risk_flags,
    extract_structured_updates,
    final_result_changed,
    merge_unique,
    merge_vitals,
    prioritize_missing_fields,
    retrieve_relevant_internal_medicine_rules,
    rule_based_internal_medicine,
    split_symptoms,
    validate_internal_medicine_result,
)
from app.agents.internal_medicine.state import InternalMedicineGraphState, WorkingMemory
from app.agents.internal_medicine.workflow import ConsultationProgress
from app.schemas.common import InternalMedicineDialogueState


def build_internal_medicine_runtime_config() -> DepartmentAgentConfig:
    return DepartmentAgentConfig(
        agent_type="internal_medicine",
        session_prefix="im-session-",
        route_slug="internal-medicine",
        state_enum=InternalMedicineDialogueState,
        graph_state_cls=InternalMedicineGraphState,
        working_memory_cls=WorkingMemory,
        progress_from_dict=ConsultationProgress.from_dict,
        min_patient_reply_count_before_complete=2,
        create_session_events=("start", "evaluate"),
        continue_session_event="receive_reply",
        followup_events=("need_followup", "wait_for_reply"),
        complete_events=("complete", "plan_treatment", "approve"),
        build_initial_message=build_initial_message,
        build_follow_up_question=build_follow_up_question,
        build_transition_follow_up_question=build_transition_follow_up_question,
        build_final_message=build_final_message,
        build_system_prompt=build_consultation_system_prompt,
        build_user_prompt=build_consultation_user_prompt,
        retrieve_rules=retrieve_relevant_internal_medicine_rules,
        fallback_result=rule_based_internal_medicine,
        validate_result=validate_internal_medicine_result,
        extract_structured_updates=extract_structured_updates,
        derive_risk_flags=derive_risk_flags,
        split_symptoms=split_symptoms,
        merge_unique=merge_unique,
        merge_vitals=merge_vitals,
        build_missing_fields=build_missing_fields,
        prioritize_missing_fields=prioritize_missing_fields,
        final_result_changed=final_result_changed,
        policy_agent_scope="internal_medicine_agent",
        policy_department_scope="internal_medicine",
        policy_registry_loader=load_internal_medicine_policy_registry,
        policy_phase_selector=select_internal_medicine_policy_phase,
        policy_prompt_adapter=adapt_internal_medicine_policy_prompt,
        policy_validator=validate_internal_medicine_policy_snapshot,
        policy_fallback_builder=build_internal_medicine_policy_fallback,
        metadata={"policy_agent_role": "internal_medicine_agent"},
    )
