from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
