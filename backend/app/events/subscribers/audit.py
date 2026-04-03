from datetime import datetime, timezone
from pathlib import Path


class AuditSubscriber:
    def __init__(self, root_dir: Path):
        self.path = root_dir / "backend" / "data" / "audit.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_name: str, payload: dict) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {event_name} {payload}\n")
