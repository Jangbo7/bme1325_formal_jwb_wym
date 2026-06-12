const PERSON_PROFILES = {
  "walk-er-1": patient("P-ER-001", "Emergency", "Alex Morgan", "Acute abdominal pain, dizziness"),
  "wait-er-1": patient("P-ER-002", "Emergency", "Jamie Chen", "Fever and sore throat"),
  "wait-er-2": patient("P-ER-003", "Emergency", "Riley Patel", "Minor trauma, awaiting triage"),
  "walk-op-1": patient("P-OP-001", "Outpatient", "Taylor Brooks", "Follow-up after medication adjustment"),
  "wait-op-1": patient("P-OP-002", "Outpatient", "Morgan Liu", "Cough, mild fever"),
  "wait-op-2": patient("P-OP-003", "Outpatient", "Casey Wong", "Headache and fatigue"),
  "consult-a": patient("P-OP-004", "Outpatient", "Lin Xia", "Chest discomfort consultation"),
  "consult-b": patient("P-OP-005", "Outpatient", "Noah Smith", "Skin rash and itching"),
  "consult-int": patient("P-IM-001", "Internal Medicine", "Avery Zhao", "Diabetes follow-up"),
  "walk-mdt-1": patient("P-MDT-001", "MDT Center", "Jordan Wu", "Complex tumor case review"),
  "wait-ward-1": patient("P-WD-001", "Ward", "Harper Sun", "Family waiting for ward update"),
  "icu-bed-a": patient("P-ICU-001", "ICU", "Ethan Zhang", "Postoperative respiratory monitoring"),
  "icu-bed-b": patient("P-ICU-002", "ICU", "Mia Huang", "Sepsis observation"),
  "icu-isolation": patient("P-ICU-003", "ICU Isolation", "Lucas Yang", "Infectious disease isolation care"),
  "ward-bed-a": patient("P-WD-002", "Ward", "Grace Li", "Postoperative recovery"),
  "ward-bed-b": patient("P-WD-003", "Ward", "Owen Wang", "Pneumonia recovery"),
  "ward-bed-c": patient("P-WD-004", "Ward", "Nora Xu", "Fracture rehabilitation"),

  "nurse-er-a": staff("nurse", "N-ER-001", "Emergency", "Nurse Emily Carter"),
  "nurse-er-b": staff("nurse", "N-ER-002", "Emergency", "Nurse Daniel Lee"),
  "doctor-er-a": staff("doctor", "D-ER-001", "Emergency", "Dr. Michael Chen"),
  "doctor-er-b": staff("doctor", "D-ER-002", "Emergency", "Dr. Sarah Lin"),
  "nurse-op-reg": staff("nurse", "N-OP-001", "Registration", "Nurse Anna Zhou"),
  "nurse-op-triage": staff("nurse", "N-OP-002", "Triage", "Nurse Kevin Wu"),
  "doctor-op-a": staff("doctor", "D-OP-001", "Outpatient", "Dr. Emma Wang"),
  "doctor-op-b": staff("doctor", "D-OP-002", "Outpatient", "Dr. Jason Liu"),
  "doctor-op-internal": staff("doctor", "D-IM-001", "Internal Medicine", "Dr. Brian Zhao"),
  "doctor-op-surgery": staff("doctor", "D-SG-001", "Surgery Clinic", "Dr. Olivia Sun"),
  "nurse-op-wait": staff("nurse", "N-OP-003", "Outpatient Waiting", "Nurse Lily Huang"),
  "nurse-icu-station-a": staff("nurse", "N-ICU-001", "ICU", "Nurse Fiona Yu"),
  "nurse-icu-station-b": staff("nurse", "N-ICU-002", "ICU", "Nurse Aaron Ma"),
  "doctor-icu-bed-a": staff("doctor", "D-ICU-001", "ICU", "Dr. Helen Guo"),
  "doctor-icu-bed-b": staff("doctor", "D-ICU-002", "ICU", "Dr. Mark Tang"),
  "nurse-icu-isolation": staff("nurse", "N-ICU-003", "ICU Isolation", "Nurse Amy Qian"),
  "doctor-mdt-a": staff("doctor", "D-MDT-001", "MDT Center", "Dr. Claire Luo"),
  "doctor-mdt-b": staff("doctor", "D-MDT-002", "MDT Center", "Dr. Eric Fang"),
  "doctor-mdt-c": staff("doctor", "D-IMG-001", "Imaging Review", "Dr. Sophia Gao"),
  "nurse-mdt-coord": staff("nurse", "N-MDT-001", "MDT Center", "Nurse Wendy He"),
  "nurse-ward-station-a": staff("nurse", "N-WD-001", "Ward", "Nurse Bella Lin"),
  "nurse-ward-station-b": staff("nurse", "N-WD-002", "Ward", "Nurse Leo Chen"),
  "doctor-ward-office": staff("doctor", "D-WD-001", "Ward", "Dr. Victor Shen"),
  "doctor-ward-round": staff("doctor", "D-WD-002", "Ward", "Dr. Rachel Xu"),
  "nurse-ward-room-c": staff("nurse", "N-WD-003", "Ward", "Nurse Ivy Deng"),
};

export function fetchPersonProfile(id) {
  return new Promise((resolve) => {
    window.setTimeout(() => {
      resolve(PERSON_PROFILES[id] || null);
    }, 120);
  });
}

function patient(patientId, department, name, symptoms) {
  return { type: "patient", patientId, department, name, symptoms };
}

function staff(type, employeeId, department, name) {
  return { type, employeeId, department, name };
}
