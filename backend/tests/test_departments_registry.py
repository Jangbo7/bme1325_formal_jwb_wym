from app.departments.registry import list_departments, map_department_from_triage, resolve_department


def test_formal_departments_have_expected_count_and_ids():
    formal = list_departments(include_legacy=False)
    assert len(formal) == 11
    assert {item["id"] for item in formal} == {
        "internal",
        "surgery",
        "obgyn",
        "pediatrics",
        "ophthalmology",
        "ent",
        "dentistry",
        "dermatology",
        "psychiatry",
        "rehabilitation",
        "pain",
    }
    sample = formal[0]
    assert sample["department_id"] == sample["id"]
    assert sample["name"] == sample["label"]
    assert isinstance(sample["entry_conditions"], list) and sample["entry_conditions"]
    assert isinstance(sample["exit_conditions"], list) and sample["exit_conditions"]
    assert isinstance(sample["supported_actions"], list) and sample["supported_actions"]
    assert sample["queue_policy"]["supports_initial_queue"] is True
    assert sample["queue_policy"]["supports_return_queue"] is True
    assert sample["queue_policy"]["queue_model"] == "dual_kind_shared_department"


def test_triage_mapping_keeps_legacy_compatibility():
    assert map_department_from_triage("anything", "H")["id"] == "emergency"
    assert map_department_from_triage("Fever Clinic", "M")["id"] == "fever"
    assert map_department_from_triage("General Medicine", "M")["id"] == "internal"


def test_resolve_department_supports_id_label_and_triage_text():
    assert resolve_department("internal", "M")["id"] == "internal"
    assert resolve_department("General Medicine", "M")["id"] == "internal"
    assert resolve_department("fever clinic", "M")["id"] == "fever"
    assert resolve_department("unknown text", "H")["id"] == "emergency"


def test_departments_api_returns_formal_and_legacy(api_client_factory):
    client = api_client_factory("departments.db")
    response = client.get("/api/v1/departments")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["total_formal"] == 11
    assert len(data["formal_departments"]) == 11
    assert all("department_id" in item for item in data["formal_departments"])
    assert all("entry_conditions" in item for item in data["formal_departments"])
    assert {item["id"] for item in data["legacy_departments"]} == {"emergency", "fever"}
