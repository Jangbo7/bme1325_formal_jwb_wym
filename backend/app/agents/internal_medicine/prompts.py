from app.agents.internal_medicine.workflow import ConsultationProgress


def build_follow_up_question(field_name: str, shared_memory: dict) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "您当前的不适"
    if field_name == "chief_complaint":
        return "请再具体说一下，您现在最困扰的主要不适是什么？"
    if field_name == "onset_time":
        return f"我已经记录到您提到的“{complaint}”。这个症状大概是什么时候开始的，持续多久了？"
    if field_name == "allergies":
        return "在继续给建议前，我需要确认一下您是否有药物过敏或其他已知过敏史。"
    return "我还需要再确认一个细节，方便继续判断。"


def build_transition_follow_up_question(shared_memory: dict) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or ""
    symptoms = shared_memory.get("clinical_memory", {}).get("symptoms") or []
    symptom_text = "、".join([item for item in symptoms if item]) if symptoms else ""
    if complaint and symptom_text:
        return (
            f"关于您提到的“{complaint}”，我再确认一下：除了{symptom_text}之外，"
            "还有没有发热、胸闷、气短、恶心、腹痛或其他新的不适？"
        )
    if complaint:
        return f"关于您提到的“{complaint}”，我再确认一下：现在还有没有新的伴随症状，或者症状有没有加重？"
    return "我再确认一下：除了刚才提到的不适之外，还有没有其他伴随症状，或者病情有没有变化？"


def build_initial_message(shared_memory: dict, progress: ConsultationProgress) -> str:
    complaint = shared_memory.get("clinical_memory", {}).get("chief_complaint") or "您当前的不适"
    if progress.patient_reply_count == 0:
        return (
            f"我看到分诊记录里提到的是“{complaint}”。我继续帮您问诊一下，请告诉我是什么时候开始的，"
            "以及现在最不舒服的地方在哪里。"
        )
    return "我还需要再补充一点信息，才能继续问诊。"


def build_consultation_system_prompt() -> str:
    return (
        "你是内科门诊医生。"
        "只用简体中文回答，不要输出英文。"
        "提问要简短明确，建议要具体实用。"
    )


def build_consultation_user_prompt(shared_memory: dict, message: str, missing_fields: list[str]) -> str:
    return (
        f"Patient shared facts: {shared_memory}\n"
        f"Latest patient message: {message}\n"
        f"Missing fields: {missing_fields}\n"
        "Return JSON with keys: assistant_message, complete(bool), department, priority, diagnosis_level, note."
    )


def build_final_message(result: dict) -> str:
    department = result.get("department") or "Internal Medicine"
    priority = result.get("priority") or "M"
    note = result.get("note") or "This looks like a common outpatient internal medicine issue."
    return (
        f"门诊建议：{department}\n"
        f"优先级：{priority}\n"
        f"{note}\n"
        "本次问诊暂时结束，您可以继续下一步。"
    )
