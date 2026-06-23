from __future__ import annotations

from typing import Any

import httpx


class FullviewClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class FullviewClient:
    def __init__(self, *, base_url: str, timeout_seconds: float):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._client = httpx.Client(
            timeout=self.timeout_seconds,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def send(self, request_type: str, payload: dict, idempotency_key: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/v1/departments/outpatient/requests/{request_type}"
        try:
            response = self._client.post(
                url,
                json=payload,
                headers={"Idempotency-Key": idempotency_key},
            )
        except httpx.RequestError as exc:
            raise FullviewClientError(str(exc)) from exc

        if response.status_code >= 500:
            raise FullviewClientError(
                f"Fullview returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise FullviewClientError(
                "Fullview returned a non-JSON response",
                status_code=response.status_code,
            ) from exc
        if not isinstance(body, dict):
            raise FullviewClientError(
                "Fullview returned an invalid response envelope",
                status_code=response.status_code,
            )

        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        core_response = data.get("coreResponse") if isinstance(data.get("coreResponse"), dict) else {}
        accepted = bool(data.get("accepted", core_response.get("accepted", False)))
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        reason_code = (
            error.get("code")
            or core_response.get("reasonCode")
            or ("HTTP_ERROR" if response.status_code >= 400 else None)
        )
        message = (
            error.get("message")
            or core_response.get("message")
            or (f"Fullview returned HTTP {response.status_code}" if not accepted else "Accepted")
        )
        return {
            "accepted": accepted,
            "trace_id": body.get("traceId") or body.get("trace_id"),
            "reason_code": reason_code,
            "message": message,
            "core_response": core_response,
            "raw": body,
            "http_status": response.status_code,
        }

    def delete_patient(self, patient_id: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/hospital/patients/{patient_id}"
        try:
            response = self._client.delete(
                url,
            )
        except httpx.RequestError as exc:
            raise FullviewClientError(str(exc)) from exc
        if response.status_code >= 500:
            raise FullviewClientError(
                f"Fullview returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise FullviewClientError(
                "Fullview returned a non-JSON response",
                status_code=response.status_code,
            ) from exc
        if not isinstance(body, dict):
            raise FullviewClientError(
                "Fullview returned an invalid response envelope",
                status_code=response.status_code,
            )
        return body

    def fetch_events(self, after_seq: int, *, limit: int = 200) -> list[dict[str, Any]]:
        url = f"{self.base_url}/api/v1/events"
        try:
            response = self._client.get(
                url,
                params={
                    "after_seq": max(0, int(after_seq)),
                    "limit": max(1, min(int(limit), 200)),
                },
            )
        except httpx.RequestError as exc:
            raise FullviewClientError(str(exc)) from exc
        if response.status_code >= 400:
            raise FullviewClientError(
                f"Fullview events returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise FullviewClientError("Fullview events returned non-JSON") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict):
            events = data.get("events", [])
        elif isinstance(body, list):
            events = body
        else:
            events = []
        if not isinstance(events, list):
            raise FullviewClientError("Fullview events returned an invalid event list")
        return [event for event in events if isinstance(event, dict)]

    def fetch_snapshot(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/hospital/snapshot"
        try:
            response = self._client.get(url)
        except httpx.RequestError as exc:
            raise FullviewClientError(str(exc)) from exc
        if response.status_code >= 400:
            raise FullviewClientError(
                f"Fullview snapshot returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise FullviewClientError("Fullview snapshot returned non-JSON") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict):
            return data
        if isinstance(body, dict):
            return body
        raise FullviewClientError("Fullview snapshot returned an invalid envelope")
