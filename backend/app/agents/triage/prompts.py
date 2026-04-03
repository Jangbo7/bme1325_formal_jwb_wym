FIELD_PROMPTS = {
    "chief_complaint": [
        "\u60f3\u5148\u786e\u8ba4\u4e00\u4e0b\uff0c\u60a8\u8fd9\u6b21\u6700\u60f3\u89e3\u51b3\u7684\u4e0d\u8212\u670d\u662f\u4ec0\u4e48\uff1f",
        "\u65b9\u4fbf\u7528\u4e00\u53e5\u8bdd\u8bf4\u4e0b\uff0c\u8fd9\u6b21\u6700\u4e3b\u8981\u7684\u95ee\u9898\u662f\u4ec0\u4e48\u5417\uff1f",
    ],
    "symptoms": [
        "\u80fd\u518d\u5177\u4f53\u63cf\u8ff0\u4e00\u4e0b\u75c7\u72b6\u5417\uff1f\u6bd4\u5982\u662f\u75bc\u3001\u95f7\u3001\u80c0\uff0c\u8fd8\u662f\u547c\u5438\u4e0d\u8212\u670d\u3002",
        "\u8bf7\u518d\u5177\u4f53\u4e00\u70b9\u63cf\u8ff0\u73b0\u5728\u7684\u4e0d\u9002\uff0c\u8fd9\u6837\u6211\u624d\u80fd\u66f4\u51c6\u786e\u5224\u65ad\u3002",
    ],
    "onset_time": [
        "\u60f3\u518d\u786e\u8ba4\u4e00\u4e2a\u5173\u952e\u65f6\u95f4\u70b9\uff1a\u8fd9\u4e9b\u75c7\u72b6\u5927\u6982\u662f\u4ece\u4ec0\u4e48\u65f6\u5019\u5f00\u59cb\u7684\uff1f",
        "\u8fd9\u4e9b\u4e0d\u8212\u670d\u662f\u4eca\u5929\u624d\u5f00\u59cb\uff0c\u8fd8\u662f\u6628\u665a\u3001\u4eca\u65e9\u5c31\u6709\u4e86\uff1f",
        "\u5982\u679c\u8bb0\u4e0d\u6e05\u5177\u4f53\u65f6\u95f4\uff0c\u4e5f\u53ef\u4ee5\u544a\u8bc9\u6211\u662f\u4eca\u5929\u65e9\u4e0a\u3001\u6628\u665a\uff0c\u8fd8\u662f\u5927\u6982\u51e0\u4e2a\u5c0f\u65f6\u4e86\u3002",
    ],
    "temp_c": [
        "\u6700\u8fd1\u91cf\u8fc7\u4f53\u6e29\u5417\uff1f\u5982\u679c\u6ca1\u91cf\uff0c\u4e5f\u53ef\u4ee5\u544a\u8bc9\u6211\u6709\u6ca1\u6709\u53d1\u70ed\u6216\u6015\u51b7\u3002",
        "\u60f3\u786e\u8ba4\u4e00\u4e0b\u4f53\u6e29\u60c5\u51b5\uff1a\u6709\u53d1\u70e7\u3001\u53d1\u70ed\u611f\uff0c\u6216\u8005\u91cf\u5230\u591a\u5c11\u5ea6\u5417\uff1f",
    ],
    "pain_score": [
        "\u5982\u679c 0 \u5206\u662f\u4e0d\u75db\uff0c10 \u5206\u662f\u6700\u75db\uff0c\u73b0\u5728\u5927\u6982\u80fd\u6253\u51e0\u5206\uff1f",
        "\u75bc\u75db\u5927\u6982\u6709\u591a\u660e\u663e\uff1f\u5982\u679c\u65b9\u4fbf\u7684\u8bdd\uff0c\u53ef\u4ee5\u7528 0 \u5230 10 \u5206\u63cf\u8ff0\u4e00\u4e0b\u3002",
        "\u5982\u679c\u4e0d\u597d\u91cf\u5316\uff0c\u4e5f\u53ef\u4ee5\u8bf4\u662f\u8f7b\u5fae\u3001\u4e2d\u7b49\uff0c\u8fd8\u662f\u5f88\u660e\u663e\u7684\u75bc\u3002",
    ],
    "allergies": [
        "\u8fd8\u6709\u4e00\u4e2a\u5e38\u89c4\u95ee\u9898\uff1a\u4ee5\u524d\u6709\u53d1\u73b0\u836f\u7269\u6216\u98df\u7269\u8fc7\u654f\u5417\uff1f",
        "\u60f3\u786e\u8ba4\u4e00\u4e0b\u8fc7\u654f\u60c5\u51b5\uff0c\u5df2\u77e5\u6709\u6ca1\u6709\u836f\u7269\u6216\u98df\u7269\u8fc7\u654f\uff1f",
    ],
}


def build_follow_up_system_prompt() -> str:
    return (
        "\u4f60\u662f\u533b\u9662\u5206\u8bca\u62a4\u58eb\uff0c\u8981\u6839\u636e\u5f53\u524d\u5df2\u77e5\u4fe1\u606f\u751f\u6210\u4e00\u6761\u81ea\u7136\u3001\u514b\u5236\u3001\u9762\u5411\u60a3\u8005\u7684\u8ffd\u95ee\u3002"
        "\u5fc5\u987b\u9075\u5b88\u8fd9\u4e9b\u89c4\u5219\uff1a"
        "1. \u53ea\u80fd\u56f4\u7ed5\u7ed9\u5b9a\u7684\u7f3a\u5931\u5b57\u6bb5\u8ffd\u95ee\uff1b"
        "2. \u4e0d\u8981\u7ed9\u8bca\u65ad\u6216\u6cbb\u7597\u5efa\u8bae\uff1b"
        "3. \u5355\u6b21\u6700\u591a\u4e24\u53e5\uff1b"
        "4. \u4ee5\u4e2d\u6587\u4e3a\u4e3b\uff0c\u53ef\u4fdd\u7559\u82f1\u6587\u79d1\u5ba4\u540d\uff1b"
        "5. \u5982\u679c\u5f53\u524d\u5206\u8bca\u5efa\u8bae\u6ca1\u6709\u53d8\u5316\uff0c\u9ed8\u8ba4\u4e0d\u8981\u91cd\u590d\u79d1\u5ba4\u548c\u4f18\u5148\u7ea7\uff1b"
        "6. \u5982\u679c\u98ce\u9669\u8f83\u9ad8\uff0c\u53ef\u4ee5\u5148\u7528\u4e00\u53e5\u77ed\u63d0\u793a\uff0c\u518d\u8ffd\u95ee\u4e00\u4e2a\u5173\u952e\u95ee\u9898\uff1b"
        "7. \u8fd4\u56de\u4e25\u683c JSON\uff0c\u5305\u542b assistant_message, question_focus, mention_recommendation, style_tag\u3002"
    )


def build_follow_up_user_prompt(
    *,
    triage_result: dict,
    missing_fields: list[str],
    patient_summary: dict,
    turns: list[dict],
    risk_flags: list[str],
    last_question_focus: str | None,
    last_question_text: str | None,
    asked_fields_history: list[str],
    recommendation_changed: bool,
) -> str:
    recent_turns = turns[-5:] if turns else []
    return (
        "\u8bf7\u57fa\u4e8e\u4e0b\u9762\u4fe1\u606f\u751f\u6210\u4e0b\u4e00\u53e5\u5206\u8bca\u8ffd\u95ee\u3002"
        f" \u5f53\u524d\u5206\u8bca\u7ed3\u679c: {triage_result}."
        f" \u7f3a\u5931\u5b57\u6bb5: {missing_fields}."
        f" \u60a3\u8005\u6458\u8981: {patient_summary}."
        f" \u98ce\u9669\u6807\u7b7e: {risk_flags}."
        f" \u6700\u8fd1\u5bf9\u8bdd: {recent_turns}."
        f" \u4e0a\u4e00\u8f6e\u8ffd\u95ee\u5b57\u6bb5: {last_question_focus}."
        f" \u4e0a\u4e00\u8f6e\u8ffd\u95ee\u539f\u6587: {last_question_text}."
        f" \u5df2\u8ffd\u95ee\u5386\u53f2: {asked_fields_history}."
        f" recommendation_changed: {recommendation_changed}."
    )


def build_final_message(triage_result: dict) -> str:
    return (
        f"\u5206\u8bca\u5b8c\u6210\u3002\u5efa\u8bae\u79d1\u5ba4\uff1a{triage_result['department']}\u3002"
        f"Triage Level {triage_result['triage_level']}\uff0cPriority {triage_result['priority']}\u3002"
        f"{triage_result['note']}"
    )


def build_fallback_follow_up_message(
    *,
    missing_fields: list[str],
    triage_result: dict,
    risk_flags: list[str],
    last_question_focus: str | None,
    asked_fields_history: list[str],
    recommendation_changed: bool,
) -> dict:
    if not missing_fields:
        return {
            "assistant_message": build_final_message(triage_result),
            "question_focus": None,
            "mention_recommendation": True,
            "style_tag": "final_recommendation",
            "message_type": "final",
        }

    focus = missing_fields[0]
    asked_count = sum(1 for item in asked_fields_history if item == focus)
    variants = FIELD_PROMPTS.get(focus, ["\u8bf7\u518d\u8865\u5145\u4e00\u70b9\u76f8\u5173\u4fe1\u606f\u3002"])
    prompt_text = variants[min(asked_count, len(variants) - 1)]
    prefix = ""
    if recommendation_changed:
        prefix = f"\u76ee\u524d\u5efa\u8bae\u79d1\u5ba4\uff1a{triage_result['department']}\u3002"
    elif risk_flags:
        prefix = "\u6211\u5148\u6293\u4e00\u4e2a\u5bf9\u5206\u8bca\u66f4\u5173\u952e\u7684\u4fe1\u606f\u3002"
    if focus == last_question_focus and asked_count >= 1:
        prefix = "\u6211\u6362\u4e2a\u95ee\u6cd5\u786e\u8ba4\u4e00\u4e0b\u3002"
    assistant_message = f"{prefix}{prompt_text}" if prefix else prompt_text
    return {
        "assistant_message": assistant_message,
        "question_focus": focus,
        "mention_recommendation": recommendation_changed,
        "style_tag": "followup",
        "message_type": "followup",
    }
