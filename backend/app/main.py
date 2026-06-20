import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from app.agents.internal_medicine import create_internal_medicine_service
from app.agents.surgery import create_surgery_service
from app.agents.interactive_debug import (
    DoctorAgentDebugController,
    FixedDoctorDebugController,
    PatientAgentChatDebugController,
    TriageAgentDebugController,
    build_default_doctor_debug_registry,
)
from app.agents.multi_patient_debug import MultiPatientDebugController
from app.agents.patient_agent import PatientAgentDebugController
from app.agents.npc_patient import NpcPatientDebugController
from app.agents.icu_doctor import create_icub_doctor_service
from app.agents.triage.graph import LANGGRAPH_AVAILABLE, TriageGraph
from app.agents.triage.service import TriageService
from app.agents.triage.state_machine import TriageDialogueStateMachine
from app.api.routes.doctor_agent_debug import router as doctor_agent_debug_router
from app.api.routes.health import router as health_router
from app.api.routes.hospital_runtime_debug import router as hospital_runtime_debug_router
from app.api.routes.department_runtime_debug import router as department_runtime_debug_router
from app.api.routes.encounters import router as encounters_router
from app.api.routes.departments import router as departments_router
from app.api.routes.events import router as events_router
from app.api.routes.fullview_sync import router as fullview_sync_router
from app.api.routes.icu import router as icu_router
from app.api.routes.internal_medicine_agent_debug import router as internal_medicine_agent_debug_router
from app.api.routes.internal_medicine import router as internal_medicine_router
from app.api.routes.medical_records import router as medical_records_router
from app.api.routes.multi_patient_debug import router as multi_patient_debug_router
from app.api.routes.npc_debug import router as npc_debug_router
from app.api.routes.patient_agent_chat_debug import router as patient_agent_chat_debug_router
from app.api.routes.patient_agent_debug import router as patient_agent_debug_router
from app.api.routes.openemr import router as openemr_router
from app.api.routes.patients import router as patients_router
from app.api.routes.queues import router as queues_router
from app.api.routes.runtime_console import router as runtime_console_router
from app.api.routes.scene_snapshot import router as scene_snapshot_router
from app.api.routes.runtime_stats_html import router as runtime_stats_html_router
from app.api.routes.surgery import router as surgery_router
from app.api.routes.triage_agent_debug import router as triage_agent_debug_router
from app.api.routes.triage import router as triage_router
from app.api.routes.visits import router as visits_router
from app.api.contract import (
    ContractError,
    error_envelope,
    fetch_idempotency_record,
    map_exception,
    new_trace_id,
    normalize_success_payload,
    request_fingerprint,
    should_require_idempotency,
    success_envelope,
    upsert_idempotency_record,
)
from app.config import get_settings
from app.database import Database
from app.domain.patient.state_machine import PatientStateMachine
from app.domain.visit.state_machine import VisitStateMachine
from app.events.bus import EventBus
from app.events.bridge import HospitalEventBridge, RedisMirrorPublisher
from app.events.subscribers.audit import AuditSubscriber
from app.events.subscribers.department_runtime import DepartmentRuntimeProjector
from app.events.subscribers.openemr_sync import OpenEMRSyncSubscriber
from app.events.subscribers.patient_projection import PatientProjectionSubscriber
from app.events.types import (
    ENCOUNTER_OPENED,
    ICU_CONSULTATION_COMPLETED,
    INTERNAL_MEDICINE_CONSULTATION_COMPLETED,
    PATIENT_STATE_CHANGED,
    QUEUE_TICKET_COMPLETED,
    QUEUE_TICKET_CALLED,
    QUEUE_TICKET_CREATED,
    TEST_REPORT_GENERATED,
    TEST_ZONE_ASSIGNED,
    TRIAGE_COMPLETED,
    VISIT_STATE_CHANGED,
)
from app.repositories.agent_memory import AgentMemoryRepository
from app.repositories.department_runtime import DepartmentRuntimeRepository
from app.repositories.fullview_sync import FullviewSyncRepository
from app.repositories.medical_records import MedicalRecordRepository
from app.repositories.patient_agent_cases import PatientAgentCaseRepository
from app.repositories.patients import PatientRepository
from app.repositories.queues import QueueRepository
from app.repositories.runtime_console import RuntimeConsoleRepository
from app.repositories.sessions import SessionRepository
from app.repositories.visits import VisitRepository
from app.repositories.runtime_stage_samples import RuntimeStageSampleRepository
from app.integrations.openemr import EMRService, OpenEMRClient
from app.integrations.fullview import FullviewClient
from app.services import (
    DepartmentRuntimeService,
    EncounterOrchestrationService,
    FullviewMappingService,
    FullviewEventListener,
    FullviewSyncSubscriber,
    FullviewSyncWorker,
    NpcPatientSimulator,
    OutpatientProcedureService,
    PatientAgentService,
    RuntimeConsoleService,
    SceneSnapshotService,
)
from app.services.hospital_supervisor import HospitalSupervisor
from app.services.patient_flow_engine import FlowDecisionEngine, FlowExecutor


def create_container():
    settings = get_settings()
    db = Database(settings["database_url"])
    db.init_schema()

    patient_repo = PatientRepository(db)
    session_repo = SessionRepository(db)
    runtime_stage_sample_repo = RuntimeStageSampleRepository(db)
    memory_repo = AgentMemoryRepository(db)
    medical_record_repo = MedicalRecordRepository(db)
    patient_agent_case_repo = PatientAgentCaseRepository(db)
    department_runtime_repo = DepartmentRuntimeRepository(db)
    fullview_sync_repo = FullviewSyncRepository(db)
    fullview_sync_repo.set_visual_cooldown_enabled(
        settings["fullview_sync_enabled"]
        and settings["fullview_step_gate_enabled"]
    )
    fullview_sync_repo.set_admission_gap_seconds(
        settings["fullview_admission_gap_seconds"]
    )
    runtime_console_repo = RuntimeConsoleRepository(db)
    queue_repo = QueueRepository(db)
    visit_repo = VisitRepository(db)
    bus = EventBus()
    redis_mirror_publisher = RedisMirrorPublisher(
        enabled=settings["redis_mirror_enabled"],
        host=settings["hospital_redis_host"],
        port=settings["hospital_redis_port"],
        db=settings["hospital_redis_db"],
        password=settings["hospital_redis_password"],
        channel_prefix=settings["hospital_redis_channel_prefix"],
        durable_stream_enabled=settings["hospital_redis_durable_stream_enabled"],
        durable_stream_key=settings["hospital_redis_durable_stream_key"],
    )
    event_bridge = HospitalEventBridge(
        producer=settings["event_producer"],
        redis_publisher=redis_mirror_publisher,
    )
    bus.tap(event_bridge.handle_internal_event)
    patient_state_machine = PatientStateMachine()
    visit_state_machine = VisitStateMachine()
    encounter_orchestration_service = EncounterOrchestrationService(
        visit_repo=visit_repo,
        patient_repo=patient_repo,
        bus=bus,
    )
    outpatient_procedure_service = OutpatientProcedureService(
        visit_repo=visit_repo,
        visit_state_machine=visit_state_machine,
        encounter_orchestration_service=encounter_orchestration_service,
        bus=bus,
    )
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
        medical_record_repo=medical_record_repo,
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
        encounter_orchestration_service=encounter_orchestration_service,
        medical_record_repo=medical_record_repo,
    )
    surgery_service = create_surgery_service(
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
        encounter_orchestration_service=encounter_orchestration_service,
        medical_record_repo=medical_record_repo,
        outpatient_procedure_service=outpatient_procedure_service,
    )
    triage_service.configure_consultation_services(
        {
            "internal_medicine": internal_medicine_service,
            "surgery": surgery_service,
        }
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
    npc_patient_debug_controller = NpcPatientDebugController(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "queue_repo": queue_repo,
            "visit_repo": visit_repo,
            "triage_service": triage_service,
            "internal_medicine_service": internal_medicine_service,
            "surgery_service": surgery_service,
            "encounter_orchestration_service": encounter_orchestration_service,
            "event_bus": bus,
            "medical_record_repo": medical_record_repo,
        }
    )
    patient_agent_service = PatientAgentService(
        llm_settings={
            "endpoint": settings["llm_endpoint"],
            "model": settings["llm_model"],
            "api_key": settings["llm_api_key"],
        },
        case_repo=patient_agent_case_repo,
        session_repo=session_repo,
        medical_record_repo=medical_record_repo,
    )
    department_runtime_service = DepartmentRuntimeService(
        runtime_repo=department_runtime_repo,
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        queue_repo=queue_repo,
        agent_memory_repo=memory_repo,
    )
    fullview_client = FullviewClient(
        base_url=settings["fullview_base_url"],
        timeout_seconds=settings["fullview_timeout_seconds"],
    )
    fullview_mapping_service = FullviewMappingService(
        visit_repo=visit_repo,
        patient_repo=patient_repo,
        department_runtime_repo=department_runtime_repo,
        sync_repo=fullview_sync_repo,
        discharge_linger_seconds=settings["fullview_discharge_linger_seconds"],
    )
    fullview_sync_worker = FullviewSyncWorker(
        repo=fullview_sync_repo,
        client=fullview_client,
        enabled=settings["fullview_sync_enabled"],
        poll_interval_seconds=settings["fullview_poll_interval_seconds"],
        max_attempts=settings["fullview_max_attempts"],
        visual_cooldown_multiplier=settings[
            "fullview_visual_cooldown_multiplier"
        ],
        admission_gap_seconds=settings["fullview_admission_gap_seconds"],
    )
    fullview_event_listener = FullviewEventListener(
        repo=fullview_sync_repo,
        client=fullview_client,
        enabled=settings["fullview_sync_enabled"],
        interval_seconds=settings["fullview_event_listener_interval_seconds"],
        observe_timeout_seconds=settings["fullview_event_observe_timeout_seconds"],
        cleanup_idle_seconds=settings["fullview_cleanup_idle_seconds"],
        worker=fullview_sync_worker,
    )
    fullview_sync_subscriber = FullviewSyncSubscriber(
        fullview_mapping_service,
        fullview_sync_worker,
    )
    runtime_console_service = RuntimeConsoleService(
        repo=runtime_console_repo,
        department_runtime_service=department_runtime_service,
        fullview_client=fullview_client,
        fullview_sync_repo=fullview_sync_repo,
        fullview_event_listener=fullview_event_listener,
        fullview_sync_enabled=settings["fullview_sync_enabled"],
        fullview_step_gate_enabled=settings["fullview_step_gate_enabled"],
    )
    scene_snapshot_service = SceneSnapshotService(
        patient_repo=patient_repo,
        queue_repo=queue_repo,
        visit_repo=visit_repo,
        triage_service=triage_service,
        medical_record_repo=medical_record_repo,
    )
    patient_agent_debug_controller = PatientAgentDebugController(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "memory_repo": memory_repo,
            "queue_repo": queue_repo,
            "visit_repo": visit_repo,
            "triage_service": triage_service,
            "internal_medicine_service": internal_medicine_service,
            "surgery_service": surgery_service,
            "encounter_orchestration_service": encounter_orchestration_service,
            "event_bus": bus,
            "medical_record_repo": medical_record_repo,
            "patient_agent_service": patient_agent_service,
            "patient_agent_case_repo": patient_agent_case_repo,
            "department_runtime_service": department_runtime_service,
        }
    )
    doctor_debug_registry = build_default_doctor_debug_registry()
    doctor_agent_debug_controller = DoctorAgentDebugController(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "memory_repo": memory_repo,
            "visit_repo": visit_repo,
            "medical_record_repo": medical_record_repo,
            "internal_medicine_service": internal_medicine_service,
            "surgery_service": surgery_service,
        },
        registry=doctor_debug_registry,
    )
    triage_agent_debug_controller = TriageAgentDebugController(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "memory_repo": memory_repo,
            "visit_repo": visit_repo,
            "medical_record_repo": medical_record_repo,
            "triage_service": triage_service,
        }
    )
    internal_medicine_agent_debug_controller = FixedDoctorDebugController(
        doctor_agent_debug_controller,
        "internal_medicine",
    )
    patient_agent_chat_debug_controller = PatientAgentChatDebugController(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "memory_repo": memory_repo,
            "visit_repo": visit_repo,
            "medical_record_repo": medical_record_repo,
            "patient_agent_service": patient_agent_service,
            "patient_agent_case_repo": patient_agent_case_repo,
        }
    )
    flow_decision_engine = FlowDecisionEngine()
    flow_executor = FlowExecutor()
    hospital_supervisor = HospitalSupervisor(
        {
            "patient_repo": patient_repo,
            "session_repo": session_repo,
            "memory_repo": memory_repo,
            "queue_repo": queue_repo,
            "visit_repo": visit_repo,
            "triage_service": triage_service,
            "internal_medicine_service": internal_medicine_service,
            "surgery_service": surgery_service,
            "encounter_orchestration_service": encounter_orchestration_service,
            "event_bus": bus,
            "medical_record_repo": medical_record_repo,
            "patient_agent_service": patient_agent_service,
            "patient_agent_case_repo": patient_agent_case_repo,
            "department_runtime_service": department_runtime_service,
            "runtime_console_service": runtime_console_service,
            "fullview_sync_repo": fullview_sync_repo,
            "fullview_sync_enabled": settings["fullview_sync_enabled"],
            "fullview_step_gate_enabled": (
                settings["fullview_sync_enabled"]
                and settings["fullview_step_gate_enabled"]
            ),
            "flow_decision_engine": flow_decision_engine,
            "flow_executor": flow_executor,
        }
    )
    multi_patient_debug_controller = hospital_supervisor

    patient_projection = PatientProjectionSubscriber(patient_repo, patient_state_machine)
    department_runtime_projector = DepartmentRuntimeProjector(department_runtime_service)
    audit = AuditSubscriber(Path(__file__).resolve().parents[2])
    openemr_client = OpenEMRClient(
        enabled=settings["openemr_enabled"],
        dry_run=settings["openemr_dry_run"],
        base_url=settings["openemr_base_url"],
        api_base_path=settings["openemr_api_base_path"],
        timeout_seconds=settings["openemr_timeout_seconds"],
        verify_ssl=settings["openemr_verify_ssl"],
        client_id=settings["openemr_client_id"],
        client_secret=settings["openemr_client_secret"],
        oauth_enabled=settings["openemr_oauth_enabled"],
        oauth_discovery_url=settings["openemr_oauth_discovery_url"],
        oauth_token_url=settings["openemr_oauth_token_url"],
        oauth_scope=settings["openemr_oauth_scope"],
        oauth_audience=settings["openemr_oauth_audience"],
        oauth_use_basic_fallback=settings["openemr_oauth_use_basic_fallback"],
        username=settings["openemr_username"],
        password=settings["openemr_password"],
        outbound_log_path=settings["openemr_outbound_log_path"],
    )
    emr_service = EMRService(
        client=openemr_client,
        patient_repo=patient_repo,
        visit_repo=visit_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        prepared_log_path=settings["openemr_prepared_log_path"],
    )
    openemr_sync_subscriber = OpenEMRSyncSubscriber(
        emr_service=emr_service,
        visit_repo=visit_repo,
        session_repo=session_repo,
    )

    bus.subscribe(PATIENT_STATE_CHANGED, patient_projection.handle_state_changed)
    bus.subscribe(TRIAGE_COMPLETED, lambda payload: audit.write(TRIAGE_COMPLETED, payload))
    bus.subscribe(ICU_CONSULTATION_COMPLETED, lambda payload: audit.write(ICU_CONSULTATION_COMPLETED, payload))
    bus.subscribe(INTERNAL_MEDICINE_CONSULTATION_COMPLETED, lambda payload: audit.write(INTERNAL_MEDICINE_CONSULTATION_COMPLETED, payload))
    bus.subscribe(PATIENT_STATE_CHANGED, lambda payload: audit.write(PATIENT_STATE_CHANGED, payload))
    bus.subscribe(VISIT_STATE_CHANGED, lambda payload: audit.write(VISIT_STATE_CHANGED, payload))
    bus.subscribe(QUEUE_TICKET_CREATED, lambda payload: audit.write(QUEUE_TICKET_CREATED, payload))
    bus.subscribe(QUEUE_TICKET_CALLED, lambda payload: audit.write(QUEUE_TICKET_CALLED, payload))
    bus.subscribe(QUEUE_TICKET_COMPLETED, lambda payload: audit.write(QUEUE_TICKET_COMPLETED, payload))
    bus.subscribe(TEST_ZONE_ASSIGNED, lambda payload: audit.write(TEST_ZONE_ASSIGNED, payload))
    bus.subscribe(TEST_REPORT_GENERATED, lambda payload: audit.write(TEST_REPORT_GENERATED, payload))
    bus.subscribe(TRIAGE_COMPLETED, department_runtime_projector.handle_triage_completed)
    bus.subscribe(PATIENT_STATE_CHANGED, department_runtime_projector.handle_patient_state_changed)
    bus.subscribe(VISIT_STATE_CHANGED, department_runtime_projector.handle_visit_state_changed)
    bus.subscribe(ENCOUNTER_OPENED, fullview_sync_subscriber.handle_encounter_opened)
    bus.subscribe(VISIT_STATE_CHANGED, fullview_sync_subscriber.handle_visit_state_changed)
    bus.subscribe(QUEUE_TICKET_CREATED, department_runtime_projector.handle_queue_ticket_created)
    bus.subscribe(QUEUE_TICKET_CALLED, department_runtime_projector.handle_queue_ticket_called)
    bus.subscribe(QUEUE_TICKET_COMPLETED, department_runtime_projector.handle_queue_ticket_completed)
    bus.subscribe(TRIAGE_COMPLETED, openemr_sync_subscriber.handle_triage_completed)
    bus.subscribe(INTERNAL_MEDICINE_CONSULTATION_COMPLETED, openemr_sync_subscriber.handle_internal_medicine_completed)
    bus.subscribe(TEST_REPORT_GENERATED, openemr_sync_subscriber.handle_test_report_generated)
    bus.subscribe(VISIT_STATE_CHANGED, openemr_sync_subscriber.handle_visit_state_changed)

    return {
        "settings": settings,
        "db": db,
        "patient_repo": patient_repo,
        "session_repo": session_repo,
        "memory_repo": memory_repo,
        "medical_record_repo": medical_record_repo,
        "patient_agent_case_repo": patient_agent_case_repo,
        "department_runtime_repo": department_runtime_repo,
        "fullview_sync_repo": fullview_sync_repo,
        "runtime_console_repo": runtime_console_repo,
        "queue_repo": queue_repo,
        "visit_repo": visit_repo,
        "encounter_orchestration_service": encounter_orchestration_service,
        "event_bus": bus,
        "event_bridge": event_bridge,
        "openemr_client": openemr_client,
        "emr_service": emr_service,
        "triage_service": triage_service,
        "internal_medicine_service": internal_medicine_service,
        "surgery_service": surgery_service,
        "icu_doctor_service": icu_doctor_service,
        "npc_simulator": npc_simulator,
        "npc_patient_debug_controller": npc_patient_debug_controller,
        "patient_agent_service": patient_agent_service,
        "department_runtime_service": department_runtime_service,

        "fullview_mapping_service": fullview_mapping_service,
        "fullview_sync_worker": fullview_sync_worker,
        "fullview_event_listener": fullview_event_listener,
        "runtime_console_service": runtime_console_service,

        "outpatient_procedure_service": outpatient_procedure_service,
        "scene_snapshot_service": scene_snapshot_service,
        "patient_agent_debug_controller": patient_agent_debug_controller,
        "doctor_debug_registry": doctor_debug_registry,
        "doctor_agent_debug_controller": doctor_agent_debug_controller,
        "triage_agent_debug_controller": triage_agent_debug_controller,
        "internal_medicine_agent_debug_controller": internal_medicine_agent_debug_controller,
        "patient_agent_chat_debug_controller": patient_agent_chat_debug_controller,
        "hospital_supervisor": hospital_supervisor,
        "multi_patient_debug_controller": multi_patient_debug_controller,
        "flow_decision_engine": flow_decision_engine,
        "flow_executor": flow_executor,
        "visit_state_machine": visit_state_machine,
        "langgraph_available": LANGGRAPH_AVAILABLE,
    }


def create_app() -> FastAPI:
    container = create_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container
        startup_cleanup_task = None
        if container["settings"]["reset_on_server_start"]:
            startup_cleanup_task = asyncio.create_task(
                asyncio.to_thread(
                    container["runtime_console_service"].cleanup_runtime_patients,
                    None,
                    reset_local=True,
                )
            )
            app.state.startup_cleanup_task = startup_cleanup_task
        container["fullview_event_listener"].start()
        container["npc_simulator"].start()
        container["fullview_sync_worker"].start()
        try:
            yield
        finally:
            container["fullview_sync_worker"].stop()
            container["fullview_event_listener"].stop()
            container["npc_simulator"].stop()
            container["multi_patient_debug_controller"].shutdown()
            if startup_cleanup_task is not None and not startup_cleanup_task.done():
                startup_cleanup_task.cancel()

    app = FastAPI(title="Hospital Agent Backend", version="0.1.0", lifespan=lifespan)
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
        # Disable frontend-to-backend API key verification in local dev.
        # Backend model access still uses llm_api_key from backend/.env.
        return await call_next(request)

    @app.middleware("http")
    async def contract_middleware(request: Request, call_next):
        trace_id = new_trace_id()
        request.state.trace_id = trace_id
        request.scope["trace_id"] = trace_id

        method = request.method.upper()
        path = request.url.path
        idempotency_enabled = should_require_idempotency(method, path)
        idempotency_key = None
        request_hash = None
        db = request.app.state.container["db"]

        if idempotency_enabled:
            idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
            if not idempotency_key:
                return JSONResponse(
                    status_code=400,
                    content=error_envelope(
                        code="IDEMPOTENCY_KEY_REQUIRED",
                        trace_id=trace_id,
                        details={"header": "Idempotency-Key"},
                    ),
                )

            body = await request.body()

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request = Request(request.scope, receive)
            request.state.trace_id = trace_id
            request_hash = request_fingerprint(
                method=method,
                path=path,
                query=request.url.query,
                body=body,
            )
            record = fetch_idempotency_record(
                db,
                key=idempotency_key,
                method=method,
                path=path,
            )
            if record:
                if record["request_hash"] != request_hash:
                    return JSONResponse(
                        status_code=409,
                        content=error_envelope(
                            code="IDEMPOTENCY_KEY_REUSED",
                            trace_id=trace_id,
                            details={"method": method, "path": path},
                        ),
                    )
                replay_body = json.loads(record["response_body"])
                headers = {"X-Idempotent-Replay": "true", "X-Trace-Id": trace_id}
                return JSONResponse(status_code=int(record["response_status"]), content=replay_body, headers=headers)

        response = await call_next(request)

        content_type = (response.headers.get("content-type") or "").lower()
        is_sse = "text/event-stream" in content_type
        payload_dict = None
        response_bytes: bytes | None = None
        if path.startswith("/api/v1/") and not is_sse and "application/json" in content_type:
            if hasattr(response, "body_iterator"):
                chunks: list[bytes] = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                response_bytes = b"".join(chunks)
            else:
                response_bytes = getattr(response, "body", None)
            if response_bytes:
                try:
                    payload = json.loads(response_bytes.decode("utf-8"))
                    if isinstance(payload, dict) and {"ok", "data", "error", "trace_id"}.issubset(payload.keys()):
                        payload_dict = payload
                        if not payload_dict.get("trace_id"):
                            payload_dict["trace_id"] = trace_id
                    elif response.status_code < 400:
                        payload_dict = success_envelope(normalize_success_payload(payload), trace_id)
                except Exception:
                    payload_dict = None

        if payload_dict is not None:
            preserved_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() not in {"content-length", "content-type"}
            }
            preserved_headers["X-Trace-Id"] = trace_id
            response = JSONResponse(
                status_code=response.status_code,
                content=payload_dict,
                headers=preserved_headers,
            )
        elif response_bytes is not None:
            preserved_headers = {
                key: value
                for key, value in response.headers.items()
                if key.lower() != "content-length"
            }
            response = Response(
                content=response_bytes,
                status_code=response.status_code,
                headers=preserved_headers,
                media_type=response.media_type,
            )

        if (
            idempotency_enabled
            and idempotency_key
            and request_hash
            and response.status_code < 500
            and payload_dict is not None
        ):
            upsert_idempotency_record(
                db,
                key=idempotency_key,
                method=method,
                path=path,
                request_hash=request_hash,
                response_status=response.status_code,
                response_body=payload_dict,
            )

        return response

    @app.exception_handler(ContractError)
    async def contract_error_handler(request: Request, exc: ContractError):
        code, message, details, status_code = map_exception(exc)
        trace_id = getattr(request.state, "trace_id", new_trace_id())
        return JSONResponse(
            status_code=status_code,
            content=error_envelope(code=code, trace_id=trace_id, message=message, details=details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        trace_id = getattr(request.state, "trace_id", new_trace_id())
        return JSONResponse(
            status_code=422,
            content=error_envelope(
                code="VALIDATION_ERROR",
                trace_id=trace_id,
                message="request validation failed",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        code, message, details, status_code = map_exception(exc)
        trace_id = getattr(request.state, "trace_id", new_trace_id())
        return JSONResponse(
            status_code=status_code,
            content=error_envelope(code=code, trace_id=trace_id, message=message, details=details),
        )

    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        code, message, details, status_code = map_exception(exc)
        trace_id = getattr(request.state, "trace_id", new_trace_id())
        return JSONResponse(
            status_code=status_code,
            content=error_envelope(code=code, trace_id=trace_id, message=message, details=details),
        )

    app.include_router(health_router)
    app.include_router(hospital_runtime_debug_router)
    app.include_router(department_runtime_debug_router)
    app.include_router(runtime_console_router)
    app.include_router(departments_router)
    app.include_router(encounters_router)
    app.include_router(events_router)
    app.include_router(fullview_sync_router)
    app.include_router(scene_snapshot_router)
    app.include_router(runtime_stats_html_router)
    app.include_router(visits_router)
    app.include_router(triage_router)
    app.include_router(internal_medicine_router)
    app.include_router(surgery_router)
    app.include_router(doctor_agent_debug_router)
    app.include_router(medical_records_router)
    app.include_router(npc_debug_router)
    app.include_router(patient_agent_debug_router)
    app.include_router(triage_agent_debug_router)
    app.include_router(internal_medicine_agent_debug_router)
    app.include_router(patient_agent_chat_debug_router)
    app.include_router(multi_patient_debug_router)
    app.include_router(icu_router)
    app.include_router(patients_router)
    app.include_router(queues_router)
    app.include_router(openemr_router)
    return app


app = create_app()
