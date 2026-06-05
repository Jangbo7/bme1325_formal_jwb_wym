from app.agents.clinical_policy import ClinicalPolicyRuntime
from app.agents.triage.policy import load_triage_policy_registry
from app.agents.triage.rules import rule_based_triage, validate_triage_result


def test_triage_policy_registry_loads_triage_card():
    registry = load_triage_policy_registry()
    card = next(card for card in registry.cards if card.id == "triage_initial_assessment")
    assert card.agent_scope == "triage_agent"
    assert card.department_scope == "triage"
    assert "initial_assessment" in card.applicable_phase


def test_triage_validator_restricts_normal_outpatient_departments_to_internal_or_surgery():
    registry = load_triage_policy_registry()
    runtime_context = ClinicalPolicyRuntime().build_runtime_context(
        registry.find(
            agent_scope="triage_agent",
            department_scope="triage",
            phase="initial_assessment",
            context={"chief_complaint": "mild cough", "symptoms": "mild cough", "risk_flags": []},
        )
    )
    fallback = rule_based_triage(
        {
            "chief_complaint": "mild cough",
            "symptoms": "mild cough",
            "vitals": {"heart_rate": 82, "temp_c": 37.0, "pain_score": 2},
        },
        policy_runtime_context=runtime_context,
    )
    normalized = validate_triage_result(
        {
            "triage_level": 4,
            "priority": "L",
            "department": "Dermatology",
            "note": "stable",
        },
        fallback,
        policy_runtime_context=runtime_context,
        payload={"chief_complaint": "mild cough", "symptoms": "mild cough"},
    )
    assert normalized["department"] == "Internal Medicine"


def test_triage_validator_keeps_emergency_for_urgent_cases():
    fallback = {
        "triage_level": 2,
        "priority": "H",
        "department": "Emergency",
        "note": "urgent",
    }
    normalized = validate_triage_result(
        {
            "triage_level": 2,
            "priority": "H",
            "department": "Surgery",
            "note": "urgent",
        },
        fallback,
        payload={"chief_complaint": "chest pain", "symptoms": "chest pain"},
    )
    assert normalized["department"] == "Emergency"
