from __future__ import annotations

import logging

from app.database import Database


logger = logging.getLogger(__name__)


class OpenEMRSyncSubscriber:
    SNAPSHOT_STATES = {
        "registered",
        "waiting_consultation",
        "in_consultation",
        "waiting_test",
        "in_test",
        "waiting_outpatient_procedure",
        "in_outpatient_procedure",
    }

    def __init__(self, *, emr_service, visit_repo, session_repo):
        self.emr_service = emr_service
        self.visit_repo = visit_repo
        self.session_repo = session_repo

    def handle_triage_completed(self, payload: dict) -> None:
        ids = self._resolve_ids(payload)
        if not ids:
            logger.warning("OpenEMR event payload missing required identifiers: triage.completed")
            return
        try:
            self.emr_service.sync_triage_summary(
                ids["patient_id"],
                ids["visit_id"],
                session_id=ids.get("session_id"),
            )
        except Exception as exc:
            logger.warning("OpenEMR sync failed for triage.completed: %s", exc)

    def handle_internal_medicine_completed(self, payload: dict) -> None:
        ids = self._resolve_ids(payload)
        if not ids:
            logger.warning("OpenEMR event payload missing required identifiers: internal_medicine.consultation_completed")
            return
        try:
            self.emr_service.sync_internal_medicine_summary(
                ids["patient_id"],
                ids["visit_id"],
                session_id=ids.get("session_id"),
            )
        except Exception as exc:
            logger.warning("OpenEMR sync failed for internal_medicine.consultation_completed: %s", exc)

    def handle_test_report_generated(self, payload: dict) -> None:
        ids = self._resolve_ids(payload)
        if not ids:
            logger.warning("OpenEMR event payload missing required identifiers: test.report_generated")
            return
        try:
            self.emr_service.sync_test_report(ids["patient_id"], ids["visit_id"])
        except Exception as exc:
            logger.warning("OpenEMR sync failed for test.report_generated: %s", exc)

    def handle_visit_state_changed(self, payload: dict) -> None:
        visit_id = payload.get("visit_id")
        if not visit_id:
            logger.warning("OpenEMR event payload missing required identifiers: visit.state_changed")
            return
        visit = self.visit_repo.get(visit_id)
        if not visit:
            return
        openemr_state = self._get_openemr_sync_state(visit)
        logger.debug(
            "OpenEMR visit state observed visit_id=%s state=%s sync_state=%s",
            visit_id,
            payload.get("state"),
            openemr_state,
        )
        state = payload.get("state")
        if state in self.SNAPSHOT_STATES:
            try:
                self.emr_service.archive_prepared_snapshot_for_visit(visit_id)
            except Exception as exc:
                logger.warning("OpenEMR prepared snapshot failed visit_id=%s state=%s error=%s", visit_id, state, exc)

    def _resolve_ids(self, payload: dict) -> dict | None:
        patient_id = payload.get("patient_id")
        visit_id = payload.get("visit_id")
        session_id = payload.get("session_id")

        if visit_id and (not patient_id or not session_id):
            visit = self.visit_repo.get(visit_id)
            if visit:
                patient_id = patient_id or visit.get("patient_id")
                data = Database.decode_json(visit.get("data_json"), {})
                if not session_id:
                    session_id = (
                        data.get("internal_medicine_session_id")
                        or data.get("triage_session_id")
                        or session_id
                    )

        if session_id and (not patient_id or not visit_id):
            session = self.session_repo.get(session_id)
            if session:
                patient_id = patient_id or session.get("patient_id")
                visit_id = visit_id or session.get("visit_id")

        if not patient_id or not visit_id:
            return None
        return {"patient_id": patient_id, "visit_id": visit_id, "session_id": session_id}

    @staticmethod
    def _get_openemr_sync_state(visit: dict) -> dict:
        data = Database.decode_json(visit.get("data_json"), {})
        openemr_sync = data.get("openemr_sync")
        if isinstance(openemr_sync, dict):
            return openemr_sync
        return {}
