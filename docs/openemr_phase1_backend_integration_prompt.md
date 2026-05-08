# OpenEMR Phase 1 Backend Integration Prompt for Codex

## Role

You are the backend implementation assistant for this project. Help implement **OpenEMR Phase 1 backend integration**.

## Project Context

This project is a simulated hospital outpatient operation system.

The backend currently uses:

- FastAPI
- SQLite Repository layer
- EventBus
- Explicit state machines
- Agent runtime modules

Existing backend modules include:

```text
backend/app/main.py
backend/app/config.py
backend/app/database.py
backend/app/api/routes/
backend/app/agents/triage/
backend/app/agents/internal_medicine/
backend/app/agents/icu_doctor/
backend/app/agents/test_simulator/
backend/app/events/
backend/app/events/subscribers/
backend/app/repositories/
backend/app/schemas/
backend/app/domain/visit/
backend/app/domain/patient/
```

The goal is to connect OpenEMR as an external **EMR system of record**, while keeping the current FastAPI backend as the **simulation orchestration layer**.

## Core Goal

Do **not** refactor the existing system.

Do **not** modify OpenEMR source code.

Do **not** directly write to OpenEMR MySQL or MariaDB.

Do **not** modify the frontend.

Only add an OpenEMR integration layer inside the existing FastAPI backend so that important simulated clinical data can be synchronized to OpenEMR after key business events.

OpenEMR will run locally through Docker. Specific API endpoints, authentication flow, and supported resources should be verified against the local OpenEMR Swagger / API documentation.

If some OpenEMR endpoints are not yet confirmed, implement a clear adapter abstraction and mock-safe / dry-run behavior. Use explicit TODO comments for uncertain endpoint details instead of hardcoding risky assumptions.

---

# Phase 1 Scope

## 1. Add OpenEMR Integration Package

Create:

```text
backend/app/integrations/openemr/
  __init__.py
  client.py
  mapper.py
  service.py
  schemas.py
  errors.py
```

This package should isolate all OpenEMR-specific logic from the existing application services.

---

## 2. Add OpenEMR Configuration

Update:

```text
backend/app/config.py
```

Add configuration fields:

```text
OPENEMR_ENABLED: bool = false
OPENEMR_BASE_URL: str = "http://localhost:8080"
OPENEMR_API_BASE_PATH: str = "/apis/default/fhir"
OPENEMR_CLIENT_ID: optional str
OPENEMR_CLIENT_SECRET: optional str
OPENEMR_USERNAME: optional str
OPENEMR_PASSWORD: optional str
OPENEMR_TIMEOUT_SECONDS: int = 10
OPENEMR_VERIFY_SSL: bool = false
OPENEMR_DRY_RUN: bool = true
```

Notes:

- `OPENEMR_ENABLED=false` should make the integration safely no-op.
- `OPENEMR_DRY_RUN=true` should avoid real HTTP requests.
- Local development may use `OPENEMR_VERIFY_SSL=false`.

---

## 3. Add Local Database Mapping Fields

Do not remove or rename existing fields.

Add backward-compatible external mapping fields to the local persistence model.

Required fields:

```text
patients.openemr_patient_id
visits.openemr_encounter_id
visits.emr_sync_status
visits.emr_synced_at
visits.emr_sync_error
```

If the project does not use a migration framework, use the existing SQLite initialization pattern and add safe `ALTER TABLE` logic.

The implementation should tolerate existing databases that do not yet have these columns.

---

## 4. Implement OpenEMR Schemas

Create:

```text
backend/app/integrations/openemr/schemas.py
```

Define Pydantic models:

```text
OpenEMRPatientPayload
OpenEMREncounterPayload
OpenEMRNotePayload
OpenEMRTestReportPayload
OpenEMRSyncResult
```

`OpenEMRSyncResult` must include at least:

```text
ok: bool
external_id: optional str
resource_type: str
operation: str
raw_response: optional dict
error: optional str
```

The payload models should be internal adapter-level models, not direct ORM models.

---

## 5. Implement OpenEMR Errors

Create:

```text
backend/app/integrations/openemr/errors.py
```

Add custom exceptions:

```text
OpenEMRError
OpenEMRConfigError
OpenEMRAuthError
OpenEMRRequestError
OpenEMRResponseError
```

All low-level HTTP errors should be wrapped before they reach business services.

---

## 6. Implement OpenEMR Client

Create:

```text
backend/app/integrations/openemr/client.py
```

Requirements:

- Use `httpx` or the HTTP client already used by the project.
- Support `enabled` and `dry_run`.
- Every network request must have a timeout.
- Wrap network and response errors in custom OpenEMR exceptions.
- Keep API base path configurable.
- Prefer FHIR R4 style payloads initially, but do not make the rest of the project depend directly on FHIR shapes.

Implement the following methods:

```text
health_check() -> dict

create_or_update_patient(
    payload: OpenEMRPatientPayload
) -> OpenEMRSyncResult

create_encounter(
    payload: OpenEMREncounterPayload
) -> OpenEMRSyncResult

add_encounter_note(
    payload: OpenEMRNotePayload
) -> OpenEMRSyncResult

add_test_report(
    payload: OpenEMRTestReportPayload
) -> OpenEMRSyncResult
```

### Dry Run Behavior

If `OPENEMR_DRY_RUN=true`:

- Do not send real HTTP requests.
- Return fake external IDs, for example:
  - `dryrun-patient-{local_patient_id}`
  - `dryrun-encounter-{local_visit_id}`
  - `dryrun-note-{local_visit_id}-{note_type}`
  - `dryrun-report-{local_visit_id}`
- Log that OpenEMR is running in dry-run mode.

### Disabled Behavior

If `OPENEMR_ENABLED=false`:

- Do not send real HTTP requests.
- Return a safe no-op `OpenEMRSyncResult`.
- Do not break the main simulation workflow.

---

## 7. Implement Mapper

Create:

```text
backend/app/integrations/openemr/mapper.py
```

The mapper converts local domain objects into OpenEMR adapter payloads.

Do not make HTTP calls inside the mapper.

Implement:

```text
map_patient_to_openemr(patient) -> OpenEMRPatientPayload

map_visit_to_encounter(
    visit,
    patient
) -> OpenEMREncounterPayload

map_triage_to_note(
    patient,
    visit,
    triage_session_or_data
) -> OpenEMRNotePayload

map_internal_medicine_to_note(
    patient,
    visit,
    internal_session_or_data
) -> OpenEMRNotePayload

map_simulated_report_to_report(
    patient,
    visit,
    simulated_report
) -> OpenEMRTestReportPayload
```

### Mapping Rules

Phase 1 should prioritize clinical summaries, not raw agent dialogue.

Do not write full agent dialogue turns to OpenEMR.

Do not write agent private memory to OpenEMR.

OpenEMR notes should be readable by clinicians and may include:

```text
Chief Complaint
History of Present Illness
Triage Level
Recommended Department
Key Symptoms
Risk Flags
Assessment
Plan
Simulated Test Report
Follow-up Advice
```

---

## 8. Implement EMRService

Create:

```text
backend/app/integrations/openemr/service.py
```

Define `EMRService` as the business-level integration entry point.

Implement at least:

```text
ensure_patient_synced(patient_id) -> OpenEMRSyncResult

ensure_visit_encounter_synced(visit_id) -> OpenEMRSyncResult

sync_triage_summary(
    patient_id,
    visit_id,
    session_id=None
) -> OpenEMRSyncResult

sync_internal_medicine_summary(
    patient_id,
    visit_id,
    session_id=None
) -> OpenEMRSyncResult

sync_test_report(
    patient_id,
    visit_id
) -> OpenEMRSyncResult
```

### Service Requirements

- Read local patient, visit, and session data through repositories.
- If a patient already has `openemr_patient_id`, do not create a duplicate patient.
- If a visit already has `openemr_encounter_id`, do not create a duplicate encounter.
- Synchronization failure must not interrupt the main business workflow.
- On failure:
  - Set `emr_sync_status = "failed"`.
  - Store the error in `emr_sync_error`.
- On success:
  - Set `emr_sync_status = "synced"`.
  - Store relevant external IDs.
  - Store `emr_synced_at`.
- If `OPENEMR_ENABLED=false`, return a safe no-op result.

---

## 9. Add EventBus Subscriber

Create:

```text
backend/app/events/subscribers/openemr_sync.py
```

Integrate with existing events where possible:

```text
triage.completed
internal_medicine.consultation_completed
test.report_generated
visit.state_changed
```

Expected behavior:

```text
triage.completed
  -> ensure patient is synced
  -> ensure visit encounter is synced
  -> sync triage summary

internal_medicine.consultation_completed
  -> ensure patient is synced
  -> ensure visit encounter is synced
  -> sync internal medicine note

test.report_generated
  -> ensure patient is synced
  -> ensure visit encounter is synced
  -> sync simulated test report

visit.state_changed
  -> optional: update sync status or finalize encounter if safe
```

If event payload lacks `patient_id`, `visit_id`, or `session_id`, try to recover them from the existing repositories or `visit.data_json`.

If recovery is not possible:

- Log a warning.
- Do not throw a fatal exception.
- Do not break existing EventBus subscribers.

---

## 10. Wire Integration in Application Startup

Update:

```text
backend/app/main.py
```

Add application wiring:

- Initialize `OpenEMRClient`.
- Initialize `EMRService`.
- Register OpenEMR sync subscriber.
- Follow the existing application composition style.
- Do not interfere with existing triage, internal medicine, ICU, queue, patient projection, or audit subscribers.

Registration strategy:

Either:

```text
Register subscriber only when OPENEMR_ENABLED=true
```

or:

```text
Always register subscriber, but make service no-op when disabled
```

Use whichever style best matches the existing project.

---

## 11. Add Debug API Endpoints

Add a development/debug route.

Possible file:

```text
backend/app/api/routes/openemr.py
```

Add endpoints:

```text
GET /api/v1/openemr/health

POST /api/v1/openemr/sync/patient/{patient_id}

POST /api/v1/openemr/sync/visit/{visit_id}

POST /api/v1/openemr/sync/visit/{visit_id}/notes
```

Requirements:

- These endpoints are for local development and debugging.
- They should return `OpenEMRSyncResult` or a similarly structured response.
- They should not require frontend integration.
- They should not alter existing frontend behavior.

---

## 12. Tests

Add pytest coverage for:

```text
Mapper converts patient to OpenEMR patient payload.

Mapper converts visit to encounter payload.

Mapper converts simulated report to report payload.

OPENEMR_ENABLED=false makes EMRService safely no-op.

OPENEMR_DRY_RUN=true avoids real HTTP requests.

Patient with existing openemr_patient_id is not created again.

Visit with existing openemr_encounter_id is not created again.

OpenEMRClient wraps network errors into OpenEMRError.

OpenEMR subscriber calls EMRService when relevant events are received.

OpenEMR subscriber failure does not break the main workflow.
```

Use mocks for HTTP and repository dependencies.

Do not require a real OpenEMR instance for unit tests.

---

## 13. Logging

Use the project's existing logging style.

Important log messages:

```text
OpenEMR integration disabled
OpenEMR dry-run mode enabled
OpenEMR patient synced
OpenEMR encounter synced
OpenEMR triage note synced
OpenEMR internal medicine note synced
OpenEMR simulated report synced
OpenEMR sync failed
OpenEMR event payload missing required identifiers
```

---

## 14. Do Not Implement

Do not implement any of the following in Phase 1:

```text
Do not clone or modify OpenEMR source code.

Do not directly connect to OpenEMR MySQL or MariaDB.

Do not replace local SQLite persistence with OpenEMR.

Do not move Visit state machine into OpenEMR.

Do not move Queue runtime into OpenEMR scheduling.

Do not write agent private memory into OpenEMR.

Do not write all dialogue turns into OpenEMR.

Do not refactor EventBus.

Do not refactor existing Visit state machine.

Do not modify Canvas frontend or UI.

Do not implement billing.

Do not implement insurance.

Do not implement pharmacy workflow.

Do not implement real lab order workflow.

Do not implement HL7 integration.
```

---

## 15. Implementation Priority

### Priority 1

```text
Configuration
Schemas
Errors
OpenEMRClient dry-run behavior
Mapper
EMRService skeleton
```

### Priority 2

```text
Repository external ID fields
ensure_patient_synced
ensure_visit_encounter_synced
Debug API endpoints
```

### Priority 3

```text
EventBus subscriber
Triage summary sync
Internal medicine summary sync
Simulated report sync
```

### Priority 4

```text
Tests
Logging polish
Error handling polish
Documentation notes
```

---

## 16. Expected Final Output

After implementation, provide a summary with:

```text
Files added
Files modified
New environment variables
How to run tests
How to validate with OPENEMR_DRY_RUN=true
How to switch from dry-run mode to real OpenEMR API calls
Which OpenEMR endpoints still need to be verified against local Swagger
Known limitations
```

---

## 17. Important Implementation Instructions

Before modifying code, scan these files and folders:

```text
backend/app/main.py
backend/app/config.py
backend/app/database.py
backend/app/repositories/
backend/app/events/bus.py
backend/app/events/types.py
backend/app/events/subscribers/
backend/app/api/routes/
backend/app/schemas/
```

Follow the existing project style.

Do not invent repository methods without checking existing implementations.

If new repository methods are needed, add the smallest possible methods and document where they are called.

Keep all OpenEMR-specific code behind the adapter/service boundary.

The rest of the project should not depend directly on OpenEMR API shapes or FHIR resource details.

## ID Mapping and Data Consistency Requirements

The existing local `patient_id` and `visit_id` are simulation-layer identifiers. Do not assume they match OpenEMR identifiers.

Never use local `patient_id` as the OpenEMR Patient resource ID.

Never use local `visit_id` as the OpenEMR Encounter resource ID.

Store OpenEMR-returned identifiers separately:

- patients.openemr_patient_id
- visits.openemr_encounter_id

Treat these external IDs as nullable strings.

If supported by the OpenEMR API / FHIR API, include local IDs as business identifiers, for example:

- Patient.identifier.system = "urn:hos-sim:patient"
- Patient.identifier.value = local patient_id
- Encounter.identifier.system = "urn:hos-sim:visit"
- Encounter.identifier.value = local visit_id

The adapter must be idempotent:

- If a local patient already has openemr_patient_id, do not create another OpenEMR patient.
- If a local visit already has openemr_encounter_id, do not create another OpenEMR encounter.
- If a sync call fails, record emr_sync_status = "failed" and emr_sync_error, but do not break the main simulation workflow.

Data normalization should happen only in the OpenEMR mapper layer.

Do not force the existing simulation schema to match OpenEMR directly.

For Phase 1, tolerate incomplete or inconsistent clinical fields by generating a readable clinical summary note.

Examples:

- If birthDate is unavailable, do not fabricate it from age. Include age in the note instead.
- If gender cannot be mapped confidently, send "unknown" or omit the coded field, depending on endpoint requirements.
- If department names do not match OpenEMR configuration, include the recommended department in the note.
- If triage level has no exact OpenEMR field, include it in the encounter note.
- If simulated lab/test report cannot be represented as a structured FHIR Observation or DiagnosticReport yet, write it as an encounter note or document-style payload.

Do not attempt full patient de-duplication, master patient index logic, billing identity matching, insurance identity matching, or cross-system reconciliation in Phase 1.