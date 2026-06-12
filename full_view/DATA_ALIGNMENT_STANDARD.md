# Full Hospital Data Alignment Standard

Note: this file is a department-alignment research record. The canonical hospital-wide standard for the new fullview core system is `HOSPITAL_CORE_STANDARD.md`.

This document records how the full-view hospital frontend/backend should align with the existing department systems under `department/`.

The goal is to keep `hospital/full_view` maintainable while it becomes the shared hospital visualization layer: department systems own clinical/business logic, and full-view renders state, sends standardized event requests, and plays approved animations.

## Source Systems Reviewed

### Shared Inter-group Contract

Primary references:

- `department/outpatient/接口契约_v1.0.md`
- `department/MDT/接口契约_v1.0.md`
- `department/ward/inpatient_bridge/contract.py`
- `department/Emergency/app_core/his/adapters/contract_adapter.py`
- `department/ICU_repo/docs/CONTRACT_v1_COMPLIANCE.md`

Core shared conventions:

- `patient_id`: `P-{8 lowercase hex}`, for example `P-a1b2c3d4`.
- `encounter_id`: `E-{YYYYMMDDHHmmss}-{4 lowercase hex}`, for example `E-20260507143022-1a2b`.
- `event_id`: `evt_` plus globally unique event token for bus events.
- Standard patient states:
  - `ARRIVED`
  - `REGISTERED`
  - `TRIAGED`
  - `IN_CONSULTATION`
  - `IN_EXAM`
  - `IN_TREATMENT`
  - `ADMITTED`
  - `DISCHARGED`
  - `COMPLETED`
  - `TRANSFERRING`
  - `CANCELLED`
  - `ERROR`
- CTAS levels: `L1` to `L5`.
- Triage zones derived from CTAS: `red`, `yellow`, `green`.
- Cross-system event envelope:

```json
{
  "event_id": "evt_01HX7K3M2N4PQRSTVWXYZA1B2C",
  "event_type": "patient.triaged",
  "schema_version": "1.0",
  "occurred_at": "2026-05-07T14:30:22.123+08:00",
  "producer": "groupB.ed",
  "patient_id": "P-a1b2c3d4",
  "encounter_id": "E-20260507143022-1a2b",
  "correlation_id": "evt_01HX7K3M2N4PQRSTVWXYZA1B2C",
  "data": {}
}
```

### Outpatient

Primary references:

- `department/outpatient/接口契约_v1.0.md`
- `department/outpatient/backend/app/services/patient_flow_engine.py`
- `department/outpatient/backend/app/services/scene_snapshot_service.py`
- `department/outpatient/scene/npc/runtime.js`

Important patterns:

- Door-to-room movement is modeled as room graph/pathfinding.
- Patients are associated with visit state, current node/room, and target room.
- Frontend can display patient movement but should not decide clinical legality.
- The course contract identifies outpatient as the shared visual entry point and event subscriber.

### Emergency

Primary references:

- `department/Emergency/app_core/his/schemas/patient.py`
- `department/Emergency/app_core/his/schemas/encounter.py`
- `department/Emergency/app_core/his/schemas/order.py`
- `department/Emergency/app_core/his/schemas/lab.py`
- `department/Emergency/app_core/his/schemas/imaging.py`
- `department/Emergency/app_core/his/schemas/handoff.py`
- `department/Emergency/app_core/his/schemas/provider.py`
- `department/Emergency/app_core/his/schemas/department.py`

Important patterns:

- `PatientRecord`: `patient_id`, `mrn`, `full_name`, `sex`, `date_of_birth`, `phone`, `identifiers`, `created_at`.
- `EncounterRecord`: `patient_id`, `encounter_id`, `status`, `arrival_mode`, `current_zone`, `ctas_level`, `metadata`, timestamps.
- `VitalSignsRecord`: `vital_id`, `encounter_id`, `patient_id`, `readings`, `recorded_at`.
- `ClinicalAssessmentRecord`: `assessment_id`, `author_role`, `findings`, `recorded_at`.
- `DiagnosisRecord`: `diagnosis_id`, `label`, `diagnosis_type`, `details`, `recorded_at`.
- `OrderRecord`: `order_id`, `order_type`, `status`, `payload`, `created_at`.
- `LabRequestRecord` / `LabResultRecord`: request/result IDs, `order_id`, `test_code`, `status`, `payload`.
- `ImagingRequestRecord` / `ImagingResultRecord`: request/result IDs, `order_id`, `modality`, `status`, `payload`.
- `HandoffSnapshotRecord`: structured handoff with current state, completed actions, pending tasks, active risks, next actions.
- `ProviderRecord`: `provider_id`, `full_name`, `role`, `department_id`.
- `DepartmentRecord`: `department_id`, `department_name`, `zone`.

### ICU

Primary references:

- `department/ICU_repo/system/backend/api/app/schemas.py`
- `department/ICU_repo/system/backend/测试数据库/init_core_tables.py`
- `department/ICU_repo/docs/CONTRACT_v1_COMPLIANCE.md`
- `department/ICU_repo/数据协议/前后端使用方法.md`

Important patterns:

- ICU has richer operational tables:
  - `patients`
  - `beds`
  - `admissions`
  - `events`
  - `vital_sign_events`
  - `lab_events`
  - `intervention_events`
  - `patient_state_current`
  - `patient_memory`
  - `agent_outputs`
  - `agent_events`
  - `risk_assessments`
  - `alerts`
  - `clinical_summaries`
- `AdmissionOut`: `admission_id`, `encounter_id`, `patient_id`, `bed_id`, `admit_time`, `status`, `encounter_status`, diagnosis/reason/severity/team.
- `PatientStateCurrentOut`: `admission_id`, `patient_id`, `bed_id`, `current_vitals`, `active_problems`, `active_risks`, `latest_interventions`, `care_phase`.
- ICU maps internal admission status to global encounter status:
  - `active` -> `ADMITTED`
  - `discharged` -> `DISCHARGED`
  - `expired` -> `COMPLETED`
  - `transferred` -> `TRANSFERRING`
- ICU has explicit bed state: `occupied`, `empty`, `cleaning`, `maintenance`.

### Ward

Primary references:

- `department/ward/inpatient_bridge/contract.py`
- `department/ward/inpatient_bridge/bridge_agent.py`
- `department/ward/domain/patient_record.py`
- `department/ward/config/ward_config.json`

Important patterns:

- Ward bridge already validates contract IDs and global state transitions.
- Admission request writes a patient record with:
  - `patient_id`
  - `encounter_id`
  - `status`
  - `global_state`
  - `patient_profile`
  - `summary`
  - `requested_resources`
  - `ctas_level`
  - `bed_id`
  - `room_id`
  - assigned doctor/nurse IDs
- Ward bed assignment currently generates `B-WARD-{room}-{bed}` and `R-WARD-{room}`.
- Discharge publishes `patient.discharged` and `encounter.closed`.

### MDT

Primary references:

- `department/MDT/integration/schemas.py`
- `department/MDT/急诊_病人输入格式说明.md`
- `department/MDT/your_icu_payload.json`
- `department/MDT/mock_neurosurgery_icu_payload.json`

Important patterns:

- MDT receives clinical summary payloads rather than managing patient movement.
- Main request fields:
  - `consultation_id`
  - `source`
  - `request_type`
  - `patient_id`
  - `encounter_id`
  - `admission_id`
  - `bed_id`
  - `reason`
  - `patient_profile`
  - `encounter_context`
  - `current_state`
  - `recent_vitals`
  - `recent_labs`
  - `recent_interventions`
  - `risk_assessments`
  - `alerts`
  - `clinical_summary`
  - `patient_memory`
  - `questions_for_mdt`
- Older MDT examples use legacy IDs such as `PAT-NS-00058` and `ADM-NS-...`; these should be treated as aliases, not canonical full-hospital IDs.

## Current Full-view Data Gaps

Current files:

- `hospital/full_view/backend-data/patients.json`
- `hospital/full_view/backend-data/staff.json`
- `hospital/full_view/backend-data/room-state.json`
- `hospital/full_view/map-config.json`
- `hospital/full_view/dev-server.py`
- `hospital/full_view/API.md`

Observed gaps:

- Patient IDs currently use demo values such as `P-ER-001`, `P-OP-004`, `P-ICU-001`; these do not match `P-{8 lowercase hex}`.
- Patient fields use frontend-friendly camelCase such as `patientId`, `roomId`, `bedRoomId`, `bedId`; department systems use snake_case.
- Rooms use local visual slugs such as `ed_minor`, `triage_2`, `icu_beds_a`, `resp_ward`; the shared contract expects canonical room IDs like `R-ED-04` or `R-ICU-03`.
- Beds use local visual slugs such as `icu_beds_a-bed-01`; the shared contract expects canonical bed IDs such as `B-ICU01-01`.
- Staff currently use `employeeId` values like `D-OP-001`; Emergency uses `provider_id`; the standard should expose `staff_id`/`provider_id` and preserve `employee_id` as an alias.
- Movement API currently uses camelCase:
  - `requestId`
  - `operatorId`
  - `eventId`
  - `patientId`
  - `fromRoomId`
  - `toRoomId`
- Event log currently uses `eventSeq`; this is useful for polling, but contract events also need `event_id`, `event_type`, and ISO timestamps.
- Bed reservation is implemented, but it should be documented as a first-class resource model: a patient can be physically away from a bed while still owning that bed.

## Standard Data Model for Full-view

### Naming Policy

Backend JSON and API responses should use snake_case as the canonical format.

The frontend may keep camelCase internally only as a rendering convenience, but data loaded from the backend should be normalized at the API boundary.

Recommended rule:

- Backend stores and returns canonical snake_case.
- Frontend normalizes once in `hospital-api.js`.
- Legacy camelCase fields are accepted during the transition but should not be added to new backend data.

### ID Policy

Canonical IDs:

| Entity | Canonical field | Format |
|---|---|---|
| Patient | `patient_id` | `P-{8 lowercase hex}` |
| Encounter | `encounter_id` | `E-{YYYYMMDDHHmmss}-{4 lowercase hex}` |
| Staff/provider | `staff_id` | `{ROLE}-{DEPT}-{3 digits}` or external provider ID |
| Department | `department_id` | `DEPT-ED`, `DEPT-OUT`, `DEPT-ICU`, `DEPT-WARD`, `DEPT-MDT`, `DEPT-LAB`, `DEPT-PHA` |
| Room | `room_id` | `R-{DEPT}-{2 digits}` |
| Bed | `bed_id` | `B-{DEPT}{room_number}-{2 digits}` |
| Admission | `admission_id` | `ADM-{DEPT}-{YYYYMMDD}-{sequence}` |
| Order | `order_id` | `ORD-{YYYYMMDD}-{5 digits}` |
| Lab request | `lab_request_id` | `LAB-{YYYYMMDD}-{5 digits}` |
| Imaging request | `imaging_request_id` | `IMG-{YYYYMMDD}-{5 digits}` |
| Intervention | `intervention_id` | `INT-{YYYYMMDD}-{5 digits}` |
| Event | `event_id` | `evt_...` |

Every visual room and bed should also keep a local alias:

```json
{
  "room_id": "R-ICU-03",
  "local_room_id": "icu_beds_a",
  "display_name": "ICU Beds1"
}
```

This lets the map keep stable layout keys while external departments use contract IDs.

### Patient Record

Canonical shape:

```json
{
  "patient_id": "P-a1b2c3d4",
  "legacy_patient_ids": ["P-ICU-001"],
  "type": "patient",
  "name": "Ethan Zhang",
  "gender": "male",
  "age": 58,
  "date_of_birth": null,
  "contact": null,
  "allergies": [],
  "chronic_conditions": [],
  "blood_type": null,
  "active_encounter_id": "E-20260611103000-1a2b",
  "status": "ADMITTED",
  "department_id": "DEPT-ICU",
  "current_location": {
    "floor_id": 3,
    "room_id": "R-ICU-03",
    "local_room_id": "icu_beds_a",
    "bed_id": "B-ICU03-01",
    "local_bed_id": "icu_beds_a-bed-01"
  },
  "home_bed": {
    "room_id": "R-ICU-03",
    "local_room_id": "icu_beds_a",
    "bed_id": "B-ICU03-01",
    "local_bed_id": "icu_beds_a-bed-01",
    "retained": true
  },
  "clinical": {
    "symptoms": "Postoperative respiratory monitoring",
    "ctas_level": null,
    "zone": null,
    "care_phase": "unstable",
    "current_vitals": {},
    "active_problems": [],
    "active_risks": [],
    "latest_interventions": []
  },
  "visual": {
    "form": "bed",
    "base_form": "bed",
    "rel_x": 0.2,
    "rel_y": 0.4,
    "skin": "#f2c799",
    "blanket": "#d46d8e"
  }
}
```

Compatibility fields during transition:

- Keep accepting `patientId` as an alias for `patient_id`.
- Keep accepting `roomId` as an alias for `current_location.local_room_id`.
- Keep accepting `bedRoomId` and `bedId` as aliases for `home_bed.local_room_id` and `home_bed.local_bed_id`.

### Encounter Record

Canonical shape:

```json
{
  "encounter_id": "E-20260611103000-1a2b",
  "patient_id": "P-a1b2c3d4",
  "status": "ADMITTED",
  "arrival_mode": "walk-in",
  "ctas_level": "L3",
  "zone": "yellow",
  "opened_at": "2026-06-11T10:30:00+08:00",
  "updated_at": "2026-06-11T10:35:00+08:00",
  "closed_at": null,
  "source_department_id": "DEPT-ED",
  "current_department_id": "DEPT-ICU",
  "metadata": {}
}
```

### Staff Record

Canonical shape:

```json
{
  "staff_id": "D-ICU-001",
  "provider_id": "D-ICU-001",
  "employee_id": "D-ICU-001",
  "type": "doctor",
  "role": "doctor",
  "name": "Dr. Helen Guo",
  "gender": "female",
  "department_id": "DEPT-ICU",
  "current_location": {
    "floor_id": 3,
    "room_id": "R-ICU-03",
    "local_room_id": "icu_beds_a"
  },
  "availability": {
    "available": true,
    "current_task_id": null
  },
  "visual": {
    "pose": "monitoring",
    "rel_x": 0.58,
    "rel_y": 0.58
  }
}
```

### Department Record

Canonical shape:

```json
{
  "department_id": "DEPT-ICU",
  "code": "ICU",
  "name": "ICU",
  "floor_ids": [3],
  "producer": "groupC.icu",
  "status": "open",
  "statistics": {
    "patients": 3,
    "staff": 5,
    "beds_total": 12,
    "beds_occupied": 3
  }
}
```

### Room Record

Canonical shape:

```json
{
  "room_id": "R-ICU-03",
  "local_room_id": "icu_beds_a",
  "floor_id": 3,
  "department_id": "DEPT-ICU",
  "display_name": "ICU Beds1",
  "kind": "icu",
  "protected": false,
  "capacity": {
    "beds": 4,
    "max_beds": 4,
    "queue": 0
  },
  "layout": {
    "x": 16,
    "y": 6,
    "w": 12,
    "h": 8
  },
  "beds": [
    {
      "bed_id": "B-ICU03-01",
      "local_bed_id": "icu_beds_a-bed-01",
      "status": "occupied",
      "patient_id": "P-a1b2c3d4",
      "reserved_by": "P-a1b2c3d4",
      "patient_current_room_id": "R-ICU-03",
      "patient_away": false
    },
    {
      "bed_id": "B-ICU03-02",
      "local_bed_id": "icu_beds_a-bed-02",
      "status": "empty",
      "patient_id": null,
      "reserved_by": null,
      "patient_current_room_id": null,
      "patient_away": false
    }
  ],
  "people": {
    "patients": ["P-a1b2c3d4"],
    "staff": ["D-ICU-001"]
  }
}
```

Bed semantics:

- `status = occupied`: the bed is assigned to a patient and unavailable.
- `patient_away = true`: the patient is temporarily elsewhere for exam/intervention, but still owns the bed.
- `reserved_by` should remain set during temporary diagnostic movement.
- Source bed should be released only on discharge, death/expired, or transfer to another care unit that assigns a new long-stay bed.

### Clinical State Record

This bridges ICU/MDT style state summaries into the full-view snapshot.

```json
{
  "patient_id": "P-a1b2c3d4",
  "encounter_id": "E-20260611103000-1a2b",
  "admission_id": "ADM-ICU-20260611-00001",
  "updated_at": "2026-06-11T11:00:00+08:00",
  "current_vitals": {
    "heart_rate": 84,
    "systolic_bp": 156,
    "diastolic_bp": 92,
    "mean_arterial_pressure": 113,
    "respiratory_rate": 18,
    "temperature": 36.8,
    "spo2": 98,
    "gcs": 15
  },
  "active_problems": [],
  "active_risks": [],
  "latest_interventions": [],
  "care_phase": "unstable"
}
```

### Order, Lab, Imaging, Intervention Records

Full-view should not implement detailed clinical logic, but it should reserve fields so department systems can display state consistently.

```json
{
  "order_id": "ORD-20260611-00001",
  "encounter_id": "E-20260611103000-1a2b",
  "patient_id": "P-a1b2c3d4",
  "order_type": "lab",
  "status": "REQUESTED",
  "created_at": "2026-06-11T11:00:00+08:00",
  "source_department_id": "DEPT-ED",
  "target_department_id": "DEPT-LAB",
  "payload": {}
}
```

```json
{
  "lab_request_id": "LAB-20260611-00001",
  "order_id": "ORD-20260611-00001",
  "encounter_id": "E-20260611103000-1a2b",
  "patient_id": "P-a1b2c3d4",
  "test_code": "CBC",
  "status": "REQUESTED",
  "created_at": "2026-06-11T11:00:00+08:00",
  "payload": {}
}
```

```json
{
  "imaging_request_id": "IMG-20260611-00001",
  "order_id": "ORD-20260611-00002",
  "encounter_id": "E-20260611103000-1a2b",
  "patient_id": "P-a1b2c3d4",
  "modality": "CT",
  "status": "REQUESTED",
  "created_at": "2026-06-11T11:00:00+08:00",
  "payload": {}
}
```

```json
{
  "intervention_id": "INT-20260611-00001",
  "admission_id": "ADM-ICU-20260611-00001",
  "encounter_id": "E-20260611103000-1a2b",
  "patient_id": "P-a1b2c3d4",
  "bed_id": "B-ICU03-01",
  "intervention_type": "fluid",
  "description": "500ml crystalloid bolus",
  "dosage": 500,
  "unit": "ml",
  "timestamp": "2026-06-11T11:00:00+08:00"
}
```

### Move Request

Canonical API request:

```json
{
  "request_id": "req-001",
  "source": "console",
  "operator_id": "manual-admin",
  "event_id": "ED_TO_ICU_MOVE",
  "patient_id": "P-a1b2c3d4",
  "encounter_id": "E-20260611103000-1a2b",
  "from_room_id": "R-ED-04",
  "from_local_room_id": "ed_red_resus",
  "to_room_id": "R-ICU-01",
  "to_local_room_id": "icu_admission",
  "context": {
    "reason": "needs ICU monitoring"
  }
}
```

Transition policy:

- During migration, `/api/hospital/events/move` should accept both snake_case and camelCase.
- Backend validation should resolve canonical IDs first, then local aliases.
- Event rules should use local visual room IDs only as aliases; each rule should also support canonical room IDs.

### Move Response and Animation Plan

Canonical response:

```json
{
  "ok": true,
  "data": {
    "accepted": true,
    "event_seq": 12,
    "event_id": "ED_TO_ICU_MOVE",
    "patient_id": "P-a1b2c3d4",
    "encounter_id": "E-20260611103000-1a2b",
    "status_updates": {
      "patient_status": "TRANSFERRING",
      "source_bed_retained": false,
      "source_bed_released": true,
      "target_reserved": true,
      "bed_id": "B-ICU03-01",
      "local_bed_id": "icu_beds_a-bed-01"
    },
    "animation_plan": {
      "kind": "patient-move",
      "transport": "stretcher",
      "escort_roles": ["porter", "ed_nurse"],
      "equipment": ["portable_monitor", "oxygen", "transport_bag"],
      "from_room_id": "R-ED-04",
      "from_local_room_id": "ed_red_resus",
      "to_room_id": "R-ICU-01",
      "to_local_room_id": "icu_admission",
      "via_room_ids": ["R-ED-13", "R-ELV-01", "R-ELV-03"],
      "via_local_room_ids": ["ed_handoff", "elevator_1", "elevator_3"],
      "final_form": "bed",
      "patient_form_during_move": "stretcher"
    }
  },
  "error": null,
  "trace_id": "trc_..."
}
```

Compatibility fields during transition:

- Keep returning `eventSeq`, `animationPlan`, `statusUpdates` until frontend callers are updated.
- Add snake_case fields beside them, then remove camelCase later.

### Event Log Record

Full-view polling can keep `event_seq`, but each event should also be a contract-style event.

```json
{
  "event_seq": 12,
  "event_id": "evt_01ABCDEF0123456789ABCDEF01",
  "event_type": "patient.transferred",
  "schema_version": "1.0",
  "occurred_at": "2026-06-11T11:00:00+08:00",
  "producer": "full_view.console",
  "patient_id": "P-a1b2c3d4",
  "encounter_id": "E-20260611103000-1a2b",
  "correlation_id": "req-001",
  "accepted": true,
  "data": {
    "event_rule_id": "ED_TO_ICU_MOVE",
    "from_room_id": "R-ED-04",
    "to_room_id": "R-ICU-01",
    "animation_plan": {}
  }
}
```

## Mapping from Current Full-view to Canonical Model

Recommended transitional mapping:

| Current full-view field | Canonical field |
|---|---|
| `patient.patientId` | `patient.patient_id` |
| `patient.id` | `patient.visual_id` or `legacy_local_id` |
| `patient.roomId` | `patient.current_location.local_room_id` |
| `patient.bedRoomId` | `patient.home_bed.local_room_id` |
| `patient.bedId` | `patient.home_bed.local_bed_id` |
| `patient.department` | `patient.department_id` plus display name |
| `patient.symptoms` | `patient.clinical.symptoms` |
| `patient.form` | `patient.visual.form` |
| `patient.relX` / `relY` | `patient.visual.rel_x` / `rel_y` |
| `staff.employeeId` | `staff.employee_id`, `staff.staff_id`, `staff.provider_id` |
| `staff.roomId` | `staff.current_location.local_room_id` |
| `room.id` | `room.local_room_id` |
| `room.roomNumber` | `room.display_room_number` |
| `room.beds` | `room.beds[]` with canonical and local IDs |
| `roomState.rooms.*.bedAssignments` | `room.beds[].patient_id` and `room.beds[].reserved_by` |
| `request.eventId` | `request.event_id` |
| `request.patientId` | `request.patient_id` |
| `request.fromRoomId` | `request.from_local_room_id` |
| `request.toRoomId` | `request.to_local_room_id` |

## Migration Plan

### Phase 1: Add Canonical Fields Without Breaking UI

- Add canonical fields to `patients.json`, `staff.json`, `map-config.json`, and `room-state.json`.
- Keep existing camelCase and local IDs.
- Update `dev-server.py` to read canonical fields first and fall back to legacy fields.
- Update `hospital-api.js` to normalize snapshot data into one frontend shape.
- Keep current map and console behavior unchanged.

### Phase 2: Normalize Backend APIs

- Make `/api/hospital/snapshot`, `/api/hospital/rooms`, `/api/hospital/people`, and `/api/hospital/events/move` return snake_case canonical fields.
- Keep compatibility aliases for one development cycle.
- Update console selectors to submit canonical `patient_id`, `from_room_id`, and `to_room_id` while also sending local aliases for animation.

### Phase 3: Department Adapter Layer

Create small adapter modules:

- `adapters/outpatient_adapter.py`
- `adapters/emergency_adapter.py`
- `adapters/icu_adapter.py`
- `adapters/ward_adapter.py`
- `adapters/mdt_adapter.py`

Each adapter should expose:

```python
def normalize_patient(raw: dict) -> dict: ...
def normalize_staff(raw: dict) -> dict: ...
def normalize_room(raw: dict) -> dict: ...
def normalize_event(raw: dict) -> dict: ...
```

### Phase 4: Strict Validation

- Reject new non-canonical patient IDs unless passed as `legacy_patient_ids`.
- Reject room/bed records without canonical ID and local alias.
- Validate movement events against canonical room IDs and department rule files.

## Recommended Next Implementation Steps

1. Add `canonical_id` fields to map rooms and generated bed IDs.
2. Add `patient_id`, `encounter_id`, `current_location`, `home_bed`, `clinical`, and `visual` fields to patient records.
3. Add `staff_id`, `provider_id`, `department_id`, `current_location`, and `visual` fields to staff records.
4. Update `dev-server.py` with a `normalize_patient_record`, `normalize_staff_record`, `normalize_room_record`, and `normalize_move_request` layer.
5. Update `API.md` after code migration so external departments see only the stable standard, not transitional internals.

## Guiding Principle

Use contract IDs and snake_case for all backend-facing data. Preserve current visual room slugs only as `local_*` aliases for Canvas rendering and pathfinding.
