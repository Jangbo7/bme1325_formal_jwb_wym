import uuid


def _headers():
    return {
        "X-API-Key": "mock-key-001",
        "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
    }


def _create_encounter(client, patient_id):
    response = client.post(
        "/api/v1/encounters",
        headers=_headers(),
        json={"patient_id": patient_id, "name": "State Debug Player"},
    )
    assert response.status_code == 200
    return response.json()["data"]["encounter"]["encounter_id"]


def test_state_debug_endpoints_disabled_by_default(api_client_factory):
    client = api_client_factory("state_debug_disabled.db")
    encounter_id = _create_encounter(client, f"P-{uuid.uuid4().hex[:8]}")
    response = client.get(f"/api/v1/encounters/{encounter_id}/state-debug", headers=_headers())
    assert response.status_code == 200


def test_state_debug_flow_and_illegal_transition(monkeypatch, api_client_factory):
    monkeypatch.setenv("STATE_DEBUG_ENABLED", "true")
    client = api_client_factory("state_debug_enabled.db")
    encounter_id = _create_encounter(client, f"P-{uuid.uuid4().hex[:8]}")

    graph_resp = client.get("/api/v1/state-machine/graph", headers=_headers())
    assert graph_resp.status_code == 200
    assert "ARRIVED" in graph_resp.json()["data"]["states"]

    debug_resp = client.get(f"/api/v1/encounters/{encounter_id}/state-debug", headers=_headers())
    assert debug_resp.status_code == 200
    assert debug_resp.json()["data"]["standard_state"] == "ARRIVED"

    events = [
        "begin_triage",
        "triage_complete",
        "register_complete",
        "call_patient",
        "start_initial_consultation",
        "finalize_without_tests",
        "request_medical_payment",
        "pay_medical",
        "plan_disposition",
        "complete_visit",
    ]
    latest = None
    for event in events:
        transition_resp = client.post(
            f"/api/v1/encounters/{encounter_id}/state-debug/transition",
            headers=_headers(),
            json={"event": event, "dry_run": False, "context": {"source": "test"}},
        )
        assert transition_resp.status_code == 200
        latest = transition_resp.json()["data"]

    assert latest is not None
    assert latest["to_state"] == "COMPLETED"

    illegal_resp = client.post(
        f"/api/v1/encounters/{encounter_id}/state-debug/transition",
        headers=_headers(),
        json={"event": "begin_triage"},
    )
    assert illegal_resp.status_code == 422
