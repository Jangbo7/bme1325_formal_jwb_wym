"""Internal Medicine Doctor Agent package."""

from app.agents.internal_medicine.graph import InternalMedicineGraph
from app.agents.internal_medicine.service import InternalMedicineService
from app.agents.internal_medicine.state_machine import InternalMedicineDialogueStateMachine


def create_internal_medicine_service(
    llm_settings: dict,
    patient_repo,
    session_repo,
    memory_repo,
    queue_repo,
    visit_repo,
    patient_state_machine,
    visit_state_machine,
    bus,
):
    dialogue_state_machine = InternalMedicineDialogueStateMachine()
    graph = InternalMedicineGraph(service=None, dialogue_state_machine=dialogue_state_machine)
    service = InternalMedicineService(
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
    )
    graph.service = service
    return service
