from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.agents.clinical_policy.loader import load_cards
from app.agents.clinical_policy.matcher import ClinicalPolicyMatcher
from app.agents.clinical_policy.models import ClinicalPolicyCard, ClinicalPolicyMatchResult


@dataclass(slots=True)
class ClinicalPolicyRegistry:
    cards: list[ClinicalPolicyCard] = field(default_factory=list)
    matcher: ClinicalPolicyMatcher = field(default_factory=ClinicalPolicyMatcher)

    @classmethod
    def load(cls, cards_path: str | Path) -> "ClinicalPolicyRegistry":
        return cls(cards=load_cards(cards_path))

    def find(
        self,
        *,
        agent_scope: str,
        department_scope: str,
        phase: str,
        context: dict,
    ) -> ClinicalPolicyMatchResult:
        return self.matcher.match(
            self.cards,
            agent_scope=agent_scope,
            department_scope=department_scope,
            phase=phase,
            context=context,
        )
