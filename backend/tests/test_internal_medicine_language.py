from types import SimpleNamespace

from app.agents.clinical_policy import ClinicalPolicyValidatorResult
from app.agents.internal_medicine.patient_reply import build_patient_reply
from app.agents.internal_medicine.policy import (
    build_internal_medicine_policy_fallback,
    validate_internal_medicine_policy_snapshot,
)
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


def test_internal_medicine_initial_message_mentions_known_triage_vitals():
    shared_memory = {
        "clinical_memory": {
            "chief_complaint": "咳嗽咽痛",
            "symptoms": ["咳嗽", "咽痛"],
            "vitals": {"temp_c": 37.8, "heart_rate": 92, "pain_score": 3},
        }
    }
    progress = ConsultationProgress(patient_reply_count=0)

    initial_message = build_initial_message(shared_memory, progress)

    assert "体温37.8℃" in initial_message
    assert "心率92次/分" in initial_message
    assert "疼痛评分3分" in initial_message
    assert "体温有点高" in initial_message
    assert "我会多问" not in initial_message
    assert "说明这次需要重点看" not in initial_message


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


def test_internal_medicine_policy_validator_ignores_patient_medication_history_false_positive():
    snapshot = {
        "agent_role": "internal_medicine_agent",
        "consultation_stage": "history_taking",
        "chief_complaint": "头晕乏力 2 天",
        "key_symptoms_collected": ["降压药一直按时吃，没有自己调整过剂量", "血压 100/65 左右"],
        "missing_information": [],
        "red_flags": [],
        "urgency": "routine",
        "follow_up_questions": ["您这两天自己量的血压具体是多少？"],
        "patient_summary": "患者表示一直按时吃药，没有自己调整过剂量。",
        "next_action": "ask_follow_up",
    }
    validation_result = ClinicalPolicyValidatorResult(
        ok=False,
        violations=[
            "forbidden action detected: prescribe_medication",
            "forbidden action detected: change_dosage",
        ],
        normalized_output=dict(snapshot),
        fallback_reason="forbidden action detected: prescribe_medication; forbidden action detected: change_dosage",
    )

    result = validate_internal_medicine_policy_snapshot(snapshot, None, {}, validation_result=validation_result)

    assert result.ok is True
    assert result.violations == []


def test_internal_medicine_policy_validator_keeps_real_medication_directive_violation():
    snapshot = {
        "agent_role": "internal_medicine_agent",
        "consultation_stage": "history_taking",
        "chief_complaint": "头晕乏力 2 天",
        "key_symptoms_collected": ["降压药一直按时吃，没有自己调整过剂量"],
        "missing_information": [],
        "red_flags": [],
        "urgency": "routine",
        "follow_up_questions": ["建议先把降压药剂量减半，再观察今天的血压变化。"],
        "patient_summary": "患者表示一直按时吃药，没有自己调整过剂量。",
        "next_action": "ask_follow_up",
    }
    validation_result = ClinicalPolicyValidatorResult(
        ok=False,
        violations=["forbidden action detected: change_dosage"],
        normalized_output=dict(snapshot),
        fallback_reason="forbidden action detected: change_dosage",
    )

    result = validate_internal_medicine_policy_snapshot(snapshot, None, {}, validation_result=validation_result)

    assert result.ok is False
    assert result.violations == ["forbidden action detected: change_dosage"]


def test_internal_medicine_policy_fallback_uses_snapshot_red_flags_when_result_is_empty():
    class _PolicyRuntime:
        def __init__(self):
            self.payload = None

        def build_safe_fallback(self, policy_runtime_context, payload, reason):
            del policy_runtime_context, reason
            self.payload = payload
            return {
                "next_action": "escalate_urgency",
                "missing_information": [],
                "red_flags": list(payload.get("red_flags") or []),
                "follow_up_questions": [],
            }

    runtime = _PolicyRuntime()
    memory = SimpleNamespace(
        shared_memory={"clinical_memory": {"chief_complaint": "头晕", "symptoms": ["头晕"]}},
        private_memory={"missing_fields": []},
    )
    validation_result = ClinicalPolicyValidatorResult(
        ok=False,
        violations=["forbidden action detected: prescribe_medication"],
        normalized_output={
            "red_flags": ["neurological_alert"],
            "follow_up_questions": ["请描述是否有肢体无力。"],
        },
        fallback_reason="forbidden action detected: prescribe_medication",
    )

    result = build_internal_medicine_policy_fallback(
        None,
        {},
        "validator_failed",
        snapshot={"red_flags": ["older_flag"]},
        validation_result=validation_result,
        memory=memory,
        consultation_result={},
        policy_runtime=runtime,
    )

    assistant_message = result["assistant_payload"]["assistant_message"]
    assert runtime.payload["red_flags"] == ["neurological_alert"]
    assert result["consultation_result"]["red_flags"] == ["neurological_alert"]
    assert result["consultation_result"]["priority"] == "H"
    assert "Please" not in assistant_message


def test_internal_medicine_round1_test_reply_prefers_natural_patient_plan_with_items():
    message = build_patient_reply(
        {
            "clinical_impression": "目前信息还不足以支持直接处理，建议先完善辅助检查。",
            "patient_plan": "建议先完成血常规和C反应蛋白，结果出来后再回来复诊",
            "tests_suggested": ["血常规", "C反应蛋白"],
            "test_items": ["血常规", "C反应蛋白"],
        },
        message_type="final",
        consultation_round=1,
        payload={},
    )

    assert "血常规" in message
    assert "C反应蛋白" in message
    assert "已为你开具" in message
    assert "结果出来后带来复诊" in message
    assert "建议先完成" not in message
    assert "根据你目前提供的情况，目前信息还不足" not in message
    assert message.count("回来") <= 1


def test_internal_medicine_round1_test_reply_names_items_without_generic_ordering():
    message = build_patient_reply(
        {
            "clinical_impression": "目前信息还不足以支持直接处理，建议先完善辅助检查。",
            "patient_plan": "请先完善辅助检查",
            "tests_suggested": ["血常规", "C反应蛋白"],
            "test_items": ["血常规", "C反应蛋白"],
        },
        message_type="final",
        consultation_round=1,
        payload={},
    )

    assert "血常规" in message
    assert "C反应蛋白" in message
    assert "已为你开具" in message
    assert "拿到结果后" in message or "结果出来后" in message
    assert "辅助检查" not in message
    assert "根据你目前提供的情况，目前信息还不足" not in message


def test_internal_medicine_round1_test_reply_keeps_tentative_impression():
    message = build_patient_reply(
        {
            "clinical_impression": "初步考虑上呼吸道感染或急性支气管炎可能",
            "patient_plan": "请先完成血常规、C反应蛋白检查，结果出来后再回来复诊",
            "tests_suggested": ["血常规", "C反应蛋白"],
            "test_items": ["血常规", "C反应蛋白"],
        },
        message_type="final",
        consultation_round=1,
        payload={},
    )

    assert "初步考虑上呼吸道感染或急性支气管炎可能" in message
    assert "我已为你开具血常规、C反应蛋白检查" in message
    assert "结果出来后带来复诊" in message
    assert "建议先完善辅助检查" not in message
    assert message.count("回来") <= 1


def test_internal_medicine_round1_test_reply_never_hides_item_names_as_these_tests():
    message = build_patient_reply(
        {
            "clinical_impression": "初步考虑急性上呼吸道感染，暂不能排除细菌感染",
            "patient_plan": "请完成已开具的检查，再带结果回来内科复诊",
            "tests_suggested": ["血常规", "C反应蛋白"],
            "test_items": ["血常规", "C反应蛋白"],
        },
        message_type="final",
        consultation_round=1,
        payload={},
    )

    assert "血常规" in message
    assert "C反应蛋白" in message
    assert "这些检查" not in message
    assert "具体项目是血常规、C反应蛋白" in message


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


def test_internal_medicine_round2_patient_reply_filters_english_and_names_specific_drugs():
    message = build_patient_reply(
        {
            "clinical_impression": "Confirmed H. pylori-positive gastritis based on positive breath test and typical symptoms.",
            "final_assessment_summary": "No evidence of complications or need for urgent intervention.",
            "patient_facing_plan": "You have a stomach infection caused by H. pylori and need a 14-day antibiotic course.",
            "primary_disposition": "outpatient_management",
            "medication_recommendation": {
                "recommended": True,
                "intent": "h_pylori_eradication",
                "summary": "Prescribe triple therapy.",
            },
            "prescription_plan": [
                {
                    "drug_name": "奥美拉唑",
                    "dose_text": "20mg",
                    "frequency_text": "每日2次",
                    "duration_text": "14天",
                    "instructions": "早晚餐前服用",
                },
                {
                    "drug_name": "甲硝唑",
                    "dose_text": "500mg",
                    "frequency_text": "每日3-4次",
                    "duration_text": "14天",
                    "instructions": "用药期间避免饮酒",
                },
            ],
        },
        message_type="final",
        consultation_round=2,
        reply_style="round2_conclusion",
        payload={},
    )

    assert "Confirmed" not in message
    assert "No evidence" not in message
    assert "You have" not in message
    assert "Prescribe triple therapy" not in message
    assert "这次检查结果支持按门诊方案用药处理" in message
    assert "奥美拉唑，20mg，每日2次，14天，早晚餐前服用" in message
    assert "甲硝唑，500mg，每日3-4次，14天，用药期间避免饮酒" in message


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
