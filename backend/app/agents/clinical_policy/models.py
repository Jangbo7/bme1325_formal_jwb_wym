from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ClinicalPolicyCard:
    id: str
    version: str
    source_layer: str
    agent_scope: str
    department_scope: str
    category: str
    retrieval_priority: str
    authority_level: str
    safety_level: str
    applicable_phase: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    symptom_patterns: tuple[str, ...] = ()
    patient_constraints: dict[str, Any] = field(default_factory=dict)
    visit_constraints: dict[str, Any] = field(default_factory=dict)
    role_boundary: str = ""
    collection_targets: tuple[dict[str, Any], ...] = ()
    question_policy: dict[str, Any] = field(default_factory=dict)
    red_flags: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    allowed_outputs: tuple[str, ...] = ()
    escalation_policy: dict[str, Any] = field(default_factory=dict)
    outcome_policy: dict[str, Any] = field(default_factory=dict)
    output_mode: str = ""
    output_schema_name: str = ""
    required_fields: tuple[str, ...] = ()
    allowed_next_actions: tuple[str, ...] = ()
    system_rules: tuple[str, ...] = ()
    style_rules: tuple[str, ...] = ()
    summary_rules: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClinicalPolicyMatchResult:
    matched_cards: list[ClinicalPolicyCard] = field(default_factory=list)
    primary_card: ClinicalPolicyCard | None = None
    policy_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClinicalPolicyValidatorResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    normalized_output: dict[str, Any] = field(default_factory=dict)
    fallback_reason: str = ""


@dataclass(slots=True)
class ClinicalPolicyRuntimeContext:
    matched_cards: list[ClinicalPolicyCard] = field(default_factory=list)
    primary_card: ClinicalPolicyCard | None = None
    policy_context: dict[str, Any] = field(default_factory=dict)
    prompt_policy_context: str = ""
    output_contract: dict[str, Any] = field(default_factory=dict)
    validator_contract: dict[str, Any] = field(default_factory=dict)
    fallback_contract: dict[str, Any] = field(default_factory=dict)
