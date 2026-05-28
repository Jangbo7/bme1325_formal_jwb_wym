from types import SimpleNamespace

from app.agents.internal_medicine.policy import build_internal_medicine_policy_fallback
from app.agents.internal_medicine.prompts import (
    build_final_message,
    build_follow_up_llm_messages,
    build_initial_message,
)
from app.agents.internal_medicine.workflow import ConsultationProgress


def test_internal_medicine_initial_and_followup_prompts_are_chinese():
    shared_memory = {
        "clinical_memory": {
            "chief_complaint": "头晕",
            "symptoms": ["头晕", "乏力"],
        }
    }
    progress = ConsultationProgress(patient_reply_count=0)

    initial_message = build_initial_message(shared_memory, progress)
    assert "内科" in initial_message
    assert "什么时候开始" in initial_message
    assert "Please" not in initial_message

    llm_messages = build_follow_up_llm_messages(
        shared_memory,
        "还是有点不舒服",
        ["onset_time"],
        question_focus="onset_time",
    )
    assert "中文追问" in llm_messages[0]["content"]
    assert "Generate one natural follow-up question" not in llm_messages[1]["content"]


def test_internal_medicine_final_message_uses_chinese_labels():
    message = build_final_message(
        {
            "department": "Internal Medicine",
            "priority": "M",
            "clinical_impression": "目前更像是常见的低风险内科门诊问题。",
            "disposition_advice": "建议先休息补水，如有加重及时复诊。",
            "tests_suggested": [],
            "medication_or_action": ["继续观察症状变化"],
            "red_flags": [],
            "next_step_decision": "treat_and_discharge",
            "needs_second_internal_medicine_consultation": False,
        }
    )
    assert "建议科室：内科" in message
    assert "优先级：" in message
    assert "下一步建议：" in message
    assert "Department:" not in message
    assert "Priority:" not in message
    assert "Patient plan:" not in message


def test_internal_medicine_policy_fallback_message_is_chinese():
    class _PolicyRuntime:
        @staticmethod
        def build_safe_fallback(policy_runtime_context, payload, reason):
            del policy_runtime_context, payload, reason
            return {
                "next_action": "escalate_urgency",
                "missing_information": [],
                "red_flags": ["高危信号"],
                "follow_up_questions": [],
            }

    memory = SimpleNamespace(
        shared_memory={"clinical_memory": {"chief_complaint": "胸痛", "symptoms": ["胸痛"]}},
        private_memory={"missing_fields": []},
    )

    result = build_internal_medicine_policy_fallback(
        None,
        {},
        "validator_failed",
        memory=memory,
        consultation_result={},
        policy_runtime=_PolicyRuntime(),
    )
    assistant_message = result["assistant_payload"]["assistant_message"]
    assert "请" in assistant_message
    assert "Please" not in assistant_message
    assert "urgent assessment" not in assistant_message
