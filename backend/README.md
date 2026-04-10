# Backend Quickstart

## Install
```powershell
cd backend
python -m pip install -r requirements.txt
```

## Run
```powershell
python server.py
```

Backend URL:
- `http://127.0.0.1:8787`

## Main Modules
- `app/main.py`: FastAPI app wiring
- `app/api/routes/`: REST API routes
- `app/agents/triage/`: triage agent runtime
- `app/domain/patient/state_machine.py`: patient lifecycle rules
- `app/events/`: EventBus and subscribers
- `app/repositories/`: persistence layer

## Main API
- `POST /api/v1/visits`
- `GET /api/v1/visits/{visit_id}`
- `POST /api/v1/visits/{visit_id}/register`
- `POST /api/v1/visits/{visit_id}/progress`
- `POST /api/v1/visits/{visit_id}/enter-consultation`
- `POST /api/v1/triage-sessions`
- `POST /api/v1/triage-sessions/{session_id}/messages`
- `GET /api/v1/patients`
- `GET /api/v1/patients/{patient_id}`
- `GET /api/v1/queues`
- `GET /api/v1/health`

## Strict V1 Flow
- Global path: `triage -> register -> wait 10s -> called -> enter consultation`.
- Triage completion moves visit to `triaged` (no auto queue creation).
- Queue ticket is created at `register` step and moves `waiting -> called -> completed`.
- Frontend `pharmacy` room is reused as doctor entry interaction point (display label: `Doctor Entry`).


## Runtime Data Reset
- Default: `RESET_ON_SERVER_START=true`.
- Effect: each backend startup clears runtime data and reseeds default patients.
- Disable before startup:
  - PowerShell: `$env:RESET_ON_SERVER_START="false"`

