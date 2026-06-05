import json
import os


RULE_STORE_PATH = os.path.join(os.path.dirname(__file__), "rule_store.json")


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_rules():
    with open(RULE_STORE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def _score_rule(rule, payload):
    score = 0
    symptoms = (payload.get("symptoms") or "").lower()
    vitals = payload.get("vitals") or {}
    conditions = rule.get("conditions") or {}

    for term in rule.get("keywords") or []:
        if term.lower() in symptoms:
            score += 2

    for symptom in conditions.get("symptoms_any", []):
        if symptom.lower() in symptoms:
            score += 4

    heart_rate = _safe_int(vitals.get("heart_rate"), 0)
    temp_c = _safe_float(vitals.get("temp_c"), 0.0)
    pain_score = _safe_int(vitals.get("pain_score"), 0)

    if "heart_rate_gte" in conditions and heart_rate >= _safe_int(conditions.get("heart_rate_gte"), 999):
        score += 3
    if "temp_c_gte" in conditions and temp_c >= _safe_float(conditions.get("temp_c_gte"), 999.0):
        score += 3
    if "pain_score_gte" in conditions and pain_score >= _safe_int(conditions.get("pain_score_gte"), 999):
        score += 3
    if conditions.get("default"):
        score += 1

    return score


def retrieve_relevant_rules(payload, top_k=3):
    rules = load_rules()
    scored = []
    for rule in rules:
        score = _score_rule(rule, payload)
        if score > 0:
            scored.append({"score": score, "rule": rule})

    scored.sort(key=lambda item: item["score"], reverse=True)
    results = [item["rule"] for item in scored if not (item["rule"].get("conditions") or {}).get("default")][:top_k]
    if results:
        return results

    for rule in rules:
        if (rule.get("conditions") or {}).get("default"):
            return [rule]
    return []
