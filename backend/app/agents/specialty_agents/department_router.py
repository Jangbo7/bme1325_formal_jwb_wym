from app.agents.specialty_agents.departments import ALLOWED_DEPARTMENT_KEYS


def build_routing_decision(agent_type: str, result: dict, red_flags: list[str]) -> dict:
    if red_flags:
        return {
            "consultation_state": "routed",
            "urgency": "emergency",
            "suspected_department_key": agent_type,
            "routing_decision": {
                "next_node": "emergency_node",
                "department_key": None,
                "reason": f"Detected red flags: {', '.join(red_flags)}",
            },
        }

    department_key = agent_type if agent_type in ALLOWED_DEPARTMENT_KEYS else "general_medicine"
    reason = result.get("note") or "Specialty routing based on dominant complaint."
    return {
        "consultation_state": "routed",
        "urgency": "routine" if result.get("priority") != "H" else "urgent",
        "suspected_department_key": department_key,
        "routing_decision": {
            "next_node": "outpatient_queue",
            "department_key": department_key,
            "reason": reason,
        },
    }
