"""Surgery Agent package."""

from app.agents.surgery.config import build_surgery_runtime_config
from app.agents.surgery.graph import SurgeryGraph
from app.agents.surgery.service import SurgeryService
from app.agents.surgery.state_machine import SurgeryDialogueStateMachine


def create_surgery_service(
    llm_settings: dict,
    patient_repo,
    session_repo,
    memory_repo,
    queue_repo,
    visit_repo,
    patient_state_machine,
    visit_state_machine,
    bus,
    encounter_orchestration_service=None,
    medical_record_repo=None,
    outpatient_procedure_service=None,
):
    config = build_surgery_runtime_config()
    dialogue_state_machine = SurgeryDialogueStateMachine()
    graph = SurgeryGraph(service=None, dialogue_state_machine=dialogue_state_machine, config=config)
    service = SurgeryService(
        config=config,
        llm_settings=llm_settings,
        patient_repo=patient_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        visit_repo=visit_repo,
        dialogue_state_machine=dialogue_state_machine,
        patient_state_machine=patient_state_machine,
        visit_state_machine=visit_state_machine,
        bus=bus,
        graph=graph,
        encounter_orchestration_service=encounter_orchestration_service,
        medical_record_repo=medical_record_repo,
        outpatient_procedure_service=outpatient_procedure_service,
    )
    graph.service = service
    return service
