from __future__ import annotations

from dataclasses import dataclass

from app.schemas.common import VisitLifecycleState
from app.services.department_assignment import resolve_assigned_department_for_visit


SECOND_CONSULTATION_VISIT_STATES = {
    VisitLifecycleState.IN_SECOND_CONSULTATION.value,
    VisitLifecycleState.DIAGNOSIS_FINALIZED.value,
    VisitLifecycleState.WAITING_PAYMENT.value,
    VisitLifecycleState.MEDICAL_PAYMENT_COMPLETED.value,
    VisitLifecycleState.DISPOSITION_PENDING.value,
    VisitLifecycleState.WAITING_PHARMACY.value,
    VisitLifecycleState.DISPOSITION_OUTPATIENT_TREATMENT.value,
    VisitLifecycleState.DISPOSITION_FOLLOWUP_BOOKING.value,
    VisitLifecycleState.DISPOSITION_REFERRAL.value,
}

CONSULTATION_OWNED_VISIT_STATES = {
    VisitLifecycleState.IN_CONSULTATION.value,
    VisitLifecycleState.WAITING_TEST.value,
    VisitLifecycleState.WAITING_TEST_PAYMENT.value,
    VisitLifecycleState.TEST_PAYMENT_COMPLETED.value,
    VisitLifecycleState.IN_TEST.value,
    VisitLifecycleState.WAITING_OUTPATIENT_PROCEDURE.value,
    VisitLifecycleState.IN_OUTPATIENT_PROCEDURE.value,
    VisitLifecycleState.WAITING_RETURN_CONSULTATION.value,
    VisitLifecycleState.RESULTS_READY.value,
    VisitLifecycleState.WAITING_SECOND_CONSULTATION.value,
    *SECOND_CONSULTATION_VISIT_STATES,
}


@dataclass(frozen=True, slots=True)
class ConsultationAgentDefinition:
    department_id: str
    agent_type: str
    service_container_key: str
    session_prefix: str
    session_ref_key: str
    round2_session_ref_key: str | None
    supports_round2: bool = True


CONSULTATION_AGENTS: tuple[ConsultationAgentDefinition, ...] = (
    ConsultationAgentDefinition(
        department_id="internal",
        agent_type="internal_medicine",
        service_container_key="internal_medicine_service",
        session_prefix="im-session-",
        session_ref_key="internal_medicine_session_id",
        round2_session_ref_key="internal_medicine_round2_session_id",
        supports_round2=True,
    ),
    ConsultationAgentDefinition(
        department_id="surgery",
        agent_type="surgery",
        service_container_key="surgery_service",
        session_prefix="surgery-session-",
        session_ref_key="surgery_session_id",
        round2_session_ref_key="surgery_round2_session_id",
        supports_round2=True,
    ),
)

CONSULTATION_AGENT_BY_DEPARTMENT = {item.department_id: item for item in CONSULTATION_AGENTS}
CONSULTATION_AGENT_BY_TYPE = {item.agent_type: item for item in CONSULTATION_AGENTS}


def is_second_consultation_flow(visit_state: str | None) -> bool:
    return str(visit_state or "") in SECOND_CONSULTATION_VISIT_STATES


def is_consultation_owned_visit_state(visit_state: str | None) -> bool:
    return str(visit_state or "") in CONSULTATION_OWNED_VISIT_STATES


def list_consultation_agents() -> tuple[ConsultationAgentDefinition, ...]:
    return CONSULTATION_AGENTS


def get_consultation_agent_by_department(department_id: str | None) -> ConsultationAgentDefinition | None:
    return CONSULTATION_AGENT_BY_DEPARTMENT.get(str(department_id or "").strip())


def get_consultation_agent_by_type(agent_type: str | None) -> ConsultationAgentDefinition | None:
    return CONSULTATION_AGENT_BY_TYPE.get(str(agent_type or "").strip())


def resolve_consultation_agent_for_visit(visit_row: dict | None, patient_row: dict | None = None) -> ConsultationAgentDefinition | None:
    if not visit_row:
        return None
    by_agent = get_consultation_agent_by_type(visit_row.get("active_agent_type"))
    if by_agent:
        return by_agent
    assigned = resolve_assigned_department_for_visit(visit_row, patient_row)
    return get_consultation_agent_by_department(assigned.get("id"))


def get_consultation_service(container: dict, *, agent_type: str | None = None, department_id: str | None = None):
    definition = get_consultation_agent_by_type(agent_type) if agent_type else get_consultation_agent_by_department(department_id)
    if not definition:
        return None
    return container.get(definition.service_container_key)
