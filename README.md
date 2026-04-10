# Hospital Agent Simulation

## Overview
This project is a hospital workflow simulation with a modular backend and a browser-based scene frontend.

Current Phase 1 baseline:
- FastAPI provides the backend API.
- LangGraph/LangChain are available for agent orchestration.
- Patient lifecycle and triage dialogue use explicit state machines.
- EventBus handles side effects such as queue creation after triage completion.
- Patient, session, memory, and queue data are persisted locally.
- The frontend remains plain JavaScript, but agent, queue, NPC, and UI logic are being split into modules.

## Structure
- `backend/app/api/`: API routes
- `backend/app/agents/triage/`: triage agent graph, state, prompts, rules, service
- `backend/app/domain/patient/`: patient lifecycle state machine
- `backend/app/events/`: EventBus and subscribers
- `backend/app/repositories/`: persistence layer
- `scene/`: browser scene and interaction modules
- `docs/AGENT_DEVELOPMENT_README.md`: how collaborators should add a new agent

## Backend Startup
```powershell
cd backend
python -m pip install -r requirements.txt
python server.py
```

Backend default URL:
- `http://127.0.0.1:8787`

## Frontend Startup
```powershell
cd scene
python -m http.server 5500
```

Frontend URL:
- `http://127.0.0.1:5500`

## Current Flow
1. Player opens the triage form.
2. Frontend creates a triage session through `/api/v1/triage-sessions`.
3. Triage agent evaluates the case and may ask follow-up questions.
4. Triage completion triggers queue creation through EventBus subscribers.
5. Frontend shows queue and dialogue updates.


## Runtime Data Reset
- Default behavior: every backend restart clears runtime tables (visits, triage sessions, dialogue turns, queue tickets, memories) and then reseeds default patients.
- Disable this behavior before starting backend:
  - PowerShell: `$env:RESET_ON_SERVER_START="false"`

