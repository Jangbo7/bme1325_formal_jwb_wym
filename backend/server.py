import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services.llm_client import get_llm_settings
from services.private_api_config import get_backend_private_config
from services.triage_service import continue_triage_chat, run_triage


private_config = get_backend_private_config()
HOST = private_config["host"]
PORT = private_config["port"]
MOCK_API_KEY = private_config["mock_api_key"]
MOCK_KEY_SOURCE = private_config["mock_key_source"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class InMemoryStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = deque()
        self.patients = {
            "P-self": {
                "id": "P-self",
                "name": "You (Player)",
                "state": "Untriaged",
                "priority": "-",
                "location": "Lobby",
                "updatedAt": now_iso(),
            },
            "P-102": {
                "id": "P-102",
                "name": "Wang Ayi",
                "state": "Waiting Consultation",
                "priority": "M",
                "location": "Consultation",
                "updatedAt": now_iso(),
            },
            "P-203": {
                "id": "P-203",
                "name": "Li Xiansheng",
                "state": "In Consultation",
                "priority": "H",
                "location": "Consultation",
                "updatedAt": now_iso(),
            },
        }


STORE = InMemoryStore()

def nurse_agent_loop():
    while True:
        task = None
        with STORE.lock:
            if STORE.queue:
                task = STORE.queue.popleft()

        if not task:
            time.sleep(0.25)
            continue

        time.sleep(1.2)
        payload = task["payload"]

        triage_output = run_triage(payload)
        result = triage_output["triage"]

        patient_id = payload["patient_id"]
        with STORE.lock:
            patient = STORE.patients.setdefault(patient_id, {"id": patient_id, "name": payload.get("name", patient_id)})
            patient["name"] = payload.get("name", patient.get("name", patient_id))
            patient["state"] = "等待问诊"
            patient["priority"] = result.get("priority", "M")
            patient["location"] = result.get("department", "General Medicine")
            patient["triage"] = {
                "level": result.get("triage_level", 3),
                "note": result.get("note", ""),
            }
            patient["triageEvidence"] = triage_output.get("evidence", [])
            patient["memory"] = triage_output.get("memory", {})
            patient["dialogue"] = triage_output.get("dialogue", {})
            patient["updatedAt"] = now_iso()


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        provided_key = (self.headers.get("X-API-Key") or "").strip()
        if not provided_key:
            auth = (self.headers.get("Authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                provided_key = auth[7:].strip()
        return provided_key == MOCK_API_KEY

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        llm_settings = get_llm_settings()
        if self.path == "/health":
            return self._send(200, {"ok": True, "time": now_iso(), "mode": "rag+llm" if llm_settings["api_key"] else "rag+rules", "key_source": MOCK_KEY_SOURCE, "llm_model": llm_settings["model"], "llm_enabled": bool(llm_settings["api_key"])})
        if self.path == "/api/statuses":
            if not self._authorized():
                return self._send(401, {"error": "unauthorized", "message": "invalid or missing api key"})
            with STORE.lock:
                patients = sorted(STORE.patients.values(), key=lambda p: p.get("updatedAt", ""), reverse=True)
            return self._send(200, {"patients": patients})
        return self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path not in ("/api/triage/request", "/api/triage/chat"):
            return self._send(404, {"error": "not_found"})

        if not self._authorized():
            return self._send(401, {"error": "unauthorized", "message": "invalid or missing api key"})

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(raw)

        if self.path == "/api/triage/chat":
            patient_id = payload.get("patient_id")
            if not patient_id:
                return self._send(400, {"error": "bad_request", "message": "patient_id is required"})
            payload["session_id"] = payload.get("session_id") or "default"
            triage_output = continue_triage_chat(payload)
            result = triage_output["triage"]
            with STORE.lock:
                patient = STORE.patients.setdefault(patient_id, {"id": patient_id})
                patient["name"] = payload.get("name", patient.get("name", patient_id))
                patient["state"] = "等待问诊" if triage_output.get("dialogue", {}).get("status") == "needs_more_info" else "分诊完成"
                patient["priority"] = result.get("priority", "M")
                patient["location"] = result.get("department", "General Medicine")
                patient["triage"] = {
                    "level": result.get("triage_level", 3),
                    "note": result.get("note", ""),
                }
                patient["triageEvidence"] = triage_output.get("evidence", [])
                patient["memory"] = triage_output.get("memory", {})
                patient["dialogue"] = triage_output.get("dialogue", {})
                patient["updatedAt"] = now_iso()
            return self._send(200, {"ok": True, "patient_id": patient_id, "dialogue": triage_output.get("dialogue", {}), "patient": patient})

        patient_id = payload.get("patient_id") or f"P-{uuid.uuid4().hex[:8]}"
        payload["patient_id"] = patient_id

        with STORE.lock:
            patient = STORE.patients.setdefault(patient_id, {"id": patient_id})
            patient["name"] = payload.get("name", patient.get("name", patient_id))
            patient["state"] = "正在分诊"
            patient["priority"] = "M"
            patient["location"] = "Triage Desk"
            patient["session_id"] = payload.get("session_id") or patient.get("session_id", "default")
            patient["updatedAt"] = now_iso()
            STORE.queue.append({"payload": payload, "enqueuedAt": now_iso()})

        return self._send(200, {"ok": True, "patient_id": patient_id, "session_id": payload.get("session_id") or "default"})

    def log_message(self, fmt, *args):
        return


def main():
    agent_thread = threading.Thread(target=nurse_agent_loop, daemon=True)
    agent_thread.start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[backend] running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
