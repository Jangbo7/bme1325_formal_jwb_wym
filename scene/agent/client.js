export function createBackendClient({ baseUrl, apiKey }) {
  const defaultHeaders = {
    "Content-Type": "application/json",
    "X-API-Key": apiKey,
  };

  async function request(path, options = {}) {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      throw new Error(`status ${response.status}`);
    }
    return response.json();
  }

  return {
    health() {
      return request("/api/v1/health", { headers: { "Content-Type": undefined } });
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
  };
}
