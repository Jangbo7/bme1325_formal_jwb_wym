from app.services.department_capabilities import (
    get_department_capability,
    list_agent_enabled_departments,
    list_departments_for_mode,
    list_script_only_departments,
)


def test_department_capabilities_default_split_matches_current_agent_support():
    assert list_agent_enabled_departments() == ["internal", "surgery"]
    assert "ophthalmology" in list_script_only_departments()

    internal = get_department_capability("internal")
    surgery = get_department_capability("surgery")
    ent = get_department_capability("ent")

    assert internal.department_agent_enabled is True
    assert surgery.department_agent_enabled is True
    assert ent.department_agent_enabled is False
    assert ent.supports_scripted_fallback is True


def test_list_departments_for_mode_uses_capability_filtering():
    assert list_departments_for_mode("intelligent_agent") == ["internal", "surgery"]
    assert "ophthalmology" in list_departments_for_mode("department_mixed")
