from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from app.agents.npc_patient.planner import NpcPlanningContext, PlannedNpcAction, plan_next_action
from app.agents.patient_agent.debug_state import PatientAgentDebugState
from app.departments.registry import resolve_department
from app.domain.identifiers import generate_patient_id
from app.events.types import ENCOUNTER_OPENED, PATIENT_STATE_CHANGED, QUEUE_TICKET_CALLED, QUEUE_TICKET_COMPLETED, QUEUE_TICKET_CREATED
from app.schemas.common import PatientLifecycleState, QueueTicketKind, QueueTicketStatus, VisitLifecycleState
from app.services.consultation_registry import resolve_consultation_agent_for_visit
from app.services.department_assignment import resolve_assigned_department_for_visit


WAIT_SECONDS = 10
CONSULTATION_ROOM = "Consultation Room"
CONSULTATION_ROUND1_PHASE = "consultation_round1"
CONSULTATION_ROUND2_PHASE = "consultation_round2"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatientAgentDebugRunner:
    def __init__(self, container: dict):
        self.container = container
        self.patient_repo = container["patient_repo"]
        self.session_repo = container["session_repo"]
        self.queue_repo = container["queue_repo"]
        self.visit_repo = container["visit_repo"]
        self.medical_record_repo = container.get("medical_record_repo")
        self.patient_agent_service = container["patient_agent_service"]
        self.triage_service = container["triage_service"]
        self.internal_medicine_service = container["internal_medicine_service"]
        self.surgery_service = container.get("surgery_service")
        self.encounter_orchestration_service = container["encounter_orchestration_service"]
        self.patient_state_machine = self.triage_service.patient_state_machine
        self.bus = container["event_bus"]

    def spawn(
        self,
        *,
        seed: str | None = None,
        department_id: str | None = None,
    ) -> PatientAgentDebugState:
        patient_id = generate_patient_id()
        case_row, case_card = self.patient_agent_service.spawn_case(
            patient_id=patient_id,
            seed=seed,
            department_id=department_id,
        )
        encounter = self.encounter_orchestration_service.create_or_get_encounter(
            patient_id=patient_id,
            patient_name=case_card.patient_profile.name,
        )
        self.patient_agent_service.attach_case_to_visit(case_row["id"], encounter["id"])
        self.bus.publish(
            ENCOUNTER_OPENED,
            {
                "patient_id": patient_id,
                "encounter_id": encounter["id"],
                "state": encounter["state"],
                "department": encounter.get("current_department"),
            },
        )
        state = PatientAgentDebugState(
            npc_id="PATIENT-AGENT-DEBUG-001",
            patient_id=patient_id,
            encounter_id=encounter["id"],
            phase="encounter",
            status="ready",
            case_id=case_row["id"],
            case_generation_status="generated",
            case_summary=self.patient_agent_service.summarize_case_for_debug(case_card),
            last_action="spawn",
        )
        hint_department = resolve_department(department_id, "M") if department_id else None
        if state.case_summary is not None:
            state.case_summary["generation_hint_department_id"] = (
                hint_department["id"] if hint_department else None
            )
            state.case_summary["generation_hint_department_name"] = (
                hint_department["label"] if hint_department else None
            )
        self._sync_state(state, preserve_dialogue=False)
        return state

    def step(self, state: PatientAgentDebugState) -> PatientAgentDebugState:
        context = self.build_context(state)
        planned = plan_next_action(context)
        return self.execute_planned_action(state, planned)

    def build_context(self, state: PatientAgentDebugState) -> NpcPlanningContext:
        return self._build_context(state)

    def execute_planned_action(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> PatientAgentDebugState:
        if state.finished:
            state.last_action = "finished"
            state.status = "finished"
            self._sync_state(state, preserve_dialogue=False)
            return state
        state.last_action = planned.action
        state.last_error = None
        if planned.action == "finished":
            state.finished = True
            state.phase = "finished"
            state.status = "finished"
            self._sync_state(state, preserve_dialogue=False)
            return state
        if planned.action == "idle":
            state.step_count += 1
            state.phase = self._phase_for_visit_state(state.visit_state)
            state.status = "idle"
            self._sync_state(state, preserve_dialogue=False)
            return state
        dispatch = {
            "create_encounter": self._create_encounter,
            "create_triage_session": self._create_triage_session,
            "reply_triage": self._reply_triage,
            "register_visit": self._register_visit,
            "progress_visit": self._progress_visit,
            "enter_consultation": self._enter_consultation,
            "create_internal_medicine_session": self._create_internal_medicine_session,
            "reply_internal_medicine": self._reply_internal_medicine,
            "trigger_encounter_event": self._trigger_encounter_event,
        }
        preserve_dialogue = planned.action in {
            "create_triage_session",
            "reply_triage",
            "create_internal_medicine_session",
            "reply_internal_medicine",
        }
        dispatch[planned.action](state, planned)
        state.step_count += 1
        self._sync_state(state, preserve_dialogue=preserve_dialogue)
        if state.visit_state == VisitLifecycleState.WAITING_PAYMENT.value:
            state.finished = True
            state.phase = "finished"
            state.status = "finished"
            state.clear_dialogue()
        return state

    def _build_context(self, state: PatientAgentDebugState) -> NpcPlanningContext:
        visit_row = self._get_visit_row(state)
        visit_data = self._decode_visit_data(visit_row)
        consultation_definition = self._consultation_definition_for_visit(visit_row)
        triage_session = self._resolve_session(visit_data.get("triage_session_id"), visit_row, "triage")
        round1_session = self._resolve_session(
            visit_data.get(consultation_definition.session_ref_key) if consultation_definition else None,
            visit_row,
            consultation_definition.agent_type if consultation_definition else "internal_medicine",
        )
        round2_session = self._resolve_session(
            visit_data.get(consultation_definition.round2_session_ref_key) if consultation_definition and consultation_definition.round2_session_ref_key else None,
            visit_row,
            consultation_definition.agent_type if consultation_definition else "internal_medicine",
            allow_latest=False,
        )
        patient_row = self.patient_repo.get(state.patient_id)
        return NpcPlanningContext(
            encounter_id=state.encounter_id,
            visit_state=visit_row.get("state") if visit_row else None,
            patient_state=patient_row.get("lifecycle_state") if patient_row else None,
            triage_session_state=triage_session.get("dialogue_state") if triage_session else None,
            internal_medicine_round1_state=round1_session.get("dialogue_state") if round1_session else None,
            internal_medicine_round2_state=round2_session.get("dialogue_state") if round2_session else None,
        )

    def _create_encounter(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        case_card = self.patient_agent_service.get_case_card(patient_id=state.patient_id, visit_id=state.encounter_id)
        encounter = self.encounter_orchestration_service.create_or_get_encounter(
            patient_id=state.patient_id,
            patient_name=case_card.patient_profile.name,
        )
        state.encounter_id = encounter["id"]
        state.phase = "encounter"
        state.status = "ready"
        state.clear_dialogue()

    def _create_triage_session(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        payload = self.patient_agent_service.build_initial_payload(
            patient_id=state.patient_id,
            visit_id=state.encounter_id,
            round_number=1,
        )
        payload["session_id"] = f"session-{uuid.uuid4().hex[:8]}"
        response = self.triage_service.create_session(payload)
        state.encounter_id = response.get("visit_id") or state.encounter_id
        state.active_session_id = response["session_id"]
        state.phase = "triage"
        state.status = response.get("dialogue", {}).get("status") or "triaging"
        self._record_session_transcript(
            state,
            session_id=response["session_id"],
            phase="triage",
            counterparty="triage_agent",
        )

    def _reply_triage(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        session_id = self._require_triage_session_id(state)
        current = self.triage_service.build_response(state.patient_id, session_id)
        question = current.get("dialogue", {}).get("assistant_message") or ""
        reply = self.patient_agent_service.build_patient_reply(
            patient_id=state.patient_id,
            visit_id=state.encounter_id,
            session_id=session_id,
            phase="triage",
            recent_question=question,
        )
        response = self.triage_service.continue_session(
            session_id,
            {
                "patient_id": state.patient_id,
                "visit_id": state.encounter_id,
                "name": reply["case_summary"]["name"],
                "message": reply["message"],
            },
        )
        state.policy_state = reply["policy_state"]
        state.case_summary = reply["case_summary"]
        state.active_session_id = session_id
        state.phase = "triage"
        state.status = response.get("dialogue", {}).get("status") or "triaging"
        self._record_session_transcript(
            state,
            session_id=session_id,
            phase="triage",
            counterparty="triage_agent",
        )

    def _register_visit(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        visit_row = self._require_visit_row(state)
        visit_state = VisitLifecycleState(visit_row["state"])
        if visit_state == VisitLifecycleState.IN_EMERGENCY:
            state.finished = True
            state.phase = "finished"
            state.status = "finished"
            state.clear_dialogue()
            return
        if visit_state != VisitLifecycleState.TRIAGED:
            return
        case_card = self.patient_agent_service.get_case_card(patient_id=state.patient_id, visit_id=visit_row["id"])
        visit_data = self._decode_visit_data(visit_row)
        visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=WAIT_SECONDS + 1)).isoformat()
        visit_data["registration_profile"] = {
            "name": case_card.patient_profile.name,
            "sex": case_card.patient_profile.sex,
            "age": case_card.patient_profile.age,
            "id_number": "PATIENT-AGENT-REG-001",
        }
        assigned_department = self._assigned_department(visit_row)
        visit_row = self._transition_visit(
            visit_row,
            "register_completed",
            current_node="registration_queue",
            current_department=assigned_department["label"],
            active_agent_type=None,
            data=visit_data,
        )
        ticket = self.queue_repo.create_ticket(
            patient_id=state.patient_id,
            visit_id=visit_row["id"],
            department_id=assigned_department["queue_department_id"],
            department_name=assigned_department["label"],
            queue_kind=QueueTicketKind.INITIAL_CONSULTATION.value,
        )
        self.bus.publish(
            QUEUE_TICKET_CREATED,
            {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": ticket},
        )
        patient_row = self.patient_repo.get(state.patient_id)
        if patient_row and patient_row["lifecycle_state"] == PatientLifecycleState.TRIAGED.value:
            next_state = self.patient_state_machine.transition(PatientLifecycleState.TRIAGED, "queue_created")
            self.patient_repo.update_patient(
                state.patient_id,
                name=case_card.patient_profile.name,
                lifecycle_state=next_state.value,
                location=assigned_department["label"],
                visit_id=visit_row["id"],
            )
            self.bus.publish(
                PATIENT_STATE_CHANGED,
                {"patient_id": state.patient_id, "lifecycle_state": next_state.value},
            )
        state.phase = "registration"
        state.status = VisitLifecycleState.REGISTERED.value
        state.clear_dialogue()

    def _progress_visit(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        visit_row = self._require_visit_row(state)
        if VisitLifecycleState(visit_row["state"]) != VisitLifecycleState.REGISTERED:
            return
        visit_data = self._decode_visit_data(visit_row)
        visit_data["registration_completed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=WAIT_SECONDS + 1)).isoformat()
        assigned_department = self._assigned_department(visit_row)
        ticket = self.queue_repo.get_active_ticket_for_patient(state.patient_id, visit_id=visit_row["id"])
        if ticket and ticket.get("status") == QueueTicketStatus.WAITING.value:
            called_ticket = self.queue_repo.mark_called(ticket["id"]) or ticket
            self.bus.publish(
                QUEUE_TICKET_CALLED,
                {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": called_ticket},
            )
        patient_row = self.patient_repo.get(state.patient_id)
        if patient_row and patient_row["lifecycle_state"] == PatientLifecycleState.QUEUED.value:
            next_state = self.patient_state_machine.transition(PatientLifecycleState.QUEUED, "ticket_called")
            self.patient_repo.update_patient(
                state.patient_id,
                lifecycle_state=next_state.value,
                location=assigned_department["label"],
                visit_id=visit_row["id"],
            )
            self.bus.publish(
                PATIENT_STATE_CHANGED,
                {"patient_id": state.patient_id, "lifecycle_state": next_state.value},
            )
        self._transition_visit(
            visit_row,
            "queue_wait_elapsed",
            current_node=f"{assigned_department['id']}_queue_gate",
            current_department=assigned_department["label"],
            active_agent_type=None,
            data=visit_data,
        )
        state.phase = "queue"
        state.status = VisitLifecycleState.WAITING_CONSULTATION.value
        state.clear_dialogue()

    def _enter_consultation(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        visit_row = self._require_visit_row(state)
        patient_row = self.patient_repo.get(state.patient_id)
        ticket = self.queue_repo.get_active_ticket_for_patient(state.patient_id, visit_id=visit_row["id"])
        if not patient_row or not ticket:
            return
        if VisitLifecycleState(visit_row["state"]) != VisitLifecycleState.WAITING_CONSULTATION:
            return
        if patient_row["lifecycle_state"] != PatientLifecycleState.CALLED.value:
            return
        if ticket.get("status") != QueueTicketStatus.CALLED.value:
            return
        assigned_department = self._assigned_department(visit_row)
        consultation_definition = self._consultation_definition_for_visit(visit_row)
        next_state = self.patient_state_machine.transition(PatientLifecycleState.CALLED, "start_consultation")
        self.patient_repo.update_patient(
            state.patient_id,
            lifecycle_state=next_state.value,
            location=CONSULTATION_ROOM,
            visit_id=visit_row["id"],
        )
        self.bus.publish(
            PATIENT_STATE_CHANGED,
            {"patient_id": state.patient_id, "lifecycle_state": next_state.value},
        )
        self._transition_visit(
            visit_row,
            "start_consultation",
            current_node=f"{assigned_department['id']}_consultation_room",
            current_department=CONSULTATION_ROOM,
            active_agent_type=consultation_definition.agent_type if consultation_definition else None,
            data=self._decode_visit_data(visit_row),
        )
        completed_ticket = self.queue_repo.mark_completed(ticket["id"])
        if completed_ticket:
            self.bus.publish(
                QUEUE_TICKET_COMPLETED,
                {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": completed_ticket},
            )
        state.phase = CONSULTATION_ROUND1_PHASE
        state.status = VisitLifecycleState.IN_CONSULTATION.value
        state.clear_dialogue()

    def _create_internal_medicine_session(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        round_number = int(planned.payload.get("round") or 1)
        consultation_definition = self._require_consultation_definition(state)
        consultation_service = self._require_consultation_service(consultation_definition.agent_type)
        payload = self.patient_agent_service.build_initial_payload(
            patient_id=state.patient_id,
            visit_id=state.encounter_id,
            round_number=round_number,
        )
        payload["session_id"] = f"{consultation_definition.session_prefix}{uuid.uuid4().hex[:8]}"
        payload["debug_read_historical_records"] = True
        response = consultation_service.create_session(payload)
        state.active_session_id = response["session_id"]
        state.phase = self._phase_for_round(round_number)
        state.status = response.get("dialogue", {}).get("status") or "awaiting_patient_reply"
        self._record_session_transcript(
            state,
            session_id=response["session_id"],
            phase=state.phase,
            counterparty=f"{consultation_definition.agent_type}_agent",
        )

    def _reply_internal_medicine(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        round_number = int(planned.payload.get("round") or 1)
        consultation_definition = self._require_consultation_definition(state)
        consultation_service = self._require_consultation_service(consultation_definition.agent_type)
        session_id = self._resolve_internal_session_id(state, round_number)
        current = consultation_service.build_response(state.patient_id, session_id)
        question = current.get("dialogue", {}).get("assistant_message") or ""
        phase = self._phase_for_round(round_number)
        reply = self.patient_agent_service.build_patient_reply(
            patient_id=state.patient_id,
            visit_id=state.encounter_id,
            session_id=session_id,
            phase=phase,
            recent_question=question,
        )
        response = consultation_service.continue_session(
            session_id,
            {
                "patient_id": state.patient_id,
                "visit_id": state.encounter_id,
                "name": reply["case_summary"]["name"],
                "message": reply["message"],
            },
        )
        state.policy_state = reply["policy_state"]
        state.case_summary = reply["case_summary"]
        state.active_session_id = session_id
        state.phase = phase
        state.status = response.get("dialogue", {}).get("status") or "awaiting_patient_reply"
        self._record_session_transcript(
            state,
            session_id=session_id,
            phase=phase,
            counterparty=f"{consultation_definition.agent_type}_agent",
        )

    def _trigger_encounter_event(self, state: PatientAgentDebugState, planned: PlannedNpcAction) -> None:
        event = planned.payload["event"]
        visit_row = self._require_visit_row(state)
        assigned_department = self._assigned_department(visit_row)
        if event == "queue_second_consultation":
            self.encounter_orchestration_service.transition(
                state.encounter_id,
                event,
                context={"source": "patient_agent_debug"},
            )
            ticket = self.queue_repo.create_ticket(
                patient_id=state.patient_id,
                visit_id=visit_row["id"],
                department_id=assigned_department["queue_department_id"],
                department_name=assigned_department["label"],
                queue_kind=QueueTicketKind.RETURN_CONSULTATION.value,
            )
            self.bus.publish(
                QUEUE_TICKET_CREATED,
                {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": ticket},
            )
            state.phase = "testing"
            state.status = VisitLifecycleState.WAITING_SECOND_CONSULTATION.value
            state.clear_dialogue()
            return
        if event == "start_second_consultation":
            ticket = self.queue_repo.get_active_ticket_for_patient(
                state.patient_id,
                visit_id=visit_row["id"],
                queue_kind=QueueTicketKind.RETURN_CONSULTATION.value,
            )
            if not ticket:
                raise ValueError("return consultation ticket not found")
            if ticket.get("status") == QueueTicketStatus.WAITING.value:
                called_ticket = self.queue_repo.mark_called(ticket["id"]) or ticket
                self.bus.publish(
                    QUEUE_TICKET_CALLED,
                    {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": called_ticket},
                )
                ticket = called_ticket
            patient_row = self.patient_repo.get(state.patient_id)
            if patient_row and patient_row["lifecycle_state"] == PatientLifecycleState.IN_TEST.value:
                next_state = self.patient_state_machine.transition(PatientLifecycleState.IN_TEST, "start_second_consultation")
                self.patient_repo.update_patient(
                    state.patient_id,
                    lifecycle_state=next_state.value,
                    location=CONSULTATION_ROOM,
                    visit_id=visit_row["id"],
                )
                self.bus.publish(
                    PATIENT_STATE_CHANGED,
                    {"patient_id": state.patient_id, "lifecycle_state": next_state.value},
                )
        self.encounter_orchestration_service.transition(
            state.encounter_id,
            event,
            context={"source": "patient_agent_debug"},
        )
        if event == "start_second_consultation":
            completed_ticket = self.queue_repo.mark_completed(ticket["id"])
            if completed_ticket:
                self.bus.publish(
                    QUEUE_TICKET_COMPLETED,
                    {"patient_id": state.patient_id, "visit_id": visit_row["id"], "ticket": completed_ticket},
                )
            state.phase = CONSULTATION_ROUND2_PHASE
            state.status = VisitLifecycleState.IN_SECOND_CONSULTATION.value
        else:
            state.phase = "testing"
            state.status = event
        state.clear_dialogue()

    def _resolve_session(
        self,
        session_id: str | None,
        visit_row: dict | None,
        agent_type: str,
        *,
        allow_latest: bool = True,
    ) -> dict | None:
        if session_id:
            row = self.session_repo.get(session_id)
            if row:
                return row
        if not visit_row or not allow_latest:
            return None
        return self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], agent_type)

    def _resolve_internal_session_id(self, state: PatientAgentDebugState, round_number: int) -> str:
        visit_row = self._require_visit_row(state)
        visit_data = self._decode_visit_data(visit_row)
        consultation_definition = self._consultation_definition_for_visit(visit_row)
        if not consultation_definition:
            raise ValueError("consultation definition not found")
        session_key = (
            consultation_definition.round2_session_ref_key
            if round_number == 2 and consultation_definition.round2_session_ref_key
            else consultation_definition.session_ref_key
        )
        session_id = visit_data.get(session_key)
        if session_id:
            return session_id
        latest = self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], consultation_definition.agent_type)
        if latest:
            return latest["id"]
        raise ValueError("consultation session not found")

    def _require_triage_session_id(self, state: PatientAgentDebugState) -> str:
        visit_row = self._require_visit_row(state)
        visit_data = self._decode_visit_data(visit_row)
        session_id = visit_data.get("triage_session_id")
        if session_id:
            return session_id
        latest = self.session_repo.get_latest_by_visit_and_agent(visit_row["id"], "triage")
        if latest:
            return latest["id"]
        raise ValueError("triage session not found")

    def _record_session_transcript(
        self,
        state: PatientAgentDebugState,
        *,
        session_id: str,
        phase: str,
        counterparty: str,
    ) -> None:
        turns = self.session_repo.list_turns(session_id, limit=64)
        previous_count = state.session_turn_offsets.get(session_id, 0)
        for turn in turns[previous_count:]:
            role = str(turn.get("role") or "")
            speaker = "patient_agent" if role == "user" else counterparty
            direction = "outbound" if role == "user" else "inbound"
            state.append_transcript(
                phase=phase,
                speaker=speaker,
                message=str(turn.get("content") or ""),
                timestamp=str(turn.get("timestamp") or now_iso()),
                counterparty=counterparty,
                direction=direction,
            )
        state.session_turn_offsets[session_id] = len(turns)

    def _sync_state(self, state: PatientAgentDebugState, *, preserve_dialogue: bool) -> None:
        visit_row = self._get_visit_row(state)
        patient_row = self.patient_repo.get(state.patient_id)
        state.encounter_id = visit_row["id"] if visit_row else state.encounter_id
        state.visit_state = visit_row.get("state") if visit_row else None
        state.patient_lifecycle_state = patient_row.get("lifecycle_state") if patient_row else None
        if self.medical_record_repo and state.encounter_id:
            timeline = self.medical_record_repo.get_visit_timeline(state.encounter_id)
            state.medical_record_summary = timeline["summary"] if timeline else None
        else:
            state.medical_record_summary = None
        if state.finished:
            state.phase = "finished"
            state.status = "finished"
        elif state.visit_state == VisitLifecycleState.IN_EMERGENCY.value:
            state.phase = "finished"
            state.status = VisitLifecycleState.IN_EMERGENCY.value
        elif state.visit_state:
            state.phase = self._phase_for_visit_state(state.visit_state)
            if not preserve_dialogue:
                state.status = state.visit_state
        if not preserve_dialogue:
            state.clear_dialogue()

    def _transition_visit(
        self,
        visit_row: dict,
        event: str,
        *,
        current_node: str | None = None,
        current_department: str | None = None,
        active_agent_type: str | None = None,
        data: dict | None = None,
    ) -> dict:
        self.encounter_orchestration_service.transition(
            visit_row["id"],
            event,
            context={"source": "patient_agent_debug"},
        )
        updated_after_state = self.visit_repo.get(visit_row["id"]) or visit_row
        merged_data = self._decode_visit_data(updated_after_state)
        if data is not None:
            protected_keys = {"orchestration_state", "orchestration_history", "orchestration_debug_log"}
            for key, value in data.items():
                if key in protected_keys:
                    continue
                merged_data[key] = value
        return self.visit_repo.update_visit(
            visit_row["id"],
            current_node=current_node if current_node is not None else updated_after_state.get("current_node"),
            current_department=current_department if current_department is not None else updated_after_state.get("current_department"),
            active_agent_type=active_agent_type if active_agent_type is not None else updated_after_state.get("active_agent_type"),
            data=merged_data,
        )

    def _get_visit_row(self, state: PatientAgentDebugState) -> dict | None:
        if state.encounter_id:
            row = self.visit_repo.get(state.encounter_id)
            if row:
                return row
        patient_row = self.patient_repo.get(state.patient_id)
        visit_id = patient_row.get("visit_id") if patient_row else None
        if visit_id:
            return self.visit_repo.get(visit_id)
        return None

    def _require_visit_row(self, state: PatientAgentDebugState) -> dict:
        visit_row = self._get_visit_row(state)
        if not visit_row:
            raise ValueError("visit not found")
        return visit_row

    @staticmethod
    def _decode_visit_data(visit_row: dict | None) -> dict:
        if not visit_row:
            return {}
        payload = visit_row.get("data_json")
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except Exception:
            return {}

    @staticmethod
    def _phase_for_round(round_number: int) -> str:
        return CONSULTATION_ROUND2_PHASE if round_number == 2 else CONSULTATION_ROUND1_PHASE

    @staticmethod
    def _phase_for_visit_state(visit_state: str | None) -> str:
        if visit_state in {None, "arrived"}:
            return "encounter"
        if visit_state in {"triaging", "waiting_followup", "triaged"}:
            return "triage"
        if visit_state in {"registered", "waiting_consultation"}:
            return "queue"
        if visit_state == "in_consultation":
            return CONSULTATION_ROUND1_PHASE
        if visit_state in {
            "waiting_test",
            "waiting_test_payment",
            "test_payment_completed",
            "in_test",
            "waiting_outpatient_procedure",
            "in_outpatient_procedure",
            "waiting_return_consultation",
            "results_ready",
            "waiting_second_consultation",
        }:
            return "testing"
        if visit_state == "in_second_consultation":
            return CONSULTATION_ROUND2_PHASE
        if visit_state == "waiting_payment":
            return "finished"
        return "system"

    def _assigned_department(self, visit_row: dict) -> dict:
        patient_row = self.patient_repo.get(visit_row["patient_id"])
        return resolve_assigned_department_for_visit(visit_row, patient_row)

    def _consultation_definition_for_visit(self, visit_row: dict | None):
        if not visit_row:
            return None
        patient_row = self.patient_repo.get(visit_row["patient_id"])
        return resolve_consultation_agent_for_visit(visit_row, patient_row)

    def _require_consultation_definition(self, state: PatientAgentDebugState):
        visit_row = self._require_visit_row(state)
        definition = self._consultation_definition_for_visit(visit_row)
        if definition is None:
            raise ValueError("consultation definition not found")
        return definition

    def _require_consultation_service(self, agent_type: str):
        if agent_type == "internal_medicine":
            return self.internal_medicine_service
        if agent_type == "surgery" and self.surgery_service is not None:
            return self.surgery_service
        raise ValueError(f"consultation service not configured for {agent_type}")
