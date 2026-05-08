import httpx
import json
from pathlib import Path
import uuid
import pytest

from app.integrations.openemr.client import OpenEMRClient
from app.integrations.openemr.errors import OpenEMRAuthError, OpenEMRRequestError
from app.integrations.openemr.schemas import OpenEMRPatientPayload


def build_client(
    *,
    enabled: bool,
    dry_run: bool,
    oauth_enabled: bool = False,
    oauth_use_basic_fallback: bool = True,
    username: str | None = None,
    password: str | None = None,
) -> OpenEMRClient:
    return OpenEMRClient(
        enabled=enabled,
        dry_run=dry_run,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        oauth_enabled=oauth_enabled,
        oauth_use_basic_fallback=oauth_use_basic_fallback,
        username=username,
        password=password,
    )


def test_disabled_mode_returns_noop_result():
    client = build_client(enabled=False, dry_run=True)
    result = client.create_or_update_patient(
        OpenEMRPatientPayload(local_patient_id="P-self", name="Player"),
    )
    assert result.ok is True
    assert result.skipped is True
    assert result.external_id is None


def test_dry_run_returns_fake_external_id():
    client = build_client(enabled=True, dry_run=True)
    result = client.create_or_update_patient(
        OpenEMRPatientPayload(local_patient_id="P-self", name="Player"),
    )
    assert result.ok is True
    assert result.external_id == "dryrun-patient-P-self"


def test_network_error_wrapped_as_openemr_request_error(monkeypatch):
    client = build_client(
        enabled=True,
        dry_run=False,
        oauth_enabled=False,
        username="u",
        password="p",
    )

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "request", _raise)
    with pytest.raises(OpenEMRRequestError):
        client.health_check()


def test_oauth_token_success_then_bearer_request(monkeypatch):
    client = OpenEMRClient(
        enabled=True,
        dry_run=False,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        client_id="cid",
        client_secret="secret",
        oauth_enabled=True,
        oauth_discovery_url="http://localhost:8080/.well-known/smart-configuration",
    )

    calls = []

    def _mock_request(**kwargs):
        calls.append(kwargs)
        method = kwargs["method"]
        url = kwargs["url"]
        if method == "GET" and url.endswith("/.well-known/smart-configuration"):
            return httpx.Response(200, json={"token_endpoint": "http://localhost:8080/oauth2/token"})
        if method == "POST" and url.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "token-123", "expires_in": 600})
        if method == "GET" and url.endswith("/metadata"):
            auth_header = (kwargs.get("headers") or {}).get("Authorization")
            assert auth_header == "Bearer token-123"
            return httpx.Response(200, json={"resourceType": "CapabilityStatement"})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(httpx, "request", _mock_request)
    first_health = client.health_check()
    second_health = client.health_check()
    assert first_health["ok"] is True
    assert second_health["ok"] is True
    assert first_health["auth_mode"] == "oauth"
    assert first_health["token_endpoint_source"] == "discovery"
    token_calls = [c for c in calls if c["method"] == "POST" and c["url"].endswith("/oauth2/token")]
    assert len(token_calls) == 1


def test_oauth_token_failure_fallback_to_basic(monkeypatch):
    client = OpenEMRClient(
        enabled=True,
        dry_run=False,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        client_id="cid",
        client_secret="secret",
        oauth_enabled=True,
        oauth_discovery_url="http://localhost:8080/.well-known/smart-configuration",
        oauth_use_basic_fallback=True,
        username="u",
        password="p",
    )

    def _mock_request(**kwargs):
        method = kwargs["method"]
        url = kwargs["url"]
        if method == "GET" and url.endswith("/.well-known/smart-configuration"):
            return httpx.Response(200, json={"token_endpoint": "http://localhost:8080/oauth2/token"})
        if method == "POST" and url.endswith("/oauth2/token"):
            return httpx.Response(401, json={"error": "invalid_client"})
        if method == "GET" and url.endswith("/metadata"):
            assert kwargs.get("auth") == ("u", "p")
            return httpx.Response(200, json={"resourceType": "CapabilityStatement"})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(httpx, "request", _mock_request)
    health = client.health_check()
    assert health["ok"] is True
    assert health["auth_mode"] == "basic_fallback"


def test_oauth_token_failure_without_fallback_raises(monkeypatch):
    client = OpenEMRClient(
        enabled=True,
        dry_run=False,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        client_id="cid",
        client_secret="secret",
        oauth_enabled=True,
        oauth_discovery_url="http://localhost:8080/.well-known/smart-configuration",
        oauth_use_basic_fallback=False,
    )

    def _mock_request(**kwargs):
        method = kwargs["method"]
        url = kwargs["url"]
        if method == "GET" and url.endswith("/.well-known/smart-configuration"):
            return httpx.Response(200, json={"token_endpoint": "http://localhost:8080/oauth2/token"})
        if method == "POST" and url.endswith("/oauth2/token"):
            return httpx.Response(401, json={"error": "invalid_client"})
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(httpx, "request", _mock_request)
    with pytest.raises(OpenEMRAuthError):
        client.health_check()


def test_outbound_payload_written_to_local_text_file(monkeypatch):
    temp_root = Path(__file__).resolve().parents[2] / ".tmp_openemr_tests"
    temp_root.mkdir(parents=True, exist_ok=True)
    log_path = temp_root / f"openemr-outbound-{uuid.uuid4().hex[:8]}.log"
    client = OpenEMRClient(
        enabled=True,
        dry_run=False,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        oauth_enabled=False,
        username="u",
        password="p",
        outbound_log_path=str(log_path),
    )

    def _mock_request(**kwargs):
        return httpx.Response(200, json={"resourceType": "CapabilityStatement"})

    monkeypatch.setattr(httpx, "request", _mock_request)
    client.health_check()

    assert log_path.exists()
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    payload = json.loads(lines[-1])
    assert payload["method"] == "GET"
    assert payload["url"].endswith("/metadata")
    assert payload["has_auth_tuple"] is True
    assert payload["params"] == {"_format": "json"}
    assert "json" not in payload
    assert "data" not in payload


def test_patient_resource_omits_null_gender_birthdate(monkeypatch):
    client = OpenEMRClient(
        enabled=True,
        dry_run=False,
        base_url="http://localhost:8080",
        api_base_path="/apis/default/fhir",
        timeout_seconds=5,
        verify_ssl=False,
        oauth_enabled=False,
        username="u",
        password="p",
    )
    captured_json = {}

    def _mock_request(**kwargs):
        if kwargs["method"] == "POST" and kwargs["url"].endswith("/apis/default/fhir/Patient"):
            captured_json.update(kwargs.get("json") or {})
            return httpx.Response(200, json={"resourceType": "Patient", "id": "ext-p-1"})
        raise AssertionError(f"unexpected request: {kwargs['method']} {kwargs['url']}")

    monkeypatch.setattr(httpx, "request", _mock_request)
    result = client.create_or_update_patient(
        OpenEMRPatientPayload(local_patient_id="P-self", name="Player"),
    )
    assert result.ok is True
    resource = captured_json
    assert "gender" not in resource
    assert "birthDate" not in resource
