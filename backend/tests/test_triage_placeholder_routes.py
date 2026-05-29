import queue
import uuid

from app.agents.triage.service import TriageService

PATIENT_ID = "P-11111111"


def _headers():
    return {
        "X-API-Key": "mock-key-001",
        "Idempotency-Key": f"idem-{uuid.uuid4().hex}",
    }


def _get_data(response):
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def _drain_events(subscriber, limit=12):
    events = []
    for _ in range(limit):
        try:
            events.append(subscriber.get(timeout=0.2))
        except queue.Empty:
            break
    return events


def test_triage_level_1_routes_to_icu_placeholder(monkeypatch, api_client_factory):
    def _mock_llm(*_args, **_kwargs):
        return {
            "triage_level": 1,
            "priority": "H",
            "department": "Emergency",
            "note": "critical",
        }

    monkeypatch.setattr(TriageService, "request_triage_from_llm", _mock_llm)
    client = api_client_factory("triage_route_icu.db")
    bridge = client.app.state.container["event_bridge"]
    subscriber = bridge.subscribe()
    try:
        session_id = f"triage-{uuid.uuid4().hex[:8]}"
        resp = client.post(
            "/api/v1/triage-sessions",
            headers=_headers(),
            json={
                "patient_id": PATIENT_ID,
                "session_id": session_id,
                "name": "Player",
                "symptoms": "mild cough",
                "onset_time": "today morning",
                "allergies": [],
                "vitals": {"heart_rate": 82, "temp_c": 36.9, "pain_score": 1},
            },
        )
        assert resp.status_code == 200, resp.text
        data = _get_data(resp)
        assert data["visit_state"] == "in_icu_rescue"

        visit_resp = client.get(f"/api/v1/visits/{data['visit_id']}", headers=_headers())
        assert visit_resp.status_code == 200
        visit = _get_data(visit_resp)["visit"]
        triage_route_hint = (visit.get("data") or {}).get("triage_route_hint") or {}
        assert triage_route_hint.get("target") == "ICU"
        assert triage_route_hint.get("source") == "triage_level"
        assert triage_route_hint.get("placeholder") is True

        events = _drain_events(subscriber)
        assert any(
            evt.get("event_type") == "patient.transferred"
            and (evt.get("data") or {}).get("placeholder") is True
            and (evt.get("data") or {}).get("to_group") == "ICU"
            for evt in events
        )
    finally:
        bridge.unsubscribe(subscriber)


def test_triage_level_2_routes_to_emergency_placeholder(api_client_factory):
    client = api_client_factory("triage_route_ed.db")
    session_id = f"triage-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/triage-sessions",
        headers=_headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "chest pain",
            "onset_time": "30 minutes ago",
            "allergies": [],
            "vitals": {"heart_rate": 110, "temp_c": 37.1, "pain_score": 6},
        },
    )
    assert resp.status_code == 200, resp.text
    data = _get_data(resp)
    assert data["visit_state"] == "in_emergency"

    visit_resp = client.get(f"/api/v1/visits/{data['visit_id']}", headers=_headers())
    assert visit_resp.status_code == 200
    visit = _get_data(visit_resp)["visit"]
    triage_route_hint = (visit.get("data") or {}).get("triage_route_hint") or {}
    assert triage_route_hint.get("target") == "ED"
    assert triage_route_hint.get("placeholder") is True


def test_triage_level_4_keeps_normal_outpatient_chain(api_client_factory):
    client = api_client_factory("triage_route_normal.db")
    session_id = f"triage-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/triage-sessions",
        headers=_headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "mild cough",
            "onset_time": "yesterday",
            "allergies": [],
            "vitals": {"heart_rate": 82, "temp_c": 37.0, "pain_score": 2},
        },
    )
    assert resp.status_code == 200, resp.text
    data = _get_data(resp)
    assert data["visit_state"] == "triaged"

    visit_resp = client.get(f"/api/v1/visits/{data['visit_id']}", headers=_headers())
    assert visit_resp.status_code == 200
    visit = _get_data(visit_resp)["visit"]
    assert "triage_route_hint" not in (visit.get("data") or {})
    assert visit["assigned_department_id"] == "internal"


def test_triage_level_4_surgery_like_case_routes_to_surgery(api_client_factory):
    client = api_client_factory("triage_route_surgery.db")
    session_id = f"triage-{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/api/v1/triage-sessions",
        headers=_headers(),
        json={
            "patient_id": PATIENT_ID,
            "session_id": session_id,
            "name": "Player",
            "symptoms": "minor wound after kitchen knife cut, no fever, no dizziness",
            "onset_time": "today morning",
            "allergies": [],
            "vitals": {"heart_rate": 84, "temp_c": 36.8, "pain_score": 3},
        },
    )
    assert resp.status_code == 200, resp.text
    data = _get_data(resp)
    assert data["visit_state"] == "triaged"

    visit_resp = client.get(f"/api/v1/visits/{data['visit_id']}", headers=_headers())
    assert visit_resp.status_code == 200
    visit = _get_data(visit_resp)["visit"]
    assert visit["assigned_department_id"] == "surgery"
