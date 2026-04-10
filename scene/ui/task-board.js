const TERMINAL_VISIT_STATES = new Set(["completed", "error"]);

function formatStateLabel(value) {
  if (value === null || value === undefined) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  if (!raw.includes("_")) return raw;
  return raw
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatField(value) {
  if (value === null || value === undefined) return "-";
  const text = String(value).trim();
  return text || "-";
}

function buildQueueTicketLabel(queueTicket) {
  if (!queueTicket) return "-";
  const department = formatField(queueTicket.department_name);
  const number = queueTicket.number ?? "-";
  const status = formatStateLabel(queueTicket.status);
  return `${department} #${number} (${status})`;
}

function buildVisitSessionTasks({ patient, visit, queueTicket }) {
  const visitId = visit?.id || patient?.visit_id || null;
  const visitStateRaw = visit?.state || patient?.visit_state || null;
  if (!visitId && !visitStateRaw) {
    return [{ text: "No active visit session", done: false }];
  }

  const isTerminal = TERMINAL_VISIT_STATES.has(String(visitStateRaw || "").toLowerCase());
  const visitState = formatStateLabel(visitStateRaw);
  const currentNode = formatStateLabel(visit?.current_node);
  const department = formatField(visit?.current_department || patient?.location);
  const activeAgent = formatField(visit?.active_agent_type);
  const lifecycle = formatStateLabel(patient?.lifecycle_state || patient?.state);
  const queueTicketLabel = buildQueueTicketLabel(queueTicket);

  return [
    { text: `Visit ID: ${formatField(visitId)}`, done: isTerminal },
    { text: `Visit State: ${visitState}`, done: isTerminal },
    { text: `Current Node: ${currentNode}`, done: isTerminal },
    { text: `Department: ${department}`, done: isTerminal },
    { text: `Active Agent: ${activeAgent}`, done: isTerminal },
    { text: `Patient Lifecycle: ${lifecycle}`, done: isTerminal },
    { text: `Queue Ticket: ${queueTicketLabel}`, done: isTerminal },
  ];
}

export function createTaskBoardPresenter(taskBoard) {
  return {
    syncVisitSession(payload = {}) {
      taskBoard.title = "Visit Session";
      taskBoard.tasks = buildVisitSessionTasks(payload);
    },
    syncOffline(message) {
      taskBoard.title = "Visit Session (Offline)";
      taskBoard.tasks = [{ text: message || "Backend unavailable", done: false }];
    },
  };
}
