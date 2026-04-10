from pathlib import Path

from app.agents.internal_medicine.workflow import ConsultationProgress, STEP_INDEX


RULE_STORE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "internal_medicine_rules.json"


def build_initial_prompt(patient_info: dict) -> str:
    return (
        f"患者信息：{patient_info}\n\n"
        "你是一位内科医生。请用中文与患者对话，了解他的症状，给出诊断和治疗建议。"
        "如果患者的问题超出你的能力范围，建议他咨询专科医生。"
    )


def build_step_aware_prompt(
    patient_info: dict,
    conversation_history: list[dict],
    retrieved_rules: list[dict],
    consultation_progress: ConsultationProgress,
) -> str:
    current_step = consultation_progress.current_step.value
    collected = consultation_progress.collected_info

    history_text = "\n".join([f"{t.get('role', 'user')}：{t.get('message', '')}" for t in conversation_history])

    collected_text = "\n".join([f"{k}: {v}" for k, v in collected.items()]) if collected else "无"

    return f"""
你是一位经验丰富的内科医生。请用中文与患者进行问诊。

## 工作流程
1. 收集患者的主诉和症状
2. 了解发病时间、伴随症状等信息
3. 询问既往病史、过敏史、用药史
4. 给出初步诊断
5. 制定治疗方案
6. 询问患者对治疗方案的反馈（药量是否合适）
7. 根据反馈调整或确认方案
8. 完成问诊

## 当前进度
步骤：{current_step}
已收集信息：
{collected_text}

## 对话历史
{history_text}

## 患者基本信息
{patient_info}

## RAG参考（仅参考，不要拘泥）
{retrieved_rules}

请继续问诊。如果患者描述了症状，你应该基于医学知识给出分析和建议。
如果患者问问题，直接回答。保持自然对话，不要机械地走流程。
""".strip()


def _format_collected_info(collected: dict) -> str:
    if not collected:
        return "无"
    lines = []
    for key, value in collected.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def build_diagnosis_prompt(patient_info: dict, retrieved_rules: list[dict]) -> str:
    return (
        f"患者信息：{patient_info}\n"
        f"RAG参考：{retrieved_rules}\n\n"
        "你是一位经验丰富的内科医生。请根据患者的症状给出诊断和治疗建议，用自然的中文对话形式回复患者。"
        "例如：'根据您说的症状，尿急和失眠可能是因为最近休息不好导致的尿路感染，我先给您开一些清热利尿的药，同时建议您睡前放松一下，帮助改善睡眠。'"
    )


def build_consultation_prompt(
    patient_info: dict, conversation_history: list[dict], retrieved_rules: list[dict]
) -> str:
    return (
        f"患者信息：{patient_info}\n"
        f"对话历史：{conversation_history}\n"
        f"RAG参考：{retrieved_rules}\n\n"
        "你是一位内科医生。请用中文与患者对话，给出诊断和建议。直接回答患者问题。"
    )


def build_treatment_plan_prompt(patient_info: dict, diagnosis: dict, retrieved_rules: list[dict]) -> str:
    return (
        f"患者信息：{patient_info}\n"
        f"诊断：{diagnosis}\n"
        f"RAG参考：{retrieved_rules}\n\n"
        "根据诊断制定治疗方案。用中文回答。"
    )


def build_follow_up_message(missing_fields: list[str], current_status: dict) -> str:
    if not missing_fields:
        return "问诊完成，祝您早日康复！"
    return f"请告诉我：{missing_fields[0]}"


def build_progress_follow_up(consultation_progress: ConsultationProgress, current_status: dict) -> str:
    if consultation_progress.is_complete():
        return "问诊完成，祝您早日康复！如有不适请随时复诊。"
    return ""


def build_initial_prompt(patient_info: dict) -> str:
    return (
        f"患者信息：{patient_info}\n\n"
        "你是一位内科医生。请用中文与患者对话，了解他的症状，给出诊断和治疗建议。"
    )
