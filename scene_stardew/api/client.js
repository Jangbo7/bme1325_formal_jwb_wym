// 星露谷场景API客户端 - 对接现有后端API
export function createBackendClient({ baseUrl, apiKey }) {
  const defaultHeaders = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey,
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
      throw new Error(`API错误: ${response.status}`);
    }
    return response.json();
  }

  return {
    // 健康检查
    health() {
      return request('/health', { headers: { 'Content-Type': undefined } });
    },

    // 病人相关
    listPatients() {
      return request('/patients');
    },
    getPatient(patientId) {
      return request(`/patients/${patientId}`);
    },

    // 队列相关
    listQueues() {
      return request('/queues');
    },
    joinQueue(queueId, patientId) {
      return request(`/queues/${queueId}/join`, {
        method: 'POST',
        body: JSON.stringify({ patient_id: patientId }),
      });
    },

    // 分诊会话
    createTriageSession(payload) {
      return request('/triage-sessions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    sendTriageMessage(sessionId, payload) {
      return request(`/triage-sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    // 内科会话
    createInternalMedicineSession(payload) {
      return request('/internal-medicine-sessions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    sendInternalMedicineMessage(sessionId, payload) {
      return request(`/internal-medicine-sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },

    // ICU会话
    createICUSession(payload) {
      return request('/icu-sessions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    sendICUMessage(sessionId, payload) {
      return request(`/icu-sessions/${sessionId}/messages`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
  };
}
