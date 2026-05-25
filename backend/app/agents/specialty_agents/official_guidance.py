from __future__ import annotations

import json
from pathlib import Path


REFERENCE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "rag" / "outpatient_official_reference_pack.json"


def load_official_reference_pack() -> list[dict]:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


SPECIALTY_TAG_HINTS = {
    "surgery": {"safety", "outpatient_quality", "workflow"},
    "pediatrics": {"pediatrics", "patient_experience", "smart_guide"},
    "ent": {"navigation", "appointment", "workflow"},
}


def retrieve_official_guidance(agent_type: str, payload: dict, top_k: int = 4) -> list[dict]:
    complaint_text = f"{payload.get('chief_complaint', '')} {payload.get('symptoms', '')} {payload.get('message', '')}".lower()
    hits: list[tuple[int, dict]] = []
    for item in load_official_reference_pack():
        score = 0
        departments = item.get("applicable_departments") or []
        if "all" in departments or agent_type in departments:
            score += 2
        tags = set(item.get("tags") or [])
        if tags & SPECIALTY_TAG_HINTS.get(agent_type, set()):
            score += 2
        summary_text = " ".join(item.get("summary") or []).lower()
        if any(token in summary_text for token in complaint_text.split() if token):
            score += 1
        if score > 0:
            hits.append((score, item))
    hits.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in hits[:top_k]]
