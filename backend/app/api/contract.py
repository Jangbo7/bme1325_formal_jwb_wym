from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.domain.identifiers import is_valid_encounter_id, is_valid_patient_id


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
IDEMPOTENCY_TTL_HOURS = 24

ERROR_MESSAGES: dict[str, str] = {
    "ID_MALFORMED": "identifier format is invalid",
    "STATE_TRANSITION_INVALID": "state transition is invalid",
    "ENCOUNTER_NOT_FOUND": "encounter not found",
    "PATIENT_NOT_FOUND": "patient not found",
    "SESSION_NOT_FOUND": "session not found",
    "LLM_UNAVAILABLE": "llm configuration unavailable",
    "LLM_REQUEST_FAILED": "llm request failed",
    "LLM_RESPONSE_INVALID": "llm response is invalid",
    "IDEMPOTENCY_KEY_REQUIRED": "Idempotency-Key header is required",
    "IDEMPOTENCY_KEY_REUSED": "Idempotency-Key is reused with different payload",
    "INTERNAL_ERROR": "internal server error",
}

ERROR_STATUS: dict[str, int] = {
    "ID_MALFORMED": 400,
    "STATE_TRANSITION_INVALID": 422,
    "ENCOUNTER_NOT_FOUND": 404,
    "PATIENT_NOT_FOUND": 404,
    "SESSION_NOT_FOUND": 404,
    "LLM_UNAVAILABLE": 503,
    "LLM_REQUEST_FAILED": 502,
    "LLM_RESPONSE_INVALID": 502,
    "IDEMPOTENCY_KEY_REQUIRED": 400,
    "IDEMPOTENCY_KEY_REUSED": 409,
    "INTERNAL_ERROR": 500,
}


@dataclass
class ContractError(Exception):
    code: str
    message: str | None = None
    details: Any = None
    status_code: int | None = None


def new_trace_id() -> str:
    return f"trc_{uuid.uuid4().hex[:20]}"


def success_envelope(data: Any, trace_id: str) -> dict:
    return {"ok": True, "data": data, "error": None, "trace_id": trace_id}


def error_envelope(*, code: str, trace_id: str, message: str | None = None, details: Any = None) -> dict:
    return {
        "ok": False,
        "data": None,
        "error": {
            "code": code,
            "message": message or ERROR_MESSAGES.get(code, code),
            "details": details,
        },
        "trace_id": trace_id,
    }


def normalize_success_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        if {"ok", "data", "error", "trace_id"}.issubset(payload.keys()):
            return payload.get("data")
        if "ok" in payload and "data" in payload and len(payload) <= 3:
            return payload.get("data")
        if "ok" in payload:
            data = dict(payload)
            data.pop("ok", None)
            return data
    return payload


def _map_detail_to_code(detail: Any, fallback_status: int) -> tuple[str, str, Any, int]:
    if isinstance(detail, dict) and "code" in detail:
        code = str(detail.get("code"))
        message = str(detail.get("message") or ERROR_MESSAGES.get(code, code))
        details = detail.get("details")
        status_code = ERROR_STATUS.get(code, fallback_status)
        return code, message, details, status_code

    text = str(detail or "").strip()
    lowered = text.lower()
    if "state_transition_invalid" in lowered:
        return "STATE_TRANSITION_INVALID", ERROR_MESSAGES["STATE_TRANSITION_INVALID"], text, 422
    if "id_malformed" in lowered:
        return "ID_MALFORMED", ERROR_MESSAGES["ID_MALFORMED"], text, 400
    if "encounter_not_found" in lowered or lowered == "visit not found":
        return "ENCOUNTER_NOT_FOUND", ERROR_MESSAGES["ENCOUNTER_NOT_FOUND"], text, 404
    if lowered == "patient not found":
        return "PATIENT_NOT_FOUND", ERROR_MESSAGES["PATIENT_NOT_FOUND"], text, 404
    if lowered in {"session not found", "triage session not found"}:
        return "SESSION_NOT_FOUND", ERROR_MESSAGES["SESSION_NOT_FOUND"], text, 404
    if lowered == "state_debug_disabled":
        return "STATE_DEBUG_DISABLED", "state debug endpoints are disabled", text, 404
    code = f"HTTP_{fallback_status}"
    return code, text or "request failed", None, fallback_status


def map_exception(exc: Exception) -> tuple[str, str, Any, int]:
    if isinstance(exc, ContractError):
        code = exc.code
        message = exc.message or ERROR_MESSAGES.get(code, code)
        status_code = exc.status_code or ERROR_STATUS.get(code, 400)
        return code, message, exc.details, status_code

    if isinstance(exc, HTTPException):
        return _map_detail_to_code(exc.detail, exc.status_code)

    return "INTERNAL_ERROR", ERROR_MESSAGES["INTERNAL_ERROR"], None, 500


def require_patient_id(patient_id: str | None, *, field: str = "patient_id") -> None:
    if not is_valid_patient_id(patient_id):
        raise ContractError(
            code="ID_MALFORMED",
            details={field: "must match ^P-[0-9a-f]{8}$"},
            status_code=400,
        )


def require_encounter_id(encounter_id: str | None, *, field: str = "encounter_id") -> None:
    if not is_valid_encounter_id(encounter_id):
        raise ContractError(
            code="ID_MALFORMED",
            details={field: "must match ^E-[0-9]{14}-[0-9a-f]{4}$"},
            status_code=400,
        )


def should_require_idempotency(method: str, path: str) -> bool:
    return method.upper() in WRITE_METHODS and path.startswith("/api/v1/")


def request_fingerprint(*, method: str, path: str, query: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\n")
    digest.update(path.encode("utf-8"))
    digest.update(b"\n")
    digest.update(query.encode("utf-8"))
    digest.update(b"\n")
    digest.update(body)
    return digest.hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.isoformat()


def fetch_idempotency_record(db, *, key: str, method: str, path: str) -> dict | None:
    now_iso = _to_iso(_now_utc())
    with db.lock:
        conn = db.connect()
        try:
            conn.execute(
                "DELETE FROM idempotency_records WHERE expires_at <= ?",
                (now_iso,),
            )
            row = conn.execute(
                """
                SELECT * FROM idempotency_records
                WHERE idempotency_key = ? AND method = ? AND path = ? AND expires_at > ?
                """,
                (key, method.upper(), path, now_iso),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None
        finally:
            conn.close()


def upsert_idempotency_record(
    db,
    *,
    key: str,
    method: str,
    path: str,
    request_hash: str,
    response_status: int,
    response_body: dict,
) -> None:
    created_at = _now_utc()
    expires_at = created_at + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
    with db.lock:
        conn = db.connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO idempotency_records
                (idempotency_key, method, path, request_hash, response_status, response_body, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    method.upper(),
                    path,
                    request_hash,
                    int(response_status),
                    json.dumps(response_body, ensure_ascii=False),
                    _to_iso(created_at),
                    _to_iso(expires_at),
                ),
            )
            conn.commit()
        finally:
            conn.close()
