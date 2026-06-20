from app.agents.department_runtime.prompting import build_shared_post_final_answer_llm_messages


def build_post_final_answer_llm_messages(
    shared_memory: dict,
    message: str,
    final_result: dict,
    *,
    previous_final_result: dict | None = None,
    previous_round_summary: dict | None = None,
    simulated_report: dict | None = None,
    diagnostic_session: dict | None = None,
    historical_records_template: dict | None = None,
    response_mode: str = "answer_only",
    consultation_round: int | None = None,
    **kwargs,
) -> list[dict]:
    del kwargs
    return build_shared_post_final_answer_llm_messages(
        shared_memory,
        message,
        final_result,
        payload={
            "previous_round_summary": previous_round_summary or {},
            "simulated_report": simulated_report or {},
            "diagnostic_session": diagnostic_session or {},
            "historical_records_template": historical_records_template or {},
            "consultation_round": consultation_round,
        },
        previous_final_result=previous_final_result,
        response_mode=response_mode,
        consultation_round=consultation_round,
        language="zh",
        assistant_label="外科门诊医生",
    )
