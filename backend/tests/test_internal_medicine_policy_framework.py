from app.agents.internal_medicine.policy import load_internal_medicine_policy_registry
from tests.test_internal_medicine_p2_finalization import (
    PATIENT_ID,
    create_internal_medicine_session,
    create_test_client,
    get_data,
    headers,
    prepare_visit_in_consultation,
)


def test_internal_medicine_round1_uses_policy_card(monkeypatch):
    registry = load_internal_medicine_policy_registry()
    assert registry.cards[0].id == "internal_medicine_initial_consultation"

    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="mild cough",
        symptoms="mild cough",
    )

    memory_repo = client.app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(create_data["session_id"], PATIENT_ID, agent_type="internal_medicine")

    assert session_memory["latest_policy"]["card_id"] == "internal_medicine_initial_consultation"
    assert session_memory["latest_policy"]["phase"] == "round1_initial_consultation"
    assert session_memory["latest_policy"]["snapshot"]["next_action"] == "ask_follow_up"


def test_internal_medicine_round1_policy_snapshot_escalates_red_flags(monkeypatch):
    client = create_test_client(monkeypatch)
    visit_id = prepare_visit_in_consultation(client)
    create_data = create_internal_medicine_session(
        client,
        visit_id,
        chief_complaint="chest pain",
        symptoms="chest pain, shortness of breath",
        onset_time="this morning",
        allergies=[],
        vitals={"heart_rate": 136, "systolic_bp": 88, "diastolic_bp": 58, "pain_score": 8},
    )
    session_id = create_data["session_id"]

    response = client.post(
        f"/api/v1/internal-medicine-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": PATIENT_ID,
            "visit_id": visit_id,
            "name": "Player",
            "message": "Chest pain started this morning and I have no allergies, but now it is worse and I feel short of breath.",
        },
    )
    assert response.status_code == 200, response.text
    data = get_data(response)

    memory_repo = client.app.state.container["memory_repo"]
    session_memory = memory_repo.get_agent_session_memory(session_id, PATIENT_ID, agent_type="internal_medicine")

    assert data["dialogue"]["status"] == "awaiting_patient_reply"
    assert session_memory["latest_policy"]["snapshot"]["next_action"] == "escalate_urgency"
    assert session_memory["latest_policy"]["snapshot"]["urgency"] == "urgent"
