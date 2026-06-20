export function createAgentStore() {
  return {
    lastPatient: null,
    lastQueues: [],
    lastSceneSnapshot: null,
    syncPatient(patient) {
      this.lastPatient = patient;
      return patient;
    },
    syncQueues(queues) {
      this.lastQueues = Array.isArray(queues) ? queues : [];
      return this.lastQueues;
    },
    syncSceneSnapshot(snapshot) {
      this.lastSceneSnapshot = snapshot || null;
      if (snapshot?.self_patient) {
        this.lastPatient = snapshot.self_patient;
      }
      if (Array.isArray(snapshot?.queues)) {
        this.lastQueues = snapshot.queues;
      }
      return this.lastSceneSnapshot;
    },
  };
}

export function buildDialogueMessages(patient, fallbackUserSummary = "") {
  const turns = patient?.dialogue?.turns || patient?.memory?.short_term_memory?.turns || [];
  if (Array.isArray(turns) && turns.length > 0) {
    return turns.map((turn) => ({
      role: turn.role === "assistant" ? "assistant" : "user",
      label: turn.role === "assistant" ? "Triage Agent" : "Patient",
      body: turn.content || "",
    }));
  }
  const assistantMessage = patient?.dialogue?.assistant_message || patient?.triage?.note || "Waiting for triage response.";
  return [
    { role: "user", label: "Patient", body: fallbackUserSummary || `${patient?.name || "Patient"} submitted triage information.` },
    { role: "assistant", label: "Triage Agent", body: assistantMessage },
  ];
}
