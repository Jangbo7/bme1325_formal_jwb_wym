import threading
from collections import deque


MAX_TURNS = 8


class InMemorySessionStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def get_or_create_session(self, patient_id, session_id="default"):
        key = (patient_id, session_id)
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                session = {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "turns": deque(maxlen=MAX_TURNS),
                    "latest_summary": {},
                }
                self.sessions[key] = session
            return {
                "patient_id": session["patient_id"],
                "session_id": session["session_id"],
                "turns": list(session["turns"]),
                "latest_summary": dict(session["latest_summary"]),
            }

    def append_turn(self, patient_id, role, content, timestamp, session_id="default", metadata=None):
        key = (patient_id, session_id)
        with self.lock:
            session = self.sessions.setdefault(
                key,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "turns": deque(maxlen=MAX_TURNS),
                    "latest_summary": {},
                },
            )
            session["turns"].append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                    "metadata": metadata or {},
                }
            )

    def update_summary(self, patient_id, summary, session_id="default"):
        key = (patient_id, session_id)
        with self.lock:
            session = self.sessions.setdefault(
                key,
                {
                    "patient_id": patient_id,
                    "session_id": session_id,
                    "turns": deque(maxlen=MAX_TURNS),
                    "latest_summary": {},
                },
            )
            session["latest_summary"] = dict(summary)

    def get_summary(self, patient_id, session_id="default"):
        key = (patient_id, session_id)
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                return {}
            return dict(session.get("latest_summary") or {})


SESSION_STORE = InMemorySessionStore()
