function normalizeBaseUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "http://127.0.0.1:8787";
  return raw.replace(/\/+$/, "");
}

function idempotencyKey() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

async function parseResponse(response) {
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (_error) {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object"
        ? payload.error?.message || payload.detail || JSON.stringify(payload).slice(0, 180)
        : text.slice(0, 180);
    throw new Error(detail || `HTTP ${response.status}`);
  }
  if (payload && typeof payload === "object" && payload.ok === false) {
    throw new Error(payload.error?.message || "request failed");
  }
  if (payload && typeof payload === "object" && "data" in payload) {
    return payload.data;
  }
  return payload;
}

export function createHospitalApi(initialBaseUrl) {
  let baseUrl = normalizeBaseUrl(initialBaseUrl);

  async function request(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (method !== "GET") {
      headers.set("Content-Type", "application/json");
      if (!headers.has("Idempotency-Key")) {
        headers.set("Idempotency-Key", idempotencyKey());
      }
    }

    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    return parseResponse(response);
  }

  return {
    getBaseUrl: () => baseUrl,
    setBaseUrl(nextBaseUrl) {
      baseUrl = normalizeBaseUrl(nextBaseUrl);
      return baseUrl;
    },
    request,
    health() {
      return request("/api/v1/health");
    },
    runtimeConsoleSnapshot() {
      return request("/api/v1/runtime-console/snapshot");
    },
    runtimeConsoleEvents(limit = 80) {
      return request(`/api/v1/runtime-console/events?limit=${encodeURIComponent(limit)}`);
    },
    departments() {
      return request("/api/v1/departments");
    },
    patients() {
      return request("/api/v1/patients");
    },
    patient(patientId) {
      return request(`/api/v1/patients/${encodeURIComponent(patientId)}`);
    },
    sceneSnapshot(patientId) {
      const suffix = patientId ? `?patient_id=${encodeURIComponent(patientId)}` : "";
      return request(`/api/v1/scene-snapshot${suffix}`);
    },
    visit(visitId) {
      return request(`/api/v1/visits/${encodeURIComponent(visitId)}`);
    },
    createVisit(payload) {
      return request("/api/v1/visits", { method: "POST", body: payload });
    },
    registerVisit(visitId, payload) {
      return request(`/api/v1/visits/${encodeURIComponent(visitId)}/register`, {
        method: "POST",
        body: payload,
      });
    },
    progressVisit(visitId) {
      return request(`/api/v1/visits/${encodeURIComponent(visitId)}/progress`, {
        method: "POST",
      });
    },
    enterConsultation(visitId) {
      return request(`/api/v1/visits/${encodeURIComponent(visitId)}/enter-consultation`, {
        method: "POST",
      });
    },
    readyPayment(visitId) {
      return request(`/api/v1/visits/${encodeURIComponent(visitId)}/ready-payment`, {
        method: "POST",
      });
    },
    medicalRecordTimeline(visitId) {
      return request(`/api/v1/medical-records/visit/${encodeURIComponent(visitId)}`);
    },
    createTriageSession(payload) {
      return request("/api/v1/triage-sessions", { method: "POST", body: payload });
    },
    sendTriageMessage(sessionId, payload) {
      return request(`/api/v1/triage-sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        body: payload,
      });
    },
    createInternalMedicineSession(payload) {
      return request("/api/v1/internal-medicine-sessions", { method: "POST", body: payload });
    },
    sendInternalMedicineMessage(sessionId, payload) {
      return request(`/api/v1/internal-medicine-sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        body: payload,
      });
    },
    getInternalMedicineSession(sessionId) {
      return request(`/api/v1/internal-medicine-sessions/${encodeURIComponent(sessionId)}`);
    },
    createSurgerySession(payload) {
      return request("/api/v1/surgery-sessions", { method: "POST", body: payload });
    },
    sendSurgeryMessage(sessionId, payload) {
      return request(`/api/v1/surgery-sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        body: payload,
      });
    },
    getSurgerySession(sessionId) {
      return request(`/api/v1/surgery-sessions/${encodeURIComponent(sessionId)}`);
    },
    createIcuSession(payload) {
      return request("/api/v1/icu-sessions", { method: "POST", body: payload });
    },
    sendIcuMessage(sessionId, payload) {
      return request(`/api/v1/icu-sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: "POST",
        body: payload,
      });
    },
    getIcuSession(sessionId) {
      return request(`/api/v1/icu-sessions/${encodeURIComponent(sessionId)}`);
    },
  };
}
