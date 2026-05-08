export function createBackendClient({ baseUrl, apiKey }) {
  const DEFAULT_TIMEOUT_MS = 30000;
  const defaultHeaders = {
    "Content-Type": "application/json",
    "X-API-Key": apiKey,
  };

  async function request(path, options = {}) {
    const { timeoutMs = DEFAULT_TIMEOUT_MS, headers: optionHeaders = {}, ...fetchOptions } = options;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const headers = Object.fromEntries(
      Object.entries({
        ...defaultHeaders,
        ...optionHeaders,
      }).filter(([, value]) => value !== undefined)
    );

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
        detail = payload?.detail ? `: ${payload.detail}` : "";
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
    return response.json();
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
    getVisit(visitId) {
      return request(`/api/v1/visits/${visitId}`, { method: "GET" });
    },
    registerVisit(visitId) {
      return request(`/api/v1/visits/${visitId}/register`, { method: "POST" });
    },
    progressVisit(visitId) {
      return request(`/api/v1/visits/${visitId}/progress`, { method: "POST" });
    },
    enterConsultation(visitId) {
      return request(`/api/v1/visits/${visitId}/enter-consultation`, { method: "POST" });
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
