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

## Runtime Console
- Page: `http://127.0.0.1:8787/runtime-console`
- The runtime console is the formal backend control surface for:
  - active patient cap
  - active intelligent/scripted patient ratio
  - independent intelligent/scripted spawn and step clocks
  - persisted runtime sessions and runtime events
  - issue, patient, and department runtime monitoring
- Legacy debug pages remain available for compatibility, but operational control should prefer `runtime-console`.

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
- `GET /api/v1/runtime-console/snapshot`
- `POST /api/v1/runtime-console/session/start`
- `POST /api/v1/runtime-console/session/command`
- `POST /api/v1/runtime-console/config/global`
- `POST /api/v1/runtime-console/config/departments`
- `GET /api/v1/runtime-console/events`
- `GET /api/v1/runtime-console/patients`
- `GET /api/v1/runtime-console/departments`
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
# Fullview synchronization

The outpatient backend can push state-driven movement requests to Fullview Core
without changing the Fullview browser renderer:

```env
FULLVIEW_SYNC_ENABLED=true
FULLVIEW_BASE_URL=http://127.0.0.1:8000
FULLVIEW_TIMEOUT_SECONDS=5
FULLVIEW_POLL_INTERVAL_SECONDS=0.5
FULLVIEW_MAX_ATTEMPTS=8
FULLVIEW_STEP_GATE_ENABLED=false
FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER=2.0
FULLVIEW_DISCHARGE_LINGER_SECONDS=30
RESET_ON_SERVER_START=false
```

`FULLVIEW_STEP_GATE_ENABLED` is the initial Runtime Console value. The same
switch is available under Global Control and can be changed with **Apply
Config**. When enabled, each patient waits for its earlier Fullview commands to
reach `accepted`, then observes an event-specific visual cooldown before taking
another backend step. The Fullview outbox also delays the next movement for the
same encounter, including commands created in one batch. Other patients
continue running. The cooldown approximates browser animation duration; it is
not a browser acknowledgement. `FULLVIEW_VISUAL_COOLDOWN_MULTIPLIER` applies a
conservative multiplier to those waits. Completed patients remain visible for
`FULLVIEW_DISCHARGE_LINGER_SECONDS` before the discharge request is delivered.

With `RESET_ON_SERVER_START=true`, a successful backend restart starts with an
empty local runtime database. Fullview cleanup for previously spawned runtime
patients runs in the background, so it does not delay availability of port
`8787`. Keep the default `false` when local patients and pending Fullview outbox
commands must survive a backend restart. Fullview remains authoritative for
rooms, resources, rules, event logs, and animation plans.
