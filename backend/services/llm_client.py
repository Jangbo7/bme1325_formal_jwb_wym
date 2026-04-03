import json
from urllib import request as urlrequest

from services.private_api_config import get_backend_private_config

def get_llm_settings():
    private_config = get_backend_private_config()
    return {
        "endpoint": private_config["llm_endpoint"],
        "model": private_config["llm_model"],
        "api_key": private_config["llm_api_key"],
    }


def extract_text_from_response(data):
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        parts = [extract_text_from_response(item) for item in data]
        return " ".join([item for item in parts if item]).strip()
    if not isinstance(data, dict):
        return ""

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_items = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_items.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    text_items.append(item)
            return " ".join([item for item in text_items if item]).strip()

    message = data.get("message")
    if isinstance(message, str):
        return message.strip()
    return ""


def request_triage_from_llm(payload, evidence_rules, memory_context=None):
    settings = get_llm_settings()
    if not settings["api_key"]:
        return None

    memory_context = memory_context or {}
    prompt = (
        "You are a hospital triage nurse assistant. "
        "Use the retrieved triage knowledge as supporting evidence, and consider both short-term conversation memory and long-term patient memory. "
        "Return strict JSON only with keys: triage_level (integer 1-5), priority (H/M/L), "
        "department (string), note (string). "
        "Patient data: "
        + json.dumps(payload, ensure_ascii=False)
        + " Short-term memory: "
        + json.dumps(memory_context.get("short_term_memory", {}), ensure_ascii=False)
        + " Long-term memory: "
        + json.dumps(memory_context.get("long_term_memory", {}), ensure_ascii=False)
        + " Missing important fields: "
        + json.dumps(memory_context.get("missing_fields", []), ensure_ascii=False)
        + " Retrieved rules: "
        + json.dumps(evidence_rules, ensure_ascii=False)
    )
    body = {
        "model": settings["model"],
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
        "temperature": 0,
        "n": 1,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 0,
    }

    req = urlrequest.Request(
        settings["endpoint"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=18) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    text = extract_text_from_response(data)
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
