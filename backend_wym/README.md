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

## LLM Provider Switching
The backend supports two startup-time LLM provider profiles and resolves one active profile into the existing unified `llm_settings` used by all agents.

- `ACTIVE_LLM_PROVIDER=current`
  - Uses `CURRENT_LLM_ENDPOINT`, `CURRENT_LLM_MODEL`, `CURRENT_LLM_API_KEY`
  - If `CURRENT_*` is not set, falls back to legacy `LLM_ENDPOINT`, `LLM_MODEL`, `LLM_API_KEY`
- `ACTIVE_LLM_PROVIDER=aliyun_dashscope`
  - Uses `ALIYUN_LLM_ENDPOINT`, `ALIYUN_LLM_MODEL`, `DASHSCOPE_API_KEY`
  - Default Aliyun endpoint is `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`
  - Default Aliyun model is `deepseek-v4-flash`

Notes:
- The switch happens at backend startup. There is no runtime API toggle in this version.
- Do not commit real API keys. Put them only in `backend/.env` or your system environment.
- `/api/v1/health` reports the active provider, endpoint, model, and whether an LLM key is currently enabled.

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
