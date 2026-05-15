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
- `app/agents/internal_medicine/`: outpatient internal medicine agent
- `app/agents/icu_doctor/`: ICU consultation agent
- `app/agents/test_simulator/`: auxiliary test simulation service
- `app/domain/patient/state_machine.py`: patient lifecycle rules
- `app/domain/visit/state_machine.py`: visit lifecycle rules
- `app/events/`: EventBus and subscribers
- `app/repositories/`: persistence layer
- `app/services/npc_simulator.py`: background simulated patient loop

## Main API
- `POST /api/v1/visits`
- `GET /api/v1/visits/{visit_id}`
- `POST /api/v1/visits/{visit_id}/register`
- `POST /api/v1/visits/{visit_id}/progress`
- `POST /api/v1/visits/{visit_id}/enter-consultation`
- `POST /api/v1/visits/{visit_id}/ready-payment`
- `POST /api/v1/triage-sessions`
- `POST /api/v1/triage-sessions/{session_id}/messages`
- `GET /api/v1/triage-sessions/{session_id}`
- `POST /api/v1/internal-medicine-sessions`
- `POST /api/v1/internal-medicine-sessions/{session_id}/messages`
- `GET /api/v1/internal-medicine-sessions/{session_id}`
- `POST /api/v1/icu-sessions`
- `POST /api/v1/icu-sessions/{session_id}/messages`
- `GET /api/v1/icu-sessions/{session_id}`
- `GET /api/v1/icu-patients`
- `GET /api/v1/patients`
- `GET /api/v1/patients/{patient_id}`
- `GET /api/v1/queues`
- `GET /api/v1/health`
