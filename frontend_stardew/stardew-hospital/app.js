import {
  createHospitalApi,
} from "./api.js";
import {
  escapeHtml,
  PALETTE,
  renderBarChart,
  renderLineChart,
  renderPieChart,
  renderStatCards,
} from "./charts.js";

const STORAGE_KEY = "stardew-hospital-dashboard";
const DEFAULT_STATE = {
  backendUrl: "http://127.0.0.1:8787",
  live: true,
  selectedPatientId: "",
  activeAgent: "triage",
  sessionIds: {
    triage: "",
    internal_medicine: "",
    surgery: "",
    icu: "",
  },
  sessionTurns: {
    triage: [],
    internal_medicine: [],
    surgery: [],
    icu: [],
  },
  selectedScene: null,
  selectedRecord: null,
  selectedVisit: null,
  patients: [],
  departments: [],
  events: [],
  snapshot: null,
  health: null,
  statusHistory: [],
  runtimeHistory: [],
  lastSync: null,
  sseState: "未连接",
  workflowNote: "先选择一个病人，再切换 Agent。分诊、挂号、进入诊室和聊天都可以在这里完成。",
};

const AGENTS = [
  {
    key: "triage",
    label: "门诊分诊",
    buttonLabel: "分诊",
    description: "用于收集主诉、症状和分诊结果。",
  },
  {
    key: "internal_medicine",
    label: "内科门诊",
    buttonLabel: "内科",
    description: "进入内科会诊流程，适合普通门诊主线。",
  },
  {
    key: "surgery",
    label: "外科门诊",
    buttonLabel: "外科",
    description: "进入外科会诊流程，适合手术相关主诉。",
  },
  {
    key: "icu",
    label: "ICU 会诊",
    buttonLabel: "ICU",
    description: "用于重症评估和转入 ICU 的对话。",
  },
];

const state = {
  ...DEFAULT_STATE,
};

const elements = {};
let api = createHospitalApi(state.backendUrl);
let pollTimer = null;
let eventsTimer = null;
let streamAbortController = null;
let pendingRefresh = null;
let lastRenderToken = 0;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      Object.assign(state, DEFAULT_STATE, parsed);
      state.sessionIds = { ...DEFAULT_STATE.sessionIds, ...(parsed.sessionIds || {}) };
      state.sessionTurns = { ...DEFAULT_STATE.sessionTurns, ...(parsed.sessionTurns || {}) };
    }
  } catch (_error) {
    Object.assign(state, DEFAULT_STATE);
  }
}

function saveState() {
  const payload = {
    backendUrl: state.backendUrl,
    live: state.live,
    selectedPatientId: state.selectedPatientId,
    activeAgent: state.activeAgent,
    sessionIds: state.sessionIds,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function $(id) {
  if (!elements[id]) {
    elements[id] = document.getElementById(id);
  }
  return elements[id];
}

function updateInputs() {
  $("backendUrl").value = state.backendUrl;
  $("patientId").value = state.selectedPatientId || "";
  $("liveToggleBtn").textContent = `实时更新：${state.live ? "开" : "关"}`;
  $("activeAgentLabel").textContent = currentAgent().label;
  $("sessionStateLabel").textContent = sessionStatusText();
  $("workflowNote").textContent = state.workflowNote;
}

function currentAgent() {
  return AGENTS.find((agent) => agent.key === state.activeAgent) || AGENTS[0];
}

function sessionStatusText() {
  const sessionId = state.sessionIds[state.activeAgent];
  return sessionId ? `已连接 ${sessionId}` : "未创建";
}

function uniqueId(prefix) {
  if (globalThis.crypto?.randomUUID) {
    return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
}

function countBy(items, getKey) {
  const map = new Map();
  for (const item of items) {
    const key = String(getKey(item) || "未知");
    map.set(key, (map.get(key) || 0) + 1);
  }
  return Array.from(map.entries())
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, "zh-Hans-CN"));
}

function deriveStageGroups(patients) {
  const groups = [
    { key: "triage", label: "分诊", match: ["triage", "pending_registration"] },
    { key: "waiting", label: "排队", match: ["waiting_call", "unassigned", "department_flow", "waiting"] },
    { key: "consultation", label: "诊中", match: ["consultation", "called"] },
    { key: "testing", label: "检查", match: ["testing", "procedure"] },
    { key: "payment", label: "缴费", match: ["payment", "pharmacy"] },
    { key: "finished", label: "完成", match: ["finished"] },
    { key: "error", label: "异常", match: ["error"] },
  ];
  const counts = new Map(groups.map((group) => [group.key, 0]));
  for (const patient of patients) {
    const stage = String(patient.display_stage || "unknown").toLowerCase();
    const match = groups.find((group) => group.match.some((item) => stage.includes(item)));
    if (match) {
      counts.set(match.key, counts.get(match.key) + 1);
    }
  }
  return groups.map((group) => ({
    label: group.label,
    value: counts.get(group.key) || 0,
    color: PALETTE[groups.indexOf(group) % PALETTE.length],
  }));
}

function deriveTrendSeries(history) {
  const labels = history.map((item) => item.shortLabel);
  return {
    labels,
    series: [
      { name: "活跃", color: PALETTE[0], values: history.map((item) => item.active) },
      { name: "等待", color: PALETTE[1], values: history.map((item) => item.waiting) },
      { name: "诊中", color: PALETTE[2], values: history.map((item) => item.consultation) },
      { name: "检查", color: PALETTE[3], values: history.map((item) => item.testing) },
      { name: "完成", color: PALETTE[4], values: history.map((item) => item.finished) },
    ],
  };
}

function buildSnapshotDigest(snapshot) {
  const patients = snapshot?.patients || [];
  const departments = snapshot?.departments || [];
  const active = patients.filter((patient) => !patient.finished).length;
  const waiting = patients.filter((patient) => String(patient.display_stage || "").includes("waiting")).length;
  const consultation = patients.filter((patient) => String(patient.display_stage || "").includes("consultation")).length;
  const testing = patients.filter((patient) => String(patient.display_stage || "").includes("testing") || String(patient.display_stage || "").includes("procedure")).length;
  const finished = patients.filter((patient) => String(patient.display_stage || "") === "finished").length;
  const blocked = patients.filter((patient) => String(patient.dispatch_state || "").startsWith("blocked")).length;
  const latest = patients[0] || null;
  return {
    active,
    waiting,
    consultation,
    testing,
    finished,
    blocked,
    total: patients.length,
    departments: departments.length,
    latestPatientName: latest?.name || latest?.patient_name || "无",
  };
}

function pushTrendSample(snapshot) {
  const digest = buildSnapshotDigest(snapshot);
  const entry = {
    shortLabel: new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
    ...digest,
  };
  state.runtimeHistory.push(entry);
  if (state.runtimeHistory.length > 30) {
    state.runtimeHistory.splice(0, state.runtimeHistory.length - 30);
  }
}

function normalizeTurns(turns) {
  if (!Array.isArray(turns)) return [];
  return turns.map((turn, index) => {
    if (typeof turn === "string") {
      return { role: index % 2 === 0 ? "assistant" : "user", content: turn, timestamp: "" };
    }
    return {
      role: String(turn.role || turn.speaker || turn.type || "assistant"),
      content: String(turn.content || turn.message || turn.text || JSON.stringify(turn)),
      timestamp: turn.timestamp || turn.created_at || turn.time || "",
    };
  });
}

function renderAgentTabs() {
  $("agentTabs").innerHTML = AGENTS.map((agent) => `
    <button class="agent-tab ${agent.key === state.activeAgent ? "is-active" : ""}" data-agent="${agent.key}">
      ${escapeHtml(agent.label)}
    </button>
  `).join("");

  $("agentTabs").querySelectorAll("[data-agent]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeAgent = button.dataset.agent;
      state.workflowNote = AGENTS.find((item) => item.key === state.activeAgent)?.description || "";
      saveState();
      render();
      syncSelectedSessionView();
    });
  });
}

function renderStats() {
  const digest = buildSnapshotDigest(state.snapshot);
  const cards = [
    { label: "总病人数", value: digest.total, note: "当前快照中的患者总数" },
    { label: "活跃患者", value: digest.active, note: "未完成流程的患者" },
    { label: "等待中", value: digest.waiting, note: "排队/候诊相关状态" },
    { label: "诊中", value: digest.consultation, note: "会诊中的患者" },
    { label: "检查中", value: digest.testing, note: "检查/处置/回诊链路" },
    { label: "完成/异常", value: `${digest.finished} / ${digest.blocked}`, note: "完成与阻塞状态" },
  ];
  $("statsGrid").innerHTML = renderStatCards(cards);
  $("patientCountHint").textContent = `${digest.total} 名`;
}

function renderCharts() {
  const patients = state.snapshot?.patients || [];
  const visitStateBars = countBy(patients, (item) => item.visit_state || "未知");
  const stagePie = deriveStageGroups(patients);
  const trend = deriveTrendSeries(state.runtimeHistory);

  $("barChart").innerHTML = patients.length
    ? renderBarChart({ title: "visit_state 分布", data: visitStateBars.slice(0, 10) })
    : `<div class="empty-state">暂无病人数据，先连接后端再刷新。</div>`;

  $("pieChart").innerHTML = patients.length
    ? renderPieChart({ title: "display_stage 占比", data: stagePie })
    : `<div class="empty-state">暂无可绘制的阶段数据。</div>`;

  $("lineChart").innerHTML = state.runtimeHistory.length
    ? renderLineChart({ title: "活跃、等待、诊中、检查、完成趋势", series: trend.series })
    : `<div class="empty-state">趋势图会在连续刷新后自动出现。</div>`;
}

function patientStageBadge(patient) {
  const stage = String(patient.display_stage || "未知");
  if (stage === "finished") return "pill";
  if (stage === "error") return "pill pill--danger";
  if (stage.includes("waiting") || stage.includes("pending")) return "pill pill--warning";
  if (stage.includes("consult")) return "pill pill--info";
  return "pill";
}

function renderPatients() {
  const patients = state.snapshot?.patients || [];
  if (!patients.length) {
    $("patientGrid").innerHTML = `<div class="empty-state">还没有患者。你可以先创建就诊，然后用 Agent 流程推进。</div>`;
    return;
  }

  $("patientGrid").innerHTML = patients.map((patient) => {
    const patientId = patient.patient_id || patient.id || "";
    const isSelected = patientId === state.selectedPatientId;
    const pillClass = patientStageBadge(patient);
    const stage = patient.display_stage || "-";
    const dispatchState = patient.dispatch_state || "-";
    const visitState = patient.visit_state || "-";
    const visitId = patient.visit_id || "";
    return `
      <article class="patient-card ${isSelected ? "is-selected" : ""}" data-patient-id="${escapeHtml(patientId)}">
        <div class="patient-card__title">
          <div>
            <strong>${escapeHtml(patient.name || patientId || "Unnamed")}</strong>
            <div class="muted">${escapeHtml(patientId)}</div>
          </div>
          <span class="${pillClass}">${escapeHtml(stage)}</span>
        </div>
        <div class="kv"><strong>科室</strong><span>${escapeHtml(patient.assigned_department_name || "未分配")}</span></div>
        <div class="kv"><strong>visit_state</strong><span>${escapeHtml(visitState)}</span></div>
        <div class="kv"><strong>dispatch_state</strong><span>${escapeHtml(dispatchState)}</span></div>
        <div class="kv"><strong>counterparty</strong><span>${escapeHtml(patient.current_counterparty || patient.active_agent_type || "无")}</span></div>
        <div class="kv"><strong>对话预览</strong><span>${escapeHtml(patient.current_dialogue_preview || "暂无")}</span></div>
        <div class="kv"><strong>visit_id</strong><span>${escapeHtml(visitId || "未创建")}</span></div>
        <div class="patient-card__actions">
          <button class="secondary" data-select-patient="${escapeHtml(patientId)}">选择</button>
          <button class="secondary" data-focus-dialogue="${escapeHtml(patientId)}">查看历史</button>
        </div>
      </article>
    `;
  }).join("");

  $("patientGrid").querySelectorAll("[data-select-patient]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedPatientId = button.dataset.selectPatient || "";
      const selected = findSelectedPatient();
      if (selected?.visit_id) {
        $("patientId").value = selected.patient_id || selected.id || "";
      }
      saveState();
      render();
      await syncSelectedSessionView();
    });
  });

  $("patientGrid").querySelectorAll("[data-focus-dialogue]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedPatientId = button.dataset.focusDialogue || "";
      saveState();
      render();
      await syncSelectedSessionView();
    });
  });
}

function renderEvents() {
  const events = state.events || [];
  if (!events.length) {
    $("eventList").innerHTML = `<div class="empty-state">还没有实时事件。等待后端产生状态变化后这里会自动更新。</div>`;
    return;
  }
  $("eventList").innerHTML = events.map((event) => {
    const title = event.event_type || event.type || event.category || "event";
    const message = event.latest_message || event.message || event.detail || JSON.stringify(event);
    const subject = [event.subject_type, event.subject_id].filter(Boolean).join(":");
    const timestamp = event.timestamp || event.created_at || event.updated_at || "";
    return `
      <article class="event-card">
        <div class="event-card__row">
          <strong>${escapeHtml(title)}</strong>
          <span class="pill">${escapeHtml(event.severity || event.category || "info")}</span>
        </div>
        <div class="muted">${escapeHtml(subject || "unknown subject")}</div>
        <div>${escapeHtml(message)}</div>
        <div class="muted">${escapeHtml(timestamp)}</div>
      </article>
    `;
  }).join("");
}

function renderDialogue() {
  const sceneTurns = normalizeTurns(state.selectedScene?.active_dialogue?.turns || []);
  const turns = normalizeTurns(state.sessionTurns[state.activeAgent] || sceneTurns);
  if (!turns.length) {
    $("dialogueBox").innerHTML = `<div class="empty-state">当前 Agent 还没有会话。先选择病人，然后发送一条消息。</div>`;
    return;
  }
  $("dialogueBox").innerHTML = turns.map((turn) => {
    const role = String(turn.role || "assistant").toLowerCase();
    const isUser = role.includes("user") || role.includes("patient");
    return `
      <div class="message ${isUser ? "message--user" : "message--assistant"}">
        <div class="message__meta">${escapeHtml(turn.role)} ${escapeHtml(turn.timestamp || "")}</div>
        <div>${escapeHtml(turn.content)}</div>
      </div>
    `;
  }).join("");
  $("dialogueBox").scrollTop = $("dialogueBox").scrollHeight;
}

function renderPatientDetail() {
  const patient = findSelectedPatient();
  if (!patient) {
    $("patientDetail").innerHTML = `<div class="empty-state">选择一个病人后，这里会显示病历摘要、最新检查结果和对话历史。</div>`;
    return;
  }

  const scene = state.selectedScene;
  const record = state.selectedRecord;
  const visit = state.selectedVisit;
  const patientLines = [
    `patient_id: ${patient.patient_id || patient.id || "-"}`,
    `visit_id: ${patient.visit_id || "-"}`,
    `visit_state: ${patient.visit_state || "-"}`,
    `display_stage: ${patient.display_stage || "-"}`,
    `dispatch_state: ${patient.dispatch_state || "-"}`,
    `assigned_department_name: ${patient.assigned_department_name || "-"}`,
    `current_counterparty: ${patient.current_counterparty || "-"}`,
    `current_dialogue_preview: ${patient.current_dialogue_preview || "-"}`,
    `consultation_round: ${patient.consultation_round || "-"}`,
  ].join("\n");

  const dialogueTurns = normalizeTurns(scene?.active_dialogue?.turns || []);
  const dialogueHtml = dialogueTurns.length
    ? dialogueTurns.map((turn) => `
      <div class="detail-card">
        <strong>${escapeHtml(turn.role)}</strong>
        <div class="muted">${escapeHtml(turn.timestamp || "")}</div>
        <pre>${escapeHtml(turn.content)}</pre>
      </div>
    `).join("")
    : `<div class="detail-card"><div class="muted">当前没有 scene 对话。</div></div>`;

  const recordSummary = scene?.medical_record_summary
    ? `
      <div class="detail-card">
        <h3>病历摘要</h3>
        <pre>${escapeHtml(JSON.stringify(scene.medical_record_summary, null, 2))}</pre>
      </div>
    `
    : "";

  const testReport = scene?.latest_test_report
    ? `
      <div class="detail-card">
        <h3>最新检查</h3>
        <pre>${escapeHtml(JSON.stringify(scene.latest_test_report, null, 2))}</pre>
      </div>
    `
    : "";

  const visitCard = visit
    ? `
      <div class="detail-card">
        <h3>就诊快照</h3>
        <pre>${escapeHtml(JSON.stringify(visit, null, 2))}</pre>
      </div>
    `
    : "";

  const recordCard = record
    ? `
      <div class="detail-card">
        <h3>诊疗历史</h3>
        <pre>${escapeHtml(JSON.stringify(record, null, 2))}</pre>
      </div>
    `
    : "";

  $("patientDetail").innerHTML = `
    <div class="detail-card">
      <h3>当前患者信息</h3>
      <pre>${escapeHtml(patientLines)}</pre>
    </div>
    ${recordSummary}
    ${testReport}
    ${visitCard}
    ${recordCard}
    <div class="detail-card">
      <h3>场景对话</h3>
      <div class="detail-stack">${dialogueHtml}</div>
    </div>
    <div class="detail-card">
      <h3>UI Flags</h3>
      <pre>${escapeHtml(JSON.stringify(scene?.ui_flags || {}, null, 2))}</pre>
    </div>
  `;
}

function findSelectedPatient() {
  return (state.snapshot?.patients || []).find((patient) => {
    const patientId = patient.patient_id || patient.id || "";
    return patientId && patientId === state.selectedPatientId;
  }) || (state.snapshot?.patients || [])[0] || null;
}

async function choosePatient(patientId) {
  state.selectedPatientId = patientId || "";
  $("patientId").value = state.selectedPatientId;
  saveState();
  render();
  await syncSelectedSessionView();
}

async function ensurePatientSelection() {
  if (state.selectedPatientId) return state.selectedPatientId;
  const selected = findSelectedPatient();
  if (selected) {
    state.selectedPatientId = selected.patient_id || selected.id || "";
    $("patientId").value = state.selectedPatientId;
    saveState();
    return state.selectedPatientId;
  }
  const generated = uniqueId("P").replace("P-", "P-").replace(/[^A-Za-z0-9-]/g, "").slice(0, 10);
  state.selectedPatientId = generated.startsWith("P-") ? generated : `P-${generated.slice(-8).padStart(8, "0")}`;
  $("patientId").value = state.selectedPatientId;
  saveState();
  return state.selectedPatientId;
}

function buildCommonPatientPayload() {
  const selected = findSelectedPatient();
  return {
    patient_id: $("patientId").value.trim() || selected?.patient_id || selected?.id || "",
    name: $("patientName").value.trim() || selected?.name || "星露谷 NPC",
    chief_complaint: $("chiefComplaint").value.trim() || selected?.chief_complaint || "门诊随访",
    symptoms: $("chiefComplaint").value.trim() || selected?.symptoms || "",
    age: Number(selected?.age || 30),
    sex: selected?.sex || "unknown",
    vitals: {
      temp_c: selected?.temp_c ?? 36.6,
      heart_rate: selected?.heart_rate ?? 82,
      systolic_bp: selected?.systolic_bp ?? 118,
      diastolic_bp: selected?.diastolic_bp ?? 76,
      pain_score: selected?.pain_score ?? 2,
    },
    allergies: selected?.allergies || [],
    chronic_conditions: selected?.chronic_conditions || [],
    location: selected?.location || "门诊大厅",
    floor: selected?.floor ?? 1,
  };
}

async function refreshHealth() {
  try {
    state.health = await api.health();
    $("healthText").textContent = [
      `provider=${state.health.active_llm_provider || "-"}`,
      `model=${state.health.llm_model || "-"}`,
      `endpoint=${state.health.llm_endpoint || "-"}`,
      `graph=${state.health.graph_runtime || "-"}`,
    ].join(" | ");
    $("healthCard").querySelector(".status-chip").textContent = state.health.llm_enabled ? "LLM 已启用" : "LLM 未启用";
  } catch (error) {
    $("healthText").textContent = `健康检查失败：${error.message}`;
    $("healthCard").querySelector(".status-chip").textContent = "连接失败";
  }
}

async function refreshSnapshot() {
  const token = ++lastRenderToken;
  try {
    const snapshot = await api.runtimeConsoleSnapshot();
    if (token !== lastRenderToken) return;
    state.snapshot = snapshot;
    state.departments = snapshot?.departments || [];
    state.patients = snapshot?.patients || [];
    state.lastSync = new Date().toLocaleTimeString("zh-CN");
    pushTrendSample(snapshot);
    syncSelectedPatientFromSnapshot();
    await loadSupplementalViews();
    state.workflowNote = `最新同步：${state.lastSync}，共有 ${state.patients.length} 名病人，${state.departments.length} 个科室。`;
    render();
    saveState();
  } catch (error) {
    state.workflowNote = `刷新失败：${error.message}`;
    render();
  }
}

async function refreshEvents() {
  try {
    const events = await api.runtimeConsoleEvents(60);
    state.events = Array.isArray(events) ? events.slice().reverse() : [];
    renderEvents();
  } catch (_error) {
    state.events = state.events || [];
  }
}

async function loadSupplementalViews() {
  const selected = findSelectedPatient();
  if (!selected) {
    state.selectedScene = null;
    state.selectedRecord = null;
    state.selectedVisit = null;
    return;
  }

  const patientId = selected.patient_id || selected.id || state.selectedPatientId;
  const visitId = selected.visit_id || "";
  const requests = [];

  requests.push(api.sceneSnapshot(patientId).then((payload) => {
    state.selectedScene = payload || null;
    const activeDialogue = payload?.active_dialogue;
    const agentType = String(activeDialogue?.agent_type || state.activeAgent || "triage").trim();
    if (activeDialogue?.turns && AGENTS.some((agent) => agent.key === agentType)) {
      state.sessionTurns[agentType] = normalizeTurns(activeDialogue.turns || []);
      if (activeDialogue.session_id) {
        state.sessionIds[agentType] = activeDialogue.session_id;
      }
    }
  }).catch(() => {
    state.selectedScene = null;
  }));

  if (visitId) {
    requests.push(api.medicalRecordTimeline(visitId).then((payload) => {
      state.selectedRecord = payload || null;
    }).catch(() => {
      state.selectedRecord = null;
    }));
    requests.push(api.visit(visitId).then((payload) => {
      state.selectedVisit = payload?.visit || payload || null;
    }).catch(() => {
      state.selectedVisit = null;
    }));
  } else {
    state.selectedRecord = null;
    state.selectedVisit = null;
  }

  await Promise.allSettled(requests);
}

function syncSelectedPatientFromSnapshot() {
  if (!state.snapshot?.patients?.length) return;
  const exists = state.snapshot.patients.some((patient) => (patient.patient_id || patient.id || "") === state.selectedPatientId);
  if (!exists) {
    const first = state.snapshot.patients[0];
    state.selectedPatientId = first?.patient_id || first?.id || "";
    $("patientId").value = state.selectedPatientId;
  }
}

async function syncSelectedSessionView() {
  const patient = findSelectedPatient();
  if (!patient) {
    state.sessionTurns[state.activeAgent] = [];
    renderDialogue();
    renderPatientDetail();
    return;
  }

  const refs = patient.session_refs || {};
  const sessionId = state.sessionIds[state.activeAgent] || refs[`${state.activeAgent}_session_id`] || refs.session_id || refs.triage_session_id || "";
  state.sessionIds[state.activeAgent] = sessionId;

  try {
    if (state.activeAgent === "internal_medicine" && sessionId) {
      const payload = await api.getInternalMedicineSession(sessionId);
      state.sessionTurns.internal_medicine = normalizeTurns(payload?.dialogue?.turns || []);
      state.workflowNote = `内科会诊会话已同步：${sessionId}`;
    } else if (state.activeAgent === "surgery" && sessionId) {
      const payload = await api.getSurgerySession(sessionId);
      state.sessionTurns.surgery = normalizeTurns(payload?.dialogue?.turns || []);
      state.workflowNote = `外科会诊会话已同步：${sessionId}`;
    } else if (state.activeAgent === "icu" && sessionId) {
      const payload = await api.getIcuSession(sessionId);
      state.sessionTurns.icu = normalizeTurns(payload?.dialogue?.turns || []);
      state.workflowNote = `ICU 会诊会话已同步：${sessionId}`;
    }
    if (state.activeAgent === "triage" && sessionId) {
      state.workflowNote = `分诊会话已存在：${sessionId}`;
    }
  } catch (error) {
    state.workflowNote = `会话同步失败：${error.message}`;
  }

  render();
}

async function createOrGetVisit() {
  const payload = {
    patient_id: $("patientId").value.trim(),
    name: $("patientName").value.trim() || "星露谷 NPC",
  };
  if (!payload.patient_id) {
    throw new Error("请先填写患者 ID");
  }
  const result = await api.createVisit(payload);
  const visit = result?.visit || result;
  state.selectedVisit = visit;
  const selected = findSelectedPatient();
  if (selected) {
    selected.visit_id = visit?.id || visit?.visit_id || selected.visit_id;
  }
  state.workflowNote = `已创建/获取就诊：${visit?.id || visit?.visit_id || "-"}`;
  await refreshSnapshot();
  return visit;
}

async function ensureVisitForConsultation() {
  const selected = findSelectedPatient();
  const visitId = selected?.visit_id || state.selectedVisit?.id || state.selectedVisit?.visit_id;
  if (visitId) return visitId;
  const visit = await createOrGetVisit();
  return visit?.id || visit?.visit_id || "";
}

async function registerFlowStep() {
  const visitId = await ensureVisitForConsultation();
  if (!visitId) throw new Error("没有可用的 visit");
  const result = await api.registerVisit(visitId, {
    name: $("patientName").value.trim() || "星露谷 NPC",
    sex: "unknown",
    age: 30,
    id_number: `TEMP-${Date.now().toString().slice(-8)}`,
  });
  state.workflowNote = `挂号完成：${visitId}`;
  return result;
}

async function progressFlowStep() {
  const visitId = await ensureVisitForConsultation();
  const result = await api.progressVisit(visitId);
  state.workflowNote = `排队推进完成：${visitId}`;
  return result;
}

async function enterConsultationFlowStep() {
  const visitId = await ensureVisitForConsultation();
  const result = await api.enterConsultation(visitId);
  state.workflowNote = `已进入诊室：${visitId}`;
  return result;
}

async function readyPaymentFlowStep() {
  const visitId = await ensureVisitForConsultation();
  const result = await api.readyPayment(visitId);
  state.workflowNote = `已标记可缴费：${visitId}`;
  return result;
}

function buildAgentPayload(agentKey) {
  const patient = findSelectedPatient();
  const common = buildCommonPatientPayload();
  const visitId = patient?.visit_id || state.selectedVisit?.id || state.selectedVisit?.visit_id || "";
  switch (agentKey) {
    case "triage":
      return {
        patient_id: common.patient_id,
        visit_id: visitId || undefined,
        session_id: state.sessionIds.triage || undefined,
        name: common.name,
        chief_complaint: common.chief_complaint,
        symptoms: common.symptoms,
        age: common.age,
        sex: common.sex,
        vitals: common.vitals,
        allergies: common.allergies,
        chronic_conditions: common.chronic_conditions,
        location: common.location,
        floor: common.floor,
      };
    case "internal_medicine":
    case "surgery":
      return {
        patient_id: common.patient_id,
        visit_id: visitId || undefined,
        session_id: state.sessionIds[agentKey] || undefined,
        name: common.name,
        chief_complaint: common.chief_complaint,
        symptoms: common.symptoms,
        age: common.age,
        sex: common.sex,
        vitals: common.vitals,
        allergies: common.allergies,
        chronic_conditions: common.chronic_conditions,
        location: common.location,
        floor: common.floor,
        round: patient?.consultation_round || undefined,
      };
    case "icu":
      return {
        patient_id: common.patient_id,
        session_id: state.sessionIds.icu || undefined,
        name: common.name,
        chief_complaint: common.chief_complaint,
        symptoms: common.symptoms,
        age: common.age,
        sex: common.sex,
        vitals: {
          ...common.vitals,
          spo2: 98,
          respiratory_rate: 18,
        },
        allergies: common.allergies,
        chronic_conditions: common.chronic_conditions,
        registration_info: {},
        location: "ICU",
        floor: 2,
      };
    default:
      return common;
  }
}

function setSessionTurns(agentKey, response) {
  const dialogue = response?.dialogue || {};
  const turns = normalizeTurns(dialogue.turns || []);
  state.sessionTurns[agentKey] = turns;
  const sessionId = response?.session_id || response?.sessionId || state.sessionIds[agentKey];
  if (sessionId) {
    state.sessionIds[agentKey] = sessionId;
  }
  state.workflowNote = dialogue.assistant_message || state.workflowNote;
}

async function ensureAgentSession(agentKey) {
  const patient = findSelectedPatient();
  if (!patient) {
    throw new Error("请先选择一个患者");
  }
  const payload = buildAgentPayload(agentKey);
  if (!payload.patient_id) {
    throw new Error("请先填写患者 ID");
  }

  if (agentKey !== "triage") {
    payload.visit_id = payload.visit_id || await ensureVisitForConsultation();
  }

  switch (agentKey) {
    case "triage":
      if (!state.sessionIds.triage) {
        const response = await api.createTriageSession(payload);
        setSessionTurns("triage", response);
      }
      return state.sessionIds.triage;
    case "internal_medicine":
      if (!state.sessionIds.internal_medicine) {
        const response = await api.createInternalMedicineSession(payload);
        setSessionTurns("internal_medicine", response);
      }
      return state.sessionIds.internal_medicine;
    case "surgery":
      if (!state.sessionIds.surgery) {
        const response = await api.createSurgerySession(payload);
        setSessionTurns("surgery", response);
      }
      return state.sessionIds.surgery;
    case "icu":
      if (!state.sessionIds.icu) {
        const response = await api.createIcuSession(payload);
        setSessionTurns("icu", response);
      }
      return state.sessionIds.icu;
    default:
      throw new Error(`不支持的 agent: ${agentKey}`);
  }
}

async function sendCurrentMessage() {
  const message = $("messageInput").value.trim();
  if (!message) return;
  await ensurePatientSelection();
  const agentKey = state.activeAgent;
  const sessionId = await ensureAgentSession(agentKey);
  const payload = { message, name: $("patientName").value.trim() || "星露谷 NPC" };
  if (agentKey !== "icu") {
    payload.visit_id = state.selectedVisit?.id || state.selectedVisit?.visit_id || findSelectedPatient()?.visit_id || undefined;
  }
  payload.patient_id = $("patientId").value.trim();

  let response;
  if (agentKey === "triage") {
    response = await api.sendTriageMessage(sessionId, payload);
  } else if (agentKey === "internal_medicine") {
    response = await api.sendInternalMedicineMessage(sessionId, payload);
  } else if (agentKey === "surgery") {
    response = await api.sendSurgeryMessage(sessionId, payload);
  } else if (agentKey === "icu") {
    response = await api.sendIcuMessage(sessionId, payload);
  }
  setSessionTurns(agentKey, response);
  $("messageInput").value = "";
  state.workflowNote = `消息已发送到 ${currentAgent().label}。`;
  await refreshSnapshot();
  render();
}

async function resetActiveSession() {
  state.sessionIds[state.activeAgent] = "";
  state.sessionTurns[state.activeAgent] = [];
  state.workflowNote = `已清空 ${currentAgent().label} 会话缓存。`;
  saveState();
  render();
}

async function refreshAll() {
  await Promise.allSettled([
    refreshHealth(),
    refreshSnapshot(),
    refreshEvents(),
  ]);
}

function stopLiveStream() {
  if (streamAbortController) {
    streamAbortController.abort();
    streamAbortController = null;
  }
}

async function streamEvents() {
  stopLiveStream();
  streamAbortController = new AbortController();
  state.sseState = "连接中";
  render();
  try {
    const response = await fetch(`${api.getBaseUrl()}/api/v1/events/stream`, {
      signal: streamAbortController.signal,
      headers: { Accept: "text/event-stream" },
    });
    if (!response.ok || !response.body) throw new Error(`SSE ${response.status}`);
    state.sseState = "已连接";
    render();
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (state.live) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let splitIndex = buffer.indexOf("\n\n");
      while (splitIndex >= 0) {
        const packet = buffer.slice(0, splitIndex);
        buffer = buffer.slice(splitIndex + 2);
        handleSsePacket(packet);
        splitIndex = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    if (error?.name !== "AbortError") {
      state.sseState = `重连中：${error.message}`;
      render();
      setTimeout(() => {
        if (state.live) streamEvents();
      }, 2500);
    }
  }
}

function handleSsePacket(packet) {
  const lines = packet.split(/\r?\n/);
  const dataLine = lines.find((line) => line.startsWith("data:"));
  if (!dataLine) return;
  const raw = dataLine.slice(5).trim();
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    state.events.unshift({
      ...parsed,
      timestamp: parsed.timestamp || parsed.created_at || new Date().toISOString(),
    });
    state.events = state.events.slice(0, 60);
    scheduleRefresh();
  } catch (_error) {
    state.events.unshift({
      event_type: "stream",
      latest_message: raw,
      timestamp: new Date().toISOString(),
    });
    state.events = state.events.slice(0, 60);
    scheduleRefresh();
  }
}

function scheduleRefresh() {
  if (pendingRefresh) return;
  pendingRefresh = setTimeout(async () => {
    pendingRefresh = null;
    await refreshSnapshot();
    await refreshEvents();
  }, 800);
}

function bindActions() {
  $("connectBtn").addEventListener("click", async () => {
    state.backendUrl = $("backendUrl").value.trim() || state.backendUrl;
    api = createHospitalApi(state.backendUrl);
    saveState();
    await refreshAll();
    if (state.live) {
      await streamEvents();
    }
  });

  $("refreshBtn").addEventListener("click", async () => {
    await refreshAll();
  });

  $("liveToggleBtn").addEventListener("click", async () => {
    state.live = !state.live;
    saveState();
    $("liveToggleBtn").textContent = `实时更新：${state.live ? "开" : "关"}`;
    if (state.live) {
      await streamEvents();
    } else {
      stopLiveStream();
    }
    render();
  });

  $("createVisitBtn").addEventListener("click", async () => {
    try {
      await ensurePatientSelection();
      await createOrGetVisit();
      await syncSelectedSessionView();
    } catch (error) {
      state.workflowNote = error.message;
      render();
    }
  });

  $("prepareVisitBtn").addEventListener("click", async () => {
    try {
      await createOrGetVisit();
      await syncSelectedSessionView();
    } catch (error) {
      state.workflowNote = error.message;
      render();
    }
  });

  $("triageBtn").addEventListener("click", async () => {
    state.activeAgent = "triage";
    saveState();
    render();
    await syncSelectedSessionView();
  });

  $("registerBtn").addEventListener("click", async () => {
    try {
      await registerFlowStep();
      await refreshAll();
    } catch (error) {
      state.workflowNote = `挂号失败：${error.message}`;
      render();
    }
  });

  $("progressBtn").addEventListener("click", async () => {
    try {
      await progressFlowStep();
      await refreshAll();
    } catch (error) {
      state.workflowNote = `推进失败：${error.message}`;
      render();
    }
  });

  $("enterConsultBtn").addEventListener("click", async () => {
    try {
      await enterConsultationFlowStep();
      await refreshAll();
    } catch (error) {
      state.workflowNote = `进入诊室失败：${error.message}`;
      render();
    }
  });

  $("paymentBtn").addEventListener("click", async () => {
    try {
      await readyPaymentFlowStep();
      await refreshAll();
    } catch (error) {
      state.workflowNote = `结算失败：${error.message}`;
      render();
    }
  });

  $("sendBtn").addEventListener("click", async () => {
    try {
      await sendCurrentMessage();
    } catch (error) {
      state.workflowNote = `发送失败：${error.message}`;
      render();
    }
  });

  $("messageInput").addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      await sendCurrentMessage();
    }
  });

  $("resetSessionBtn").addEventListener("click", async () => {
    await resetActiveSession();
  });

  $("backendUrl").addEventListener("change", () => {
    state.backendUrl = $("backendUrl").value.trim() || state.backendUrl;
    api = createHospitalApi(state.backendUrl);
    saveState();
  });

  $("patientId").addEventListener("change", async () => {
    state.selectedPatientId = $("patientId").value.trim();
    saveState();
    await syncSelectedSessionView();
  });

  $("patientName").addEventListener("change", saveState);
  $("chiefComplaint").addEventListener("change", saveState);
}

function render() {
  updateInputs();
  renderAgentTabs();
  renderStats();
  renderCharts();
  renderPatients();
  renderEvents();
  renderDialogue();
  renderPatientDetail();
  $("sessionStateLabel").textContent = sessionStatusText();
  $("workflowNote").textContent = `${state.workflowNote} | SSE: ${state.sseState}`;
}

async function bootstrap() {
  loadState();
  api = createHospitalApi(state.backendUrl);
  state.workflowNote = AGENTS.find((agent) => agent.key === state.activeAgent)?.description || state.workflowNote;
  bindActions();
  updateInputs();
  render();
  await refreshAll();
  if (state.live) {
    await streamEvents();
  }
  clearInterval(pollTimer);
  clearInterval(eventsTimer);
  pollTimer = setInterval(() => {
    if (state.live) scheduleRefresh();
  }, 3000);
  eventsTimer = setInterval(() => {
    if (state.live) refreshEvents();
  }, 6000);
}

window.addEventListener("beforeunload", () => {
  stopLiveStream();
  clearInterval(pollTimer);
  clearInterval(eventsTimer);
  if (pendingRefresh) {
    clearTimeout(pendingRefresh);
  }
  saveState();
});

bootstrap().catch((error) => {
  $("healthText").textContent = `启动失败：${error.message}`;
  $("healthCard").querySelector(".status-chip").textContent = "初始化失败";
});
