from types import SimpleNamespace

from app.agents.clinical_policy import ClinicalPolicyRuntime
from app.agents.surgery import create_surgery_service
from app.agents.surgery.config import build_surgery_runtime_config
from app.agents.surgery.patient_reply import build_patient_reply
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
    assert config.build_patient_reply is not None


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


def test_surgery_reassessment_reply_answers_question_without_template_prefix():
    message = build_patient_reply(
        {
            "clinical_impression": "这次伤口复查总体稳定，暂时没有看到需要紧急处理的感染迹象",
            "patient_plan": "继续按门诊方案换药和观察伤口恢复情况",
            "followup_recommendation": {
                "revisit_required": True,
                "revisit_window": "2-3 days",
                "revisit_conditions": ["fever", "pus", "worsening pain"],
            },
            "return_precautions": ["fever", "pus", "worsening pain"],
        },
        message_type="final_no_change",
        consultation_round=1,
        reply_style="round1_reassessment",
        reassessment_intent="question_only",
        reply_rendering_mode="answer_only",
        payload={"message": "Do I need to come back soon?"},
    )
    assert "2-3 days" in message
    assert "assessment unchanged" not in message.lower()
    assert "updated assessment" not in message.lower()


def test_surgery_round2_reply_explains_report_in_natural_chinese():
    message = build_patient_reply(
        {
            "clinical_impression": "这次复查结果提示伤口恢复总体平稳，没有看到脓肿或明显感染扩散的证据",
            "final_assessment_summary": "目前更适合继续门诊换药和短期复查，而不是重复做基础检查",
            "patient_facing_plan": "先继续按外科门诊方案换药和观察，按时回来复查伤口变化",
            "followup_recommendation": {
                "revisit_required": True,
                "revisit_window": "48-72小时",
                "revisit_conditions": ["发热", "渗液增多", "疼痛明显加重"],
            },
            "return_precautions": ["发热", "渗液增多", "疼痛明显加重"],
        },
        message_type="final",
        consultation_round=2,
        reply_style="round2_conclusion",
        payload={"message": "报告说明什么？"},
    )
    assert "这次复查结果主要提示" in message
    assert "48-72小时" in message
    assert "primary_disposition" not in message
    assert "procedure_recommendation" not in message
    assert "assessment unchanged" not in message.lower()


def test_surgery_round2_question_only_reassessment_answers_report_without_repeating_schema():
    message = build_patient_reply(
        {
            "clinical_impression": "这次复查结果提示局部软组织恢复平稳，没有看到需要急诊升级的异常",
            "final_assessment_summary": "目前更适合继续门诊观察和短期复诊",
            "patient_facing_plan": "继续按门诊方案观察，如果症状加重再提前回来",
            "followup_recommendation": {
                "revisit_required": True,
                "revisit_window": "2-3天",
                "revisit_conditions": ["肿胀加重", "麻木", "疼痛明显加重"],
            },
            "return_precautions": ["肿胀加重", "麻木", "疼痛明显加重"],
        },
        message_type="final_no_change",
        consultation_round=2,
        reply_style="round2_reassessment",
        reassessment_intent="question_only",
        reply_rendering_mode="answer_only",
        payload={"message": "What does the report show, and do I still need more tests?"},
    )
    assert "这次复查结果主要提示" in message
    assert "暂时没有必要重复基础检查" in message
    assert "基于你刚补充的信息" not in message
    assert "primary_disposition" not in message


def test_surgery_round2_result_update_reassessment_restates_updated_conclusion():
    message = build_patient_reply(
        {
            "clinical_impression": "你刚补充了发热和渗液增多，这提示伤口感染风险比刚才更高",
            "final_assessment_summary": "现在不适合继续单纯门诊观察，建议尽快回外科评估是否需要住院处理",
            "patient_facing_plan": "请今天尽快回外科或急诊处理，由医生当面复查伤口并决定下一步",
            "followup_recommendation": {
                "revisit_required": False,
                "revisit_window": "",
                "revisit_conditions": [],
            },
            "return_precautions": ["高热", "脓性分泌物明显增多", "伤口裂开"],
        },
        message_type="final_update",
        consultation_round=2,
        reply_style="round2_reassessment",
        reassessment_intent="result_update",
        reply_rendering_mode="updated_summary",
        payload={"message": "现在开始发热，而且渗液比刚才多。"},
    )
    assert "基于你刚补充的信息" in message
    assert "伤口感染风险" in message
    assert "尽快回外科或急诊处理" in message
