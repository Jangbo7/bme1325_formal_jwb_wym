import re
import uuid

from app.domain.identifiers import generate_encounter_id, generate_patient_id


PATIENT_ID_RE = re.compile(r"^P-[0-9a-f]{8}$")
ENCOUNTER_ID_RE = re.compile(r"^E-[0-9]{14}-[0-9a-f]{4}$")


def _headers():
    return {"X-API-Key": "mock-key-001", "Idempotency-Key": uuid.uuid4().hex}


def test_identifier_generators_match_contract_format():
    for _ in range(1000):
        assert PATIENT_ID_RE.fullmatch(generate_patient_id())
        assert ENCOUNTER_ID_RE.fullmatch(generate_encounter_id())


def test_create_encounter_and_transfer_emit_contract_event(api_client_factory):
    client = api_client_factory("encounter_contract.db")
    patient_id = f"P-{uuid.uuid4().hex[:8]}"

    bridge = client.app.state.container["event_bridge"]
    subscriber = bridge.subscribe()
    try:
    create_resp = client.post(
        "/api/v1/encounters",
        headers=_headers(),
        json={"patient_id": patient_id, "name": "Player"},
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()["data"]["encounter"]
        encounter_id = create_data["encounter_id"]
        assert PATIENT_ID_RE.fullmatch(create_data["patient_id"])
        assert ENCOUNTER_ID_RE.fullmatch(encounter_id)

        triage_resp = client.post(
            "/api/v1/triage-sessions",
            headers=_headers(),
            json={
                "patient_id": patient_id,
                "session_id": f"session-{uuid.uuid4().hex[:8]}",
                "name": "Player",
                "visit_id": encounter_id,
                "symptoms": "chest pain",
                "onset_time": "30 minutes ago",
                "allergies": [],
                "vitals": {"heart_rate": 102, "temp_c": 37.2, "pain_score": 6},
            },
        )
        assert triage_resp.status_code == 200

        transfer_resp = client.post(
            f"/api/v1/encounters/{encounter_id}/transfer",
            headers=_headers(),
            json={
                "from_group": "groupA.outpatient",
                "to_group": "groupC.icu",
                "reason": "rule based escalation",
                "ctas_level": "L2",
                "summary": {"chief_complaint": "chest pain"},
                "requested_resources": {"bed_type": "ICU"},
            },
        )
        assert transfer_resp.status_code == 200
        transfer_data = transfer_resp.json()["data"]
        assert transfer_data["status"] == "accepted"
        assert transfer_data["encounter"]["state"] == "TRANSFERRING"

        envelopes = []
        for _ in range(8):
            try:
                envelopes.append(subscriber.get(timeout=0.1))
            except Exception:
                break
        assert any(env.get("event_type") == "encounter.opened" for env in envelopes)
        assert any(
            env.get("event_type") == "patient.transferred"
            and env.get("encounter_id") == encounter_id
            and env.get("patient_id") == patient_id
            for env in envelopes
        )
    finally:
        bridge.unsubscribe(subscriber)
