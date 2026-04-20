from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agents.internal_medicine import create_internal_medicine_service
from app.agents.icu_doctor import create_icub_doctor_service
from app.agents.triage.graph import LANGGRAPH_AVAILABLE, TriageGraph
from app.agents.triage.service import TriageService
from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.api.routes.health import router as health_router
from app.api.routes.icu import router as icu_router
from app.api.routes.internal_medicine import router as internal_medicine_router
from app.api.routes.patients import router as patients_router
from app.api.routes.queues import router as queues_router
from app.api.routes.triage import router as triage_router
from app.api.routes.visits import router as visits_router
from app.config import get_settings
from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.domain.visit.state_machine import VisitStateMachine
from app.events.bus import EventBus
from app.events.subscribers.audit import AuditSubscriber
from app.events.subscribers.patient_projection import PatientProjectionSubscriber
from app.events.types import (
    ICU_CONSULTATION_COMPLETED,
    INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
    PATIENT_STATE_CHANGED,
    QUEUE_TICKET_CALLED,
    QUEUE_TICKET_CREATED,
    TRIAGE_COMPLETED,
    VISIT_STATE_CHANGED,
)
from app.repositories.agent_memory import AgentMemoryRepository
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.repositories.sessions import SessionRepository
from app.repositories.visits import VisitRepository
from app.services import NpcPatientSimulator


def create_container():
    settings = get_settings()
    db = Database(settings["database_url"])
    db.init_schema()
    if settings["reset_on_server_start"]:
        db.reset_runtime_data()

    patient_repo = PatientRepository(db)
    session_repo = SessionRepository(db)
    memory_repo = AgentMemoryRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    bus = EventBus()
    patient_state_machine = PatientStateMachine()
    visit_state_machine = VisitStateMachine()
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
        visit_repo=visit_repo,
        dialogue_state_machine=dialogue_state_machine,
        patient_state_machine=patient_state_machine,
        visit_state_machine=visit_state_machine,
        bus=bus,
        graph=None,
    )
    triage_graph = TriageGraph(triage_service, dialogue_state_machine)
    triage_service.graph = triage_graph

    internal_medicine_service = create_internal_medicine_service(
        llm_settings={
            "endpoint": settings["llm_endpoint"],
            "model": settings["llm_model"],
            "api_key": settings["llm_api_key"],
        },
        patient_repo=patient_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        visit_repo=visit_repo,
        patient_state_machine=patient_state_machine,
        visit_state_machine=visit_state_machine,
        bus=bus,
    )

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

    npc_simulator = NpcPatientSimulator(
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        session_repo=session_repo,
        patient_state_machine=patient_state_machine,
        visit_state_machine=visit_state_machine,
        bus=bus,
        enabled=settings["simulator_enabled"],
        tick_interval_seconds=settings["simulator_tick_seconds"],
        spawn_interval_seconds=settings["simulator_spawn_interval_seconds"],
        max_active_patients=settings["simulator_max_active_patients"],
        queue_wait_seconds=settings["simulator_queue_wait_seconds"],
        consult_seconds=settings["simulator_consult_seconds"],
    )

    patient_projection = PatientProjectionSubscriber(patient_repo, patient_state_machine)
    audit = AuditSubscriber(Path(__file__).resolve().parents[2])

    bus.subscribe(PATIENT_STATE_CHANGED, patient_projection.handle_state_changed)
    bus.subscribe(TRIAGE_COMPLETED, lambda payload: audit.write(TRIAGE_COMPLETED, payload))
    bus.subscribe(ICU_CONSULTATION_COMPLETED, lambda payload: audit.write(ICU_CONSULTATION_COMPLETED, payload))
    bus.subscribe(INTERNAL_MEDICINE_CONSULTATION_COMPLETED, lambda payload: audit.write(INTERNAL_MEDICINE_CONSULTATION_COMPLETED, payload))
    bus.subscribe(PATIENT_STATE_CHANGED, lambda payload: audit.write(PATIENT_STATE_CHANGED, payload))
    bus.subscribe(VISIT_STATE_CHANGED, lambda payload: audit.write(VISIT_STATE_CHANGED, payload))
    bus.subscribe(QUEUE_TICKET_CREATED, lambda payload: audit.write(QUEUE_TICKET_CREATED, payload))
    bus.subscribe(QUEUE_TICKET_CALLED, lambda payload: audit.write(QUEUE_TICKET_CALLED, payload))

    return {
        "settings": settings,
        "db": db,
        "patient_repo": patient_repo,
        "session_repo": session_repo,
        "memory_repo": memory_repo,
        "queue_repo": queue_repo,
        "visit_repo": visit_repo,
        "event_bus": bus,
        "triage_service": triage_service,
        "internal_medicine_service": internal_medicine_service,
        "icu_doctor_service": icu_doctor_service,
        "npc_simulator": npc_simulator,
        "visit_state_machine": visit_state_machine,
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

    @app.on_event("startup")
    async def start_npc_simulator():
        container["npc_simulator"].start()

    @app.on_event("shutdown")
    async def stop_npc_simulator():
        container["npc_simulator"].stop()

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        # Disable frontend-to-backend API key verification in local dev.
        # Backend model access still uses llm_api_key from backend/.env.
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(visits_router)
    app.include_router(triage_router)
    app.include_router(internal_medicine_router)
    app.include_router(icu_router)
    app.include_router(patients_router)
    app.include_router(queues_router)
    return app


app = create_app()
