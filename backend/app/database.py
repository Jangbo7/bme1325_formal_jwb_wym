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
        conn = sqlite3.connect(self.path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
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
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
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
                        assigned_department_id TEXT,
                        assigned_department_name TEXT,
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
                        queue_kind TEXT NOT NULL,
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

                    CREATE TABLE IF NOT EXISTS idempotency_records (
                        idempotency_key TEXT NOT NULL,
                        method TEXT NOT NULL,
                        path TEXT NOT NULL,
                        request_hash TEXT NOT NULL,
                        response_status INTEGER NOT NULL,
                        response_body TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        PRIMARY KEY (idempotency_key, method, path)
                    );

                    CREATE TABLE IF NOT EXISTS medical_records (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        visit_id TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS medical_record_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_id TEXT NOT NULL,
                        patient_id TEXT NOT NULL,
                        visit_id TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        entry_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content_text TEXT NOT NULL,
                        content_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS patient_agent_cases (
                        id TEXT PRIMARY KEY,
                        patient_id TEXT NOT NULL,
                        visit_id TEXT,
                        mode TEXT NOT NULL,
                        status TEXT NOT NULL,
                        case_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS department_patient_runtime (
                        patient_id TEXT NOT NULL,
                        visit_id TEXT NOT NULL,
                        assigned_department_id TEXT NOT NULL,
                        assigned_department_name TEXT NOT NULL,
                        execution_runner_kind TEXT,
                        department_agent_enabled INTEGER NOT NULL DEFAULT 0,
                        department_capability_class TEXT,
                        assigned_doctor_slot_id TEXT,
                        assigned_doctor_slot_name TEXT,
                        queue_kind TEXT,
                        department_status TEXT NOT NULL DEFAULT 'assigned_pending_registration',
                        department_round TEXT NOT NULL DEFAULT 'none',
                        department_flow_status TEXT NOT NULL,
                        queue_ticket_id TEXT,
                        visit_state TEXT,
                        patient_lifecycle_state TEXT,
                        active_agent_type TEXT,
                        current_node TEXT,
                        current_node_id TEXT,
                        current_room_node_id TEXT,
                        current_room_name TEXT,
                        room_type TEXT,
                        target_node_id TEXT,
                        last_transition_action TEXT,
                        transition_version TEXT,
                        current_counterparty TEXT,
                        current_dialogue_preview TEXT,
                        entered_department_at TEXT,
                        updated_at TEXT NOT NULL,
                        source_of_truth_version TEXT,
                        finished_at TEXT,
                        PRIMARY KEY (patient_id, visit_id)
                    );

                    CREATE TABLE IF NOT EXISTS department_runtime_summary (
                        department_id TEXT PRIMARY KEY,
                        department_name TEXT NOT NULL,
                        active_count INTEGER NOT NULL,
                        pending_registration_count INTEGER NOT NULL,
                        waiting_round1_count INTEGER NOT NULL DEFAULT 0,
                        waiting_round2_count INTEGER NOT NULL DEFAULT 0,
                        called_round1_count INTEGER NOT NULL DEFAULT 0,
                        called_round2_count INTEGER NOT NULL DEFAULT 0,
                        in_consultation_round1_count INTEGER NOT NULL DEFAULT 0,
                        in_consultation_round2_count INTEGER NOT NULL DEFAULT 0,
                        waiting_count INTEGER NOT NULL,
                        called_count INTEGER NOT NULL,
                        in_consultation_count INTEGER NOT NULL,
                        in_test_count INTEGER NOT NULL,
                        finished_count INTEGER NOT NULL,
                        updated_at TEXT NOT NULL
                    );


                    CREATE TABLE IF NOT EXISTS runtime_console_sessions (
                        session_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        running INTEGER NOT NULL DEFAULT 0,
                        spawn_paused INTEGER NOT NULL DEFAULT 0,
                        step_paused INTEGER NOT NULL DEFAULT 0,
                        drain_mode INTEGER NOT NULL DEFAULT 0,
                        mode TEXT NOT NULL DEFAULT 'runtime_console',
                        started_at TEXT,
                        ended_at TEXT,
                        updated_at TEXT NOT NULL,
                        global_config_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS runtime_console_department_configs (
                        session_id TEXT NOT NULL,
                        department_id TEXT NOT NULL,
                        department_name TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        spawn_weight REAL NOT NULL DEFAULT 1.0,
                        allow_agent_patients INTEGER NOT NULL DEFAULT 0,
                        allow_script_patients INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (session_id, department_id)
                    );

                    CREATE TABLE IF NOT EXISTS runtime_console_events (
                        event_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        category TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        subject_type TEXT NOT NULL,
                        subject_id TEXT NOT NULL,
                        department_id TEXT,
                        patient_id TEXT,
                        npc_id TEXT,
                        payload_json TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS fullview_sync_outbox (
                        command_id TEXT PRIMARY KEY,
                        transition_key TEXT NOT NULL UNIQUE,
                        patient_id TEXT NOT NULL,
                        encounter_id TEXT NOT NULL,
                        sequence_no INTEGER NOT NULL,
                        request_type TEXT NOT NULL,
                        event_id TEXT,
                        payload_json TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        next_attempt_at TEXT NOT NULL,
                        response_json TEXT NOT NULL DEFAULT '{}',
                        event_seq INTEGER,
                        trace_id TEXT,
                        reason_code TEXT,
                        last_error TEXT,
                        accepted_at TEXT,
                        observed_at TEXT,
                        observe_status TEXT NOT NULL DEFAULT 'pending',
                        visual_cooldown_seconds REAL NOT NULL DEFAULT 0,
                        visual_ready_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(encounter_id, sequence_no)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fullview_sync_ready
                    ON fullview_sync_outbox(status, next_attempt_at, created_at);

                    CREATE TABLE IF NOT EXISTS fullview_patient_projection (
                        patient_id TEXT NOT NULL,
                        encounter_id TEXT NOT NULL,
                        current_room_id TEXT,
                        sync_status TEXT NOT NULL,
                        last_command_id TEXT,
                        last_event_id TEXT,
                        last_event_seq INTEGER,
                        last_error TEXT,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (patient_id, encounter_id)
                    );

                    CREATE TABLE IF NOT EXISTS fullview_listener_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        last_event_seq INTEGER NOT NULL DEFAULT 0,
                        last_event_at TEXT,
                        last_movement_observed_at TEXT,
                        cleanup_barrier_until TEXT,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS fullview_observed_events (
                        event_seq INTEGER PRIMARY KEY,
                        patient_id TEXT,
                        event_type TEXT,
                        event_id TEXT,
                        payload_json TEXT NOT NULL,
                        occurred_at TEXT,
                        observed_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS fullview_cleanup_queue (
                        patient_id TEXT PRIMARY KEY,
                        encounter_id TEXT,
                        command_id TEXT,
                        status TEXT NOT NULL DEFAULT 'cleanup_pending',
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        next_attempt_at TEXT NOT NULL,
                        last_error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_fullview_cleanup_ready
                    ON fullview_cleanup_queue(status, next_attempt_at, created_at);

                    """
                )
                self._ensure_column(conn, "patients", "visit_id", "TEXT")
                self._ensure_column(conn, "patients", "openemr_patient_id", "TEXT")
                self._ensure_column(conn, "triage_sessions", "visit_id", "TEXT")
                self._ensure_column(conn, "queue_tickets", "visit_id", "TEXT")
                self._ensure_column(conn, "queue_tickets", "queue_kind", "TEXT NOT NULL DEFAULT 'initial_consultation'")
                self._ensure_column(conn, "visits", "assigned_department_id", "TEXT")
                self._ensure_column(conn, "visits", "assigned_department_name", "TEXT")
                self._ensure_column(
                    conn,
                    "department_patient_runtime",
                    "department_status",
                    "TEXT NOT NULL DEFAULT 'assigned_pending_registration'",
                )
                self._ensure_column(conn, "department_patient_runtime", "department_round", "TEXT NOT NULL DEFAULT 'none'")
                self._ensure_column(conn, "department_patient_runtime", "entered_department_at", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "source_of_truth_version", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "execution_runner_kind", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "department_agent_enabled", "INTEGER NOT NULL DEFAULT 0")
                self._ensure_column(conn, "department_patient_runtime", "department_capability_class", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "assigned_doctor_slot_id", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "assigned_doctor_slot_name", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "current_node_id", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "current_room_node_id", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "current_room_name", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "room_type", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "target_node_id", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "last_transition_action", "TEXT")
                self._ensure_column(conn, "department_patient_runtime", "transition_version", "TEXT")
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "waiting_round1_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "waiting_round2_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "called_round1_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "called_round2_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "in_consultation_round1_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(
                    conn,
                    "department_runtime_summary",
                    "in_consultation_round2_count",
                    "INTEGER NOT NULL DEFAULT 0",
                )
                self._ensure_column(conn, "visits", "openemr_encounter_id", "TEXT")
                self._ensure_column(conn, "visits", "emr_sync_status", "TEXT")
                self._ensure_column(conn, "visits", "emr_synced_at", "TEXT")
                self._ensure_column(conn, "visits", "emr_sync_error", "TEXT")
                self._ensure_column(conn, "fullview_sync_outbox", "visual_ready_at", "TEXT")
                self._ensure_column(conn, "fullview_sync_outbox", "accepted_at", "TEXT")
                self._ensure_column(conn, "fullview_sync_outbox", "observed_at", "TEXT")
                self._ensure_column(conn, "fullview_sync_outbox", "observe_status", "TEXT NOT NULL DEFAULT 'pending'")
                self._ensure_column(conn, "fullview_sync_outbox", "visual_cooldown_seconds", "REAL NOT NULL DEFAULT 0")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO fullview_listener_state (
                        id, last_event_seq, updated_at
                    ) VALUES (1, 0, datetime('now'))
                    """
                )
                conn.execute(
                    """
                    UPDATE fullview_sync_outbox
                    SET status='observed',
                        accepted_at=COALESCE(accepted_at, updated_at),
                        observed_at=COALESCE(observed_at, updated_at),
                        observe_status='observed',
                        visual_ready_at=COALESCE(visual_ready_at, updated_at)
                    WHERE status='accepted'
                    """
                )
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
            "idempotency_records",
            "medical_record_entries",
            "medical_records",
            "patient_agent_cases",
            "department_patient_runtime",
            "department_runtime_summary",

            "runtime_console_sessions",
            "runtime_console_department_configs",
            "runtime_console_events",
            "fullview_sync_outbox",
            "fullview_patient_projection",
            "fullview_cleanup_queue",

        ]

        with self.lock:
            conn = self.connect()
            try:
                for table_name in runtime_tables:
                    conn.execute(f"DELETE FROM {table_name}")
                conn.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN (?, ?, ?)",
                    ("session_turns", "triage_history", "medical_record_entries"),
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
