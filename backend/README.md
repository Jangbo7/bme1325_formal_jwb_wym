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
- `POST /api/v1/triage-sessions`
- `POST /api/v1/triage-sessions/{session_id}/messages`
- `GET /api/v1/patients`
- `GET /api/v1/patients/{patient_id}`
- `GET /api/v1/queues`
- `GET /api/v1/health`
