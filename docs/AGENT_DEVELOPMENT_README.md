# Agent Development Guide

## Goal
This guide describes how a collaborator should add a new independent agent feature or background simulator, for example an outpatient doctor agent or a fully automatic patient agent.

## Recommended Workflow
1. Define the business boundary.
   - Example: `outpatient internal medicine consultation`
   - Clarify what the agent owns and what it does not own.

2. Define the state machine first.
   - Add or document the consultation states before writing prompts.
   - Keep the patient lifecycle state machine as the global workflow owner.
   - Add a sub-state machine only for the new consultation flow.
   - If the feature is a background simulator, define its tick/advance rules and the global states it is allowed to drive.

3. Create a dedicated agent package.
   - Recommended location: `backend/app/agents/<agent_name>/`
   - Standard files:
     - `graph.py`
     - `state.py`
     - `schemas.py`
     - `prompts.py`
     - `rules.py`
     - `service.py`
   - For non-interactive simulators, a service-only package is acceptable if the feature does not need its own graph.
    - Current repository packages that already follow this split include:
       - `triage/`
       - `internal_medicine/`
       - `icu_doctor/`
       - `patient_agent/`
       - `npc_patient/`
       - `test_simulator/`
       - `interactive_debug/`
       - `multi_patient_debug/`
       - `department_runtime/`
       - `clinical_policy/`

4. Separate memory correctly.
   - Shared patient facts go to shared memory.
   - Agent-specific progress goes to agent-private memory.
   - Working graph state stays runtime-only.

5. Register API entrypoints.
    - Add a route file under `backend/app/api/routes/`.
    - Expose only typed request/response contracts.
    - Background-only agents can skip a public route and be wired from `backend/app/main.py` instead.
    - For doctor-style consultation agents, do not add a new dedicated `xxx_agent_debug.py` by default.
    - Register the doctor config in the unified doctor debug registry and reuse `doctor-agent-debug`.

6. Decide EventBus outputs.
   - Emit events only after state transitions are committed.
   - Use events for side effects such as queue updates, audit logs, or downstream triggers.
   - Do not let EventBus decide core workflow logic.

7. Add tests before frontend integration.
   - State machine tests
   - Service/graph tests
   - API tests
   - Repository tests if new persistence is added

8. Integrate frontend last.
    - Add a dedicated frontend client call.
    - Keep UI state separate from queue/NPC state.
    - Do not patch everything back into one large file.
    - If the agent is backend-driven only, keep the frontend as a passive viewer unless a UI action is truly needed.

## Debug Guidance
- `triage`, `patient_agent`, `npc_debug`, and runtime-level debug pages remain separate because they do not share the same consultation contract.
- Doctor-style agents should prefer the unified `doctor-agent-debug` entrypoint.
- Compatibility pages such as `internal-medicine-agent-debug` may remain temporarily, but new doctor agents should not copy that pattern forward.

## Example: Outpatient Doctor Agent
If a collaborator adds an internal medicine doctor agent, the expected flow is:
1. Patient completes triage.
2. Patient is queued and then called.
3. Patient enters `in_consultation` in the global patient lifecycle.
4. Internal medicine consultation sub-state machine starts.
5. Doctor agent runs its own graph and updates only its own agent-private progress state.
6. Confirmed clinical facts are written back to shared patient memory.
7. If the consultation reaches completion, the service can hand off to `test_simulator` to produce a first-level auxiliary test zone and simulated report.
8. Follow-up events are published after consultation milestones are committed.

## Example: Fully Automatic Patient Agent
If a collaborator adds an automatic patient agent, the expected flow is:
1. The simulator creates or reuses a synthetic patient record.
2. The simulator advances only through allowed patient and visit states.
3. The simulator writes its state transitions through repositories, not through the frontend.
4. The simulator emits events only after each transition is committed.
5. The frontend only renders the resulting patient, queue, and visit views.

## Rules To Keep The Codebase Stable
- Do not mix prompts, persistence, and API glue in one file.
- Do not write new agent logic directly into `server.py` or one large frontend script.
- Do not use EventBus as the decision engine.
- Do not store all agent memory in one shared blob.
