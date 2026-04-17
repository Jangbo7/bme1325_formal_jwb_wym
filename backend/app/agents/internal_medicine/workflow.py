from dataclasses import dataclass, field


QUESTION_ORDER = [
    "chief_complaint",
    "onset_time",
    "allergies",
]


@dataclass
class ConsultationProgress:
    followup_count: int = 0
    asked_fields_history: list[str] = field(default_factory=list)
    patient_reply_count: int = 0
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "followup_count": self.followup_count,
            "asked_fields_history": list(self.asked_fields_history),
            "patient_reply_count": self.patient_reply_count,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ConsultationProgress":
        payload = data or {}
        return cls(
            followup_count=int(payload.get("followup_count", 0)),
            asked_fields_history=list(payload.get("asked_fields_history", [])),
            patient_reply_count=int(payload.get("patient_reply_count", 0)),
            completed=bool(payload.get("completed", False)),
        )
