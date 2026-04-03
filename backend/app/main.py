from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.triage.graph import LANGGRAPH_AVAILABLE, TriageGraph
from app.agents.triage.service import TriageService
from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.agents.icu_doctor import create_icub_doctor_service
from app.api.routes.health import router as health_router
from app.api.routes.patients import router as patients_router
from app.api.routes.queues import router as queues_router
from app.api.routes.triage import router as triage_router
from app.api.routes.icu import router as icu_router
from app.config import get_settings
from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.events.bus import EventBus
from app.events.subscribers.audit import AuditSubscriber
from app.events.subscribers.patient_projection import PatientProjectionSubscriber
from app.events.subscribers.queue import QueueSubscriber
from app.events.types import PATIENT_STATE_CHANGED, QUEUE_TICKET_CREATED, TRIAGE_COMPLETED
from app.repositories.agent_memory import AgentMemoryRepository
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.repositories.sessions import SessionRepository


def create_container():
    settings = get_settings()
    db = Database(settings["database_url"])
    db.init_schema()
    patient_repo = PatientRepository(db)
    session_repo = SessionRepository(db)
    memory_repo = AgentMemoryRepository(db)
    queue_repo = QueueRepository(db)
    bus = EventBus()
    patient_state_machine = PatientStateMachine()
    dialogue_state_machine = TriageDialogueStateMachine()
    triage_service = TriageService(
        llm_settings={
            "endpoint": settings["llm_endpoint"],
            "model": settings["llm_model"],
            "api_key": settings["llm_api_key"],
        },
        patient_repo=patient_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        dialogue_state_machine=dialogue_state_machine,
        patient_state_machine=patient_state_machine,
        bus=bus,
        graph=None,
    )
    triage_graph = TriageGraph(triage_service, dialogue_state_machine)
    triage_service.graph = triage_graph

    queue_subscriber = QueueSubscriber(patient_repo, queue_repo, patient_state_machine, bus)
    patient_projection = PatientProjectionSubscriber(patient_repo, patient_state_machine)
    audit = AuditSubscriber(Path(__file__).resolve().parents[2])

    bus.subscribe(TRIAGE_COMPLETED, queue_subscriber.handle_triage_completed)
    bus.subscribe(PATIENT_STATE_CHANGED, patient_projection.handle_state_changed)
    bus.subscribe(TRIAGE_COMPLETED, lambda payload: audit.write(TRIAGE_COMPLETED, payload))
    bus.subscribe(PATIENT_STATE_CHANGED, lambda payload: audit.write(PATIENT_STATE_CHANGED, payload))
    bus.subscribe(QUEUE_TICKET_CREATED, lambda payload: audit.write(QUEUE_TICKET_CREATED, payload))

    icu_doctor_service = create_icub_doctor_service(
        llm_settings={
            "endpoint": settings["llm_endpoint"],
            "model": settings["llm_model"],
            "api_key": settings["llm_api_key"],
        },
        patient_repo=patient_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        patient_state_machine=patient_state_machine,
        bus=bus,
    )

    return {
        "settings": settings,
        "db": db,
        "patient_repo": patient_repo,
        "session_repo": session_repo,
        "memory_repo": memory_repo,
        "queue_repo": queue_repo,
        "event_bus": bus,
        "triage_service": triage_service,
        "icu_doctor_service": icu_doctor_service,
        "langgraph_available": LANGGRAPH_AVAILABLE,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Hospital Agent Backend", version="0.1.0")
    container = create_container()
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        if request.method != "OPTIONS" and request.url.path != "/api/v1/health":
            provided_key = (request.headers.get("X-API-Key") or "").strip()
            if not provided_key:
                auth = (request.headers.get("Authorization") or "").strip()
                if auth.lower().startswith("bearer "):
                    provided_key = auth[7:].strip()
            if provided_key != container["settings"]["mock_api_key"]:
                return JSONResponse({"detail": "invalid or missing api key"}, status_code=401)
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(triage_router)
    app.include_router(patients_router)
    app.include_router(queues_router)
    app.include_router(icu_router)
    return app


app = create_app()
