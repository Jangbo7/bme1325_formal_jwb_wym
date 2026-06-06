from __future__ import annotations

from app.agents.patient_agent.patient_agent import ControlledPatientAgent
from app.agents.patient_agent.schemas import PatientCaseCard, PatientReplyContext
from app.repositories.patient_agent_cases import PatientAgentCaseRepository


class PatientAgentService:
    def __init__(
        self,
        *,
        llm_settings: dict,
        case_repo: PatientAgentCaseRepository,
        session_repo,
        medical_record_repo,
        agent: ControlledPatientAgent | None = None,
    ):
        self.case_repo = case_repo
        self.session_repo = session_repo
        self.medical_record_repo = medical_record_repo
        self.agent = agent or ControlledPatientAgent(llm_settings)

    def spawn_case(
        self,
        *,
        patient_id: str,
        visit_id: str | None = None,
        seed: str | None = None,
        department_id: str | None = None,
        mode: str = "intelligent_agent",
    ) -> tuple[dict, PatientCaseCard]:
        case_card = self.agent.generate_case(seed=seed, department_id=department_id)
        row = self.case_repo.create(
            patient_id=patient_id,
            visit_id=visit_id,
            mode=mode,
            case_payload=case_card.model_dump(),
            status="generated",
        )
        return row, case_card

    def attach_case_to_visit(self, case_id: str, visit_id: str) -> dict:
        return self.case_repo.update(case_id, visit_id=visit_id, status="active")

    def get_case_row(self, *, patient_id: str | None = None, visit_id: str | None = None) -> dict | None:
        if visit_id:
            row = self.case_repo.get_latest_by_visit(visit_id, mode="intelligent_agent")
            if row:
                return row
        if patient_id:
            return self.case_repo.get_latest_by_patient(patient_id, mode="intelligent_agent")
        return None

    def get_case_card(self, *, patient_id: str | None = None, visit_id: str | None = None) -> PatientCaseCard:
        row = self.get_case_row(patient_id=patient_id, visit_id=visit_id)
        if not row:
            raise LookupError("patient agent case not found")
        return PatientCaseCard.model_validate(self._decode_case(row))

    def summarize_case_for_debug(self, case_card: PatientCaseCard) -> dict:
        return {
            "case_id": case_card.case_id,
            "name": case_card.patient_profile.name,
            "age": case_card.patient_profile.age,
            "sex": case_card.patient_profile.sex,
            "chief_complaint": case_card.chief_complaint,
            "symptoms": list(case_card.symptom_facts.symptoms),
            "communication_style": case_card.communication_style,
            "patient_goals": list(case_card.patient_goals),
            "hidden_diagnosis_hint": case_card.hidden_diagnosis_hint,
        }

    def build_initial_payload(
        self,
        *,
        patient_id: str,
        visit_id: str,
        round_number: int = 1,
    ) -> dict:
        case_card = self.get_case_card(patient_id=patient_id, visit_id=visit_id)
        symptoms = list(case_card.symptom_facts.symptoms)
        associated = list(case_card.symptom_facts.associated_symptoms)
        return {
            "patient_id": patient_id,
            "visit_id": visit_id,
            "name": case_card.patient_profile.name,
            "age": case_card.patient_profile.age,
            "sex": case_card.patient_profile.sex,
            "chief_complaint": case_card.chief_complaint,
            "symptoms": ", ".join(symptoms + associated),
            "onset_time": case_card.symptom_facts.onset_time,
            "vitals": dict(case_card.symptom_facts.vitals),
            "allergies": list(case_card.patient_profile.allergies),
            "chronic_conditions": list(case_card.patient_profile.chronic_conditions),
            "round": round_number,
        }

    def build_patient_reply(
        self,
        *,
        patient_id: str,
        visit_id: str,
        session_id: str,
        phase: str,
        recent_question: str,
    ) -> dict:
        case_card = self.get_case_card(patient_id=patient_id, visit_id=visit_id)
        timeline = self.medical_record_repo.get_visit_timeline(visit_id) if self.medical_record_repo else None
        entries = list((timeline or {}).get("entries") or [])
        known_test_results = [
            entry for entry in entries
            if entry.get("entry_type") == "test_result_note"
        ]
        excerpt = entries[-3:]
        context = PatientReplyContext(
            phase=phase,
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            recent_question=recent_question or "",
            recent_turns=self.session_repo.list_turns(session_id, limit=8),
            known_test_results=known_test_results,
            medical_record_excerpt=excerpt,
        )
        turn = self.agent.reply(case_card=case_card, context=context)
        return {
            "message": turn.message,
            "policy_state": turn.policy_state,
            "used_facts": turn.used_facts,
            "case_summary": self.summarize_case_for_debug(case_card),
        }

    @staticmethod
    def _decode_case(row: dict) -> dict:
        from app.database import Database

        return Database.decode_json(row.get("case_json"), {})
