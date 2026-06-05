import threading


class InMemoryPatientMemoryStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.memories = {}

    def get_or_create(self, patient_id, name=""):
        with self.lock:
            memory = self.memories.get(patient_id)
            if memory is None:
                memory = {
                    "patient_id": patient_id,
                    "profile": {
                    "name": name or patient_id,
                    "age": None,
                    "sex": None,
                    "allergies": [],
                    "allergy_status": "unknown",
                    "chronic_conditions": [],
                    "baseline_risk_flags": [],
                },
                    "clinical_memory": {
                        "chief_complaint": "",
                        "symptoms": [],
                        "onset_time": None,
                        "vitals": {},
                        "risk_flags": [],
                        "last_department": None,
                        "last_triage_level": None,
                    },
                    "triage_history": [],
                }
                self.memories[patient_id] = memory
            elif name:
                memory["profile"]["name"] = name
            return {
                "patient_id": memory["patient_id"],
                "profile": {
                    "name": memory["profile"]["name"],
                    "age": memory["profile"]["age"],
                    "sex": memory["profile"]["sex"],
                    "allergies": list(memory["profile"]["allergies"]),
                    "allergy_status": memory["profile"].get("allergy_status", "unknown"),
                    "chronic_conditions": list(memory["profile"]["chronic_conditions"]),
                    "baseline_risk_flags": list(memory["profile"]["baseline_risk_flags"]),
                },
                "clinical_memory": {
                    "chief_complaint": memory["clinical_memory"]["chief_complaint"],
                    "symptoms": list(memory["clinical_memory"]["symptoms"]),
                    "onset_time": memory["clinical_memory"]["onset_time"],
                    "vitals": dict(memory["clinical_memory"]["vitals"]),
                    "risk_flags": list(memory["clinical_memory"]["risk_flags"]),
                    "last_department": memory["clinical_memory"]["last_department"],
                    "last_triage_level": memory["clinical_memory"]["last_triage_level"],
                },
                "triage_history": list(memory["triage_history"]),
            }

    def upsert(self, patient_id, memory):
        with self.lock:
            self.memories[patient_id] = memory


PATIENT_MEMORY_STORE = InMemoryPatientMemoryStore()
