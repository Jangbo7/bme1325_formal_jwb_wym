"""ICU Doctor Agent package."""

from app.agents.icu_doctor.service import ICUDoctorService
from app.agents.icu_doctor.graph import ICUDoctorGraph
from app.agents.icu_doctor.state_machine import ICUDoctorDialogueStateMachine


def create_icub_doctor_service(llm_settings: dict, patient_repo, session_repo, memory_repo, queue_repo, patient_state_machine, bus):
    from app.agents.icu_doctor.state_machine import ICUDoctorDialogueStateMachine
    dialogue_state_machine = ICUDoctorDialogueStateMachine()
    graph = ICUDoctorGraph(service=None, dialogue_state_machine=dialogue_state_machine)
    service = ICUDoctorService(
        llm_settings=llm_settings,
        patient_repo=patient_repo,
        session_repo=session_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
        dialogue_state_machine=dialogue_state_machine,
        patient_state_machine=patient_state_machine,
        bus=bus,
        graph=graph,
    )
    graph.service = service
    return service
