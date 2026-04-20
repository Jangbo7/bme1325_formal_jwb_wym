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

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row["name"] == column_name for row in rows)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
        if not Database._column_exists(conn, table_name, column_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return bool(row)

    @staticmethod
    def _agent_session_memory_has_composite_pk(conn: sqlite3.Connection) -> bool:
        if not Database._table_exists(conn, "agent_session_memory"):
            return False
        rows = conn.execute("PRAGMA table_info(agent_session_memory)").fetchall()
        pk_rows = sorted((row for row in rows if row["pk"] > 0), key=lambda row: row["pk"])
        pk_columns = [row["name"] for row in pk_rows]
        return pk_columns == ["session_id", "agent_type"]

    @staticmethod
    def _migrate_agent_session_memory_to_composite_pk(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_session_memory_v2 (
                session_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                data_json TEXT NOT NULL,
                PRIMARY KEY (session_id, agent_type)
            );

            DELETE FROM agent_session_memory_v2;

            INSERT INTO agent_session_memory_v2 (session_id, patient_id, agent_type, data_json)
            SELECT session_id, patient_id, COALESCE(agent_type, 'triage'), data_json
            FROM agent_session_memory;

            DROP TABLE agent_session_memory;
            ALTER TABLE agent_session_memory_v2 RENAME TO agent_session_memory;
            """
        )

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

                    CREATE TABLE IF NOT EXISTS visits (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        state TEXT NOT NULL,
                        current_node TEXT,
                        current_department TEXT,
                        active_agent_type TEXT,
                        data_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS triage_sessions (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        visit_id TEXT,
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
                        session_id TEXT NOT NULL,
                        patient_id TEXT NOT NULL,
                        agent_type TEXT NOT NULL,
                        data_json TEXT NOT NULL,
                        PRIMARY KEY (session_id, agent_type)
                    );

                    CREATE TABLE IF NOT EXISTS queue_tickets (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        visit_id TEXT,
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
                    """
                )
                self._ensure_column(conn, "patients", "visit_id", "TEXT")
                self._ensure_column(conn, "triage_sessions", "visit_id", "TEXT")
                self._ensure_column(conn, "queue_tickets", "visit_id", "TEXT")
                if not self._agent_session_memory_has_composite_pk(conn):
                    self._migrate_agent_session_memory_to_composite_pk(conn)
                conn.commit()
            finally:
                conn.close()

    def reset_runtime_data(self) -> None:
        runtime_tables = [
            "visits",
            "triage_sessions",
            "session_turns",
            "patient_shared_memory",
            "agent_session_memory",
            "queue_tickets",
            "triage_history",
            "patients",
        ]

        with self.lock:
            conn = self.connect()
            try:
                for table_name in runtime_tables:
                    conn.execute(f"DELETE FROM {table_name}")
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (?, ?)",
                    ("session_turns", "triage_history"),
                )
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def encode_json(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def decode_json(payload: str | None, default):
        if not payload:
            return default
        return json.loads(payload)

