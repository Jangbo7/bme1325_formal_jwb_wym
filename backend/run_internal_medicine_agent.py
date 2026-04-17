"""Small helper script for manual internal medicine API testing.

Usage:
    python backend/run_internal_medicine_agent.py <visit_id>

It expects the main backend server to already be running.
"""

import json
import sys
from urllib import request as urlrequest


BASE_URL = "http://127.0.0.1:8787"
API_KEY = "mock-key-001"


def post(path: str, payload: dict) -> dict:
    req = urlrequest.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python backend/run_internal_medicine_agent.py <visit_id>")
        return 1
    visit_id = sys.argv[1]
    session = post(
        "/api/v1/internal-medicine-sessions",
        {"patient_id": "P-self", "name": "You (Player)", "visit_id": visit_id},
    )
    print(json.dumps(session, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
