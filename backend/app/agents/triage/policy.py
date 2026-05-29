from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agents.clinical_policy import ClinicalPolicyRegistry, ClinicalPolicyRuntime


CARD_DIRECTORY = Path(__file__).resolve().parent.parent / "clinical_policy" / "cards"
TRIAGE_POLICY_PHASE = "initial_assessment"


@lru_cache(maxsize=1)
def load_triage_policy_registry() -> ClinicalPolicyRegistry:
    return ClinicalPolicyRegistry.load(CARD_DIRECTORY)


@lru_cache(maxsize=1)
def load_triage_policy_runtime() -> ClinicalPolicyRuntime:
    return ClinicalPolicyRuntime()
