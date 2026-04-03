# Agent Development Guide

## Goal
This guide describes how a collaborator should add a new independent agent feature, for example an outpatient doctor agent.

## Recommended Workflow
1. Define the business boundary.
   - Example: `outpatient internal medicine consultation`
   - Clarify what the agent owns and what it does not own.

2. Define the state machine first.
   - Add or document the consultation states before writing prompts.
   - Keep the patient lifecycle state machine as the global workflow owner.
   - Add a sub-state machine only for the new consultation flow.

3. Create a dedicated agent package.
   - Recommended location: `backend/app/agents/<agent_name>/`
   - Standard files:
     - `graph.py`
     - `state.py`
     - `schemas.py`
     - `prompts.py`
     - `rules.py`
     - `service.py`

4. Separate memory correctly.
   - Shared patient facts go to shared memory.
   - Agent-specific progress goes to agent-private memory.
   - Working graph state stays runtime-only.

5. Register API entrypoints.
   - Add a route file under `backend/app/api/routes/`.
   - Expose only typed request/response contracts.

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

## Example: Outpatient Doctor Agent
If a collaborator adds an internal medicine doctor agent, the expected flow is:
1. Patient completes triage.
2. Patient is queued and then called.
3. Patient enters `in_consultation` in the global patient lifecycle.
4. Internal medicine consultation sub-state machine starts.
5. Doctor agent runs its own graph and updates only its own agent-private progress state.
6. Confirmed clinical facts are written back to shared patient memory.
7. Follow-up events are published after consultation milestones are committed.

## Rules To Keep The Codebase Stable
- Do not mix prompts, persistence, and API glue in one file.
- Do not write new agent logic directly into `server.py` or one large frontend script.
- Do not use EventBus as the decision engine.
- Do not store all agent memory in one shared blob.
