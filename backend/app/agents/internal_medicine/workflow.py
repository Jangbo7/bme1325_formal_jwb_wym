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
    last_question_focus: str | None = None
    last_question_text: str = ""
    last_extracted_fields: list[str] = field(default_factory=list)
    patient_reply_count: int = 0
    completed: bool = False

    def to_dict(self) -> dict:
        return {
            "followup_count": self.followup_count,
            "asked_fields_history": list(self.asked_fields_history),
            "last_question_focus": self.last_question_focus,
            "last_question_text": self.last_question_text,
            "last_extracted_fields": list(self.last_extracted_fields),
            "patient_reply_count": self.patient_reply_count,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ConsultationProgress":
        payload = data or {}
        asked_fields_history = payload.get("asked_fields_history", [])
        if not isinstance(asked_fields_history, list):
            asked_fields_history = []
        last_extracted_fields = payload.get("last_extracted_fields", [])
        if not isinstance(last_extracted_fields, list):
            last_extracted_fields = []
        return cls(
            followup_count=int(payload.get("followup_count", 0)),
            asked_fields_history=[str(item) for item in asked_fields_history if str(item).strip()],
            last_question_focus=payload.get("last_question_focus"),
            last_question_text=str(payload.get("last_question_text", "")),
            last_extracted_fields=[str(item) for item in last_extracted_fields if str(item).strip()],
            patient_reply_count=int(payload.get("patient_reply_count", 0)),
            completed=bool(payload.get("completed", False)),
        )
