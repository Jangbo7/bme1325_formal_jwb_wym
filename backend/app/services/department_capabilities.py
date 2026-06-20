from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.departments.registry import list_departments
from app.schemas.multi_patient_debug import MultiPatientMode


CapabilityClass = Literal["agent_enabled", "script_only"]
RunnerKind = Literal["intelligent", "legacy"]


@dataclass(frozen=True, slots=True)
class DepartmentCapability:
    department_id: str
    supports_patient_agent: bool
    supports_consultation_agent: bool
    supports_scripted_fallback: bool
    preferred_runner_kind: RunnerKind

    @property
    def department_agent_enabled(self) -> bool:
        return self.supports_patient_agent and self.supports_consultation_agent

    @property
    def department_capability_class(self) -> CapabilityClass:
        return "agent_enabled" if self.department_agent_enabled else "script_only"


DEPARTMENT_CAPABILITY_OVERRIDES: dict[str, DepartmentCapability] = {
    "internal": DepartmentCapability(
        department_id="internal",
        supports_patient_agent=True,
        supports_consultation_agent=True,
        supports_scripted_fallback=True,
        preferred_runner_kind="intelligent",
    ),
    "surgery": DepartmentCapability(
        department_id="surgery",
        supports_patient_agent=True,
        supports_consultation_agent=True,
        supports_scripted_fallback=True,
        preferred_runner_kind="intelligent",
    ),
}


def _default_capability(department_id: str) -> DepartmentCapability:
    return DepartmentCapability(
        department_id=department_id,
        supports_patient_agent=False,
        supports_consultation_agent=False,
        supports_scripted_fallback=True,
        preferred_runner_kind="legacy",
    )


def get_department_capability(department_id: str | None) -> DepartmentCapability:
    normalized = str(department_id or "").strip()
    return DEPARTMENT_CAPABILITY_OVERRIDES.get(normalized) or _default_capability(normalized)


def list_department_capabilities(*, include_legacy: bool = False) -> list[DepartmentCapability]:
    return [
        get_department_capability(item["id"])
        for item in list_departments(include_legacy=include_legacy)
    ]


def list_agent_enabled_departments() -> list[str]:
    return [
        item.department_id
        for item in list_department_capabilities(include_legacy=False)
        if item.department_agent_enabled
    ]


def list_script_only_departments() -> list[str]:
    return [
        item.department_id
        for item in list_department_capabilities(include_legacy=False)
        if item.department_capability_class == "script_only"
    ]



def is_script_only_department(department_id: str | None) -> bool:
    return get_department_capability(department_id).department_capability_class == "script_only"


def list_departments_for_mode(mode: MultiPatientMode) -> list[str]:
    capabilities = list_department_capabilities(include_legacy=False)
    if mode in {"legacy_template", "legacy_probabilistic_llm", "department_mixed"}:
        return [item.department_id for item in capabilities]
    if mode == "intelligent_agent":
        return [item.department_id for item in capabilities if item.department_agent_enabled]
    return [item.department_id for item in capabilities]
