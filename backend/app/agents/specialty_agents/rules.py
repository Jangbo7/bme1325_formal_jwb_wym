from __future__ import annotations

import json
from pathlib import Path


RAG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "rag"

SPECIALTY_RULE_PATHS = {
    "surgery": RAG_DIR / "surgery_rules.json",
    "pediatrics": RAG_DIR / "pediatrics_rules.json",
    "ent": RAG_DIR / "ent_rules.json",
}


def load_specialty_rules(agent_type: str) -> list[dict]:
    path = SPECIALTY_RULE_PATHS[agent_type]
    return json.loads(path.read_text(encoding="utf-8"))


def retrieve_relevant_specialty_rules(agent_type: str, payload: dict, top_k: int = 3) -> list[dict]:
    text = f"{payload.get('chief_complaint', '')} {payload.get('symptoms', '')} {payload.get('message', '')}".lower()
    scored: list[tuple[int, dict]] = []
    for rule in load_specialty_rules(agent_type):
      score = 0
      for keyword in rule.get("keywords", []):
          if keyword and keyword.lower() in text:
              score += 2
      if score > 0 or not rule.get("keywords"):
          scored.append((score, rule))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def rule_based_specialty(agent_type: str, payload: dict) -> dict:
    rules = retrieve_relevant_specialty_rules(agent_type, payload, top_k=1)
    selected = dict((rules[0] if rules else load_specialty_rules(agent_type)[-1]).get("result") or {})
    selected["agent_type"] = agent_type
    selected.setdefault("tests_required", False)
    selected.setdefault("tests_suggested", [])
    selected.setdefault("action_plan", [])
    selected.setdefault("red_flags", [])
    return selected
