# SIM Hospital Core Standard

This is the canonical data and API standard for the full hospital system.

`hospital/full_view` is the source-of-truth core for shared hospital state, visualization, movement events, room resources, bed ownership, and operations-console control. Department systems should adapt to this model through adapters instead of forcing fullview to mirror each department's internal schema.

## Principles

1. Fullview owns hospital state.
2. Department systems own department-specific clinical reasoning.
3. Frontend renders snapshots and animations; it does not decide business legality.
4. Backend APIs and JSON files use snake_case as the canonical data format.
5. Existing camelCase fields may remain as compatibility aliases while the UI is migrating.
6. Room IDs and bed IDs are fullview-native stable slugs, because the Canvas map, event rules, pathfinding, and console all depend on them.

## Canonical Files

Core state lives in:

- `map-config.json`: floor, room, layout, furniture, room capacity.
- `backend-data/patients.json`: patient identity, current location, clinical summary, visual state.
- `backend-data/staff.json`: doctors, nurses, porters, and other staff.
- `backend-data/room-state.json`: room resource state, bed IDs, bed assignments, queues.
- `backend-data/event-log.json`: accepted/rejected event history and animation instructions.
- `event-rules/*.json`: reusable movement rules.

## IDs

Fullview IDs are semantic, stable, and readable.

| Entity | Field | Format | Example |
|---|---|---|---|
| Floor | `floor_id` | integer 1-5 | `3` |
| Department | `department_id` | lowercase slug | `emergency`, `outpatient`, `icu`, `ward`, `mdt` |
| Room | `room_id` | lowercase semantic slug | `ed_triage`, `icu_beds_a`, `resp_ward` |
| Display room number | `display_room_id` | `{floor}F-Room{n}` | `3F-Room3` |
| Bed | `bed_id` | `{room_id}-bed-{nn}` | `icu_beds_a-bed-01` |
| Patient | `patient_id` | `P-{dept_code}-{nnn}` | `P-ICU-001` |
| Staff | `staff_id` | `{role_code}-{dept_code}-{nnn}` | `D-ICU-001`, `N-WD-001` |
| Encounter | `encounter_id` | `ENC-{dept_code}-{nnn}` or external alias | `ENC-ICU-001` |
| Event rule | `event_id` | uppercase action ID | `ED_TO_ICU_MOVE` |
| Runtime event sequence | `event_seq` | monotonically increasing integer | `12` |

Department codes used by fullview:

- `ER`: Emergency
- `OP`: Outpatient
- `LAB`: Laboratory
- `PHA`: Pharmacy
- `ICU`: ICU
- `WD`: Ward
- `MDT`: MDT Center

External departments may use their own IDs internally. They must provide an adapter mapping into these fullview IDs.

## Floor And Room Model

Canonical room record:

```json
{
  "room_id": "icu_beds_a",
  "id": "icu_beds_a",
  "display_room_id": "3F-Room3",
  "roomCode": "3F-Room3",
  "floor_id": 3,
  "department_id": "icu",
  "display_name": "ICU Beds1",
  "label": "ICU Beds1",
  "kind": "icu",
  "protected": false,
  "layout": {
    "x": 16,
    "y": 6,
    "w": 12,
    "h": 8
  },
  "capacity": {
    "beds": 4,
    "max_beds": 4,
    "queue": 0
  },
  "items": []
}
```

Compatibility aliases:

- `id` aliases `room_id`.
- `roomCode` aliases `display_room_id`.
- `label` aliases `display_name`.
- `floor` aliases `floor_id` in snapshot output.
- `capacityBeds` aliases `capacity.beds` in snapshot output.

Protected rooms cannot be deleted or renamed through the map editor. Elevators are always protected.

## Bed And Resource Model

Beds are room resources. A bed can remain assigned to a patient even when that patient is temporarily away for diagnostics or procedures.

Canonical bed record in snapshot:

```json
{
  "bed_id": "icu_beds_a-bed-01",
  "bedId": "icu_beds_a-bed-01",
  "occupied": true,
  "patient_id": "P-ICU-001",
  "patientId": "P-ICU-001",
  "patient_name": "Ethan Zhang",
  "patientName": "Ethan Zhang",
  "patient_current_room_id": "icu_beds_a",
  "patientCurrentRoomId": "icu_beds_a",
  "patient_away": false,
  "patientAway": false
}
```

Bed assignment record in `room-state.json`:

```json
{
  "bed_id": "resp_ward-bed-01",
  "bedId": "resp_ward-bed-01",
  "patient_id": "P-WD-002",
  "patientId": "P-WD-002"
}
```

Rules:

- Ward and ICU diagnostic moves retain the source bed.
- Transfers to another long-stay care area release the source bed only after a target bed is assigned.
- Discharge releases all bed assignments.
- Empty beds must still be listed in the room detail and console.

## Patient Model

Canonical patient record:

```json
{
  "patient_id": "P-ICU-001",
  "patientId": "P-ICU-001",
  "local_person_id": "icu-bed-a",
  "id": "icu-bed-a",
  "type": "patient",
  "name": "Ethan Zhang",
  "gender": "male",
  "department_id": "icu",
  "department": "ICU",
  "status": "ADMITTED",
  "current_location": {
    "room_id": "icu_beds_a"
  },
  "room_id": "icu_beds_a",
  "roomId": "icu_beds_a",
  "home_bed": {
    "room_id": "icu_beds_a",
    "bed_id": "icu_beds_a-bed-01",
    "retained": true
  },
  "bed_room_id": "icu_beds_a",
  "bedRoomId": "icu_beds_a",
  "bed_id": "icu_beds_a-bed-01",
  "bedId": "icu_beds_a-bed-01",
  "clinical": {
    "status": "ADMITTED",
    "symptoms": "Postoperative respiratory monitoring",
    "care_phase": "unstable",
    "ctas_level": null,
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

Status values:

- `ARRIVED`
- `REGISTERED`
- `TRIAGED`
- `WAITING`
- `IN_CONSULTATION`
- `IN_EXAM`
- `IN_TREATMENT`
- `ADMITTED`
- `TRANSFERRING`
- `DISCHARGED`
- `COMPLETED`
- `ERROR`

Visual forms:

- `walking`
- `waiting`
- `consultation`
- `stretcher`
- `bed`
- `hidden`

## Staff Model

Canonical staff record:

```json
{
  "staff_id": "D-ICU-001",
  "employee_id": "D-ICU-001",
  "employeeId": "D-ICU-001",
  "provider_id": "D-ICU-001",
  "local_person_id": "doctor-icu-bed-a",
  "id": "doctor-icu-bed-a",
  "type": "doctor",
  "role": "doctor",
  "name": "Dr. Helen Guo",
  "gender": "female",
  "department_id": "icu",
  "department": "ICU",
  "current_location": {
    "room_id": "icu_beds_a"
  },
  "room_id": "icu_beds_a",
  "roomId": "icu_beds_a",
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

Staff roles:

- `doctor`
- `nurse`
- `porter`
- `technician`
- `admin`
- `coordinator`

## Snapshot API

`GET /api/hospital/snapshot`

Returns:

```json
{
  "floors": [],
  "rooms": [],
  "patients": [],
  "staff": [],
  "departments": {},
  "eventSeq": 0
}
```

Canonical fields are snake_case. Compatibility aliases are included while the frontend migrates.

## Movement API

Canonical move request:

```json
{
  "request_id": "console-001",
  "source": "console",
  "operator_id": "manual-admin",
  "event_id": "ED_TO_ICU_MOVE",
  "patient_id": "P-ER-001",
  "from_room_id": "ed_red_resus",
  "to_room_id": "icu_admission",
  "context": {
    "reason": "needs ICU monitoring"
  }
}
```

Compatibility aliases accepted:

- `requestId`
- `operatorId`
- `eventId`
- `patientId`
- `fromRoomId`
- `toRoomId`

Accepted response:

```json
{
  "accepted": true,
  "event_seq": 12,
  "eventSeq": 12,
  "event_id": "ED_TO_ICU_MOVE",
  "eventId": "ED_TO_ICU_MOVE",
  "patient_id": "P-ER-001",
  "patientId": "P-ER-001",
  "status_updates": {
    "patient_status": "TRANSFERRING",
    "source_bed_retained": false,
    "target_reserved": true,
    "bed_room_id": "icu_beds_a",
    "bed_id": "icu_beds_a-bed-01"
  },
  "animation_plan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "escort_roles": ["porter", "ed_nurse"],
    "equipment": ["portable_monitor", "oxygen"],
    "from_room_id": "ed_red_resus",
    "to_room_id": "icu_admission",
    "via_room_ids": ["ed_handoff", "elevator_1", "elevator_3"],
    "final_form": "bed",
    "patient_form_during_move": "stretcher"
  }
}
```

Rejected response:

```json
{
  "accepted": false,
  "event_seq": 13,
  "eventSeq": 13,
  "event_id": "ED_TO_ICU_MOVE",
  "eventId": "ED_TO_ICU_MOVE",
  "patient_id": "P-ER-001",
  "patientId": "P-ER-001",
  "reasonCode": "NO_BED_AVAILABLE",
  "message": "Target care room has no available bed."
}
```

## Event Rules

Movement rules are the reusable authorization and animation contract.

Required fields:

```json
{
  "id": "ed-to-icu-move",
  "eventId": "ED_TO_ICU_MOVE",
  "event_id": "ED_TO_ICU_MOVE",
  "name": "急诊转 ICU",
  "classification": "patient_movement",
  "movement": {
    "from": "current_ed_bed_room",
    "to": "icu_admission",
    "via": ["ed_handoff", "elevator_1", "elevator_3"],
    "transport": "stretcher",
    "patientFormDuringMove": "stretcher",
    "finalForm": "bed",
    "escortRequired": true,
    "escortRoles": ["porter", "ed_nurse"],
    "equipment": ["portable_monitor", "oxygen"],
    "resourcePolicy": {
      "retainSourceBed": false,
      "releaseSourceBed": true
    }
  }
}
```

Rules use fullview `room_id` values. Department systems should request a move by `event_id`, `patient_id`, and target fullview `room_id`.

## Department Adapter Contract

Each department adapter should convert department-local records into fullview records.

Minimum adapter output:

```json
{
  "source": "department.icu",
  "patients": [],
  "staff": [],
  "room_updates": [],
  "events": []
}
```

Adapter responsibilities:

- Map local patient IDs to `patient_id`.
- Map local room/bed names to fullview `room_id` and `bed_id`.
- Map local staff IDs to `staff_id`.
- Map local statuses to fullview status values.
- Submit movement requests through `/api/hospital/events/move`.
- Never mutate frontend state directly.

## Migration Rule

New code must write canonical snake_case fields. Existing camelCase fields are temporary aliases and should be read-only from new department adapters.
