from app.agents.internal_medicine.prompts import build_follow_up_llm_messages as build_internal_follow_up_llm_messages
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
