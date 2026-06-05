from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRegistry, ClinicalPolicyRuntime


CARD_DIR = Path(__file__).resolve().parents[1] / "app" / "agents" / "clinical_policy" / "cards"


def test_clinical_policy_registry_loads_internal_medicine_card():
    registry = ClinicalPolicyRegistry.load(CARD_DIR)

    assert len(registry.cards) >= 1
    card = registry.cards[0]
    assert card.id == "internal_medicine_initial_consultation"
    assert "round1_initial_consultation" in card.applicable_phase
    assert "ask_follow_up" in card.allowed_next_actions
    assert "treat_and_discharge" in card.outcome_policy["allowed_decisions"]


def test_clinical_policy_registry_matches_by_scope_and_phase():
    registry = ClinicalPolicyRegistry.load(CARD_DIR)

    matched = registry.find(
        agent_scope="internal_medicine_agent",
        department_scope="internal_medicine",
        phase="round1_initial_consultation",
        context={
            "message": "Chest pain since this morning with shortness of breath.",
            "chief_complaint": "chest pain",
            "symptoms": "chest pain, shortness of breath",
            "risk_flags": ["cardiac_alert"],
            "patient": {},
            "visit": {"consultation_round": 1},
        },
    )
    unmatched = registry.find(
        agent_scope="internal_medicine_agent",
        department_scope="internal_medicine",
        phase="round2_reassessment",
        context={"message": "", "patient": {}, "visit": {"consultation_round": 2}},
    )

    assert matched.primary_card is not None
    assert matched.primary_card.id == "internal_medicine_initial_consultation"
    assert unmatched.primary_card is None


def test_clinical_policy_runtime_validates_and_builds_safe_fallback():
    registry = ClinicalPolicyRegistry.load(CARD_DIR)
    match_result = registry.find(
        agent_scope="internal_medicine_agent",
        department_scope="internal_medicine",
        phase="round1_initial_consultation",
        context={
            "message": "I have severe chest pain and trouble breathing.",
            "chief_complaint": "chest pain",
            "symptoms": "severe chest pain, trouble breathing",
            "risk_flags": ["cardiac_alert", "respiratory_alert"],
            "patient": {},
            "visit": {"consultation_round": 1},
        },
    )
    runtime = ClinicalPolicyRuntime()
    runtime_context = runtime.build_runtime_context(match_result)

    invalid_snapshot = {
        "agent_role": "internal_medicine_agent",
        "consultation_stage": "summary",
        "chief_complaint": "chest pain",
        "key_symptoms_collected": ["chest pain"],
        "missing_information": [],
        "red_flags": ["persistent chest pain"],
        "urgency": "routine",
        "follow_up_questions": ["one", "two", "three", "four"],
        "patient_summary": "Final diagnosis: acute coronary syndrome. No problem.",
        "next_action": "invalid_action",
    }

    validation = runtime.validate_snapshot(invalid_snapshot, runtime_context)
    fallback = runtime.build_safe_fallback(
        runtime_context,
        {
            "shared_memory": {"clinical_memory": {"chief_complaint": "chest pain", "symptoms": ["chest pain"]}},
            "chief_complaint": "chest pain",
            "symptoms": ["chest pain"],
            "missing_fields": ["onset_time"],
            "red_flags": ["persistent chest pain"],
        },
        reason=validation.fallback_reason,
    )

    assert validation.ok is False
    assert any("invalid next_action" in violation for violation in validation.violations)
    assert any("follow_up_questions exceeds" in violation for violation in validation.violations)
    assert any("forbidden action detected" in violation for violation in validation.violations)
    assert fallback["next_action"] == "escalate_urgency"
    assert fallback["urgency"] == "urgent"
