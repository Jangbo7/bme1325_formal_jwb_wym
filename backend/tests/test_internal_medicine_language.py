from types import SimpleNamespace

from app.agents.internal_medicine.patient_reply import build_patient_reply
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


def test_internal_medicine_round2_initial_message_mentions_second_round():
    shared_memory = {
        "clinical_memory": {
            "chief_complaint": "腹痛",
            "symptoms": ["腹痛"],
        }
    }
    progress = ConsultationProgress(patient_reply_count=0)

    initial_message = build_initial_message(shared_memory, progress, consultation_round=2)
    assert "二轮" in initial_message
    assert "初步问诊" not in initial_message


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
    assert "建议科室" in message
    assert "优先级" in message
    assert "下一步建议" in message
    assert "Department:" not in message


def test_internal_medicine_round2_final_message_prefers_report_review_conclusion():
    message = build_final_message(
        {
            "department": "Internal Medicine",
            "priority": "L",
            "clinical_impression": "检查提示幽门螺杆菌阳性，结合症状更像胃炎相关问题。",
            "final_assessment_summary": "本轮重点应直接给出门诊处理和复诊建议，而不是重复基础检查。",
            "primary_disposition": "outpatient_management",
            "patient_facing_plan": "建议结合报告制定门诊治疗方案，并安排后续复诊。",
            "medication_recommendation": {
                "recommended": True,
                "intent": "targeted_treatment",
                "summary": "建议评估抑酸治疗，并结合结果决定是否启动根除方案。",
            },
            "followup_recommendation": {
                "observation_required": False,
                "observation_setting": "none",
                "revisit_required": True,
                "revisit_window": "1-2周",
                "revisit_conditions": ["腹痛持续加重", "出现黑便"],
            },
            "tests_suggested": [],
            "return_precautions": ["黑便", "呕血"],
        }
    )
    assert "二轮结论" in message
    assert "报告解读" in message
    assert "当前不建议重复基础检查" in message
    assert "建议检查：血常规" not in message


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


def test_internal_medicine_round2_patient_reply_is_natural_and_mentions_prescription_plan():
    message = build_patient_reply(
        {
            "clinical_impression": "检查提示幽门螺杆菌阳性，结合上腹烧灼痛，更像胃炎或消化性溃疡相关问题。",
            "final_assessment_summary": "目前不需要重复基础检查，重点是结合报告制定治疗和复诊安排。",
            "patient_facing_plan": "建议先按门诊方案治疗，并在 1-2 周内复诊。",
            "prescription_plan": [
                {
                    "drug_name": "质子泵抑制剂",
                    "dose_text": "按常规门诊剂量",
                    "frequency_text": "每日 1-2 次",
                    "duration_text": "2-4 周",
                    "instructions": "餐前服用",
                    "requires_doctor_review": True,
                }
            ],
            "followup_recommendation": {
                "revisit_required": True,
                "revisit_window": "1-2周",
                "revisit_conditions": ["黑便", "呕血"],
            },
            "return_precautions": ["黑便", "呕血"],
        },
        message_type="final",
        consultation_round=2,
        reply_style="round2_conclusion",
        changed_fields=[],
        update_reason=None,
        payload={"message": "我的报告有什么问题？"},
    )
    assert "建议科室" not in message
    assert "主去向" not in message
    assert "幽门螺杆菌阳性" in message
    assert "质子泵抑制剂" in message
    assert "1-2周" in message


def test_internal_medicine_round2_question_only_reassessment_answers_report_without_repeating_unchanged_judgment():
    message = build_patient_reply(
        {
            "clinical_impression": "检查提示幽门螺杆菌阳性，结合上腹烧灼痛，更像胃炎或消化性溃疡相关问题。",
            "final_assessment_summary": "目前不需要重复基础检查，重点是结合报告制定治疗和复诊安排。",
            "patient_facing_plan": "建议先按门诊方案治疗，并在 1-2 周内复诊。",
            "followup_recommendation": {
                "revisit_required": True,
                "revisit_window": "1-2周",
                "revisit_conditions": ["黑便", "呕血"],
            },
            "return_precautions": ["黑便", "呕血"],
        },
        message_type="final_no_change",
        consultation_round=2,
        reply_style="round2_reassessment",
        changed_fields=[],
        update_reason="test_update",
        reassessment_intent="question_only",
        reply_rendering_mode="answer_only",
        payload={"message": "我的报告有什么问题？"},
    )
    assert "这次报告主要提示" in message
    assert "目前我的判断没有明显变化" not in message
    assert "我把这次复诊的判断再更新一下" not in message


def test_internal_medicine_round2_result_update_reassessment_restates_summary_after_change():
    message = build_patient_reply(
        {
            "clinical_impression": "这次补充的信息提示有消化道出血风险，需要提高警惕。",
            "final_assessment_summary": "相比之前的门诊随访方案，现在更需要尽快复诊并重新评估处理优先级。",
            "patient_facing_plan": "建议尽快回诊，必要时加快处理。",
            "return_precautions": ["黑便", "呕血"],
        },
        message_type="final_update",
        consultation_round=2,
        reply_style="round2_reassessment",
        changed_fields=["priority", "return_precautions"],
        update_reason="safety_flag",
        reassessment_intent="result_update",
        reply_rendering_mode="updated_summary",
        payload={"message": "现在有黑便，而且比昨天更痛。"},
    )
    assert "基于你刚补充的信息" in message
    assert "需要提高警惕" in message
    assert "建议尽快回诊" in message
