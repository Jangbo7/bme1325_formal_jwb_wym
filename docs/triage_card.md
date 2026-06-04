---

id: triage_knowledge_base_v1
source_layer: triage_reference
agent_scope: triage_agent
category: triage_knowledge_base
language: en
retrieval_priority: high
authority_level: national_policy_and_international_reference
safety_level: red_flag_screening
version: 0.1
last_reviewed: 2026-05-28
-------------------------

# Outpatient and Emergency Triage Knowledge Base v1

## 0. Purpose

This file is a lightweight triage knowledge base for the `triage_agent` in the simulated hospital project. It is not a complete clinical guideline. Its purpose is to provide:

1. A basic triage priority framework;
2. Red-flag recognition for common chief complaints;
3. Common department-routing references;
4. Escalation cues for special populations and potentially critical conditions;
5. Structured knowledge blocks suitable for RAG retrieval.

This file should not be used to provide definitive diagnosis, treatment plans, prescriptions, or interpretation of test results. In real clinical settings, triage should be performed by trained healthcare professionals using vital signs, physical examination, medical history, direct observation, and institutional protocols.

---

# 1. Core Goal of Triage

The core goal of triage is not to diagnose the patient’s exact disease. Instead, triage should determine:

1. Whether there is an immediate risk to life or organ function;
2. Whether the patient needs emergency care, a green-channel workflow, or high-priority handling;
3. Whether the patient can enter a routine outpatient workflow;
4. Which department or specialty pathway is most appropriate;
5. What key information is still missing.

Triage decisions should prioritize severity and risk before disease naming.

---

# 2. Four-Level Triage Priority Reference

## Level I: Critical Patient

### Key Features

The patient may be experiencing, or about to experience, life-threatening deterioration and requires immediate rescue or emergency intervention.

### Common Signals

* Cardiac arrest or respiratory arrest;
* Airway obstruction, choking, or severe respiratory distress;
* Shock-like presentation;
* Loss of consciousness, coma, or persistent seizure;
* Major trauma, multiple injuries, or massive bleeding;
* Extreme abnormalities in vital signs;
* Severe allergic reaction with breathing difficulty, throat swelling, or blood pressure drop.

### Triage Meaning

The patient should enter immediate emergency treatment or a green-channel rescue workflow.

---

## Level II: High-Risk Emergency Patient

### Key Features

The patient is not yet fully decompensated but has a high risk of rapid deterioration. Priority assessment and treatment are usually required.

### Common Signals

* Persistent or severe chest pain;
* Obvious shortness of breath;
* Sudden limb weakness, slurred speech, facial droop, or altered consciousness;
* Severe abdominal pain, suspected peritoneal irritation, or persistent vomiting;
* Serious trauma with temporarily stable vital signs;
* Pregnant or postpartum patient with significant abdominal pain, heavy vaginal bleeding, or abnormal fetal movement;
* Child with poor responsiveness, lethargy, breathing difficulty, or obvious dehydration;
* Severe psychiatric or behavioral disturbance with risk of self-harm or harm to others.

### Triage Meaning

The patient should be assigned higher priority and enter an emergency or rapid-assessment workflow.

---

## Level III: Urgent Patient

### Key Features

The patient has acute symptoms requiring timely medical care, but there is no clear immediate life-threatening signal at the moment.

### Common Signals

* Moderate fever, pain, vomiting, or diarrhea;
* Mild to moderate trauma or wound;
* Acute symptoms with relatively stable vital signs;
* Acute worsening of chronic disease without obvious red flags;
* Eye pain, ear pain, toothache, rash, or other symptoms that significantly affect daily life but lack immediate danger signs.

### Triage Meaning

The patient may enter the corresponding specialty clinic, urgent outpatient queue, or non-critical emergency queue.

---

## Level IV: Non-Urgent or Subacute Patient

### Key Features

Symptoms are mild, stable, chronic, or mainly related to follow-up, documents, routine consultation, or routine health checks.

### Common Signals

* Mild, stable symptoms that do not affect basic activities;
* Stable chronic disease follow-up;
* Routine health check or report consultation;
* Mild rash, mild cough, or mild pain;
* Routine outpatient needs without red-flag symptoms.

### Triage Meaning

The patient may enter a routine outpatient or appointment-based workflow.

---

# 3. Information to Collect During Triage

## 3.1 Basic Information

* Age;
* Sex;
* Pregnancy or postpartum status;
* Whether the patient is a child, older adult, disabled person, or other special population;
* Chronic diseases;
* Current use of anticoagulants, glucose-lowering drugs, antihypertensives, psychiatric medications, or other high-risk medications;
* Severe allergy history;
* Recent surgery, trauma, hospitalization, or infectious exposure.

## 3.2 Current Chief Complaint

* What is the main discomfort or concern?
* When did it start?
* Did it start suddenly or gradually?
* Is it getting worse?
* Is this the first episode?
* Does it affect breathing, consciousness, movement, eating, urination, bowel movement, or sleep?

## 3.3 Symptom Severity

* Pain score or subjective severity;
* Whether the symptom is persistent and not relieved;
* Whether there is fainting, sweating, shortness of breath, vomiting blood, black stool, seizure, or other severe associated symptoms;
* Whether the symptom affects walking, speaking, swallowing, breathing, or consciousness.

## 3.4 Vital-Sign Clues

If the system can collect or simulate vital signs, pay attention to:

* Body temperature;
* Heart rate;
* Respiratory rate;
* Blood pressure;
* Oxygen saturation;
* Blood glucose;
* Mental status.

Markedly abnormal vital signs should trigger escalation rather than routine outpatient handling.

---

# 4. General Red-Flag Signal Library

The following situations are high-risk triage signals. If any are present, priority should be increased and emergency care, a green-channel workflow, or another high-priority pathway should be considered.

## 4.1 Airway and Breathing Red Flags

* Breathing difficulty;
* Difficulty speaking or inability to speak full sentences;
* Wheezing, suffocation sensation, or choking;
* Blue or gray lips or skin;
* Suspected foreign body aspiration;
* Severe asthma-like attack;
* Throat swelling or severe allergic reaction;
* Markedly low oxygen saturation.

## 4.2 Circulation and Shock Red Flags

* Fainting or near-fainting;
* Cold sweat, pale face, cold or clammy limbs;
* Palpitations with chest pain or shortness of breath;
* Heavy bleeding;
* Markedly abnormal blood pressure;
* Severe dehydration;
* Shock-like presentation.

## 4.3 Consciousness and Neurological Red Flags

* Confusion;
* Coma;
* Seizure;
* Sudden limb weakness or numbness;
* Facial droop;
* Slurred speech;
* Sudden blurred vision or double vision;
* Sudden severe headache;
* Neck stiffness with fever;
* Altered consciousness, vomiting, or seizure after head trauma.

## 4.4 Chest Pain and Cardiovascular Red Flags

* Persistent chest pain not relieved;
* Crushing, squeezing, or tight chest pain;
* Chest pain radiating to the left arm, right arm, shoulder, back, neck, or jaw;
* Chest pain with sweating, nausea, shortness of breath, dizziness, or fainting;
* Chest pain with syncope;
* Significant palpitations with chest tightness or shortness of breath;
* New or worsening chest symptoms in a patient with known heart disease.

## 4.5 Abdominal Pain and Gastrointestinal Red Flags

* Severe abdominal pain;
* Abdominal pain that keeps worsening;
* Abdominal pain with fever, chills, or marked weakness;
* Vomiting blood;
* Black stool;
* Bloody stool;
* Persistent vomiting with inability to eat or drink;
* Marked abdominal distension with inability to pass stool or gas;
* Abdominal pain with fainting or shock-like presentation;
* Abdominal pain or abnormal vaginal bleeding during pregnancy.

## 4.6 Trauma Red Flags

* Traffic accident, fall from height, crushing injury, or other high-energy trauma;
* Head or neck trauma;
* Chest or abdominal trauma;
* Multiple injuries;
* Deep, large, or obviously contaminated wound;
* Bleeding that cannot be stopped;
* Limb deformity, suspected fracture, or dislocation;
* Sensory or motor impairment after injury;
* Altered consciousness, persistent vomiting, or seizure after trauma.

## 4.7 Infection and Fever Red Flags

* High fever with altered consciousness;
* Fever with breathing difficulty;
* Fever with neck stiffness;
* Fever with purpura or non-blanching rash;
* Fever with severe abdominal pain;
* Fever with markedly reduced urine output;
* Fever in immunocompromised patients, patients receiving cancer treatment, or patients using long-term steroids;
* High fever or poor general condition in infants, older adults, or pregnant/postpartum patients.

## 4.8 Allergy and Skin Red Flags

* Rash with breathing difficulty;
* Swelling of lips, tongue, or throat;
* Generalized hives with dizziness, chest tightness, or blood pressure drop;
* Widespread blisters;
* Rash with erosion of the mouth, eyes, or genital mucosa;
* Severe rash or systemic discomfort after starting a new medication;
* Rapidly spreading skin redness, swelling, heat, and pain with fever.

## 4.9 Obstetrics and Gynecology Red Flags

* Heavy vaginal bleeding during pregnancy;
* Severe abdominal pain during pregnancy;
* Markedly reduced or absent fetal movement in late pregnancy;
* Heavy postpartum bleeding;
* Postpartum fever with abdominal pain or abnormal wound symptoms;
* Gynecologic abdominal pain with fainting;
* Possible ectopic pregnancy risk: missed period, abdominal pain, vaginal bleeding, dizziness, or fainting.

## 4.10 Pediatric Red Flags

* Fever in an infant younger than 3 months;
* Breathing difficulty, wheezing, or blue lips;
* Seizure;
* Lethargy or poor responsiveness;
* Persistent crying that cannot be comforted;
* Severe dehydration: markedly reduced urine output, sunken eyes, poor responsiveness;
* Repeated vomiting;
* Bloody stool;
* Non-blanching rash;
* High fever with altered mental status.

## 4.11 Psychiatric and Behavioral Red Flags

* Clear suicidal thoughts;
* Self-harm plan or recent self-harm behavior;
* Risk of harming others;
* Extreme agitation or uncontrolled behavior;
* Hallucinations or delusions with dangerous behavior;
* Severe alcohol or drug intoxication/withdrawal;
* Inability to care for oneself or immediate safety risk.

---

# 5. Common Chief Complaint Guidance

## 5.1 Fever

### Key Questions

* What is the measured temperature?
* How long has the fever lasted?
* Is there chills or rigors?
* Is there cough, sore throat, diarrhea, painful urination, or rash?
* Is there poor responsiveness, altered consciousness, or breathing difficulty?
* Is the patient a child, older adult, pregnant/postpartum, or immunocompromised?
* Has there been recent travel, infectious exposure, or clustered illness?

### Common Direction

* Fever with cough or sore throat: respiratory/infectious disease direction or internal medicine;
* Fever with painful urination or flank pain: urinary/internal medicine direction;
* Fever with abdominal pain or diarrhea: internal medicine/gastrointestinal direction;
* Fever with rash: dermatology or infectious disease direction;
* Fever in children: pediatrics;
* High fever with altered consciousness, breathing difficulty, or severe dehydration: high-priority emergency workflow.

---

## 5.2 Chest Pain / Chest Tightness

### Key Questions

* Did it start suddenly?
* Is it persistent and not relieved?
* Is it crushing, squeezing, or tight?
* Does it radiate to the shoulder, back, arm, neck, or jaw?
* Is there sweating, nausea, shortness of breath, dizziness, or fainting?
* Are there risk factors such as hypertension, diabetes, coronary heart disease, or smoking history?

### Common Direction

* Chest pain with shortness of breath, sweating, radiating pain, or fainting: emergency/cardiovascular high-priority workflow;
* Chest pain related to breathing, cough, or fever: respiratory/internal medicine direction, but red flags still need exclusion;
* Chest wall tenderness or post-traumatic chest pain: surgery/orthopedics direction, but breathing difficulty or severe trauma requires escalation;
* Long-term mild chest tightness without red flags: internal medicine or cardiology outpatient workflow.

---

## 5.3 Breathing Difficulty / Shortness of Breath

### Key Questions

* Did it appear suddenly?
* Is the patient short of breath even at rest?
* Can the patient speak full sentences?
* Is there chest pain, wheezing, coughing blood, or fever?
* Is there a history of asthma, COPD, or heart disease?
* Is oxygen saturation low?

### Common Direction

* Severe breathing difficulty, cyanosis, or inability to speak: high-priority emergency workflow;
* Breathing difficulty with chest pain: emergency/cardiovascular or respiratory high-priority workflow;
* Breathing difficulty with fever and cough: respiratory/infectious disease direction;
* Chronic shortness of breath on exertion: internal medicine, respiratory medicine, or cardiology direction.

---

## 5.4 Abdominal Pain

### Key Questions

* Where is the pain located?
* Did it start suddenly?
* Is it continuously worsening?
* Is it severe?
* Is there fever, vomiting, or diarrhea?
* Is there vomiting blood, black stool, or bloody stool?
* Is there abdominal distension or inability to pass stool or gas?
* Is the patient pregnant or possibly pregnant?
* Did the pain occur after trauma?

### Common Direction

* Mild to moderate abdominal pain with diarrhea or nausea: internal medicine/gastroenterology direction;
* Right lower abdominal pain, worsening pain, or fever: surgery or emergency evaluation;
* Severe abdominal pain, black stool, vomiting blood, or fainting: high-priority emergency workflow;
* Abdominal pain or abnormal bleeding during pregnancy: obstetrics/gynecology or high-priority emergency workflow;
* Abdominal pain after trauma: surgery/emergency direction.

---

## 5.5 Headache / Dizziness

### Key Questions

* Is this a sudden, worst-ever headache?
* Is there limb weakness, slurred speech, or visual disturbance?
* Is there fever or neck stiffness?
* Was there head trauma?
* Is there vomiting, altered consciousness, or seizure?
* Is this a long-term recurrent symptom?

### Common Direction

* Sudden severe headache, neurological deficit, or altered consciousness: emergency/neurology high-priority workflow;
* Headache with fever and neck stiffness: high-priority emergency workflow;
* Headache and vomiting after head trauma: emergency/surgery direction;
* Chronic recurrent headache without red flags: neurology or pain medicine outpatient workflow;
* Dizziness with tinnitus or hearing loss: ENT or neurology direction.

---

## 5.6 Cough / Sore Throat

### Key Questions

* How long has it lasted?
* Is there fever?
* Is there shortness of breath?
* Is there chest pain?
* Is there coughing blood?
* Is there difficulty swallowing or breathing?
* Is the patient a child, older adult, or someone with underlying disease?
* Has cough with sputum lasted more than 2 weeks?

### Common Direction

* Mild to moderate cough or sore throat: internal medicine, respiratory medicine, or ENT direction;
* Coughing blood, breathing difficulty, or chest pain: emergency or respiratory high-priority workflow;
* Cough with sputum lasting more than 2 weeks: chronic respiratory disease or tuberculosis-screening direction;
* Child with cough, wheezing, or poor responsiveness: pediatric high-priority workflow.

---

## 5.7 Trauma / Wound / Pain

### Key Questions

* What was the injury mechanism?
* Was it a fall from height, traffic accident, or crushing injury?
* Is there head, neck, chest, or abdominal injury?
* Is bleeding difficult to stop?
* Is there limb deformity, inability to move, or numbness?
* Is the wound deep, dirty, or associated with foreign body?
* Is there a tetanus risk or animal bite?

### Common Direction

* Minor abrasion or sprain: surgery/orthopedics routine workflow;
* Deep wound, contaminated wound, or bleeding that cannot be stopped: surgery/emergency workflow;
* Suspected fracture or dislocation: orthopedics/emergency workflow;
* Multiple injuries or high-energy trauma: high-priority emergency workflow;
* Animal bite: surgery/emergency/vaccination-related workflow.

---

## 5.8 Eye Symptoms

### Key Questions

* One eye or both eyes?
* Is there sudden vision loss?
* Is there obvious eye pain?
* Was there trauma or chemical exposure?
* Is there redness, photophobia, or discharge?
* Are there flashes, floaters, or a curtain-like visual field defect?
* Is there headache or nausea?

### Common Direction

* Sudden vision loss, chemical injury, or penetrating injury: ophthalmology emergency high-priority workflow;
* Red eye with pain and vision loss: ophthalmology high-priority workflow;
* Eye dryness or visual fatigue: ophthalmology routine outpatient workflow;
* Flashes/floaters with visual field shadow: ophthalmology high-priority workflow.

---

## 5.9 ENT Symptoms

### Key Questions

* Is there ear pain, hearing loss, tinnitus, or vertigo?
* Can a nosebleed be stopped?
* Is there throat swelling, sore throat, or swallowing difficulty?
* Is there breathing difficulty?
* Is there suspected aspiration or foreign body stuck in the throat?
* How long has hoarseness lasted?

### Common Direction

* Sudden hearing loss: ENT high-priority workflow;
* Nosebleed that cannot be stopped: ENT/emergency workflow;
* Throat swelling with breathing difficulty: high-priority emergency workflow;
* Common rhinitis, sore throat, or ear fullness: ENT routine outpatient workflow.

---

## 5.10 Oral and Dental Symptoms

### Key Questions

* Where is the tooth pain located?
* Is there facial swelling?
* Is there fever?
* Is there difficulty opening the mouth?
* Is there difficulty swallowing or breathing?
* Was there trauma causing tooth avulsion or fracture?
* Is bleeding difficult to stop?

### Common Direction

* Common toothache or gum bleeding: dentistry/stomatology workflow;
* Facial or neck swelling with fever: dentistry/emergency high-priority workflow;
* Breathing or swallowing difficulty: high-priority emergency workflow;
* Traumatic tooth avulsion or severe bleeding: dental emergency or surgery workflow.

---

## 5.11 Rash / Allergy

### Key Questions

* When did the rash appear?
* Was there any new medication?
* Was there suspicious food or allergen exposure?
* Are there generalized hives?
* Is there swelling of lips, tongue, or throat?
* Is there breathing difficulty?
* Is there fever, pain, blistering, or mucosal erosion?

### Common Direction

* Mild localized rash or itching: dermatology workflow;
* Rash with breathing difficulty or throat swelling: high-priority emergency workflow;
* Widespread rash, blisters, or mucosal involvement after a new medication: emergency/dermatology high-priority workflow;
* Fever with rash: dermatology, infectious disease, or emergency workflow depending on severity.

---

## 5.12 Obstetrics and Gynecology Symptoms

### Key Questions

* Is the patient pregnant or possibly pregnant?
* What was the last menstrual period?
* How much vaginal bleeding is present?
* How severe is the abdominal pain?
* Is there dizziness or fainting?
* Is there fever?
* Is the patient postpartum?
* Is fetal movement abnormal?

### Common Direction

* Menstrual abnormalities, abnormal discharge, or mild to moderate pelvic discomfort: gynecology outpatient workflow;
* Abdominal pain, bleeding, or abnormal fetal movement during pregnancy: obstetrics/gynecology high-priority workflow;
* Heavy vaginal bleeding or abdominal pain with fainting: high-priority emergency workflow;
* Postpartum bleeding or fever: obstetrics/gynecology or emergency high-priority workflow.

---

## 5.13 Pediatric Symptoms

### Key Questions

* What is the child’s age?
* What is the temperature?
* What is the child’s mental status?
* Is feeding normal?
* Is urine output reduced?
* Is there breathing difficulty?
* Was there a seizure?
* Is there rash?
* Is there diarrhea, vomiting, or dehydration?

### Common Direction

* Common fever, cough, vomiting, or diarrhea: pediatrics workflow;
* Fever in an infant younger than 3 months: pediatric high-priority workflow;
* Breathing difficulty, seizure, lethargy, or obvious dehydration: emergency/pediatric high-priority workflow;
* Rash with poor responsiveness or non-blanching rash: high-priority emergency workflow.

---

## 5.14 Mental Health and Behavioral Concerns

### Key Questions

* Are there thoughts of self-harm or suicide?
* Is there a clear plan?
* Has there been recent self-harm or a suicide attempt?
* Is there risk of harming others?
* Is the patient extremely agitated or unable to control behavior?
* Are there hallucinations or delusions?
* Is alcohol or drug use involved?
* Can immediate safety be maintained?

### Common Direction

* Sleep problems, anxiety, low mood, or stress without safety risk: psychiatry/psychological medicine routine outpatient workflow;
* Self-harm, suicide, or harm-to-others risk: emergency or psychiatric high-priority workflow;
* Confusion, severe agitation, intoxication, or withdrawal: high-priority emergency workflow.

---

# 6. Common Department Direction Reference

## Internal Medicine

Common adult internal-medicine symptoms, multi-system symptoms, chronic disease follow-up, fever, cough, diarrhea, fatigue, dizziness, blood pressure or blood glucose abnormalities.

## Surgery

Trauma, wounds, lumps or masses, suspected acute abdomen, postoperative issues, or problems requiring surgical assessment.

## Obstetrics and Gynecology

Menstrual abnormalities, vaginal bleeding, abnormal discharge, pelvic pain, pregnancy-related problems, postpartum issues, infertility, contraception, or reproductive health consultation.

## Pediatrics

Common symptoms in children and adolescents, including fever, cough, vomiting, diarrhea, rash, feeding problems, and growth/development concerns.

## Ophthalmology

Vision loss, eye pain, red eye, eye trauma, floaters, flashes, foreign body sensation, and other eye-related symptoms.

## ENT

Ear pain, hearing loss, tinnitus, vertigo, nasal congestion, nosebleed, sore throat, hoarseness, and swallowing discomfort.

## Dentistry / Stomatology

Toothache, gum swelling, oral ulcer, dental trauma, oral mucosal problems, restoration, orthodontics, and tooth extraction-related issues.

## Dermatology

Rash, itching, acne, eczema-like symptoms, urticaria, skin infection, pigmentation or mole changes, and hair/scalp problems.

## Psychiatry / Psychological Medicine

Anxiety, depression, sleep disorder, panic symptoms, abnormal behavior, psychological stress, and functional somatic complaints.

## Rehabilitation

Functional impairment, postoperative rehabilitation, post-stroke rehabilitation, reduced mobility, gait/balance problems, and chronic pain causing functional limitation.

## Pain Medicine

Chronic pain, neuropathic pain, neck/shoulder/back/leg pain, postherpetic neuralgia-like pain, cancer-related pain, postoperative persistent pain, and pain affecting sleep or daily life.

---

# 7. Special Population Triage Notes

## 7.1 Children

Children may deteriorate quickly, especially infants. Triage should pay close attention to mental status, feeding, urine output, breathing, crying pattern, skin color, and caregiver-reported abnormal behavior.

## 7.2 Pregnant and Postpartum Patients

During pregnancy or postpartum, abdominal pain, vaginal bleeding, severe headache, visual symptoms, abnormal fetal movement, severe swelling, fever, or fainting should increase priority.

## 7.3 Older Adults

Symptoms in older adults may be atypical. Chest pain, infection, dehydration, confusion, falls, and generalized weakness may indicate higher risk than they initially appear.

## 7.4 Patients With Chronic Disease

Patients with diabetes, hypertension, coronary heart disease, chronic lung disease, kidney disease, liver disease, cancer, or immunosuppression should be handled more cautiously when acute symptoms occur.

## 7.5 Patients With Mental Health Safety Risk

Self-harm, suicide risk, harm-to-others risk, severe agitation, hallucinations or delusions with dangerous behavior, and inability to care for oneself should be treated as safety-priority signals.

---

# 8. Suggested RAG Retrieval Tags

## High-Priority Tags

* red_flag
* emergency
* chest_pain
* dyspnea
* stroke_symptom
* severe_abdominal_pain
* major_trauma
* heavy_bleeding
* pregnancy_bleeding
* pediatric_fever
* suicidal_ideation
* allergic_reaction

## Chief Complaint Tags

* fever
* cough
* sore_throat
* abdominal_pain
* diarrhea
* vomiting
* headache
* dizziness
* chest_discomfort
* trauma
* wound
* rash
* toothache
* eye_pain
* hearing_loss
* pelvic_pain
* sleep_problem
* chronic_pain

## Department Tags

* internal_medicine
* surgery
* obgyn
* pediatrics
* ophthalmology
* ent
* dentistry
* dermatology
* psychiatry
* rehabilitation
* pain

---

# 9. Suggested Structured Triage Result Fields

```json
{
  "triage_level": "I | II | III | IV | unknown",
  "urgency": "immediate | high | medium | routine | unknown",
  "chief_complaint": "",
  "red_flags_detected": [],
  "special_population_flags": [],
  "suggested_department": "",
  "suggested_subspecialty": "",
  "missing_key_information": [],
  "common_judgment_basis": [],
  "next_flow": "emergency_green_channel | urgent_assessment | specialty_outpatient | routine_appointment | ask_more_information"
}
```

---

# 10. Source Registry

## S1. National Health Commission of China: Medical Quality Control Indicators for Emergency Medicine, 2024 Edition

Purpose: Supports the emergency triage Level I-IV framework and emphasizes graded triage execution and emergency quality management.

## S2. National Health Commission of China: Action Plan for Comprehensively Improving Medical Quality, 2023-2025

Purpose: Supports strengthening pre-examination triage, optimizing emergency workflows, green-channel pathways for critical illness, and multidisciplinary emergency coordination.

## S3. National Health Commission of China: Interim Provisions on Outpatient Quality Management in Medical Institutions and Policy Interpretation

Purpose: Supports outpatient quality management, process-based outpatient care, and standardization of outpatient diagnosis and treatment workflows.

## S4. WHO: Emergency Triage Assessment and Treatment, ETAT

Purpose: Supports recognition of pediatric emergency signs, especially airway, breathing, circulation, consciousness disturbance, seizure, and severe dehydration.

## S5. NHS: Public Guidance on Heart Attack and Stomach Pain

Purpose: Supports emergency warning signs such as chest pain, shortness of breath, fainting, severe abdominal pain, vomiting blood, bloody stool, abdominal distension, and inability to pass stool or gas.

## S6. CDC: Heart Attack Warning Signs

Purpose: Supports cardiovascular red flags including chest discomfort, shortness of breath, arm/neck/jaw/back pain, nausea, dizziness, and unusual fatigue.

## S7. Emergency Medicine Expert Consensus and Triage Standards

Purpose: Supports symptom-based and sign-based triage using airway, breathing, circulation, consciousness, pain, vital signs, and overall risk severity.
