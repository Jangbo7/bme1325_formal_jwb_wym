from app.agents.department_runtime.config import DepartmentAgentConfig

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except Exception:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class DepartmentAgentGraph:
    def __init__(self, service, dialogue_state_machine, config: DepartmentAgentConfig):
        self.service = service
        self.dialogue_state_machine = dialogue_state_machine
        self.config = config
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
        session_id = work.get("session_id") or payload.get("session_id")
        payload["session_id"] = session_id
        patient_id = payload["patient_id"]
        mode = work["mode"]

        if mode == "create_session":
            dialogue_state = self.config.state_enum.IDLE
            for event in self.config.create_session_events:
                dialogue_state = self.dialogue_state_machine.transition(dialogue_state, event)
            self.service.prepare_create_session(payload, session_id, dialogue_state)
        else:
            session_row = self.service.validate_continue_session(session_id, payload)
            current_dialogue_state = self.config.state_enum(session_row["dialogue_state"])
            dialogue_state = self.dialogue_state_machine.transition(
                current_dialogue_state,
                self.config.continue_session_event,
            )
            self.service.session_repo.update_state(session_id, dialogue_state.value)
            self.service.append_user_turn(session_id, patient_id, payload.get("message", ""), mode)

        memory = self.service.prepare_context(payload, session_id, dialogue_state)
        if mode == "continue_session":
            self.service.apply_chat_updates(payload, memory)
        self.service.sync_progress_to_private_memory(memory)
        merged_payload = self.service.build_merged_payload(payload, memory.shared_memory, memory.private_memory)
        state = self.service.build_graph_state(
            payload=payload,
            patient_row=self.service.patient_repo.get(patient_id),
            session_row=self.service.session_repo.get(session_id),
            shared_memory=memory.shared_memory,
            private_memory=memory.private_memory,
            turns=memory.short_term_turns,
            merged_payload=merged_payload,
            dialogue_state=dialogue_state,
        )
        return {"work": work, "state": state, "memory": memory}

    def _evaluate_node(self, bundle: dict):
        if bundle.get("response"):
            return bundle
        state = bundle["state"]
        memory = self.service.build_working_memory_from_state(bundle, state)
        final_result, evidence, missing_fields, assistant_payload, complete = self.service.evaluate(
            state.merged_payload,
            memory,
            bundle["work"]["mode"],
        )
        state.shared_memory = memory.shared_memory
        state.private_memory = memory.private_memory
        state.final_result = final_result
        state.evidence = evidence
        state.missing_fields = missing_fields
        state.assistant_message = assistant_payload
        state.complete = complete
        transition_events = self.config.complete_events if complete else self.config.followup_events
        for event in transition_events:
            state.dialogue_state = self.dialogue_state_machine.transition(state.dialogue_state, event)
        return bundle

    def _persist_node(self, bundle: dict):
        if bundle.get("response"):
            return bundle
        state = bundle["state"]
        memory = self.service.build_working_memory_from_state(bundle, state)
        self.service.persist_result(
            patient_id=state.payload["patient_id"],
            session_id=state.payload["session_id"],
            payload=state.payload,
            memory=memory,
            dialogue_state=state.dialogue_state,
            consultation_result=state.final_result,
            evidence=state.evidence,
            missing_fields=state.missing_fields,
            assistant_payload=state.assistant_message,
            complete=state.complete,
        )
        return bundle

    def _build_response_node(self, bundle: dict):
        if bundle.get("response"):
            return bundle
        state = bundle["state"]
        bundle["response"] = self.service.build_response(state.payload["patient_id"], state.payload["session_id"])
        return bundle
