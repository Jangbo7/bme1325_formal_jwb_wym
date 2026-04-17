import json
import sqlite3
import threading
from pathlib import Path


class Database:
    def __init__(self, database_url: str):
        if not database_url.startswith("sqlite:///"):
            raise ValueError("Phase 1 database backend supports sqlite:/// URLs only.")
        relative_path = database_url.replace("sqlite:///", "", 1)
        self.path = Path(relative_path)
        if not self.path.is_absolute():
            root = Path(__file__).resolve().parent.parent
            self.path = root / relative_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.lock:
            conn = self.connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS patients (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        lifecycle_state TEXT NOT NULL,
                        display_state TEXT NOT NULL,
                        priority TEXT NOT NULL,
                        location TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        triage_level INTEGER,
                        triage_note TEXT,
                        session_id TEXT,
                        visit_id TEXT
                    );

                    CREATE TABLE IF NOT EXISTS triage_sessions (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        agent_type TEXT NOT NULL,
                        dialogue_state TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS session_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        patient_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS patient_shared_memory (
                        patient_id TEXT PRIMARY KEY,
                        data_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS agent_session_memory (
                        session_id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        agent_type TEXT NOT NULL,
                        data_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS queue_tickets (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        department_id TEXT NOT NULL,
                        department_name TEXT NOT NULL,
                        number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS triage_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        data_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS icu_consultation_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        data_json TEXT NOT NULL
                    );
                    """
                )
                # Backward-compatible lightweight migration for old local DB files.
                self._ensure_column(conn, "patients", "visit_id", "TEXT")
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
        columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {row[1] for row in columns}
        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    @staticmethod
    def encode_json(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def decode_json(payload: str | None, default):
        if not payload:
            return default
        return json.loads(payload)
