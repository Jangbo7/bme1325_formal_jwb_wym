export function createTaskBoardPresenter(taskBoard) {
  const activeStates = new Set(["Triaging", "Waiting Follow-up", "Queued", "Called", "In Consultation"]);

  function summarizeRuntime(runtimeSnapshot) {
    if (!runtimeSnapshot || typeof runtimeSnapshot !== "object") return null;
    const activeCount = Number(runtimeSnapshot.active_count ?? 0);
    const departmentCount = Array.isArray(runtimeSnapshot.departments) ? runtimeSnapshot.departments.length : 0;
    const nodeCount = Array.isArray(runtimeSnapshot.nodes) ? runtimeSnapshot.nodes.length : 0;
    const blockedCount = Number(runtimeSnapshot.blocked_count ?? 0);
    const dispatchCount = Number(runtimeSnapshot.dispatch_count ?? 0);
    const mode = runtimeSnapshot.mode || "unknown";
    const running = runtimeSnapshot.running ? "running" : "idle";
    return `Runtime ${running} | mode ${mode} | active ${activeCount} | depts ${departmentCount} | nodes ${nodeCount} | dispatch ${dispatchCount} | blocked ${blockedCount}`;
  }

  function pushLine(lines, text, done = false) {
    if (!text) return;
    lines.push({ text, done });
  }

  return {
    syncPatients(patients) {
      taskBoard.title = "Live Patient Status";
      taskBoard.tasks = (patients || []).slice(0, 6).map((patient) => ({
        text: `${patient.name} | ${patient.state} | ${patient.location ?? "-"}`,
        done: !activeStates.has(patient.state),
      }));
      if (taskBoard.tasks.length === 0) {
        taskBoard.tasks = [{ text: "No patient status available", done: false }];
      }
    },
    syncOffline(message) {
      taskBoard.title = "Live Patient Status (Offline)";
      taskBoard.tasks = [{ text: message || "Backend unavailable", done: false }];
    },
    syncVisitSession({ patient, visit, queueTicket }) {
      taskBoard.title = "Visit Session Sync";

      if (!patient) {
        taskBoard.tasks = [
          { text: "Waiting for player patient profile", done: false },
          { text: "Backend polling active", done: true },
        ];
        return;
      }

      const visitId = visit?.id || patient.visit_id || "-";
      const visitState = visit?.state || patient.visit_state || "unknown";
      const activeAgentType = patient.active_agent_type || visit?.active_agent_type || "unknown";
      const dialogueSourceAgent = patient.dialogue_source_agent || "none";
      const sessionRefs = patient.session_refs || {};
      const triageSessionId = sessionRefs.triage_session_id || null;
      const internalSessionId = sessionRefs.internal_medicine_session_id || null;
      const patientSessionId = patient.session_id || null;

      let expectedSessionId = null;
      if (activeAgentType === "internal_medicine") {
        expectedSessionId = internalSessionId;
      } else if (activeAgentType === "triage") {
        expectedSessionId = triageSessionId;
      }

      const sessionSynced = !expectedSessionId || !patientSessionId || expectedSessionId === patientSessionId;

      const queueLabel = queueTicket
        ? `#${queueTicket.number} ${queueTicket.department_name} (${queueTicket.status})`
        : "not queued";

      taskBoard.tasks = [
        { text: `${patient.name} | ${patient.state} | ${patient.location || "-"}`, done: !activeStates.has(patient.state) },
        { text: `Visit ${visitId} | ${visitState}`, done: visitId !== "-" },
        { text: `Agent ${activeAgentType} | Dialogue ${dialogueSourceAgent}`, done: activeAgentType !== "unknown" },
        {
          text: sessionSynced
            ? `Session synced (${patientSessionId || "none"})`
            : `Session mismatch patient=${patientSessionId || "none"} expected=${expectedSessionId || "none"}`,
          done: sessionSynced,
        },
        { text: `Queue ${queueLabel}`, done: Boolean(queueTicket) },
      ];
    },
    syncSceneSnapshot(snapshot) {
      if (!snapshot?.self_patient) {
        if (Array.isArray(snapshot?.other_patients) && snapshot.other_patients.length > 0) {
          this.syncPatients(snapshot.other_patients);
          return;
        }
        this.syncOffline("Waiting for player patient profile");
        return;
      }
      this.syncVisitSession({
        patient: snapshot.self_patient,
        visit: snapshot.active_visit,
        queueTicket: snapshot.active_queue_ticket,
      });
    },
    syncIntegratedView({
      snapshot,
      medicalRecordTimeline,
      hospitalRuntime,
      departmentRuntime,
      departments,
      openEmrHealth,
      icuPatients,
    }) {
      const selfPatient = snapshot?.self_patient || null;
      const activeVisit = snapshot?.active_visit || null;
      const queueTicket = snapshot?.active_queue_ticket || null;
      const lines = [];

      taskBoard.title = "Frontend / Backend Merge View";

      if (!selfPatient) {
        pushLine(lines, "Waiting for player patient profile", false);
      } else {
        const visitId = activeVisit?.id || selfPatient.visit_id || "-";
        const visitState = activeVisit?.state || selfPatient.visit_state || "unknown";
        const location = selfPatient.location || activeVisit?.current_department || "-";
        pushLine(lines, `${selfPatient.name} | ${selfPatient.state} | ${location}`, !activeStates.has(selfPatient.state));
        pushLine(lines, `Visit ${visitId} | ${visitState}`, visitId !== "-");
        pushLine(lines, `Agent ${selfPatient.active_agent_type || "none"} | Dialogue ${selfPatient.dialogue_source_agent || "none"}`, Boolean(selfPatient.active_agent_type));
      }

      if (queueTicket) {
        pushLine(lines, `Queue #${queueTicket.number} ${queueTicket.department_name} (${queueTicket.status})`, true);
      }

      if (snapshot?.medical_record_summary) {
        const summary = snapshot.medical_record_summary;
        pushLine(
          lines,
          `Record ${summary.record_id} | entries ${summary.entry_count} | latest ${summary.latest_phase || "-"} / ${summary.latest_entry_type || "-"}`,
          summary.entry_count > 0
        );
      }

      if (snapshot?.latest_test_report) {
        const report = snapshot.latest_test_report;
        const items = Array.isArray(report.test_items) ? report.test_items.length : 0;
        pushLine(lines, `Test report ready | ${report.category_label || report.category_code || "-"} | items ${items}`, true);
      }

      if (medicalRecordTimeline?.entries?.length) {
        const latestEntry = medicalRecordTimeline.entries[medicalRecordTimeline.entries.length - 1];
        pushLine(
          lines,
          `Timeline latest | ${latestEntry.phase || "-"} | ${latestEntry.title || latestEntry.entry_type || "-"}`,
          true
        );
      }

      if (Array.isArray(snapshot?.other_patients) && snapshot.other_patients.length > 0) {
        pushLine(lines, `Other active patients ${snapshot.other_patients.length}`, true);
      }

      const hospitalRuntimeSummary = summarizeRuntime(hospitalRuntime);
      if (hospitalRuntimeSummary) {
        pushLine(lines, hospitalRuntimeSummary, true);
      }

      const departmentRuntimeSummary = summarizeRuntime(departmentRuntime);
      if (departmentRuntimeSummary) {
        pushLine(lines, departmentRuntimeSummary, true);
      }

      if (departments && typeof departments === "object") {
        const formalCount = Array.isArray(departments.formal_departments) ? departments.formal_departments.length : 0;
        const legacyCount = Array.isArray(departments.legacy_departments) ? departments.legacy_departments.length : 0;
        pushLine(lines, `Department catalog | formal ${formalCount} | legacy ${legacyCount}`, formalCount > 0);
      }

      if (openEmrHealth && typeof openEmrHealth === "object") {
        const healthLabel = openEmrHealth.ok === false ? "OpenEMR offline" : "OpenEMR ready";
        const detail = openEmrHealth.message || openEmrHealth.detail || openEmrHealth.status || "";
        pushLine(lines, detail ? `${healthLabel} | ${detail}` : healthLabel, openEmrHealth.ok !== false);
      }

      if (Array.isArray(icuPatients?.patients)) {
        pushLine(lines, `ICU patient pool ${icuPatients.patients.length}`, true);
      }

      taskBoard.tasks = lines.length > 0
        ? lines.slice(0, 10)
        : [{ text: "No merged runtime data available", done: false }];
    },
  };
}
