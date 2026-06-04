from __future__ import annotations

import json
from datetime import datetime, timezone

from app.events.types import VISIT_STATE_CHANGED
from app.schemas.common import VisitLifecycleState


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OutpatientProcedureService:
    def __init__(self, *, visit_repo, visit_state_machine=None, encounter_orchestration_service=None, bus=None):
        self.visit_repo = visit_repo
        self.visit_state_machine = visit_state_machine
        self.encounter_orchestration_service = encounter_orchestration_service
        self.bus = bus

    @staticmethod
    def build_pre_round2_requirements(*, tests_required: bool, outpatient_procedure_required: bool) -> dict:
        return {
            "tests_required": bool(tests_required),
            "tests_completed": False,
            "outpatient_procedure_required": bool(outpatient_procedure_required),
            "outpatient_procedure_completed": False,
        }

    @staticmethod
    def requirements_ready(value: dict | None) -> bool:
        requirements = value or {}
        tests_ready = (not requirements.get("tests_required")) or bool(requirements.get("tests_completed"))
        procedure_ready = (not requirements.get("outpatient_procedure_required")) or bool(requirements.get("outpatient_procedure_completed"))
        return tests_ready and procedure_ready

    def route_after_round1(
        self,
        visit_row: dict,
        *,
        session_id: str,
        active_agent_type: str,
        tests_required: bool,
        outpatient_procedure_required: bool,
        outpatient_procedure_category: str,
        outpatient_procedure_reason: str,
        extra_data: dict | None = None,
        ordered_at: str | None = None,
    ) -> dict:
        data = self._get_visit_data(visit_row)
        requirements = self.build_pre_round2_requirements(
            tests_required=tests_required,
            outpatient_procedure_required=outpatient_procedure_required,
        )
        data["pre_round2_requirements"] = requirements
        if outpatient_procedure_required:
            data["outpatient_procedure_plan"] = {
                "category": str(outpatient_procedure_category or "").strip(),
                "reason": str(outpatient_procedure_reason or "").strip(),
                "ordered_by_session_id": session_id,
                "ordered_at": ordered_at or now_iso(),
            }
        if extra_data:
            data.update(extra_data)

        if outpatient_procedure_required:
            return self._transition_visit(
                visit_row,
                "order_outpatient_procedure",
                current_node="outpatient_procedure_wait",
                current_department="Outpatient Procedure",
                active_agent_type=active_agent_type,
                extra_data=data,
            )
        return self._transition_visit(
            visit_row,
            "consultation_completed",
            current_node="diagnostic_wait",
            current_department="Auxiliary Diagnostic Center",
            active_agent_type=active_agent_type,
            extra_data=data,
        )

    def mark_tests_completed(self, visit_row: dict, *, active_agent_type: str | None = None) -> dict:
        data = self._get_visit_data(visit_row)
        requirements = dict(data.get("pre_round2_requirements") or {})
        requirements["tests_completed"] = True
        data["pre_round2_requirements"] = requirements

        if requirements.get("outpatient_procedure_required") and not requirements.get("outpatient_procedure_completed"):
            return self._transition_visit(
                visit_row,
                "order_outpatient_procedure",
                current_node="outpatient_procedure_wait",
                current_department="Outpatient Procedure",
                active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
                extra_data=data,
            )

        return self._transition_visit(
            visit_row,
            "results_ready",
            current_node=visit_row.get("assigned_department_id") or visit_row.get("current_node"),
            current_department=visit_row.get("assigned_department_name") or visit_row.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            extra_data=data,
        )

    def start_outpatient_procedure(self, visit_row: dict, *, active_agent_type: str | None = None) -> dict:
        return self._transition_visit(
            visit_row,
            "start_outpatient_procedure",
            current_node="outpatient_procedure_room",
            current_department="Outpatient Procedure",
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            extra_data=self._get_visit_data(visit_row),
        )

    def finish_outpatient_procedure(self, visit_row: dict, *, active_agent_type: str | None = None) -> dict:
        data = self._get_visit_data(visit_row)
        requirements = dict(data.get("pre_round2_requirements") or {})
        requirements["outpatient_procedure_completed"] = True
        data["pre_round2_requirements"] = requirements
        plan = dict(data.get("outpatient_procedure_plan") or {})
        data["outpatient_procedure_summary"] = {
            "completed": True,
            "category": str(plan.get("category") or "").strip(),
            "completed_at": now_iso(),
            "status": "completed",
        }

        if requirements.get("tests_required") and not requirements.get("tests_completed"):
            return self._transition_visit(
                visit_row,
                "order_tests",
                current_node="diagnostic_wait",
                current_department="Auxiliary Diagnostic Center",
                active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
                extra_data=data,
            )

        return self._transition_visit(
            visit_row,
            "finish_outpatient_procedure",
            current_node=visit_row.get("assigned_department_id") or visit_row.get("current_node"),
            current_department=visit_row.get("assigned_department_name") or visit_row.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            extra_data=data,
        )

    def _transition_visit(
        self,
        visit_row: dict,
        event: str,
        *,
        current_node: str | None = None,
        current_department: str | None = None,
        active_agent_type: str | None = None,
        extra_data: dict | None = None,
    ) -> dict:
        if self.encounter_orchestration_service is not None:
            self.encounter_orchestration_service.transition(
                visit_row["id"],
                event,
                context={"source": "outpatient_procedure_service"},
            )
            refreshed = self.visit_repo.get(visit_row["id"]) or visit_row
            merged = self._get_visit_data(refreshed)
            if extra_data:
                protected = {"orchestration_state", "orchestration_history", "orchestration_debug_log"}
                for key, value in extra_data.items():
                    if key not in protected:
                        merged[key] = value
            return self.visit_repo.update_visit(
                visit_row["id"],
                current_node=current_node if current_node is not None else refreshed.get("current_node"),
                current_department=current_department if current_department is not None else refreshed.get("current_department"),
                active_agent_type=active_agent_type if active_agent_type is not None else refreshed.get("active_agent_type"),
                data=merged,
            )

        current_state = VisitLifecycleState(visit_row["state"])
        next_state = self.visit_state_machine.transition(current_state, event)
        updated = self.visit_repo.update_visit(
            visit_row["id"],
            state=next_state.value,
            current_node=current_node if current_node is not None else visit_row.get("current_node"),
            current_department=current_department if current_department is not None else visit_row.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else visit_row.get("active_agent_type"),
            data=extra_data if extra_data is not None else self._get_visit_data(visit_row),
        )
        if self.bus is not None:
            self.bus.publish(
                VISIT_STATE_CHANGED,
                {
                    "visit_id": updated["id"],
                    "patient_id": updated["patient_id"],
                    "state": updated["state"],
                    "event": event,
                },
            )
        return updated

    @staticmethod
    def _get_visit_data(visit_row: dict | None) -> dict:
        if not visit_row:
            return {}
        data_json = visit_row.get("data_json")
        if not data_json:
            return {}
        try:
            return json.loads(data_json)
        except Exception:
            return {}
