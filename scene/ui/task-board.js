export function createTaskBoardPresenter(taskBoard) {
  const activeStates = new Set(["Triaging", "Waiting Follow-up", "Queued", "Called", "In Consultation"]);

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
  };
}
