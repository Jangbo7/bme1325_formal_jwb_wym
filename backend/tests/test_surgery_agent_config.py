from types import SimpleNamespace

from app.agents.clinical_policy import ClinicalPolicyRuntime
from app.agents.surgery import create_surgery_service
from app.agents.surgery.config import build_surgery_runtime_config
from app.agents.surgery.policy import load_surgery_policy_registry
from app.agents.surgery.rules import rule_based_surgery, validate_surgery_result


def _build_policy_runtime_context(*, chief_complaint: str, symptoms: str = "", message: str = ""):
    registry = load_surgery_policy_registry()
    match_result = registry.find(
        agent_scope="surgery_agent",
        department_scope="surgery",
        phase="round1_initial_consultation",
        context={
            "chief_complaint": chief_complaint,
            "symptoms": symptoms,
            "message": message,
        },
    )
    runtime = ClinicalPolicyRuntime()
    return runtime.build_runtime_context(match_result)


def _build_memory(*, chief_complaint: str, onset_time: str, symptoms: list[str], allergies: list[str] | None = None, vitals: dict | None = None):
    return SimpleNamespace(
        shared_memory={
            "clinical_memory": {
                "chief_complaint": chief_complaint,
                "onset_time": onset_time,
                "symptoms": list(symptoms),
                "vitals": dict(vitals or {}),
                "risk_flags": [],
            },
            "profile": {
                "allergy_status": "known",
                "allergies": list(allergies or []),
            },
        },
        private_memory={"consultation_round": 1},
    )


def test_surgery_policy_registry_and_runtime_config_load():
    registry = load_surgery_policy_registry()
    card = next(card for card in registry.cards if card.id == "surgery_initial_consultation")
    assert card.agent_scope == "surgery_agent"
    assert "recommend_other_clinic" in card.outcome_policy["allowed_decisions"]

    config = build_surgery_runtime_config()
    assert config.agent_type == "surgery"
    assert config.session_prefix == "surgery-session-"
    assert config.policy_registry_loader is not None
    assert config.validate_result is not None


def test_create_surgery_service_is_instantiable():
    service = create_surgery_service(
        llm_settings={"endpoint": "", "model": "", "api_key": ""},
        patient_repo=object(),
        session_repo=object(),
        memory_repo=object(),
        queue_repo=object(),
        visit_repo=object(),
        patient_state_machine=object(),
        visit_state_machine=object(),
        bus=object(),
    )
    assert service.config.agent_type == "surgery"
    assert service.graph.service is service


def test_surgery_round1_can_recommend_direct_discharge_for_stable_dressing_change():
    payload = {
        "chief_complaint": "postoperative dressing change",
        "symptoms": "postoperative dressing change",
        "message": "I need a dressing change after surgery, there is no fever, no pus, and the pain is not worse.",
        "onset_time": "yesterday",
        "allergies": [],
        "vitals": {"temp_c": 37.0, "heart_rate": 84},
    }
    memory = _build_memory(
        chief_complaint=payload["chief_complaint"],
        onset_time="yesterday",
        symptoms=["postoperative dressing change"],
        vitals=payload["vitals"],
    )
    context = _build_policy_runtime_context(
        chief_complaint=payload["chief_complaint"],
        symptoms=payload["symptoms"],
        message=payload["message"],
    )

    result = validate_surgery_result(None, rule_based_surgery(payload), payload, memory=memory, policy_runtime_context=context)

    assert result["next_step_decision"] == "treat_and_discharge"
    assert result["needs_second_consultation"] is False
    assert result["needs_second_internal_medicine_consultation"] is False
    assert result["needs_tests"] is False
    assert result["needs_medication"] is False


def test_surgery_round1_defaults_to_test_first_for_abdominal_pain():
    payload = {
        "chief_complaint": "abdominal pain",
        "symptoms": "abdominal pain",
        "message": "Abdominal pain started yesterday and I have no allergies.",
        "onset_time": "yesterday",
        "allergies": [],
        "vitals": {"temp_c": 37.1, "heart_rate": 90},
    }
    memory = _build_memory(
        chief_complaint=payload["chief_complaint"],
        onset_time="yesterday",
        symptoms=["abdominal pain"],
        vitals=payload["vitals"],
    )
    context = _build_policy_runtime_context(
        chief_complaint=payload["chief_complaint"],
        symptoms=payload["symptoms"],
        message=payload["message"],
    )

    result = validate_surgery_result(None, rule_based_surgery(payload), payload, memory=memory, policy_runtime_context=context)

    assert result["next_step_decision"] == "test_first"
    assert result["needs_second_consultation"] is True
    assert result["needs_second_internal_medicine_consultation"] is True
    assert result["needs_tests"] is True


def test_surgery_round1_can_recommend_orthopedics():
    payload = {
        "chief_complaint": "ankle injury",
        "symptoms": "ankle injury, swelling",
        "message": "I twisted my ankle yesterday during sports, it is swollen, and I have no allergies.",
        "onset_time": "yesterday",
        "allergies": [],
        "vitals": {"temp_c": 36.9, "heart_rate": 86},
    }
    memory = _build_memory(
        chief_complaint=payload["chief_complaint"],
        onset_time="yesterday",
        symptoms=["ankle injury", "swelling"],
        vitals=payload["vitals"],
    )
    context = _build_policy_runtime_context(
        chief_complaint=payload["chief_complaint"],
        symptoms=payload["symptoms"],
        message=payload["message"],
    )

    result = validate_surgery_result(None, rule_based_surgery(payload), payload, memory=memory, policy_runtime_context=context)

    assert result["next_step_decision"] == "recommend_other_clinic"
    assert result["recommended_department"] == "Orthopedics"
    assert result["needs_second_consultation"] is False
    assert result["needs_second_internal_medicine_consultation"] is False


def test_surgery_round1_escalates_postoperative_fever_and_pus():
    payload = {
        "chief_complaint": "postoperative wound problem",
        "symptoms": "postoperative wound pain",
        "message": "After surgery I now have fever and pus from the wound, and the pain is getting worse.",
        "onset_time": "today",
        "allergies": [],
        "vitals": {"temp_c": 38.7, "heart_rate": 112},
    }
    memory = _build_memory(
        chief_complaint=payload["chief_complaint"],
        onset_time="today",
        symptoms=["postoperative wound pain", "fever", "pus"],
        vitals=payload["vitals"],
    )
    context = _build_policy_runtime_context(
        chief_complaint=payload["chief_complaint"],
        symptoms=payload["symptoms"],
        message=payload["message"],
    )

    result = validate_surgery_result(None, rule_based_surgery(payload), payload, memory=memory, policy_runtime_context=context)

    assert result["next_step_decision"] == "urgent_escalation"
    assert result["needs_second_consultation"] is False
    assert result["needs_second_internal_medicine_consultation"] is False
    assert result["priority"] == "H"
    assert result["red_flags"]


def test_surgery_final_result_matches_internal_round1_contract():
    payload = {
        "chief_complaint": "minor cut",
        "symptoms": "minor cut",
        "message": "I have a minor cut since yesterday and no allergies.",
        "onset_time": "yesterday",
        "allergies": [],
        "vitals": {"temp_c": 36.8, "heart_rate": 80},
    }
    memory = _build_memory(
        chief_complaint=payload["chief_complaint"],
        onset_time="yesterday",
        symptoms=["minor cut"],
        vitals=payload["vitals"],
    )
    context = _build_policy_runtime_context(
        chief_complaint=payload["chief_complaint"],
        symptoms=payload["symptoms"],
        message=payload["message"],
    )
    result = validate_surgery_result(None, rule_based_surgery(payload), payload, memory=memory, policy_runtime_context=context)

    expected_keys = {
        "department",
        "priority",
        "diagnosis_level",
        "note",
        "patient_plan",
        "tests_suggested",
        "medication_or_action",
        "red_flags",
        "test_required",
        "test_category",
        "test_items",
        "test_reason",
        "next_step_decision",
        "needs_second_consultation",
        "needs_second_internal_medicine_consultation",
        "next_step_reason",
        "clinical_impression",
        "needs_tests",
        "needs_medication",
        "recommended_department",
        "recommended_department_reason",
        "disposition_advice",
    }
    assert expected_keys.issubset(result.keys())
