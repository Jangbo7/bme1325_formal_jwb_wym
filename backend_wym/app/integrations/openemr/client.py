from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import json
from pathlib import Path
from typing import Any

import httpx

from app.integrations.openemr.errors import OpenEMRAuthError, OpenEMRConfigError, OpenEMRRequestError, OpenEMRResponseError
from app.integrations.openemr.schemas import (
    OpenEMREncounterPayload,
    OpenEMRNotePayload,
    OpenEMRPatientPayload,
    OpenEMRSyncResult,
    OpenEMRTestReportPayload,
)


DEFAULT_SCOPE = "api:fhir user/Patient.write user/DocumentReference.write"
DEFAULT_REFRESH_SKEW_SECONDS = 30


@dataclass
class _TokenCache:
    access_token: str
    expires_at: datetime


class OpenEMRClient:
    def __init__(
        self,
        *,
        enabled: bool,
        dry_run: bool,
        base_url: str,
        api_base_path: str = "/apis/default/fhir",
        timeout_seconds: int = 10,
        verify_ssl: bool = False,
        client_id: str | None = None,
        client_secret: str | None = None,
        oauth_enabled: bool = True,
        oauth_discovery_url: str | None = None,
        oauth_token_url: str | None = None,
        oauth_scope: str | None = None,
        oauth_audience: str | None = None,
        oauth_use_basic_fallback: bool = True,
        username: str | None = None,
        password: str | None = None,
        outbound_log_path: str | None = None,
    ):
        self.enabled = enabled
        self.dry_run = dry_run
        self.base_url = (base_url or "").rstrip("/")
        self.api_base_path = (api_base_path or "/apis/default/fhir").strip()
        if not self.api_base_path.startswith("/"):
            self.api_base_path = f"/{self.api_base_path}"
        self.timeout_seconds = timeout_seconds
        self.verify_ssl = verify_ssl
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_enabled = oauth_enabled
        self.oauth_discovery_url = oauth_discovery_url
        self.oauth_token_url_override = oauth_token_url
        self.oauth_scope = oauth_scope or DEFAULT_SCOPE
        self.oauth_audience = oauth_audience
        self.oauth_use_basic_fallback = oauth_use_basic_fallback
        self.username = username
        self.password = password
        self.outbound_log_path = outbound_log_path

        self._token_cache: _TokenCache | None = None
        self._discovered_token_url: str | None = None
        self._token_endpoint_source = "unknown"
        self._auth_mode = "oauth"

        if self.enabled and not self.base_url:
            raise OpenEMRConfigError("OPENEMR_BASE_URL is required when OPENEMR_ENABLED=true")

    def health_check(self) -> dict:
        if not self.enabled:
            return {
                "ok": True,
                "mode": "disabled",
                "auth_mode": "disabled",
                "base_url": self.base_url,
                "api_base_path": self.api_base_path,
                "token_endpoint_source": "n/a",
                "token_endpoint": None,
            }
        if self.dry_run:
            return {
                "ok": True,
                "mode": "dry_run",
                "auth_mode": "dry_run",
                "base_url": self.base_url,
                "api_base_path": self.api_base_path,
                "token_endpoint_source": "n/a",
                "token_endpoint": None,
            }

        response = self._request(
            "GET",
            f"{self.api_base_path}/metadata",
            params={"_format": "json"},
        )
        return {
            "ok": response.status_code < 400,
            "mode": "live",
            "auth_mode": self._auth_mode,
            "token_endpoint_source": self._token_endpoint_source,
            "token_endpoint": self._resolved_token_endpoint_or_none(),
            "status_code": response.status_code,
            "base_url": self.base_url,
            "api_base_path": self.api_base_path,
        }

    def create_or_update_patient(self, payload: OpenEMRPatientPayload) -> OpenEMRSyncResult:
        if not self.enabled:
            return self._noop("Patient", "create_or_update")
        if self.dry_run:
            return self._dry_run("Patient", "create_or_update", f"dryrun-patient-{payload.local_patient_id}")

        bundle = {
            "resource": self._build_patient_resource(payload),
        }
        response = self._request("POST", f"{self.api_base_path}/Patient", json=bundle["resource"])
        body = self._parse_json(response)
        patient_id = (body.get("id") if isinstance(body, dict) else None) or payload.external_patient_id
        if not patient_id:
            raise OpenEMRResponseError("OpenEMR did not return patient id")
        return OpenEMRSyncResult(
            ok=True,
            external_id=patient_id,
            resource_type="Patient",
            operation="create_or_update",
            raw_response=body,
        )

    def create_encounter(self, payload: OpenEMREncounterPayload) -> OpenEMRSyncResult:
        if not self.enabled:
            return self._noop("Encounter", "create")
        if self.dry_run:
            return self._dry_run("Encounter", "create", f"dryrun-encounter-{payload.local_visit_id}")

        resource = {
            "resourceType": "Encounter",
            "status": payload.status,
            "class": {
                "code": payload.class_code,
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            },
            "subject": {"reference": f"Patient/{payload.external_patient_id}"},
            "identifier": [
                {
                    "system": payload.identifier_system,
                    "value": payload.local_visit_id,
                }
            ],
            "serviceType": {"text": payload.department or "General Medicine"},
        }
        if payload.started_at:
            resource["period"] = {"start": payload.started_at}

        response = self._request("POST", f"{self.api_base_path}/Encounter", json=resource)
        body = self._parse_json(response)
        encounter_id = (body.get("id") if isinstance(body, dict) else None) or payload.external_encounter_id
        if not encounter_id:
            raise OpenEMRResponseError("OpenEMR did not return encounter id")
        return OpenEMRSyncResult(
            ok=True,
            external_id=encounter_id,
            resource_type="Encounter",
            operation="create",
            raw_response=body,
        )

    def add_encounter_note(self, payload: OpenEMRNotePayload) -> OpenEMRSyncResult:
        if not self.enabled:
            return self._noop("DocumentReference", "add_note")
        if self.dry_run:
            return self._dry_run(
                "DocumentReference",
                "add_note",
                f"dryrun-note-{payload.note_type}-{payload.local_visit_id}",
            )

        document = {
            "resourceType": "DocumentReference",
            "status": "current",
            "type": {"text": payload.title},
            "subject": {"reference": f"Patient/{payload.external_patient_id}"},
            "context": {"encounter": [{"reference": f"Encounter/{payload.external_encounter_id}"}]},
            "date": payload.created_at or datetime.now(timezone.utc).isoformat(),
            "description": payload.note_type,
            "content": [
                {
                    "attachment": {
                        "contentType": "text/plain",
                        "data": base64.b64encode(payload.content.encode("utf-8")).decode("ascii"),
                        "title": payload.title,
                    }
                }
            ],
        }
        response = self._request("POST", f"{self.api_base_path}/DocumentReference", json=document)
        body = self._parse_json(response)
        doc_id = body.get("id") if isinstance(body, dict) else None
        if not doc_id:
            raise OpenEMRResponseError("OpenEMR did not return note document id")
        return OpenEMRSyncResult(
            ok=True,
            external_id=doc_id,
            resource_type="DocumentReference",
            operation="add_note",
            raw_response=body,
        )

    def add_test_report(self, payload: OpenEMRTestReportPayload) -> OpenEMRSyncResult:
        if not self.enabled:
            return self._noop("DocumentReference", "add_test_report")
        if self.dry_run:
            return self._dry_run(
                "DocumentReference",
                "add_test_report",
                f"dryrun-report-{payload.local_visit_id}",
            )

        category = payload.category or "diagnostic"
        report_body = payload.report_content
        if payload.report_data:
            report_body = f"{payload.report_content}\n\nRaw Data:\n{payload.report_data}"

        document = {
            "resourceType": "DocumentReference",
            "status": "current",
            "type": {"text": payload.report_title},
            "subject": {"reference": f"Patient/{payload.external_patient_id}"},
            "context": {"encounter": [{"reference": f"Encounter/{payload.external_encounter_id}"}]},
            "date": payload.created_at or datetime.now(timezone.utc).isoformat(),
            "description": category,
            "content": [
                {
                    "attachment": {
                        "contentType": "text/plain",
                        "data": base64.b64encode(report_body.encode("utf-8")).decode("ascii"),
                        "title": payload.report_title,
                    }
                }
            ],
        }
        response = self._request("POST", f"{self.api_base_path}/DocumentReference", json=document)
        body = self._parse_json(response)
        doc_id = body.get("id") if isinstance(body, dict) else None
        if not doc_id:
            raise OpenEMRResponseError("OpenEMR did not return test report id")
        return OpenEMRSyncResult(
            ok=True,
            external_id=doc_id,
            resource_type="DocumentReference",
            operation="add_test_report",
            raw_response=body,
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = path if path.startswith("http://") or path.startswith("https://") else f"{self.base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        auth_errors: list[str] = []

        if self.oauth_enabled:
            try:
                headers["Authorization"] = f"Bearer {self._get_access_token()}"
                self._auth_mode = "oauth"
                response = self._http_request(method, url, headers=headers, **kwargs)
                if response.status_code in (401, 403):
                    raise OpenEMRAuthError(f"oauth access rejected: HTTP {response.status_code}")
                self._raise_for_http_error(response)
                return response
            except (OpenEMRAuthError, OpenEMRConfigError, OpenEMRRequestError) as exc:
                auth_errors.append(str(exc))
                if self.oauth_use_basic_fallback and self._has_basic_credentials():
                    self._auth_mode = "basic_fallback"
                    headers.pop("Authorization", None)
                    response = self._http_request(method, url, headers=headers, auth=(self.username, self.password), **kwargs)
                    self._raise_for_http_error(response)
                    return response
                raise

        if self._has_basic_credentials():
            self._auth_mode = "basic_fallback" if self.oauth_enabled else "basic"
            response = self._http_request(method, url, headers=headers, auth=(self.username, self.password), **kwargs)
            self._raise_for_http_error(response)
            return response

        if self.oauth_enabled:
            error_detail = "; ".join(auth_errors) if auth_errors else "oauth authentication failed"
            raise OpenEMRAuthError(error_detail)
        raise OpenEMRConfigError("missing OpenEMR credentials: OAuth disabled and basic auth not configured")

    def _http_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self._persist_outbound_request(method=method, url=url, kwargs=kwargs)
        request_kwargs = {
            "method": method,
            "url": url,
            "timeout": self.timeout_seconds,
            "verify": self.verify_ssl,
            "trust_env": False,
            **kwargs,
        }
        try:
            return httpx.request(**request_kwargs)
        except httpx.RequestError as exc:
            raise OpenEMRRequestError(f"request to OpenEMR failed: {exc}") from exc

    def _persist_outbound_request(self, *, method: str, url: str, kwargs: dict[str, Any]) -> None:
        if not self.outbound_log_path:
            return
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "url": url,
            "headers": self._sanitize_headers(kwargs.get("headers") or {}),
            "params": self._to_loggable(kwargs.get("params")),
            "json": self._to_loggable(kwargs.get("json")),
            "data": self._sanitize_data(kwargs.get("data")),
            "has_auth_tuple": bool(kwargs.get("auth")),
            "timeout": kwargs.get("timeout", self.timeout_seconds),
        }
        entry = self._drop_none_fields(entry)
        try:
            log_path = Path(self.outbound_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False))
                fh.write("\n")
        except Exception:
            # Logging must not break main sync flow.
            return

    @staticmethod
    def _sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in headers.items():
            lowered = str(key).lower()
            if lowered == "authorization":
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = str(value)
        return sanitized

    def _sanitize_data(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return self._to_loggable(data)
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if str(key).lower() in {"client_secret", "password"}:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = self._to_loggable(value)
        return sanitized

    def _to_loggable(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._to_loggable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_loggable(v) for v in value]
        return str(value)

    @staticmethod
    def _drop_none_fields(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                normalized = OpenEMRClient._drop_none_fields(item)
                if normalized is not None:
                    cleaned[key] = normalized
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                normalized = OpenEMRClient._drop_none_fields(item)
                if normalized is not None:
                    cleaned_list.append(normalized)
            return cleaned_list
        return value

    @staticmethod
    def _build_patient_resource(payload: OpenEMRPatientPayload) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "resourceType": "Patient",
            "identifier": [
                {
                    "system": payload.identifier_system,
                    "value": payload.local_patient_id,
                }
            ],
            "name": [{"text": payload.name}],
        }
        if payload.sex:
            resource["gender"] = payload.sex
        if payload.birth_date:
            resource["birthDate"] = payload.birth_date
        return resource

    def _raise_for_http_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code in (401, 403):
            raise OpenEMRAuthError(f"OpenEMR auth rejected request: HTTP {response.status_code}")
        raise OpenEMRRequestError(f"OpenEMR request failed: HTTP {response.status_code}")

    def _get_access_token(self) -> str:
        cached = self._token_cache
        now = datetime.now(timezone.utc)
        if cached and cached.expires_at > now + timedelta(seconds=DEFAULT_REFRESH_SKEW_SECONDS):
            return cached.access_token

        token_url = self._resolve_token_endpoint()
        if not self.client_id or not self.client_secret:
            raise OpenEMRConfigError("OPENEMR_CLIENT_ID and OPENEMR_CLIENT_SECRET are required for OAuth")

        data = {
            "grant_type": "client_credentials",
            "scope": self.oauth_scope,
        }
        if self.oauth_audience:
            data["audience"] = self.oauth_audience

        response = self._http_request(
            "POST",
            token_url,
            data=data,
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )

        if response.status_code >= 400:
            if response.status_code in (401, 403):
                raise OpenEMRAuthError(f"oauth token rejected: HTTP {response.status_code}")
            raise OpenEMRAuthError(f"oauth token request failed: HTTP {response.status_code}")

        payload = self._parse_json(response)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        expires_in = payload.get("expires_in", 300) if isinstance(payload, dict) else 300
        if not token:
            raise OpenEMRAuthError("oauth token response missing access_token")
        try:
            expires_seconds = int(expires_in)
        except (TypeError, ValueError):
            expires_seconds = 300
        self._token_cache = _TokenCache(
            access_token=token,
            expires_at=now + timedelta(seconds=max(60, expires_seconds)),
        )
        return token

    def _resolve_token_endpoint(self) -> str:
        if self.oauth_token_url_override:
            self._token_endpoint_source = "override"
            return self.oauth_token_url_override
        if self._discovered_token_url:
            self._token_endpoint_source = "discovery"
            return self._discovered_token_url
        discovery_url = self.oauth_discovery_url or f"{self.base_url}{self.api_base_path}/.well-known/smart-configuration"
        response = self._http_request("GET", discovery_url, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise OpenEMRAuthError(f"oauth discovery failed: HTTP {response.status_code}")
        payload = self._parse_json(response)
        token_url = payload.get("token_endpoint") if isinstance(payload, dict) else None
        if not token_url:
            raise OpenEMRAuthError("oauth discovery missing token_endpoint")
        self._discovered_token_url = token_url
        self._token_endpoint_source = "discovery"
        return token_url

    def _resolved_token_endpoint_or_none(self) -> str | None:
        if self.oauth_token_url_override:
            return self.oauth_token_url_override
        return self._discovered_token_url

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenEMRResponseError("OpenEMR returned invalid JSON response") from exc
        if not isinstance(payload, dict):
            raise OpenEMRResponseError("OpenEMR returned unexpected JSON payload")
        return payload

    @staticmethod
    def _extract_patient_id(bundle_payload: dict[str, Any]) -> str | None:
        entries = bundle_payload.get("entry")
        if not isinstance(entries, list):
            return None
        for item in entries:
            if not isinstance(item, dict):
                continue
            response = item.get("response")
            if isinstance(response, dict):
                location = response.get("location")
                if isinstance(location, str) and location.startswith("Patient/"):
                    return location.split("/")[1].split("/")[0]
                if isinstance(location, str) and "Patient/" in location:
                    suffix = location.split("Patient/", 1)[1]
                    return suffix.split("/")[0]
            resource = item.get("resource")
            if isinstance(resource, dict) and resource.get("resourceType") == "Patient":
                rid = resource.get("id")
                if isinstance(rid, str):
                    return rid
        return None

    def _has_basic_credentials(self) -> bool:
        return bool(self.username and self.password)

    @staticmethod
    def _noop(resource_type: str, operation: str) -> OpenEMRSyncResult:
        return OpenEMRSyncResult(
            ok=True,
            resource_type=resource_type,
            operation=operation,
            skipped=True,
            raw_response={"mode": "disabled"},
        )

    @staticmethod
    def _dry_run(resource_type: str, operation: str, external_id: str) -> OpenEMRSyncResult:
        return OpenEMRSyncResult(
            ok=True,
            external_id=external_id,
            resource_type=resource_type,
            operation=operation,
            raw_response={"mode": "dry_run"},
        )
