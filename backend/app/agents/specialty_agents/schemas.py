from pydantic import BaseModel, Field


class RoutingDecision(BaseModel):
    next_node: str
    department_key: str | None = None
    reason: str


class SpecialtyDoctorDecision(BaseModel):
    reply_to_patient: str
    consultation_state: str
    suspected_department_key: str
    urgency: str
    red_flags: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    routing_decision: RoutingDecision
    structured_result: dict = Field(default_factory=dict)
