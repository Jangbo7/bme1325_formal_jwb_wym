from __future__ import annotations

from app.agents.specialty_agents.department_router import build_routing_decision
from app.agents.specialty_agents.official_guidance import retrieve_official_guidance
from app.agents.specialty_agents.prompts import (
    build_specialty_reply_message,
    build_specialty_system_prompt,
    build_specialty_user_prompt,
)
from app.agents.specialty_agents.rules import (
    retrieve_relevant_specialty_rules,
    rule_based_specialty,
)
from app.agents.specialty_agents.red_flag_rules import detect_red_flags
from app.agents.specialty_agents.schemas import SpecialtyDoctorDecision


class SpecialtyAgentService:
    def __init__(self, agent_type: str):
        self.agent_type = agent_type

    def evaluate(self, payload: dict) -> dict:
        retrieved_rules = retrieve_relevant_specialty_rules(self.agent_type, payload, top_k=3)
        official_guidance = retrieve_official_guidance(self.agent_type, payload, top_k=4)
        result = rule_based_specialty(self.agent_type, payload)
        red_flags = detect_red_flags(payload)
        routing = build_routing_decision(self.agent_type, result, red_flags)
        decision = SpecialtyDoctorDecision(
            reply_to_patient=build_specialty_reply_message(self.agent_type, result),
            consultation_state=routing["consultation_state"],
            suspected_department_key=routing["suspected_department_key"],
            urgency=routing["urgency"],
            red_flags=red_flags,
            missing_information=[],
            routing_decision=routing["routing_decision"],
            structured_result=result,
        )
        return {
            "system_prompt": build_specialty_system_prompt(self.agent_type),
            "user_prompt": build_specialty_user_prompt(self.agent_type, payload, retrieved_rules),
            "rag_hits": retrieved_rules,
            "official_guidance_hits": official_guidance,
            "result": result,
            "assistant_message": decision.reply_to_patient,
            "decision": decision.model_dump(),
        }
