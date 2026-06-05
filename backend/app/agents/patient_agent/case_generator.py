from __future__ import annotations

from app.api.contract import ContractError
from app.agents.patient_agent.prompt_builder import build_generate_case_messages
from app.agents.patient_agent.rag_context import PatientAgentRagContext
from app.agents.patient_agent.schemas import PatientCaseCard


class PatientCaseGenerator:
    def __init__(self, *, request_json, rag_context: PatientAgentRagContext):
        self.request_json = request_json
        self.rag_context = rag_context

    def generate(
        self,
        *,
        seed: str | None = None,
        department_id: str | None = None,
        retries: int = 2,
    ) -> PatientCaseCard:
        messages = build_generate_case_messages(
            constraints=self.rag_context.build_case_constraints(department_id=department_id),
            seed=seed,
        )
        last_error = "unknown"
        for _ in range(retries + 1):
            try:
                data = self.request_json(messages)
            except ContractError:
                raise
            if not isinstance(data, dict):
                last_error = "case generator returned non-object payload"
                continue
            try:
                return PatientCaseCard.model_validate(data)
            except Exception as exc:
                last_error = str(exc)
        raise ContractError(
            code="LLM_RESPONSE_INVALID",
            message="patient case generation returned invalid structured JSON",
            details={
                "agent": "patient_agent",
                "stage": "generate_case",
                "last_error": last_error,
                "retries": retries,
            },
            status_code=502,
        )
