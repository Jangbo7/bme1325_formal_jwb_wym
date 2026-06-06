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
    target_department_id: str
    target_department_name: str
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
    "internal_respiratory": NpcPatientProfile(
        profile_id="internal_respiratory",
        name="Lin Wei",
        age=29,
        sex="female",
        chief_complaint="Cough and low fever",
        symptoms="cough, sore throat, runny nose",
        onset_time="2 days ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 92, "temp_c": 37.8, "pain_score": 3},
        target_department_id="internal",
        target_department_name="Internal Medicine",
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
    "surgery_wound_pain": NpcPatientProfile(
        profile_id="surgery_wound_pain",
        name="Qin Hao",
        age=34,
        sex="male",
        chief_complaint="Pain around a finger cut wound",
        symptoms="finger cut wound, swelling, throbbing pain",
        onset_time="8 hours ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 90, "temp_c": 37.3, "pain_score": 6},
        target_department_id="surgery",
        target_department_name="General Surgery",
        triage_answers={
            "chief_complaint": "I cut my finger and now it hurts with swelling.",
            "symptoms": "There is a cut wound, swelling, and throbbing pain.",
            "onset_time": "It happened around 8 hours ago.",
            "temp_c": "My temperature is around 37.3 C.",
            "pain_score": "The pain is around 6 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "The swelling increased after work, and touching the wound is painful.",
            "I cleaned the wound myself, but the pain is still persistent.",
        ],
        internal_medicine_round2_replies=[
            "I completed the requested checks and returned with the result.",
            "Please confirm if this needs additional treatment.",
        ],
        revisit_note="I returned after completing the requested check.",
    ),
    "obgyn_lower_abdominal_discomfort": NpcPatientProfile(
        profile_id="obgyn_lower_abdominal_discomfort",
        name="Zhang Rui",
        age=31,
        sex="female",
        chief_complaint="Lower abdominal discomfort",
        symptoms="lower abdominal discomfort, light nausea, irregular spotting",
        onset_time="3 days ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 86, "temp_c": 36.9, "pain_score": 4},
        target_department_id="obgyn",
        target_department_name="Obstetrics and Gynecology",
        triage_answers={
            "chief_complaint": "I feel lower abdominal discomfort with mild nausea.",
            "symptoms": "I have lower abdominal discomfort and irregular spotting.",
            "onset_time": "It started about 3 days ago.",
            "temp_c": "No fever, around 36.9 C.",
            "pain_score": "Pain is around 4 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "The discomfort is intermittent and gets worse in the evening.",
            "I am worried about whether this is a gynecological issue.",
        ],
        internal_medicine_round2_replies=[
            "I finished the examinations and came back for interpretation.",
            "Please tell me the diagnosis and next treatment steps.",
        ],
        revisit_note="I came back after the exams for follow-up advice.",
    ),
    "pediatrics_fever_cough": NpcPatientProfile(
        profile_id="pediatrics_fever_cough",
        name="Guo An",
        age=8,
        sex="male",
        chief_complaint="Child fever and cough",
        symptoms="fever, cough, reduced appetite",
        onset_time="1 day ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 108, "temp_c": 38.2, "pain_score": 3},
        target_department_id="pediatrics",
        target_department_name="Pediatrics",
        triage_answers={
            "chief_complaint": "My child has fever and cough.",
            "symptoms": "There is fever, cough, and poor appetite.",
            "onset_time": "Symptoms started yesterday.",
            "temp_c": "The temperature is around 38.2 C.",
            "pain_score": "Discomfort is around 3 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "The cough is more frequent at night, and appetite is still low.",
            "There is no history of chronic disease for the child.",
        ],
        internal_medicine_round2_replies=[
            "We completed the tests and came back as instructed.",
            "Please explain the findings in simple terms.",
        ],
        revisit_note="We returned after the tests for the second consultation.",
    ),
    "ophthalmology_red_eye": NpcPatientProfile(
        profile_id="ophthalmology_red_eye",
        name="Wen Jia",
        age=27,
        sex="female",
        chief_complaint="Red painful eye",
        symptoms="red eye, eye pain, tearing",
        onset_time="12 hours ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 82, "temp_c": 36.8, "pain_score": 5},
        target_department_id="ophthalmology",
        target_department_name="Ophthalmology",
        triage_answers={
            "chief_complaint": "My right eye is red and painful.",
            "symptoms": "There is redness, pain, and increased tearing.",
            "onset_time": "It began around 12 hours ago.",
            "temp_c": "No fever, around 36.8 C.",
            "pain_score": "Eye pain is around 5 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "Bright light makes the discomfort worse.",
            "Vision is a little blurred when the pain gets stronger.",
        ],
        internal_medicine_round2_replies=[
            "I completed the eye-related checks and returned.",
            "Please confirm the diagnosis and treatment plan.",
        ],
        revisit_note="I came back after eye tests for final advice.",
    ),
    "ent_sore_throat": NpcPatientProfile(
        profile_id="ent_sore_throat",
        name="Han Qi",
        age=38,
        sex="male",
        chief_complaint="Severe sore throat",
        symptoms="sore throat, nasal congestion, mild ear fullness",
        onset_time="2 days ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 88, "temp_c": 37.5, "pain_score": 5},
        target_department_id="ent",
        target_department_name="Otolaryngology",
        triage_answers={
            "chief_complaint": "I have severe sore throat and blocked nose.",
            "symptoms": "Sore throat with congestion and ear fullness.",
            "onset_time": "Started 2 days ago.",
            "temp_c": "Temperature is around 37.5 C.",
            "pain_score": "Pain is around 5 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "Swallowing is painful, especially in the morning.",
            "I also feel pressure around the ears when blowing my nose.",
        ],
        internal_medicine_round2_replies=[
            "I completed the requested tests and returned for review.",
            "Please tell me if I need additional treatment.",
        ],
        revisit_note="I returned after ENT checks for a second consultation.",
    ),
    "dentistry_toothache": NpcPatientProfile(
        profile_id="dentistry_toothache",
        name="Li Na",
        age=45,
        sex="female",
        chief_complaint="Toothache on left lower molar",
        symptoms="toothache, gum swelling, pain while chewing",
        onset_time="4 days ago",
        allergies=["amoxicillin"],
        chronic_conditions=[],
        vitals={"heart_rate": 84, "temp_c": 37.0, "pain_score": 7},
        target_department_id="dentistry",
        target_department_name="Dentistry",
        triage_answers={
            "chief_complaint": "The left lower tooth hurts a lot.",
            "symptoms": "There is tooth pain, gum swelling, and chewing pain.",
            "onset_time": "Pain started about 4 days ago.",
            "temp_c": "No clear fever, around 37.0 C.",
            "pain_score": "Pain is around 7 out of 10.",
            "allergies": "I am allergic to amoxicillin.",
        },
        internal_medicine_round1_replies=[
            "The pain is worse at night and with cold drinks.",
            "I can chew only on the other side now.",
        ],
        internal_medicine_round2_replies=[
            "I finished the examination and returned for the result.",
            "Please explain the treatment options clearly.",
        ],
        revisit_note="I came back after dental checks for follow-up.",
    ),
    "dermatology_itchy_rash": NpcPatientProfile(
        profile_id="dermatology_itchy_rash",
        name="Sun Bo",
        age=26,
        sex="male",
        chief_complaint="Itchy skin rash",
        symptoms="itchy rash on forearms, redness, dry skin",
        onset_time="5 days ago",
        allergies=["seafood"],
        chronic_conditions=["eczema"],
        vitals={"heart_rate": 80, "temp_c": 36.7, "pain_score": 2},
        target_department_id="dermatology",
        target_department_name="Dermatology",
        triage_answers={
            "chief_complaint": "I have an itchy rash on my arms.",
            "symptoms": "There is redness, itching, and dry skin patches.",
            "onset_time": "It started about 5 days ago.",
            "temp_c": "No fever, around 36.7 C.",
            "pain_score": "Pain is low, around 2 out of 10.",
            "allergies": "I am allergic to seafood.",
        },
        internal_medicine_round1_replies=[
            "The itching gets worse at night and after sweating.",
            "I had similar eczema flares before but this one is more persistent.",
        ],
        internal_medicine_round2_replies=[
            "I completed the relevant checks and returned.",
            "Please confirm the diagnosis and how to control recurrence.",
        ],
        revisit_note="I returned after skin-related checks for follow-up.",
    ),
    "psychiatry_anxiety_insomnia": NpcPatientProfile(
        profile_id="psychiatry_anxiety_insomnia",
        name="He Xuan",
        age=33,
        sex="female",
        chief_complaint="Anxiety and insomnia",
        symptoms="anxiety, insomnia, poor concentration",
        onset_time="3 weeks ago",
        allergies=[],
        chronic_conditions=[],
        vitals={"heart_rate": 94, "temp_c": 36.6, "pain_score": 1},
        target_department_id="psychiatry",
        target_department_name="Psychiatry",
        triage_answers={
            "chief_complaint": "I feel anxious and cannot sleep well.",
            "symptoms": "I have anxiety, insomnia, and poor concentration.",
            "onset_time": "This started about 3 weeks ago.",
            "temp_c": "No fever, around 36.6 C.",
            "pain_score": "No obvious physical pain, around 1 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "I wake up many times at night and feel tired during the day.",
            "The anxiety has affected my work in recent days.",
        ],
        internal_medicine_round2_replies=[
            "I completed the suggested assessment and came back.",
            "Please explain the next treatment plan.",
        ],
        revisit_note="I returned after the requested assessment.",
    ),
    "rehabilitation_postop_recovery": NpcPatientProfile(
        profile_id="rehabilitation_postop_recovery",
        name="Luo Peng",
        age=52,
        sex="male",
        chief_complaint="Limited shoulder movement after surgery",
        symptoms="reduced shoulder range of motion, stiffness, mild pain",
        onset_time="2 weeks ago",
        allergies=[],
        chronic_conditions=["hypertension"],
        vitals={"heart_rate": 78, "temp_c": 36.8, "pain_score": 4},
        target_department_id="rehabilitation",
        target_department_name="Rehabilitation Medicine",
        triage_answers={
            "chief_complaint": "My shoulder movement is limited after surgery.",
            "symptoms": "There is stiffness, mild pain, and reduced motion range.",
            "onset_time": "Symptoms have been present for around 2 weeks.",
            "temp_c": "No fever, around 36.8 C.",
            "pain_score": "Pain is around 4 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "I cannot raise my arm fully, especially in the morning.",
            "Pain increases after activity but improves with rest.",
        ],
        internal_medicine_round2_replies=[
            "I completed the planned checks and came back.",
            "Please tell me the rehabilitation steps I should follow.",
        ],
        revisit_note="I returned after examination for rehab planning.",
    ),
    "pain_chronic_back_pain": NpcPatientProfile(
        profile_id="pain_chronic_back_pain",
        name="Tang Lei",
        age=47,
        sex="male",
        chief_complaint="Chronic low back pain",
        symptoms="chronic low back pain, occasional leg numbness",
        onset_time="6 months ago",
        allergies=[],
        chronic_conditions=["lumbar disc disease"],
        vitals={"heart_rate": 82, "temp_c": 36.7, "pain_score": 7},
        target_department_id="pain",
        target_department_name="Pain Management",
        triage_answers={
            "chief_complaint": "I have chronic low back pain.",
            "symptoms": "Back pain with occasional numbness down the leg.",
            "onset_time": "It has lasted around 6 months.",
            "temp_c": "No fever, around 36.7 C.",
            "pain_score": "Pain is around 7 out of 10.",
            "allergies": "No known drug allergies.",
        },
        internal_medicine_round1_replies=[
            "Sitting for long periods makes the pain worse.",
            "I get temporary relief after stretching but pain returns quickly.",
        ],
        internal_medicine_round2_replies=[
            "I finished the ordered checks and came back with the report.",
            "Please explain the long-term pain management plan.",
        ],
        revisit_note="I returned after tests for pain management follow-up.",
    ),
}

_PROFILES_BY_DEPARTMENT: dict[str, list[NpcPatientProfile]] = {}
for _profile in _PROFILES.values():
    _PROFILES_BY_DEPARTMENT.setdefault(_profile.target_department_id, []).append(_profile)

_PROFILE_ALIASES = {
    "respiratory_mild": "internal_respiratory",
    "abdominal_pain": "internal_respiratory",
    "dizziness_followup": "internal_respiratory",
}


def list_profiles(department_id: str | None = None) -> list[NpcPatientProfile]:
    if department_id:
        return list(_PROFILES_BY_DEPARTMENT.get(department_id, []))
    return list(_PROFILES.values())


def get_profile(profile_id: str) -> NpcPatientProfile:
    canonical_id = _PROFILE_ALIASES.get(profile_id, profile_id)
    try:
        return _PROFILES[canonical_id]
    except KeyError as exc:
        raise KeyError(f"unknown npc profile: {profile_id}") from exc
