from app.agents.department_runtime.prompting import (
    build_shared_consultation_user_prompt,
    build_shared_follow_up_llm_messages,
    build_shared_physical_exam_decision_llm_messages,
    build_shared_physical_exam_result_llm_messages,
)
from app.agents.internal_medicine.prompts import (
    build_consultation_user_prompt as build_internal_consultation_user_prompt,
    build_follow_up_llm_messages as build_internal_follow_up_llm_messages,
)
from app.agents.surgery.prompts import (
    build_consultation_system_prompt as build_surgery_system_prompt,
    build_consultation_user_prompt as build_surgery_user_prompt,
    build_follow_up_llm_messages as build_surgery_follow_up_llm_messages,
    build_initial_message as build_surgery_initial_message,
)


def test_surgery_round2_system_and_user_prompts_share_reassessment_context():
    shared_memory = {
        "clinical_memory": {
            "chief_complaint": "abdominal pain",
            "symptoms": ["abdominal pain", "vomiting"],
        }
    }
    payload = {
        "consultation_round": 2,
        "previous_round_summary": {
            "assistant_message": "Initial surgery assessment favored further tests first.",
            "next_step_decision": "test_first",
        },
        "simulated_report": {
            "report_text": "Ultrasound did not show free fluid.",
        },
        "diagnostic_session": {
            "window_label": "Ultrasound Room 2",
        },
    }

    system_prompt = build_surgery_system_prompt(consultation_round=2)
    user_prompt = build_surgery_user_prompt(
        shared_memory,
        "Pain is still there but slightly better.",
        ["allergies"],
        payload=payload,
        historical_records_template={"current_visit": {"summary": {"entry_count": 2}}},
    )

    assert "二轮面诊" in system_prompt
    assert "问诊轮次：第 2 轮" in user_prompt
    assert "上一轮摘要" in user_prompt
    assert "Ultrasound did not show free fluid." in user_prompt
    assert "这是二轮面诊" in user_prompt
    assert "primary_disposition" in user_prompt
    assert "medication_recommendation" in user_prompt
    assert "followup_recommendation" in user_prompt


def test_surgery_round2_followup_prompt_uses_shared_second_round_scaffold():
    messages = build_surgery_follow_up_llm_messages(
        {
            "clinical_memory": {
                "chief_complaint": "wound pain",
                "symptoms": ["wound pain"],
            }
        },
        "The wound is still painful today.",
        ["allergies"],
        question_focus="allergies",
        payload={
            "consultation_round": 2,
            "previous_round_summary": {"assistant_message": "Need wound reassessment after tests."},
            "simulated_report": {"report_text": "No retained foreign body seen."},
        },
    )

    assert "二轮面诊追问助手" in messages[0]["content"]
    assert "上一轮摘要" in messages[1]["content"]
    assert "No retained foreign body seen." in messages[1]["content"]


def test_shared_followup_prompt_lists_known_vitals_and_hides_vital_rules():
    messages = build_shared_follow_up_llm_messages(
        {
            "clinical_memory": {
                "chief_complaint": "cough and sore throat",
                "symptoms": ["cough", "sore throat"],
                "vitals": {"temp_c": 37.7, "heart_rate": 88},
            }
        },
        "",
        ["onset_time"],
        question_focus="onset_time",
        payload={
            "consultation_round": 1,
            "recent_turns": [{"role": "user", "content": "I have yellow sputum."}],
        },
        language="en",
        assistant_label="Internal Medicine",
    )

    assert "Recent turns" in messages[1]["content"]
    assert "I have yellow sputum." in messages[1]["content"]
    assert "Known vital signs" in messages[1]["content"]
    assert '"temp_c": 37.7' in messages[1]["content"]
    assert '"heart_rate": 88' in messages[1]["content"]
    assert "do not ask for body temperature or whether the patient has fever" in messages[0]["content"]
    assert "assistant_message must first include one short patient-facing, non-diagnostic analysis" in messages[0]["content"]
    assert "Do not expose internal strategy" in messages[0]["content"]
    assert "Do not repeat questions already answered" in messages[0]["content"]
    assert "Internal rule" not in messages[1]["content"]


def test_internal_medicine_round1_conclusion_prompt_requires_explicit_test_items():
    prompt = build_internal_consultation_user_prompt(
        {"clinical_memory": {"chief_complaint": "cough", "symptoms": ["cough"]}},
        "The cough is worse.",
        [],
        payload={"consultation_round": 1},
    )

    assert "test_required=true" in prompt
    assert "test_items must be a non-empty array" in prompt
    assert "naturally mention those exact items" in prompt
    assert "vague wording" in prompt
    assert "tentative diagnosis direction" in prompt


def test_surgery_round1_system_prompt_allows_tentative_impression_without_definitive_diagnosis():
    prompt = build_surgery_system_prompt(consultation_round=1)

    assert "初步考虑" in prompt
    assert "更像是" in prompt
    assert "不要写成已经确诊" in prompt


def test_surgery_initial_message_mentions_known_triage_vitals():
    message = build_surgery_initial_message(
        {
            "clinical_memory": {
                "chief_complaint": "术后伤口红肿",
                "symptoms": ["伤口红肿"],
                "vitals": {"temp_c": 37.2, "heart_rate": 88, "pain_score": 2},
            }
        },
        type("Progress", (), {"patient_reply_count": 0})(),
    )

    assert "体温37.2℃" in message
    assert "心率88次/分" in message
    assert "疼痛评分2分" in message
    assert "分诊生命体征整体还算平稳" in message


def test_shared_physical_exam_prompts_define_basic_exam_contract():
    shared_memory = {
        "clinical_memory": {
            "chief_complaint": "cough and sore throat",
            "symptoms": ["cough", "sore throat"],
            "vitals": {"temp_c": 37.2},
        }
    }
    payload = {"consultation_round": 1}
    decision_messages = build_shared_physical_exam_decision_llm_messages(
        shared_memory,
        "My throat hurts when I cough.",
        ["allergies"],
        payload=payload,
        language="en",
        assistant_label="Internal Medicine",
    )
    result_messages = build_shared_physical_exam_result_llm_messages(
        shared_memory,
        "My throat hurts when I cough.",
        {
            "exam_needed": True,
            "exam_type": "respiratory_basic_exam",
            "exam_targets": ["throat", "lung auscultation"],
        },
        payload=payload,
        language="en",
        assistant_label="Internal Medicine",
    )

    assert "exam_needed" in decision_messages[1]["content"]
    assert "doctor_action_message" in decision_messages[1]["content"]
    assert "Known vital signs" in decision_messages[1]["content"]
    assert '"temp_c": 37.2' in decision_messages[1]["content"]
    assert "Do not order or invent laboratory, imaging, pathology" in decision_messages[0]["content"]
    assert "physical_exam" in result_messages[1]["content"]
    assert "llm_simulated_physical_exam" in result_messages[1]["content"]
    assert "Do not create laboratory, imaging, pathology" in result_messages[0]["content"]
    assert "must report completed findings" in result_messages[0]["content"]
    assert "findings and physical_exam.impression must be non-empty" in result_messages[0]["content"]
    assert "Do not output an action sentence" in result_messages[1]["content"]


def test_surgery_round2_initial_message_mentions_second_round():
    message = build_surgery_initial_message(
        {
            "clinical_memory": {
                "chief_complaint": "wound pain",
                "symptoms": ["wound pain"],
            }
        },
        type("Progress", (), {"patient_reply_count": 0})(),
        consultation_round=2,
    )

    assert "外科二轮复诊" in message
    assert "外科初步问诊" not in message


def test_internal_medicine_round2_followup_prompt_remains_chinese():
    messages = build_internal_follow_up_llm_messages(
        {
            "clinical_memory": {
                "chief_complaint": "腹痛",
                "symptoms": ["腹痛", "恶心"],
            }
        },
        "化验做完了，现在还是有点不舒服。",
        ["onset_time"],
        question_focus="onset_time",
        payload={
            "consultation_round": 2,
            "previous_round_summary": {"assistant_message": "上一轮建议先做检查再复诊。"},
            "simulated_report": {"report_text": "未见明显急性异常。"},
        },
    )

    assert "二轮" in messages[0]["content"]
    assert "问诊轮次" in messages[1]["content"]
    assert "second-round follow-up assistant" not in messages[0]["content"]


def test_internal_medicine_optional_past_medical_history_followup_prompt_can_skip():
    messages = build_internal_follow_up_llm_messages(
        {
            "profile": {
                "allergy_status": "known",
                "allergies": [],
                "chronic_conditions": [],
                "chronic_conditions_status": "unknown",
            },
            "clinical_memory": {
                "chief_complaint": "cough",
                "symptoms": ["cough"],
                "onset_time": "yesterday",
            },
        },
        "No drug allergies.",
        [],
        question_focus="past_medical_history",
        payload={
            "consultation_round": 1,
            "optional_followup_focus": "past_medical_history",
        },
    )

    assert "past medical history is optional" in messages[0]["content"]
    assert "empty assistant_message" in messages[0]["content"]
    assert "Do not combine this with medication or allergy history" in messages[0]["content"]
    assert "Optional follow-up focus: past_medical_history" in messages[1]["content"]


def test_shared_prompt_marks_referral_handoff_as_fresh_receiving_doctor_visit():
    prompt = build_shared_consultation_user_prompt(
        {
            "profile": {"name": "Patient"},
            "clinical_memory": {"chief_complaint": None, "symptoms": []},
        },
        "Pain is still present today.",
        ["chief_complaint"],
        payload={
            "consultation_round": 1,
            "consultation_context": {
                "intake_mode": "referral_handoff",
                "doctor_memory_policy": "chart_only",
            },
            "chart_view": {
                "handoff": {
                    "special_event_type": "specialty_referral",
                    "recommended_department": "Surgery",
                }
            },
        },
        language="en",
        round1_response_keys="department, priority",
        default_response_keys="primary_disposition",
    )

    assert "receiving-doctor consultation after referral" in prompt
    assert "Consultation context" in prompt
    assert "Doctor chart view" in prompt
