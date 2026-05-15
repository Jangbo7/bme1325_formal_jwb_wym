from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NpcPatientProfile:
    profile_id: str
    name: str
    age: int
    sex: str
    chief_complaint: str
    symptoms: str
    onset_time: str
    allergies: list[str]
    chronic_conditions: list[str]
    vitals: dict[str, int | float]
    triage_answers: dict[str, str] = field(default_factory=dict)
    internal_medicine_round1_replies: list[str] = field(default_factory=list)
    internal_medicine_round2_replies: list[str] = field(default_factory=list)
    revisit_note: str = ""

    def triage_reply_for(self, missing_fields: list[str]) -> str:
        ordered_parts: list[str] = []
        for field_name in missing_fields:
            text = self.triage_answers.get(field_name)
            if text and text not in ordered_parts:
                ordered_parts.append(text)
        if ordered_parts:
            return " ".join(ordered_parts)
        return self.revisit_note or "I have no additional details right now."


_PROFILES = {
    "respiratory_mild": NpcPatientProfile(
        profile_id="respiratory_mild",
        name="Lin Wei",
        age=29,
        sex="female",
        chief_complaint="Cough and low fever",
        symptoms="cough, sore throat, runny nose",
        onset_time="2 days ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 92, "temp_c": 37.8, "pain_score": 3},
        triage_answers={
            "chief_complaint": "My main problem is cough with a mild fever.",
            "symptoms": "I have cough, sore throat, and a runny nose.",
            "onset_time": "It started 2 days ago.",
            "temp_c": "My temperature was about 37.8 C.",
            "pain_score": "The discomfort is around 3 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "The cough became more obvious yesterday, and my throat feels dry. No drug allergies.",
            "This morning I still have cough and sore throat, and I do not have chronic diseases.",
        ],
        internal_medicine_round2_replies=[
            "I completed the ordered test and came back for the report review.",
            "Please finalize the diagnosis and treatment plan based on the report.",
        ],
        revisit_note="I came back after the test for report review.",
    ),
    "abdominal_pain": NpcPatientProfile(
        profile_id="abdominal_pain",
        name="Zhao Ming",
        age=41,
        sex="male",
        chief_complaint="Upper abdominal pain",
        symptoms="upper abdominal pain, nausea, reduced appetite",
        onset_time="1 day ago",
        allergies=["penicillin"],
        chronic_conditions=["gastritis"],
        vitals={"heart_rate": 98, "temp_c": 37.2, "pain_score": 6},
        triage_answers={
            "chief_complaint": "My main problem is upper abdominal pain with nausea.",
            "symptoms": "I have upper abdominal pain, nausea, and poor appetite.",
            "onset_time": "It started 1 day ago after dinner.",
            "temp_c": "No obvious fever, around 37.2 C.",
            "pain_score": "The pain is about 6 out of 10.",
            "allergies": "I am allergic to penicillin.",
        },
        internal_medicine_round1_replies=[
            "The pain is worse after eating, and I feel nauseated but I have not vomited. I have a penicillin allergy.",
            "I had gastritis before, and the pain today is more persistent than usual.",
        ],
        internal_medicine_round2_replies=[
            "I finished the test and came back because I want to know what the result means.",
            "Please explain the final diagnosis and what treatment I should follow.",
        ],
        revisit_note="I am back after the test and want the result explained.",
    ),
    "dizziness_followup": NpcPatientProfile(
        profile_id="dizziness_followup",
        name="Chen Yu",
        age=35,
        sex="female",
        chief_complaint="Dizziness and headache",
        symptoms="dizziness, headache, blurred vision for a short while",
        onset_time="3 hours ago",
        allergies=[],
        chronic_conditions=["migraine"],
        vitals={"heart_rate": 88, "temp_c": 36.9, "pain_score": 5},
        triage_answers={
            "chief_complaint": "My main problem is dizziness with headache.",
            "symptoms": "I have dizziness, headache, and brief blurred vision.",
            "onset_time": "It started about 3 hours ago.",
            "temp_c": "No fever, around 36.9 C.",
            "pain_score": "The headache is about 5 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "The dizziness is better when I sit down, but the headache is still there. I do not have drug allergies.",
            "I have a history of migraine, but this episode felt stronger than usual at the beginning.",
        ],
        internal_medicine_round2_replies=[
            "I already completed the examination and returned for the doctor to review the findings.",
            "Please give me the final diagnosis and tell me what I should do next.",
        ],
        revisit_note="I returned after the examination for the follow-up consultation.",
    ),
}


def list_profiles() -> list[NpcPatientProfile]:
    return list(_PROFILES.values())


def get_profile(profile_id: str) -> NpcPatientProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise KeyError(f"unknown npc profile: {profile_id}") from exc
