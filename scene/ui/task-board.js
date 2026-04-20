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
  };
}
