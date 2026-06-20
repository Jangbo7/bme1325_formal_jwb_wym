from __future__ import annotations

from datetime import datetime, timezone

from app.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStageSampleRepository:
    def __init__(self, db):
        self.db = db

    def append_sample(
        self,
        *,
        window_label: str,
        phase_counts: dict,
        room_counts: dict,
        active_total: int,
        historical_total: int,
        sampled_at: str | None = None,
    ) -> None:
        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO runtime_stage_samples (
                    sampled_at, window_label, phase_counts_json, room_counts_json, active_total, historical_total
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    sampled_at or now_iso(),
                    window_label,
                    Database.encode_json(phase_counts),
                    Database.encode_json(room_counts),
                    int(active_total),
                    int(historical_total),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_recent_samples(self, *, limit: int = 240) -> list[dict]:
        conn = self.db.connect()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM runtime_stage_samples
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
            samples = []
            for row in reversed(rows):
                samples.append(
                    {
                        "id": row["id"],
                        "sampled_at": row["sampled_at"],
                        "window_label": row["window_label"],
                        "phase_counts": Database.decode_json(row["phase_counts_json"], {}),
                        "room_counts": Database.decode_json(row["room_counts_json"], {}),
                        "active_total": row["active_total"],
                        "historical_total": row["historical_total"],
                    }
                )
            return samples
        finally:
            conn.close()

    def get_latest_sample(self) -> dict | None:
        conn = self.db.connect()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM runtime_stage_samples
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "sampled_at": row["sampled_at"],
                "window_label": row["window_label"],
                "phase_counts": Database.decode_json(row["phase_counts_json"], {}),
                "room_counts": Database.decode_json(row["room_counts_json"], {}),
                "active_total": row["active_total"],
                "historical_total": row["historical_total"],
            }
        finally:
            conn.close()
