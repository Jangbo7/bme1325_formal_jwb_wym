from __future__ import annotations

from typing import Any

from app.agents.clinical_policy.models import ClinicalPolicyCard, ClinicalPolicyMatchResult


def _priority_weight(priority: str) -> int:
    weights = {"high": 3, "medium": 2, "low": 1}
    return weights.get(str(priority or "").strip().lower(), 0)


def _text_blob(context: dict[str, Any]) -> str:
    parts = [
        context.get("message"),
        context.get("chief_complaint"),
        context.get("symptoms"),
        " ".join(context.get("risk_flags") or []),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _matches_constraints(context_payload: dict[str, Any], constraints: dict[str, Any]) -> bool:
    for key, expected in constraints.items():
        if context_payload.get(key) != expected:
            return False
    return True


class ClinicalPolicyMatcher:
    def match(
        self,
        cards: list[ClinicalPolicyCard],
        *,
        agent_scope: str,
        department_scope: str,
        phase: str,
        context: dict[str, Any],
    ) -> ClinicalPolicyMatchResult:
        text = _text_blob(context)
        patient_context = dict(context.get("patient") or {})
        visit_context = dict(context.get("visit") or {})
        scored: list[tuple[tuple[int, int, int, int], ClinicalPolicyCard]] = []

        for card in cards:
            if card.agent_scope not in {agent_scope, "*"}:
                continue
            if card.department_scope not in {department_scope, "*"}:
                continue
            if phase not in card.applicable_phase:
                continue
            if not _matches_constraints(patient_context, card.patient_constraints):
                continue
            if not _matches_constraints(visit_context, card.visit_constraints):
                continue

            keyword_score = sum(1 for keyword in card.keywords if keyword.lower() in text)
            symptom_score = sum(1 for pattern in card.symptom_patterns if pattern.lower() in text)
            exact_agent = 1 if card.agent_scope == agent_scope else 0
            exact_department = 1 if card.department_scope == department_scope else 0
            scored.append(
                (
                    (exact_agent, exact_department, _priority_weight(card.retrieval_priority), keyword_score + symptom_score),
                    card,
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        matched_cards = [item[1] for item in scored]
        primary_card = matched_cards[0] if matched_cards else None
        return ClinicalPolicyMatchResult(
            matched_cards=matched_cards,
            primary_card=primary_card,
            policy_context={
                "phase": phase,
                "matched_card_ids": [card.id for card in matched_cards],
                "match_count": len(matched_cards),
            },
        )
