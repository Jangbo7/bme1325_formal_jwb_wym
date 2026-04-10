from app.agents.internal_medicine.state import InternalMedicineGraphState
from app.agents.internal_medicine.state_machine import InternalMedicineDialogueStateMachine
from app.schemas.common import PatientLifecycleState, InternalMedicineDialogueState

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class InternalMedicineGraph:
    def __init__(self, service, dialogue_state_machine: InternalMedicineDialogueStateMachine):
        self.service = service
        self.dialogue_state_machine = dialogue_state_machine
        self.graph = self._build_graph() if LANGGRAPH_AVAILABLE else None

    def _build_graph(self):
        workflow = StateGraph(dict)
        workflow.add_node("load_context", self._load_context_node)
        workflow.add_node("evaluate", self._evaluate_node)
        workflow.add_node("persist", self._persist_node)
        workflow.add_node("build_response", self._build_response_node)
        workflow.add_edge(START, "load_context")
        workflow.add_edge("load_context", "evaluate")
        workflow.add_edge("evaluate", "persist")
        workflow.add_edge("persist", "build_response")
        workflow.add_edge("build_response", END)
        return workflow.compile()

    def invoke(self, work: dict):
        if self.graph:
            result = self.graph.invoke(work)
            return result["response"]
        bundle = self._load_context_node(work)
        bundle = self._evaluate_node(bundle)
        bundle = self._persist_node(bundle)
        bundle = self._build_response_node(bundle)
        return bundle["response"]

    def _load_context_node(self, work: dict):
        payload = dict(work["payload"])
        session_id = work.get("session_id") or payload.get("session_id") or f"im-session-{payload.get('patient_id', 'unknown')}"
        payload["session_id"] = session_id
        patient_id = payload["patient_id"]

        self.service.patient_repo.upsert_basic(patient_id, payload.get("name", patient_id))

        if work["mode"] == "create_session":
            dialogue_state = self.dialogue_state_machine.transition(InternalMedicineDialogueState.IDLE, "start")
            dialogue_state = self.dialogue_state_machine.transition(dialogue_state, "evaluate")
            self.service.session_repo.create_or_update(session_id, patient_id, dialogue_state.value)
            patient_row = self.service.patient_repo.get(patient_id)
            if patient_row:
                current_patient_state = PatientLifecycleState(patient_row["lifecycle_state"])
                next_patient_state = self.service.patient_state_machine.transition(
                    current_patient_state, "start_internal_medicine"
                )
                self.service.patient_repo.update_patient(
                    patient_id,
                    lifecycle_state=next_patient_state.value,
                    session_id=session_id,
                )
                self.service.bus.publish(
                    "patient.state_changed",
                    {"patient_id": patient_id, "lifecycle_state": next_patient_state.value},
                )
        else:
            session_row = self.service.session_repo.get(session_id)
            current_dialogue_state = InternalMedicineDialogueState(session_row["dialogue_state"])
            dialogue_state = self.dialogue_state_machine.transition(current_dialogue_state, "receive_reply")
            self.service.session_repo.update_state(session_id, dialogue_state.value)

        memory = self.service.prepare_context(payload, session_id, dialogue_state)
        if payload.get("message"):
            self.service.apply_chat_updates(payload, memory)

        user_message = (
            payload.get("message")
            or payload.get("symptoms")
            or payload.get("chief_complaint")
            or payload.get("registration_info", {})
            or "Internal medicine consultation request"
        )
        if isinstance(user_message, dict):
            user_message = str(user_message)
        self.service.session_repo.append_turn(
            session_id,
            patient_id,
            "user",
            user_message,
            self.service.patient_repo.get(patient_id)["updated_at"],
            metadata={"mode": work["mode"]},
        )
        merged_payload = self.service.build_merged_payload(payload, memory.shared_memory)
        state = InternalMedicineGraphState(
            payload=payload,
            patient_row=self.service.patient_repo.get(patient_id),
            session_row=self.service.session_repo.get(session_id),
            shared_memory=memory.shared_memory,
            private_memory=memory.private_memory,
            turns=memory.short_term_turns,
            merged_payload=merged_payload,
            dialogue_state=dialogue_state,
        )
        return {"work": work, "state": state}

    def _evaluate_node(self, bundle: dict):
        state: InternalMedicineGraphState = bundle["state"]
        memory = self.service.prepare_context(state.payload, state.payload["session_id"], state.dialogue_state)
        if state.payload.get("message"):
            self.service.apply_chat_updates(state.payload, memory)
        final_result, evidence, missing_fields, assistant_message = self.service.evaluate(
            state.merged_payload, memory
        )
        state.shared_memory = memory.shared_memory
        state.private_memory = memory.private_memory
        state.final_result = final_result
        state.evidence = evidence
        state.missing_fields = missing_fields
        state.assistant_message = assistant_message
        if missing_fields:
            state.dialogue_state = self.dialogue_state_machine.transition(state.dialogue_state, "need_followup")
            state.dialogue_state = self.dialogue_state_machine.transition(state.dialogue_state, "wait_for_reply")
        else:
            state.dialogue_state = self.dialogue_state_machine.transition(state.dialogue_state, "complete")
        return bundle

    def _persist_node(self, bundle: dict):
        state: InternalMedicineGraphState = bundle["state"]
        memory = self.service.prepare_context(state.payload, state.payload["session_id"], state.dialogue_state)
        if state.payload.get("message"):
            self.service.apply_chat_updates(state.payload, memory)
        self.service.persist_result(
            patient_id=state.payload["patient_id"],
            session_id=state.payload["session_id"],
            payload=state.payload,
            memory=memory,
            dialogue_state=state.dialogue_state,
            consultation_result=state.final_result,
            evidence=state.evidence,
            missing_fields=state.missing_fields,
            assistant_message=state.assistant_message,
        )
        return bundle

    def _build_response_node(self, bundle: dict):
        state: InternalMedicineGraphState = bundle["state"]
        bundle["response"] = self.service.build_response(
            state.payload["patient_id"], state.payload["session_id"]
        )
        return bundle
