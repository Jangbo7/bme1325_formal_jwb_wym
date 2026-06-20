from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatientRareEventProfile(BaseModel):
    patient_special_event_enabled: bool = False
    patient_special_event_type: str | None = None
    special_event_intensity: str | None = None
    special_event_reveal_phase: str | None = None
    report_special_signal_enabled: bool = False
    report_special_signal_type: str | None = None
    triggered_by: str = "none"
    event_type: str | None = None
    target_department: str | None = None
    target_department_id: str | None = None
    target_department_reason: str | None = None
    patient_signal_instruction: str | None = None
    report_signal_instruction: str | None = None
    report_escalation_target: str | None = None
    report_escalation_reason: str | None = None
    alignment_keywords: list[str] = Field(default_factory=list)
    seed: str | None = None


class PatientProfileCard(BaseModel):
    name: str
    age: int
    sex: str
    allergies: list[str] = Field(default_factory=list)
    chronic_conditions: list[str] = Field(default_factory=list)


class PatientSymptomFacts(BaseModel):
    symptoms: list[str] = Field(default_factory=list)
    onset_time: str
    vitals: dict[str, Any] = Field(default_factory=dict)
    associated_symptoms: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)
    aggravating_factors: list[str] = Field(default_factory=list)
    relieving_factors: list[str] = Field(default_factory=list)


class PatientCaseCard(BaseModel):
    case_id: str
    patient_profile: PatientProfileCard
    chief_complaint: str
    present_illness: str
    symptom_facts: PatientSymptomFacts
    communication_style: str
    hidden_diagnosis_hint: str
    patient_goals: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    rare_event_profile: PatientRareEventProfile | None = None


class PatientReplyContext(BaseModel):
    phase: str
    patient_id: str
    visit_id: str | None = None
    session_id: str | None = None
    recent_question: str = ""
    recent_turns: list[dict[str, Any]] = Field(default_factory=list)
    known_test_results: list[dict[str, Any]] = Field(default_factory=list)
    medical_record_excerpt: list[dict[str, Any]] = Field(default_factory=list)


class PatientPolicyDecision(BaseModel):
    allowed_fact_keys: list[str] = Field(default_factory=list)
    should_ask_follow_up: bool = False
    avoid_diagnosis_labels: bool = True
    style_hints: list[str] = Field(default_factory=list)
    allowed_topics: list[str] = Field(default_factory=list)
    summary: str = ""


class PatientAgentTurnResult(BaseModel):
    message: str
    used_facts: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    policy_state: dict[str, Any] = Field(default_factory=dict)
