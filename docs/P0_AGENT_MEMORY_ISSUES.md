# Multi-Agent Memory P0 Issues (Detailed)

Date: 2026-04-17  
Scope: backend multi-agent memory isolation and patient-view session routing

## Overview

This document expands the two P0 issues identified in the current multi-agent memory design.

- P0-1: Agent-private memory isolation is insufficient at the storage key level.
- P0-2: Patient-level single session pointer causes cross-agent context confusion in patient view APIs.

Both issues can produce incorrect dialogue context and should be fixed before adding more agents.

---

## P0-1: Agent-private Memory Isolation Is Not Strong Enough

### Current Behavior

`agent_session_memory` currently uses `session_id` as the primary key, and repository reads/writes are keyed by `session_id` only.

Observed code points:

- `backend/app/database.py`: `agent_session_memory` table uses `session_id TEXT PRIMARY KEY`.
- `backend/app/repositories/agent_memory.py`: read by `WHERE session_id = ?`.
- `backend/app/repositories/agent_memory.py`: upsert conflict target is `ON CONFLICT(session_id)`.

### Why This Is P0

The system architecture expects agent-private memory to be isolated per agent type, but storage identity does not enforce that isolation.

Risk patterns:

1. If two agents reuse the same `session_id` (manual input, integration bug, or future orchestration flow), one agent can overwrite the other agent's private memory.
2. Even if current session prefixes reduce collision probability (`session-...`, `im-session-...`), this is naming convention safety, not schema safety.
3. On conflict, old memory can be silently replaced, causing non-obvious behavioral drift.

### Repro Scenario (Conceptual)

1. Create triage session with `session_id = S` and persist private memory.
2. Create internal medicine session using the same `session_id = S` (accidental/manual).
3. Internal medicine save path upserts by `session_id` and overwrites triage private memory row.
4. Subsequent triage reads pull incompatible private fields and produce wrong follow-up behavior.

### User/Business Impact

1. Wrong follow-up questions and wrong state continuity.
2. Apparent hallucination-like behavior because memory context is actually from another agent.
3. Hard-to-debug production issues due to silent overwrite semantics.

### Recommended Fix

#### 1) Schema Identity Hardening (Required)

Use composite identity for private memory:

- Primary choice: `UNIQUE(session_id, agent_type)`
- Stricter option: `UNIQUE(session_id, patient_id, agent_type)`

This turns isolation from naming convention into database constraint.

#### 2) Repository Contract Hardening (Required)

Update repository read/write signatures and SQL:

- Read: `WHERE session_id = ? AND agent_type = ?` (optionally also `AND patient_id = ?`)
- Upsert: `ON CONFLICT(session_id, agent_type)`

Also validate loaded row patient identity when provided.

#### 3) Migration Plan (SQLite-safe)

Because SQLite cannot trivially change PK in-place:

1. Create `agent_session_memory_v2` with new unique key.
2. Copy old rows with existing `agent_type` values.
3. Swap table names in a migration step.
4. Keep one-release compatibility fallback for legacy read path if needed.

#### 4) Guardrails

Add log warnings for any detected session reuse across agents during transition.

### Acceptance Criteria

1. Same `session_id` across different `agent_type` no longer causes overwrite.
2. Each agent always reads its own private memory slice.
3. Legacy data is migrated without losing memory blobs.

### Tests To Add

1. Repository test: same `session_id`, different `agent_type` -> two independent rows.
2. Service test: triage and internal medicine with same `session_id` keep independent `missing_fields`, `message_type`, and progress state.
3. Negative test: mismatched patient/session read should return not found or raise explicit error.

---

## P0-2: Patient-level Single Session Pointer Causes Cross-agent View Confusion

### Current Behavior

Patient storage has a single `session_id` pointer. Multiple agents write this field over time, and patient API views are built through triage service by default.

Observed code points:

- `backend/app/repositories/patients.py`: single `session_id` field in patient row update path.
- `backend/app/agents/internal_medicine/service.py`: internal medicine updates patient `session_id`.
- `backend/app/api/routes/patients.py`: patient read API uses `triage_service` for view composition.

### Why This Is P0

In a multi-agent runtime, a patient can have multiple agent sessions in one visit lifecycle. A single pointer cannot represent this safely.

Failure mode:

1. Agent A writes `patient.session_id = SA`.
2. Agent B writes `patient.session_id = SB` later.
3. Shared patient API reads through triage view logic and may interpret `SB` with triage assumptions.
4. Returned dialogue can be wrong agent context or partially incompatible shape.

### Repro Scenario (Conceptual)

1. Triage session starts and stores triage private memory.
2. Patient enters consultation; internal medicine session starts and updates patient `session_id`.
3. Call patient list/detail API.
4. API composes response using triage service + latest patient session pointer, producing incorrect dialogue context for one of the agents.

### User/Business Impact

1. Frontend may show wrong conversation thread for current stage.
2. Status cards can diverge from true active agent.
3. Future agents will amplify this issue (more overwrite races).

### Recommended Fix

#### 1) Stop Using Single Session Pointer as Source of Truth (Required)

Replace patient-level single pointer with agent-aware session mapping.

Two implementation options:

- Option A (recommended): introduce agent-session index by visit.
  - Example model: `(visit_id, patient_id, agent_type, session_id, is_active, updated_at)`
- Option B (minimal): keep `session_id` but add `active_agent_type` and enforce route-level dispatch.

Option A scales better for true multi-agent state.

#### 2) Route-level View Dispatch (Required)

Patient read routes should not always delegate to triage service.

Dispatch view composition by active agent context (from visit state or session index), then include:

- `active_agent_type`
- per-agent session reference
- agent-consistent dialogue payload

#### 3) Data Contract Clarification

Patient API response should be explicit:

1. current active agent
2. dialogue block source agent
3. optional multi-agent summary block if needed by frontend

#### 4) Transition Strategy

1. Add new mapping storage first.
2. Write both legacy and new fields for one release.
3. Read path switches to new mapping.
4. Remove legacy single-pointer dependency after validation.

### Acceptance Criteria

1. A patient with triage + internal medicine sessions can retrieve correct dialogue for active stage.
2. Switching stages does not lose previous agent context.
3. Patient list/detail APIs remain deterministic under multi-agent progression.

### Tests To Add

1. API test: triage -> internal medicine progression, patient detail returns active agent-consistent dialogue.
2. API test: list endpoint remains stable with mixed agent states.
3. Repository/service test: multiple agent sessions for same patient/visit do not overwrite each other.

---

## Suggested Execution Order

1. Land P0-1 schema + repository isolation first (hard correctness boundary).
2. Add regression tests for private-memory isolation.
3. Land P0-2 session mapping + patient route dispatch.
4. Add API regression tests for multi-agent patient views.
5. Remove temporary compatibility fallback.

---

## Definition of Done for This P0 Pair

1. Agent-private memory cannot cross-overwrite by design.
2. Patient API no longer depends on a single global session pointer.
3. Multi-agent stage transitions preserve dialogue continuity and correctness.
4. All new behavior covered by repository and API tests.
