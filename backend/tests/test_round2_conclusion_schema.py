from types import SimpleNamespace

from app.agents.internal_medicine.rules import rule_based_internal_medicine, validate_internal_medicine_result
from app.agents.surgery.rules import rule_based_surgery, validate_surgery_result
from app.services.disposition import build_consultation_disposition


def _round2_memory(*, symptoms: list[str], chief_complaint: str, vitals: dict | None = None):
    return SimpleNamespace(
        shared_memory={
            "clinical_memory": {
                "chief_complaint": chief_complaint,
                "symptoms": list(symptoms),
                "vitals": dict(vitals or {}),
                "risk_flags": [],
            },
            "profile": {
                "allergy_status": "known",
                "allergies": [],
            },
        },
        private_memory={"consultation_round": 2},
    )


def test_internal_medicine_round2_can_recommend_medication_and_revisit_together():
    payload = {
        "chief_complaint": "fever and cough",
        "symptoms": "fever, cough",
        "message": "I reviewed the report and the fever is better, but I still cough.",
        "vitals": {"temp_c": 37.4, "heart_rate": 88},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["fever", "cough"],
        vitals=payload["vitals"],
    )

    result = validate_internal_medicine_result(
        {
            "clinical_impression": "The report does not show a high-risk bacterial pattern.",
            "final_assessment_summary": "Stable for outpatient treatment with close follow-up.",
            "medication_recommendation": {
                "recommended": True,
                "intent": "symptom_control",
                "summary": "Recommend symptomatic medication for cough relief.",
            },
            "followup_recommendation": {
                "observation_required": True,
                "observation_setting": "outpatient_home",
                "revisit_required": True,
                "revisit_window": "48 hours",
                "revisit_conditions": ["persistent fever", "worsening cough"],
            },
            "patient_facing_plan": "Use the medication as advised and return within 48 hours if the fever persists or the cough worsens.",
        },
        rule_based_internal_medicine(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "observe_then_revisit"
    assert result["medication_recommendation"]["recommended"] is True
    assert result["followup_recommendation"]["revisit_required"] is True
    assert result["followup_recommendation"]["revisit_window"] == "48 hours"
    assert result["admission_recommendation"]["recommended"] is False


def test_internal_medicine_round2_with_report_does_not_repeat_basic_tests():
    payload = {
        "chief_complaint": "Burning upper abdominal pain",
        "symptoms": "epigastric burning pain, nocturnal discomfort",
        "message": "",
        "consultation_round": 2,
        "vitals": {"pain_score": 4, "heart_rate": 82},
        "simulated_report": {
            "category_code": "medical_laboratory",
            "report_summary": {"cbc": "normal", "h_pylori": "positive"},
            "test_items": ["CBC", "H. pylori breath test"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["epigastric burning pain", "nocturnal discomfort"],
        vitals=payload["vitals"],
    )

    result = validate_internal_medicine_result(
        None,
        rule_based_internal_medicine(payload),
        payload,
        memory=memory,
    )

    assert result["test_required"] is False
    assert result["tests_suggested"] == []
    assert result["primary_disposition"] == "outpatient_management"
    assert result["medication_recommendation"]["recommended"] is True
    assert result["prescription_plan"]
    assert result["prescription_plan"][0]["drug_name"] == "质子泵抑制剂"
    assert "幽门螺杆菌" in result["clinical_impression"]


def test_surgery_round2_can_recommend_admission_and_surgery_evaluation_together():
    payload = {
        "chief_complaint": "abdominal pain",
        "symptoms": "abdominal pain, vomiting",
        "message": "The pain remains localized and stronger after the tests.",
        "vitals": {"temp_c": 37.8, "heart_rate": 104},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["abdominal pain", "vomiting"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        {
            "clinical_impression": "The result raises concern for a surgical abdominal process.",
            "final_assessment_summary": "Needs inpatient monitoring and expedited surgical evaluation.",
            "admission_recommendation": {
                "recommended": True,
                "reason": "Pain progression after the test still needs inpatient observation and management.",
            },
            "procedure_recommendation": {
                "surgery_evaluation_recommended": True,
                "urgency": "expedited",
                "reason": "The second-round findings may require a procedural decision after bedside reassessment.",
            },
            "patient_facing_plan": "Admission is recommended today, and the surgical team should reassess you promptly for possible procedure planning.",
        },
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "inpatient_admission_recommended"
    assert result["admission_recommendation"]["recommended"] is True
    assert result["procedure_recommendation"]["surgery_evaluation_recommended"] is True
    assert result["procedure_recommendation"]["urgency"] == "expedited"


def test_surgery_round2_stable_postoperative_report_defaults_to_observe_then_revisit():
    payload = {
        "chief_complaint": "postoperative wound check",
        "symptoms": "postoperative wound soreness, no fever",
        "message": "The dressing was changed and the wound looks cleaner after the tests.",
        "consultation_round": 2,
        "vitals": {"temp_c": 36.9, "heart_rate": 82},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {"wound_status": "clean wound, no abscess", "foreign_body": "no retained foreign body"},
            "test_items": ["Focused wound assessment"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["postoperative wound soreness", "no fever"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        None,
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["test_required"] is False
    assert result["tests_suggested"] == []
    assert result["primary_disposition"] == "observe_then_revisit"
    assert result["followup_recommendation"]["revisit_required"] is True
    assert result["followup_recommendation"]["revisit_window"] == "48-72小时"
    assert "伤口恢复总体平稳" in result["clinical_impression"]


def test_round2_emergency_primary_disposition_clears_conflicting_followup_and_admission():
    payload = {
        "chief_complaint": "postoperative wound problem",
        "symptoms": "wound pain, fever",
        "message": "The wound is worse and I feel unwell.",
        "vitals": {"temp_c": 38.9, "heart_rate": 126},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["wound pain", "fever"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        {
            "department": "Emergency",
            "priority": "H",
            "clinical_impression": "Possible severe postoperative complication.",
            "next_step_decision": "urgent_escalation",
            "admission_recommendation": {
                "recommended": True,
                "reason": "Conflicting legacy value that should be cleared by emergency escalation.",
            },
            "followup_recommendation": {
                "observation_required": True,
                "observation_setting": "outpatient_home",
                "revisit_required": True,
                "revisit_window": "24 hours",
                "revisit_conditions": ["more drainage"],
            },
        },
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "emergency_escalation"
    assert result["admission_recommendation"]["recommended"] is False
    assert result["followup_recommendation"]["observation_required"] is False
    assert result["followup_recommendation"]["revisit_required"] is False


def test_round2_specialty_referral_can_keep_followup_guidance():
    payload = {
        "chief_complaint": "ankle injury",
        "symptoms": "ankle injury, swelling",
        "message": "The swelling is a bit better after the imaging.",
        "vitals": {"temp_c": 36.8, "heart_rate": 84},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["ankle injury", "swelling"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        {
            "recommended_department": "Orthopedics",
            "recommended_department_reason": "The remaining issue is more suitable for orthopedics follow-up.",
            "clinical_impression": "No urgent general surgery issue remains after test review.",
            "followup_recommendation": {
                "observation_required": True,
                "observation_setting": "outpatient_home",
                "revisit_required": True,
                "revisit_window": "72 hours",
                "revisit_conditions": ["worsening swelling", "new numbness"],
            },
            "patient_facing_plan": "Arrange orthopedics follow-up, monitor swelling at home, and return sooner if numbness develops.",
        },
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "specialty_referral"
    assert result["followup_recommendation"]["revisit_required"] is True
    assert result["followup_recommendation"]["revisit_window"] == "72 hours"


def test_internal_medicine_round2_report_referral_requires_new_registration():
    payload = {
        "chief_complaint": "back pain after minor fall",
        "symptoms": "back pain, bruising",
        "message": "I want to know what the report means.",
        "consultation_round": 2,
        "vitals": {"temp_c": 36.8, "heart_rate": 82},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {
                "cross_specialty_clues": [
                    {
                        "target_department": "Surgery",
                        "reason": "The remaining issue now looks trauma-focused rather than internal-medicine-focused.",
                    }
                ]
            },
            "test_items": ["Focused imaging review"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["back pain", "bruising"],
        vitals=payload["vitals"],
    )

    result = validate_internal_medicine_result(
        None,
        rule_based_internal_medicine(payload),
        payload,
        memory=memory,
    )
    disposition = build_consultation_disposition(result, source_phase="internal_medicine_round2")

    assert result["primary_disposition"] == "specialty_referral"
    assert result["recommended_department"] == "Surgery"
    assert result["requires_new_registration"] is True
    assert result["carry_forward_summary"]["origin_department"] == "Internal Medicine"
    assert disposition["category"] == "specialty_referral"
    assert disposition["requires_new_registration"] is True


def test_surgery_round2_report_can_recommend_icu_escalation():
    payload = {
        "chief_complaint": "postoperative bleeding",
        "symptoms": "heavy bleeding, dizziness",
        "message": "The bleeding is still not stopping after the review.",
        "consultation_round": 2,
        "vitals": {"temp_c": 37.2, "heart_rate": 124},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {
                "escalation_clues": {
                    "to_emergency": True,
                    "to_icu": True,
                    "reason": "Report-level findings suggest unstable bleeding with ICU-level risk.",
                }
            },
            "test_items": ["Focused bleeding assessment"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["heavy bleeding", "dizziness"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        None,
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )
    disposition = build_consultation_disposition(result, source_phase="surgery_round2")

    assert result["primary_disposition"] == "icu_escalation"
    assert result["recommended_department"] == "ICU"
    assert result["priority"] == "H"
    assert disposition["category"] == "icu_rescue"


def test_round2_escalation_disposition_forces_high_priority_and_default_target():
    payload = {
        "chief_complaint": "worsening breathing problem",
        "symptoms": "shortness of breath, chest tightness",
        "message": "I still feel much worse after the review.",
        "vitals": {"temp_c": 37.1, "heart_rate": 118},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["shortness of breath", "chest tightness"],
        vitals=payload["vitals"],
    )

    result = validate_internal_medicine_result(
        {
            "priority": "M",
            "primary_disposition": "icu_escalation",
            "clinical_impression": "The current review suggests instability.",
            "final_assessment_summary": "Needs ICU-level rescue instead of routine follow-up.",
            "handoff_reason": "Persistent instability after reassessment.",
        },
        rule_based_internal_medicine(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "icu_escalation"
    assert result["priority"] == "H"
    assert result["recommended_department"] == "ICU"
    assert result["recommended_department_reason"] == "Persistent instability after reassessment."


def test_round2_report_icu_escalation_cannot_be_downgraded_by_llm_result():
    payload = {
        "chief_complaint": "dizziness and fatigue",
        "symptoms": "dizziness, fatigue",
        "message": "I almost fainted again after the review.",
        "consultation_round": 2,
        "vitals": {"temp_c": 37.2, "heart_rate": 118},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {
                "escalation_clues": {
                    "to_emergency": True,
                    "to_icu": True,
                    "reason": "Report-level findings suggest a critical deterioration pattern needing ICU rescue consideration.",
                }
            },
            "test_items": ["Focused instability assessment"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["dizziness", "fatigue"],
        vitals=payload["vitals"],
    )

    result = validate_internal_medicine_result(
        {
            "priority": "H",
            "department": "Internal Medicine",
            "primary_disposition": "emergency_escalation",
            "recommended_department": "Emergency Medicine",
            "recommended_department_reason": "Legacy emergency-only phrasing from the LLM output.",
            "handoff_reason": "Legacy emergency-only phrasing from the LLM output.",
        },
        rule_based_internal_medicine(payload),
        payload,
        memory=memory,
    )

    disposition = build_consultation_disposition(result, source_phase="internal_medicine_round2")

    assert result["primary_disposition"] == "icu_escalation"
    assert result["priority"] == "H"
    assert result["recommended_department"] == "ICU"
    assert result["icu_escalation"] is True
    assert disposition["category"] == "icu_rescue"


def test_round2_defaults_to_outpatient_management_when_no_other_disposition_is_triggered():
    payload = {
        "chief_complaint": "minor cut",
        "symptoms": "minor cut",
        "message": "The wound is cleaner after care and the report is reassuring.",
        "vitals": {"temp_c": 36.7, "heart_rate": 78},
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["minor cut"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        {
            "clinical_impression": "Stable after reassessment with no need for escalation.",
            "final_assessment_summary": "Continue standard outpatient wound care.",
            "patient_facing_plan": "Continue wound care and routine outpatient recovery instructions.",
        },
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["primary_disposition"] == "outpatient_management"
    assert result["admission_recommendation"]["recommended"] is False
    assert result["procedure_recommendation"]["surgery_evaluation_recommended"] is False


def test_surgery_round2_abdominal_report_can_directly_recommend_admission_without_repeated_tests():
    payload = {
        "chief_complaint": "abdominal pain",
        "symptoms": "abdominal pain, vomiting",
        "message": "The pain is still strong after the imaging review.",
        "consultation_round": 2,
        "vitals": {"temp_c": 37.9, "heart_rate": 102},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {"appendix": "appendicitis suspected", "free_fluid": "small collection"},
            "test_items": ["Abdominal CT"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["abdominal pain", "vomiting"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        None,
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["test_required"] is False
    assert result["tests_suggested"] == []
    assert result["primary_disposition"] == "inpatient_admission_recommended"
    assert result["admission_recommendation"]["recommended"] is True
    assert result["procedure_recommendation"]["surgery_evaluation_recommended"] is True


def test_surgery_round2_postoperative_infection_report_can_escalate_without_repeated_tests():
    payload = {
        "chief_complaint": "postoperative wound problem",
        "symptoms": "postoperative wound pain, drainage",
        "message": "The wound is more swollen and the drainage is getting worse after the review.",
        "consultation_round": 2,
        "vitals": {"temp_c": 38.2, "heart_rate": 108},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {"wound_status": "purulent drainage and soft tissue collection", "abscess": "possible early abscess"},
            "test_items": ["Focused wound ultrasound"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["postoperative wound pain", "drainage"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        None,
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["test_required"] is False
    assert result["tests_suggested"] == []
    assert result["primary_disposition"] == "emergency_escalation"
    assert result["admission_recommendation"]["recommended"] is False
    assert result["followup_recommendation"]["revisit_required"] is False


def test_surgery_round2_trauma_report_can_directly_refer_without_repeated_tests():
    payload = {
        "chief_complaint": "ankle injury",
        "symptoms": "ankle pain, swelling",
        "message": "The swelling is still there after imaging review.",
        "consultation_round": 2,
        "vitals": {"temp_c": 36.8, "heart_rate": 86},
        "simulated_report": {
            "category_code": "medical_imaging",
            "report_summary": {"xray": "distal fibula fracture", "joint": "no dislocation"},
            "test_items": ["Ankle X-ray"],
        },
    }
    memory = _round2_memory(
        chief_complaint=payload["chief_complaint"],
        symptoms=["ankle pain", "swelling"],
        vitals=payload["vitals"],
    )

    result = validate_surgery_result(
        None,
        rule_based_surgery(payload),
        payload,
        memory=memory,
    )

    assert result["test_required"] is False
    assert result["tests_suggested"] == []
    assert result["primary_disposition"] == "specialty_referral"
    assert result["recommended_department"] == "Orthopedics"
    assert result["procedure_recommendation"]["surgery_evaluation_recommended"] is True
    assert result["procedure_recommendation"]["urgency"] == "expedited"
