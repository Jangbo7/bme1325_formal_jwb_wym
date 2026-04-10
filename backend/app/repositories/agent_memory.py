from app.database import Database


class AgentMemoryRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_shared_memory(self, patient_id: str, name: str = "") -> dict:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT data_json FROM patient_shared_memory WHERE patient_id = ?", (patient_id,)).fetchone()
            if row:
                return Database.decode_json(row["data_json"], {})
            payload = {
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
            }
            conn.execute(
                "INSERT INTO patient_shared_memory (patient_id, data_json) VALUES (?, ?)",
                (patient_id, Database.encode_json(payload)),
            )
            conn.commit()
            return payload
        finally:
            conn.close()

    def save_shared_memory(self, patient_id: str, payload: dict) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO patient_shared_memory (patient_id, data_json)
                VALUES (?, ?)
                ON CONFLICT(patient_id) DO UPDATE SET data_json=excluded.data_json
                """,
                (patient_id, Database.encode_json(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def get_agent_session_memory(self, session_id: str, patient_id: str, agent_type: str = "triage") -> dict:
        conn = self.db.connect()
        try:
            row = conn.execute("SELECT data_json FROM agent_session_memory WHERE session_id = ?", (session_id,)).fetchone()
            if row:
                return Database.decode_json(row["data_json"], {})
            payload = {
                "session_id": session_id,
                "patient_id": patient_id,
                "agent_type": agent_type,
                "dialogue_state": "idle",
                "latest_summary": {},
                "missing_fields": [],
                "expected_field": None,
                "assistant_message": "",
                "evidence": [],
            }
            conn.execute(
                "INSERT INTO agent_session_memory (session_id, patient_id, agent_type, data_json) VALUES (?, ?, ?, ?)",
                (session_id, patient_id, agent_type, Database.encode_json(payload)),
            )
            conn.commit()
            return payload
        finally:
            conn.close()

    def save_agent_session_memory(self, session_id: str, patient_id: str, payload: dict, agent_type: str = "triage") -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO agent_session_memory (session_id, patient_id, agent_type, data_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    patient_id=excluded.patient_id,
                    agent_type=excluded.agent_type,
                    data_json=excluded.data_json
                """,
                (session_id, patient_id, agent_type, Database.encode_json(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def append_triage_history(self, patient_id: str, session_id: str, payload: dict, created_at: str) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO triage_history (patient_id, session_id, created_at, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (patient_id, session_id, created_at, Database.encode_json(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def append_icu_consultation_history(self, patient_id: str, session_id: str, payload: dict, created_at: str) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO icu_consultation_history (patient_id, session_id, created_at, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (patient_id, session_id, created_at, Database.encode_json(payload)),
            )
            conn.commit()
        finally:
            conn.close()

    def append_internal_medicine_history(self, patient_id: str, session_id: str, payload: dict, created_at: str) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO internal_medicine_history (patient_id, session_id, created_at, data_json)
                VALUES (?, ?, ?, ?)
                """,
                (patient_id, session_id, created_at, Database.encode_json(payload)),
            )
            conn.commit()
        finally:
            conn.close()
