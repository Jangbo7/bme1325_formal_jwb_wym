from pydantic import BaseModel, Field


class QueueTicketView(BaseModel):
    id: str
    patient_id: str
    visit_id: str | None = None
    department_id: str
    department_name: str
    number: int
    status: str
    created_at: str
    updated_at: str


class QueueView(BaseModel):
    department_id: str
    department_name: str
    waiting: list[QueueTicketView] = Field(default_factory=list)
    called: QueueTicketView | None = None
