function createElement(tag, className, text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function formatNow() {
  return new Date().toLocaleTimeString();
}

export function createStateDebugPanel({ enabled, backendClient, onHint, ensureEncounter }) {
  if (!enabled) {
    return {
      setEncounterId() {},
      refresh() {},
      dispose() {},
    };
  }

  const container = createElement("aside", "state-debug-panel");
  Object.assign(container.style, {
    position: "fixed",
    right: "12px",
    bottom: "12px",
    width: "360px",
    maxHeight: "55vh",
    overflow: "auto",
    padding: "10px",
    zIndex: "9999",
    borderRadius: "10px",
    border: "1px solid rgba(255, 235, 190, 0.45)",
    background: "rgba(30, 22, 15, 0.95)",
    color: "#fff3db",
    font: "12px/1.45 'Trebuchet MS', sans-serif",
    boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
  });

  const title = createElement("div", "", "State Debug Mode");
  title.style.fontWeight = "700";
  title.style.fontSize = "13px";
  title.style.marginBottom = "6px";

  const encounterRow = createElement("div", "", "Encounter: -");
  encounterRow.style.marginBottom = "6px";

  const currentRow = createElement("div", "", "State: -");
  currentRow.style.marginBottom = "8px";

  const graphSummary = createElement("div", "", "Graph: loading...");
  graphSummary.style.opacity = "0.85";
  graphSummary.style.marginBottom = "8px";

  const controlRow = createElement("div", "");
  Object.assign(controlRow.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    marginBottom: "8px",
  });

  const buttonsWrap = createElement("div", "");
  Object.assign(buttonsWrap.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    marginBottom: "8px",
  });

  const logsTitle = createElement("div", "", "Recent transitions");
  logsTitle.style.fontWeight = "700";
  logsTitle.style.marginBottom = "4px";

  const logsWrap = createElement("div", "");
  Object.assign(logsWrap.style, {
    border: "1px solid rgba(255, 235, 190, 0.25)",
    borderRadius: "8px",
    padding: "6px",
    minHeight: "68px",
    background: "rgba(255,255,255,0.04)",
  });

  container.append(title, encounterRow, currentRow, graphSummary, controlRow, buttonsWrap, logsTitle, logsWrap);
  document.body.appendChild(container);

  let encounterId = "";
  let refreshing = false;
  const logs = [];

  function createControlButton(label, onClick) {
    const btn = createElement("button", "", label);
    Object.assign(btn.style, {
      border: "1px solid rgba(255, 226, 170, 0.5)",
      borderRadius: "6px",
      background: "rgba(255, 236, 200, 0.1)",
      color: "#fff3db",
      cursor: "pointer",
      padding: "4px 8px",
    });
    btn.addEventListener("click", onClick);
    return btn;
  }

  function pushLog(message, error = false) {
    logs.unshift(`[${formatNow()}] ${message}`);
    while (logs.length > 8) logs.pop();
    logsWrap.innerHTML = "";
    for (const line of logs) {
      const item = createElement("div", "", line);
      if (error) item.style.color = "#ffb5a7";
      logsWrap.appendChild(item);
    }
  }

  function renderAllowedNext(items = []) {
    buttonsWrap.innerHTML = "";
    if (!items.length) {
      const empty = createElement("div", "", "No allowed next events.");
      empty.style.opacity = "0.8";
      buttonsWrap.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const btn = createElement("button", "", `${item.event} -> ${item.to_state}`);
      Object.assign(btn.style, {
        border: "1px solid rgba(255, 226, 170, 0.5)",
        borderRadius: "6px",
        background: "rgba(255, 196, 116, 0.14)",
        color: "#fff3db",
        cursor: "pointer",
        padding: "4px 8px",
      });
      btn.addEventListener("click", async () => {
        if (!encounterId || refreshing) return;
        refreshing = true;
        try {
          const response = await backendClient.transitionEncounterState(encounterId, {
            event: item.event,
            dry_run: false,
            context: { source: "scene_state_debug_panel" },
          });
          const data = response?.data || {};
          pushLog(`${data.from_state} --${data.event}--> ${data.to_state}`);
          if (typeof onHint === "function") {
            onHint(`Debug transition: ${data.from_state} -> ${data.to_state}`);
          }
          await refresh();
        } catch (error) {
          const detail = error?.message || "transition failed";
          pushLog(detail, true);
          if (typeof onHint === "function") {
            onHint(`Debug transition failed: ${detail}`);
          }
        } finally {
          refreshing = false;
        }
      });
      buttonsWrap.appendChild(btn);
    });
  }

  async function loadGraph() {
    try {
      const response = await backendClient.getStateMachineGraph();
      const graph = response?.data || {};
      const stateCount = Array.isArray(graph.states) ? graph.states.length : 0;
      const edgeCount = Array.isArray(graph.edges) ? graph.edges.length : 0;
      graphSummary.textContent = `Graph: ${stateCount} states / ${edgeCount} edges`;
    } catch (error) {
      graphSummary.textContent = `Graph unavailable: ${error?.message || "unknown error"}`;
    }
  }

  async function ensureEncounterAndRefresh() {
    if (encounterId) {
      await refresh();
      return;
    }
    if (typeof ensureEncounter !== "function") {
      pushLog("no encounter context yet", true);
      return;
    }
    try {
      const nextEncounterId = await ensureEncounter();
      if (nextEncounterId) {
        setEncounterId(nextEncounterId);
        pushLog(`encounter bound: ${nextEncounterId}`);
        await refresh();
      } else {
        pushLog("encounter create returned empty id", true);
      }
    } catch (error) {
      pushLog(error?.message || "encounter create failed", true);
    }
  }

  async function resetState() {
    if (!encounterId || refreshing) return;
    refreshing = true;
    try {
      const response = await backendClient.resetEncounterState(encounterId);
      const data = response?.data || {};
      pushLog(`${data.from_state} --debug_reset--> ${data.to_state}`);
      await refresh();
    } catch (error) {
      pushLog(error?.message || "reset failed", true);
    } finally {
      refreshing = false;
    }
  }

  async function rollbackState() {
    if (!encounterId || refreshing) return;
    refreshing = true;
    try {
      const response = await backendClient.rollbackEncounterState(encounterId);
      const data = response?.data || {};
      pushLog(`${data.from_state} --debug_back--> ${data.to_state}`);
      await refresh();
    } catch (error) {
      pushLog(error?.message || "rollback failed", true);
    } finally {
      refreshing = false;
    }
  }

  const bindBtn = createControlButton("Create/Bind Encounter", () => {
    ensureEncounterAndRefresh();
  });
  const resetBtn = createControlButton("Reset to ARRIVED", () => {
    resetState();
  });
  const backBtn = createControlButton("Back One Step", () => {
    rollbackState();
  });
  const refreshBtn = createControlButton("Refresh", () => {
    refresh();
  });
  controlRow.append(bindBtn, resetBtn, backBtn, refreshBtn);

  async function refresh() {
    if (!encounterId) {
      encounterRow.textContent = "Encounter: -";
      currentRow.textContent = "State: -";
      renderAllowedNext([]);
      return;
    }
    try {
      const response = await backendClient.getEncounterStateDebug(encounterId);
      const data = response?.data || {};
      encounterRow.textContent = `Encounter: ${data.encounter_id || encounterId}`;
      currentRow.textContent = `State: ${data.standard_state || "-"} (internal: ${data.internal_state || "-"})`;
      renderAllowedNext(Array.isArray(data.allowed_next) ? data.allowed_next : []);
    } catch (error) {
      currentRow.textContent = `State: error (${error?.message || "request failed"})`;
      renderAllowedNext([]);
    }
  }

  function setEncounterId(nextEncounterId) {
    if (nextEncounterId === encounterId) return;
    encounterId = nextEncounterId || "";
    refresh();
  }

  function setVisible(visible) {
    container.style.display = visible ? "block" : "none";
  }

  loadGraph();

  return {
    setEncounterId,
    setVisible,
    refresh,
    dispose() {
      container.remove();
    },
  };
}
