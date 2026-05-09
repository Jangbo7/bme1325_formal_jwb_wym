export function createBackendClient({ baseUrl, apiKey }) {
  const DEFAULT_TIMEOUT_MS = 30000;
  const WRITE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
  const defaultHeaders = {
    "Content-Type": "application/json",
    "X-API-Key": apiKey,
  };

  function createIdempotencyKey() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return `idem-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  }

  async function request(path, options = {}) {
    const { timeoutMs = DEFAULT_TIMEOUT_MS, headers: optionHeaders = {}, ...fetchOptions } = options;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const method = (fetchOptions.method || "GET").toUpperCase();
    const headers = Object.fromEntries(
      Object.entries({
        ...defaultHeaders,
        ...optionHeaders,
      }).filter(([, value]) => value !== undefined)
    );
    if (WRITE_METHODS.has(method) && !headers["Idempotency-Key"]) {
      headers["Idempotency-Key"] = createIdempotencyKey();
    }

    let response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(`request timeout after ${timeoutMs}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }

    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        const errorMessage = payload?.error?.message || payload?.detail || "";
        const errorCode = payload?.error?.code ? `[${payload.error.code}] ` : "";
        detail = errorMessage ? `: ${errorCode}${errorMessage}` : "";
      } catch (_error) {
        try {
          const text = await response.text();
          detail = text ? `: ${text.slice(0, 160)}` : "";
        } catch (_textError) {
          detail = "";
        }
      }
      throw new Error(`status ${response.status}${detail}`);
    }
    const payload = await response.json();
    if (payload && typeof payload === "object" && "ok" in payload && "data" in payload) {
      return payload.data;
    }
    return payload;
  }

  return {
    health() {
      return request("/api/v1/health", { headers: { "Content-Type": undefined } });
    },
    createVisit(payload) {
      return request("/api/v1/visits", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    createEncounter(payload) {
      return request("/api/v1/encounters", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getEncounter(encounterId) {
      return request(`/api/v1/encounters/${encounterId}`, { method: "GET" });
    },
    transferEncounter(encounterId, payload) {
      return request(`/api/v1/encounters/${encounterId}/transfer`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    triggerEncounterEvent(encounterId, payload) {
      return request(`/api/v1/encounters/${encounterId}/events`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getEncounterStateDebug(encounterId) {
      return request(`/api/v1/encounters/${encounterId}/state-debug`, { method: "GET" });
    },
    transitionEncounterState(encounterId, payload) {
      return request(`/api/v1/encounters/${encounterId}/state-debug/transition`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    resetEncounterState(encounterId) {
      return request(`/api/v1/encounters/${encounterId}/state-debug/reset`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    rollbackEncounterState(encounterId) {
      return request(`/api/v1/encounters/${encounterId}/state-debug/back`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    },
    getStateMachineGraph() {
      return request("/api/v1/state-machine/graph", { method: "GET" });
    },
    getVisit(visitId) {
      return request(`/api/v1/visits/${visitId}`, { method: "GET" });
    },
    registerVisit(visitId, payload) {
      return request(`/api/v1/visits/${visitId}/register`, {
        method: "POST",
        body: JSON.stringify(payload || {}),
      });
    },
    progressVisit(visitId) {
      return request(`/api/v1/visits/${visitId}/progress`, { method: "POST" });
    },
    enterConsultation(visitId) {
      return request(`/api/v1/visits/${visitId}/enter-consultation`, { method: "POST" });
    },
    readyPayment(visitId) {
      return request(`/api/v1/visits/${visitId}/ready-payment`, { method: "POST" });
    },
    listPatients() {
      return request("/api/v1/patients", { method: "GET" });
    },
    getPatient(patientId) {
      return request(`/api/v1/patients/${patientId}`, { method: "GET" });
    },
    listQueues() {
      return request("/api/v1/queues", { method: "GET" });
    },
    createTriageSession(payload) {
      return request("/api/v1/triage-sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    sendTriageMessage(sessionId, payload) {
      return request(`/api/v1/triage-sessions/${sessionId}/messages`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    createInternalMedicineSession(payload) {
      return request("/api/v1/internal-medicine-sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    sendInternalMedicineMessage(sessionId, payload) {
      return request(`/api/v1/internal-medicine-sessions/${sessionId}/messages`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    getInternalMedicineSession(sessionId) {
      return request(`/api/v1/internal-medicine-sessions/${sessionId}`, { method: "GET" });
    },
    getSimulatedReport(visitId) {
      return request(`/api/v1/visits/${visitId}/simulated-report`, { method: "GET" });
    },
    completeAuxiliaryTest(visitId) {
      return request(`/api/v1/visits/${visitId}/complete-auxiliary-test`, { method: "POST" });
    },
  };
}
