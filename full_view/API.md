# Full Hospital API

The full-view frontend treats the backend as the source of truth. The map only renders snapshots, sends event requests, and plays approved animation plans.

Canonical data shapes are defined in `HOSPITAL_CORE_STANDARD.md`. New fullview backend data and department adapters should write the snake_case core fields described there. camelCase fields remain available as compatibility aliases for the current Canvas and console UI.

## Runtime

Run:

```bash
python dev-server.py 8000
```

Open:

```text
http://localhost:8000/
http://localhost:8000/console.html
```

The lightweight backend reads and writes:

- `backend-data/patients.json`
- `backend-data/staff.json`
- `backend-data/room-state.json`
- `backend-data/event-log.json`
- `map-config.json`
- `../rules/event-rules/*.json`

## Read APIs

`GET /api/hospital/snapshot`

Returns the full hospital state:

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

`GET /api/hospital/rooms`

Returns all rooms with people and resource state.

Care-room bed occupancy is tracked by `room.bedAssignments`, not only by the patient's current visible room. A ward/ICU patient can temporarily leave for an exam while their assigned bed remains unavailable to other patients.

Each room with beds also includes a `beds` list:

```json
{
  "bedId": "resp_ward-bed-01",
  "occupied": true,
  "patientId": "P-WD-002",
  "patientName": "Grace Li",
  "patientCurrentRoomId": "diagnostic_center",
  "patientAway": true
}
```

`GET /api/hospital/people`

Returns all patients, doctors, and nurses.

`GET /api/hospital/events?after=12`

Returns event-log entries with `eventSeq > after`. The map page polls this endpoint and only animates accepted events with an `animationPlan`.

## Patient Intake API

`POST /api/hospital/patients/admit`

Creates a new entry patient. Current entry patients must enter through emergency or outpatient, then the backend immediately routes them through the corresponding triage movement rule:

- `department: "emergency"` creates the patient at `ed_registration`, then sends `ED_REGISTRATION_TO_TRIAGE_OR_WAITING`.
- `department: "outpatient"` creates the patient at `registration_2`, then sends `OP_REGISTRATION_TO_TRIAGE_OR_WAITING`.

Request:

```json
{
  "requestId": "console-intake-emergency-001",
  "source": "console-intake",
  "operatorId": "manual-admin",
  "department": "emergency",
  "context": {
    "reason": "walk-in chest tightness"
  }
}
```

Response:

```json
{
  "accepted": true,
  "patient": {
    "patientId": "P-ER-006",
    "name": "陈安然",
    "roomId": "ed_triage",
    "status": "WAITING"
  },
  "move": {
    "accepted": true,
    "eventSeq": 27,
    "eventId": "ED_REGISTRATION_TO_TRIAGE_OR_WAITING"
  }
}
```

## Move Event API

`POST /api/hospital/events/move`

Request:

```json
{
  "requestId": "req-001",
  "source": "console",
  "operatorId": "manual-admin",
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "fromRoomId": "ed_red_resus",
  "toRoomId": "icu_admission",
  "context": {
    "reason": "needs ICU monitoring"
  }
}
```

Accepted response:

```json
{
  "accepted": true,
  "eventSeq": 12,
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "statusUpdates": {
    "patientStatus": "TRANSFERRING",
    "fromRoomReleased": true,
    "sourceBedRetained": false,
    "targetReserved": true,
    "bedRoomId": "icu_beds_a",
    "bedId": "icu_beds_a-bed-01"
  },
  "animationPlan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "escortRoles": ["porter", "ed_nurse"],
    "equipment": ["portable_monitor", "oxygen", "transport_bag"],
    "fromRoomId": "ed_red_resus",
    "toRoomId": "icu_admission",
    "viaRoomIds": ["ed_handoff", "elevator_1", "elevator_3"],
    "finalForm": "bed",
    "patientFormDuringMove": "stretcher"
  }
}
```

Rejected response:

```json
{
  "accepted": false,
  "eventSeq": 13,
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "reasonCode": "TARGET_ROOM_NOT_FOUND",
  "message": "Unknown target room: not_a_room."
}
```

## Movement Rule Standard

Every reusable movement rule should include:

- `eventId`: stable event name used by departments and console.
- `rooms`: related room ids.
- `movement.from`: source room id or symbolic source such as `current_ed_room`.
- `movement.to`: target room id, room-id list, or symbolic target.
- `movement.via`: ordered intermediate room ids, especially elevators.
- `movement.transport`: `walking`, `wheelchair`, or `stretcher`.
- `movement.patientFormDuringMove`: visual form during transport.
- `movement.finalForm`: `walking`, `waiting`, `consultation`, `stretcher`, `bed`, or `hidden`.
- `movement.escortRequired`, `movement.escortRoles`, and `movement.equipment`.
- `movement.pathPolicy`, `movement.resourcePolicy`, and `movement.failurePolicy`.
- For ward/ICU exam moves, set `resourcePolicy.retainSourceBed: true` and use `stretcher` transport when the patient should keep their original bed while away.
- For discharge or transfer to another care area, set `resourcePolicy.releaseSourceBed: true` so the old bed becomes available.

The backend checks the event rule first, then updates state and event log. The frontend should not decide whether a move is legal.

## Adding a New Department or Move

1. Add rooms to `map-config.json`.
2. Add seed people or room resources under `backend-data/` if needed.
3. Add a movement rule in `../rules/event-rules/*.json`.
4. Ensure `movement.via` includes cross-floor elevator rooms.
5. Start `dev-server.py`, open `console.html`, and submit a move request.
6. Confirm the map page animates the approved event and then matches `/api/hospital/snapshot`.
