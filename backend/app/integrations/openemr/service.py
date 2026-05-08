from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from app.integrations.openemr.client import OpenEMRClient
from app.integrations.openemr.errors import OpenEMRError
from app.integrations.openemr.mapper import (
    map_internal_medicine_to_note,
    map_patient_to_openemr_with_context,
    map_simulated_report_to_report,
    map_triage_to_note,
    map_visit_to_encounter,
)
from app.integrations.openemr.schemas import OpenEMRSyncResult


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


logger = logging.getLogger(__name__)


class EMRService:
    def __init__(
        self,
        *,
        client: OpenEMRClient,
        patient_repo,
        visit_repo,
        session_repo,
        memory_repo,
        prepared_log_path: str | None = None,
    ):
        self.client = client
        self.patient_repo = patient_repo
        self.visit_repo = visit_repo
        self.session_repo = session_repo
        self.memory_repo = memory_repo
        self.prepared_log_path = prepared_log_path

    def archive_prepared_snapshot_for_visit(self, visit_id: str) -> None:
        visit = self.visit_repo.get(visit_id)
        if not visit:
            return
        patient_id = visit.get("patient_id")
        if not patient_id:
            return
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return

        patient_payload = map_patient_to_openemr_with_context(patient, None)
        self._archive_prepared_payload(
            resource_type="Patient",
            operation="create_or_update",
            payload=patient_payload.model_dump(),
            status="prepared_snapshot",
            metadata={"visit_id": visit_id, "patient_id": patient_id, "source": "visit_state_changed"},
        )

        encounter_payload = map_visit_to_encounter(visit, patient)
        self._archive_prepared_payload(
            resource_type="Encounter",
            operation="create",
            payload=encounter_payload.model_dump(),
            status="prepared_snapshot",
            metadata={"visit_id": visit_id, "patient_id": patient_id, "source": "visit_state_changed"},
        )

    def ensure_patient_synced(self, patient_id: str, source_payload: dict | None = None) -> OpenEMRSyncResult:
        patient = self.patient_repo.get(patient_id)
        if not patient:
            return self._error_result("Patient", "create_or_update", f"patient not found: {patient_id}")
        if patient.get("openemr_patient_id"):
            return OpenEMRSyncResult(
                ok=True,
                external_id=patient["openemr_patient_id"],
                resource_type="Patient",
                operation="create_or_update",
                raw_response={"skipped": "already_synced"},
                skipped=True,
            )
        payload = map_patient_to_openemr_with_context(patient, source_payload)
        self._archive_prepared_payload(
            resource_type="Patient",
            operation="create_or_update",
            payload=payload.model_dump(),
            status="prepared",
            metadata={"patient_id": patient_id},
        )
        try:
            result = self.client.create_or_update_patient(payload)
        except OpenEMRError as exc:
            return self._error_result("Patient", "create_or_update", str(exc))

        if result.ok and result.external_id:
            self.patient_repo.update_openemr_patient_id(patient_id, result.external_id)
            logger.info("OpenEMR patient synced patient_id=%s external_id=%s", patient_id, result.external_id)
        return result

    def ensure_visit_encounter_synced(self, visit_id: str, source_payload: dict | None = None) -> OpenEMRSyncResult:
        visit = self.visit_repo.get(visit_id)
        if not visit:
            return self._error_result("Encounter", "create", f"visit not found: {visit_id}")
        if visit.get("openemr_encounter_id"):
            return OpenEMRSyncResult(
                ok=True,
                external_id=visit["openemr_encounter_id"],
                resource_type="Encounter",
                operation="create",
                raw_response={"skipped": "already_synced"},
                skipped=True,
            )

        patient = self.patient_repo.get(visit["patient_id"])
        if patient:
            prepared_payload = map_visit_to_encounter(visit, patient)
            self._archive_prepared_payload(
                resource_type="Encounter",
                operation="create",
                payload=prepared_payload.model_dump(),
                status="prepared",
                metadata={"visit_id": visit_id, "patient_id": visit["patient_id"]},
            )

        patient_result = self.ensure_patient_synced(visit["patient_id"], source_payload=source_payload)
        if not patient_result.ok:
            self._mark_visit_failed(visit_id, patient_result.error or "patient sync failed")
            return patient_result

        patient = self.patient_repo.get(visit["patient_id"])
        if not patient or not patient.get("openemr_patient_id"):
            error = "patient openemr id missing after sync"
            self._mark_visit_failed(visit_id, error)
            return self._error_result("Encounter", "create", error)

        try:
            payload = map_visit_to_encounter(visit, patient)
            result = self.client.create_encounter(payload)
        except OpenEMRError as exc:
            self._mark_visit_failed(visit_id, str(exc))
            return self._error_result("Encounter", "create", str(exc))

        if result.ok and result.external_id:
            self.visit_repo.update_openemr_encounter_id(visit_id, result.external_id)
            self._mark_visit_synced(visit_id)
            logger.info("OpenEMR encounter synced visit_id=%s external_id=%s", visit_id, result.external_id)
        return result

    def sync_triage_summary(self, patient_id: str, visit_id: str, session_id: str | None = None, *, force: bool = False) -> OpenEMRSyncResult:
        return self._sync_note(
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            force=force,
            note_key="triage_note_id",
            note_type="triage",
            mapper_fn=map_triage_to_note,
        )

    def sync_internal_medicine_summary(self, patient_id: str, visit_id: str, session_id: str | None = None, *, force: bool = False) -> OpenEMRSyncResult:
        return self._sync_note(
            patient_id=patient_id,
            visit_id=visit_id,
            session_id=session_id,
            force=force,
            note_key="internal_medicine_note_id",
            note_type="internal_medicine",
            mapper_fn=map_internal_medicine_to_note,
        )

    def sync_test_report(self, patient_id: str, visit_id: str, *, force: bool = False) -> OpenEMRSyncResult:
        patient = self.patient_repo.get(patient_id)
        visit = self.visit_repo.get(visit_id)
        if not patient or not visit or visit.get("patient_id") != patient_id:
            return self._error_result("DocumentReference", "add_test_report", "patient/visit mismatch")

        encounter_result = self.ensure_visit_encounter_synced(visit_id)
        if not encounter_result.ok:
            return encounter_result
        patient = self.patient_repo.get(patient_id) or patient
        visit = self.visit_repo.get(visit_id) or visit

        sync_data = self._get_openemr_sync_data(visit)
        existing_id = sync_data.get("test_report_id")
        if existing_id and not force:
            return OpenEMRSyncResult(
                ok=True,
                external_id=existing_id,
                resource_type="DocumentReference",
                operation="add_test_report",
                raw_response={"skipped": "already_synced"},
                skipped=True,
            )

        visit_data = self._get_visit_data(visit)
        report = visit_data.get("simulated_report")
        if not isinstance(report, dict):
            error = "simulated report not found in visit data"
            self._mark_visit_failed(visit_id, error)
            return self._error_result("DocumentReference", "add_test_report", error)

        prepared_report = map_simulated_report_to_report(patient, visit, report)
        self._archive_prepared_payload(
            resource_type="DocumentReference",
            operation="add_test_report",
            payload=prepared_report.model_dump(),
            status="prepared",
            metadata={"visit_id": visit_id, "patient_id": patient_id, "report_type": "simulated_report"},
        )

        try:
            payload = map_simulated_report_to_report(patient, visit, report)
            result = self.client.add_test_report(payload)
        except OpenEMRError as exc:
            self._mark_visit_failed(visit_id, str(exc))
            return self._error_result("DocumentReference", "add_test_report", str(exc))

        if result.ok and result.external_id:
            self.visit_repo.set_openemr_sync_ref(visit_id, "test_report_id", result.external_id)
            self._mark_visit_synced(visit_id)
            logger.info("OpenEMR simulated report synced visit_id=%s external_id=%s", visit_id, result.external_id)
        return result

    def _sync_note(
        self,
        *,
        patient_id: str,
        visit_id: str,
        session_id: str | None,
        force: bool,
        note_key: str,
        note_type: str,
        mapper_fn,
    ) -> OpenEMRSyncResult:
        patient = self.patient_repo.get(patient_id)
        visit = self.visit_repo.get(visit_id)
        if not patient or not visit or visit.get("patient_id") != patient_id:
            return self._error_result("DocumentReference", "add_note", "patient/visit mismatch")

        source_payload = self._resolve_note_source_payload(
            patient_id=patient_id,
            visit=visit,
            session_id=session_id,
            note_type=note_type,
        )
        prepared_note = mapper_fn(patient, visit, source_payload)
        self._archive_prepared_payload(
            resource_type="DocumentReference",
            operation="add_note",
            payload=prepared_note.model_dump(),
            status="prepared",
            metadata={"visit_id": visit_id, "patient_id": patient_id, "note_type": note_type},
        )
        encounter_result = self.ensure_visit_encounter_synced(visit_id, source_payload=source_payload)
        if not encounter_result.ok:
            return encounter_result
        patient = self.patient_repo.get(patient_id) or patient
        visit = self.visit_repo.get(visit_id) or visit

        sync_data = self._get_openemr_sync_data(visit)
        existing_id = sync_data.get(note_key)
        if existing_id and not force:
            return OpenEMRSyncResult(
                ok=True,
                external_id=existing_id,
                resource_type="DocumentReference",
                operation="add_note",
                raw_response={"skipped": "already_synced"},
                skipped=True,
            )
        try:
            payload = mapper_fn(patient, visit, source_payload)
            result = self.client.add_encounter_note(payload)
        except OpenEMRError as exc:
            self._mark_visit_failed(visit_id, str(exc))
            return self._error_result("DocumentReference", "add_note", str(exc))

        if result.ok and result.external_id:
            self.visit_repo.set_openemr_sync_ref(visit_id, note_key, result.external_id)
            self._mark_visit_synced(visit_id)
            if note_key == "triage_note_id":
                logger.info("OpenEMR triage note synced visit_id=%s external_id=%s", visit_id, result.external_id)
            else:
                logger.info("OpenEMR internal medicine note synced visit_id=%s external_id=%s", visit_id, result.external_id)
        return result

    def _resolve_note_source_payload(self, *, patient_id: str, visit: dict, session_id: str | None, note_type: str) -> dict:
        visit_data = self._get_visit_data(visit)
        resolved_session_id = session_id
        if not resolved_session_id:
            key = "triage_session_id" if note_type == "triage" else "internal_medicine_session_id"
            resolved_session_id = visit_data.get(key)
        if not resolved_session_id:
            return {"visit_data": visit_data}

        agent_type = "triage" if note_type == "triage" else "internal_medicine"
        try:
            memory = self.memory_repo.get_agent_session_memory(resolved_session_id, patient_id, agent_type=agent_type)
        except Exception:
            memory = {}
        source = dict(memory) if isinstance(memory, dict) else {}
        source["visit_data"] = visit_data
        return source

    @staticmethod
    def _get_visit_data(visit: dict) -> dict:
        return self_or_decode_json(visit.get("data_json"))

    @staticmethod
    def _get_openemr_sync_data(visit: dict) -> dict:
        data = self_or_decode_json(visit.get("data_json"))
        openemr_sync = data.get("openemr_sync")
        if isinstance(openemr_sync, dict):
            return openemr_sync
        return {}

    def _mark_visit_failed(self, visit_id: str, error: str) -> None:
        logger.warning("OpenEMR sync failed visit_id=%s error=%s", visit_id, error)
        self.visit_repo.set_emr_sync_status(
            visit_id,
            status="failed",
            error=error,
            synced_at=None,
        )

    def _mark_visit_synced(self, visit_id: str) -> None:
        self.visit_repo.set_emr_sync_status(
            visit_id,
            status="synced",
            error=None,
            synced_at=now_iso(),
        )

    def _archive_prepared_payload(
        self,
        *,
        resource_type: str,
        operation: str,
        payload: dict,
        status: str,
        metadata: dict | None = None,
    ) -> None:
        if not self.prepared_log_path:
            return
        record = {
            "timestamp": now_iso(),
            "resource_type": resource_type,
            "operation": operation,
            "status": status,
            "payload": payload,
            "metadata": metadata or {},
        }
        record = self._drop_none_fields(record)
        try:
            path = Path(self.prepared_log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False))
                fh.write("\n")
        except Exception:
            return

    @staticmethod
    def _drop_none_fields(value):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                normalized = EMRService._drop_none_fields(item)
                if normalized is not None:
                    cleaned[key] = normalized
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                normalized = EMRService._drop_none_fields(item)
                if normalized is not None:
                    cleaned_list.append(normalized)
            return cleaned_list
        return value

    @staticmethod
    def _error_result(resource_type: str, operation: str, error: str) -> OpenEMRSyncResult:
        return OpenEMRSyncResult(
            ok=False,
            resource_type=resource_type,
            operation=operation,
            error=error,
        )


def self_or_decode_json(payload: str | dict | None) -> dict:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        from app.database import Database

        return Database.decode_json(payload, {})
    except Exception:
        return {}
