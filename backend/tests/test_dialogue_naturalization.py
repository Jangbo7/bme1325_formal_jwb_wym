import uuid

from fastapi.testclient import TestClient

from app.agents.triage.rules import extract_structured_updates
from app.main import create_app


NATURAL_REPLY = "\u4eca\u5929\u65e9\u4e0a\u5f00\u59cb\u7684\uff0c\u5df2\u7ecf\u6301\u7eed\u4e863\u5c0f\u65f6\uff0c\u6709\u70b9\u75db\uff0c\u4f46\u4e0d\u662f\u7279\u522b\u4e25\u91cd\uff0c\u5e94\u8be5\u6ca1\u53d1\u70e7\uff0c\u4ee5\u524d\u6ca1\u53d1\u73b0\u8fc7\u654f"
VAGUE_REPLY = "\u8fd8\u4e0d\u592a\u6e05\u695a"
RECOMMENDATION_LABEL = "\u5efa\u8bae\u79d1\u5ba4"
FINAL_REPLY = "\u4eca\u5929\u65e9\u4e0a\u5f00\u59cb\u7684\uff0c\u5df2\u7ecf\u6301\u7eed\u4e863\u5c0f\u65f6\uff0c\u6ca1\u6709\u8fc7\u654f\uff0c\u75bc\u75db6\u5206\uff0c\u6ca1\u53d1\u70e7"
EXTRA_REPLY = "\u6211\u518d\u8865\u5145\u4e00\u70b9"


def create_test_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test_naturalization.db'}")
    monkeypatch.setenv("MOCK_API_KEY", "mock-key-001")
    monkeypatch.setenv("SIMULATOR_ENABLED", "false")
    app = create_app()
    return TestClient(app)


def headers():
    return {"X-API-Key": "mock-key-001"}


def test_extract_structured_updates_handles_natural_chinese_reply():
    extracted = extract_structured_updates(NATURAL_REPLY)
    assert extracted["onset_time"] is not None
    assert extracted["pain_score"] in {2, 3}
    assert extracted["temp_c"] == 37.0
    assert extracted["allergy_status"] == "known"
    assert "onset_time" in extracted["extracted_fields"]


def test_followup_rewording_avoids_repeating_recommendation(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    create_resp = client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "chest tightness",
            "vitals": {"heart_rate": 105, "temp_c": 37.1, "pain_score": 5},
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert create_data["dialogue"]["question_focus"] == "onset_time"
    assert create_data["dialogue"]["message_type"] == "followup"
    assert create_data["dialogue"]["recommendation_changed"] is True

    reply_resp = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "message": VAGUE_REPLY,
        },
    )
    assert reply_resp.status_code == 200
    reply_data = reply_resp.json()
    assistant_message = reply_data["dialogue"]["assistant_message"]
    assert reply_data["dialogue"]["status"] == "awaiting_patient_reply"
    assert reply_data["dialogue"]["question_focus"] == "onset_time"
    assert reply_data["dialogue"]["recommendation_changed"] is False
    assert RECOMMENDATION_LABEL not in assistant_message
    assert any(
        token in assistant_message
        for token in ("换个问法", "再确认", "回想一下", "开始", "最早", "时间", "几小时")
    )


def test_completed_session_does_not_reenter_state_machine(tmp_path, monkeypatch):
    client = create_test_client(tmp_path, monkeypatch)
    session_id = f"session-{uuid.uuid4().hex[:8]}"

    client.post(
        "/api/v1/triage-sessions",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "session_id": session_id,
            "name": "Player",
            "symptoms": "chest tightness",
            "vitals": {"heart_rate": 105, "temp_c": 37.1, "pain_score": 5},
        },
    )

    reply_resp = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "message": FINAL_REPLY,
        },
    )
    assert reply_resp.status_code == 200
    reply_data = reply_resp.json()
    assert reply_data["dialogue"]["status"] == "triaged"
    turns_before = len(reply_data["dialogue"]["turns"])

    extra_resp = client.post(
        f"/api/v1/triage-sessions/{session_id}/messages",
        headers=headers(),
        json={
            "patient_id": "P-self",
            "name": "Player",
            "message": EXTRA_REPLY,
        },
    )
    assert extra_resp.status_code == 200
    extra_data = extra_resp.json()
    assert extra_data["dialogue"]["status"] == "triaged"
    assert len(extra_data["dialogue"]["turns"]) == turns_before
