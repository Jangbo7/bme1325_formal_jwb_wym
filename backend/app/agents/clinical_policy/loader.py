from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.agents.clinical_policy.models import ClinicalPolicyCard


class ClinicalPolicyCardSchemaError(ValueError):
    pass


def _as_string(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ClinicalPolicyCardSchemaError(f"clinical policy field '{field_name}' is required")
    return text


def _as_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ClinicalPolicyCardSchemaError(f"clinical policy field '{field_name}' must be a list")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _as_dict(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ClinicalPolicyCardSchemaError(f"clinical policy field '{field_name}' must be a mapping")
    return dict(value)


def _as_collection_targets(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ClinicalPolicyCardSchemaError("clinical policy field 'behavior_policy.collection_targets' must be a list")
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ClinicalPolicyCardSchemaError("each collection target must be a mapping")
        field_name = str(item.get("field") or "").strip()
        if not field_name:
            raise ClinicalPolicyCardSchemaError("each collection target requires a non-empty 'field'")
        normalized.append(dict(item))
    return tuple(normalized)


def _priority_weight(priority: str) -> int:
    weights = {"high": 3, "medium": 2, "low": 1}
    return weights.get(str(priority or "").strip().lower(), 0)


def build_card_from_payload(payload: dict[str, Any], *, source_path: Path | None = None) -> ClinicalPolicyCard:
    match_criteria = _as_dict(payload.get("match_criteria"), field_name="match_criteria")
    behavior_policy = _as_dict(payload.get("behavior_policy"), field_name="behavior_policy")
    output_contract = _as_dict(payload.get("output_contract"), field_name="output_contract")
    prompt_hints = _as_dict(payload.get("prompt_hints"), field_name="prompt_hints")

    card = ClinicalPolicyCard(
        id=_as_string(payload.get("id"), field_name="id"),
        version=_as_string(payload.get("version", "1"), field_name="version"),
        source_layer=_as_string(payload.get("source_layer", "specialty_policy"), field_name="source_layer"),
        agent_scope=_as_string(payload.get("agent_scope"), field_name="agent_scope"),
        department_scope=_as_string(payload.get("department_scope"), field_name="department_scope"),
        category=_as_string(payload.get("category"), field_name="category"),
        retrieval_priority=_as_string(payload.get("retrieval_priority", "medium"), field_name="retrieval_priority"),
        authority_level=_as_string(payload.get("authority_level", "internal"), field_name="authority_level"),
        safety_level=_as_string(payload.get("safety_level", "standard"), field_name="safety_level"),
        applicable_phase=_as_string_tuple(match_criteria.get("applicable_phase"), field_name="match_criteria.applicable_phase"),
        keywords=_as_string_tuple(match_criteria.get("keywords"), field_name="match_criteria.keywords"),
        symptom_patterns=_as_string_tuple(match_criteria.get("symptom_patterns"), field_name="match_criteria.symptom_patterns"),
        patient_constraints=_as_dict(match_criteria.get("patient_constraints"), field_name="match_criteria.patient_constraints"),
        visit_constraints=_as_dict(match_criteria.get("visit_constraints"), field_name="match_criteria.visit_constraints"),
        role_boundary=str(behavior_policy.get("role_boundary") or "").strip(),
        collection_targets=_as_collection_targets(behavior_policy.get("collection_targets")),
        question_policy=_as_dict(behavior_policy.get("question_policy"), field_name="behavior_policy.question_policy"),
        red_flags=_as_string_tuple(behavior_policy.get("red_flags"), field_name="behavior_policy.red_flags"),
        forbidden_actions=_as_string_tuple(behavior_policy.get("forbidden_actions"), field_name="behavior_policy.forbidden_actions"),
        allowed_outputs=_as_string_tuple(behavior_policy.get("allowed_outputs"), field_name="behavior_policy.allowed_outputs"),
        escalation_policy=_as_dict(behavior_policy.get("escalation_policy"), field_name="behavior_policy.escalation_policy"),
        output_mode=_as_string(output_contract.get("output_mode", "policy_snapshot"), field_name="output_contract.output_mode"),
        output_schema_name=_as_string(output_contract.get("output_schema_name", "policy_snapshot"), field_name="output_contract.output_schema_name"),
        required_fields=_as_string_tuple(output_contract.get("required_fields"), field_name="output_contract.required_fields"),
        allowed_next_actions=_as_string_tuple(output_contract.get("allowed_next_actions"), field_name="output_contract.allowed_next_actions"),
        system_rules=_as_string_tuple(prompt_hints.get("system_rules"), field_name="prompt_hints.system_rules"),
        style_rules=_as_string_tuple(prompt_hints.get("style_rules"), field_name="prompt_hints.style_rules"),
        summary_rules=_as_string_tuple(prompt_hints.get("summary_rules"), field_name="prompt_hints.summary_rules"),
        metadata={"source_path": str(source_path) if source_path else None},
    )

    if not card.applicable_phase:
        raise ClinicalPolicyCardSchemaError("clinical policy card must declare at least one applicable phase")
    if not card.allowed_next_actions:
        raise ClinicalPolicyCardSchemaError("clinical policy card must declare at least one allowed next action")
    if _priority_weight(card.retrieval_priority) == 0:
        raise ClinicalPolicyCardSchemaError("clinical policy retrieval_priority must be one of: high, medium, low")
    return card


def load_cards(cards_path: str | Path) -> list[ClinicalPolicyCard]:
    path = Path(cards_path)
    if not path.exists():
        raise FileNotFoundError(path)
    files = [path] if path.is_file() else sorted([item for item in path.rglob("*") if item.suffix.lower() in {".yaml", ".yml"}])
    cards: list[ClinicalPolicyCard] = []
    for file_path in files:
        payload = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ClinicalPolicyCardSchemaError(f"clinical policy file '{file_path}' must contain a mapping")
        cards.append(build_card_from_payload(payload, source_path=file_path))
    return cards
