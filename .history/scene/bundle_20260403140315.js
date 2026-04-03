const TILE = 32;
const WALL_THICKNESS = TILE * 0.5;
const DOOR_THICKNESS = 12;
const WALL_HEIGHT = 58;
const FLOOR_HEIGHT = 170;
const DOOR_SENSOR_DISTANCE = 64;
const DOOR_CLOSE_DISTANCE = 96;
const STAIR_TRIGGER_COOLDOWN_MS = 3000;
const ISO_X = 0.92;
const ISO_Y = 0.48;
const CHARACTER_FOOT_RADIUS = 7;
const CHARACTER_BODY_HEIGHT = 32;
const CHARACTER_HEAD_RADIUS = 8;
const WORLD = { width: 52 * TILE, height: 36 * TILE };
const FLOOR_BASE_Z = { 1: 0, 2: FLOOR_HEIGHT };

const palette = {
  roomFloor: "#705970",
  hallFloor: "#8a7188",
  wallFront: "#593b56",
  wallSide: "#4a3047",
  wallTop: "#866783",
  wallEdge: "rgba(255, 225, 255, 0.18)",
  bed: "#7db1c4",
  desk: "#6d4b35",
  sofa: "#816b4b",
  plant: "#6fa26b",
  screen: "#7fe0dc",
  cabinet: "#8b6b89",
  reception: "#865c74",
  doorFrame: "#8aa5b6",
  doorGlass: "rgba(141, 233, 255, 0.32)",
  doorSensor: "#4ce4ff",
  playerBody: "#2f8fb0",
  playerHead: "#f6d4c0",
  playerLeg: "#28465a",
  shadow: "rgba(0, 0, 0, 0.26)",
  label: "rgba(248, 233, 252, 0.82)",
  inactiveMask: "rgba(7, 7, 12, 0.62)",
};

const INTERNAL_MEDICINE_RAG = `
## 内科医学知识库

### 常见内科疾病及症状

**1. 呼吸道感染**
- 普通感冒：鼻塞、流涕、咽痛、咳嗽、发热
- 流感：高热（39-40℃）、头痛、肌肉酸痛、乏力
- 支气管炎：咳嗽、咳痰（黄痰或白痰）、喘息

**2. 消化系统疾病**
- 急性胃炎：上腹疼痛、恶心、呕吐、食欲不振
- 慢性胃炎：上腹隐痛、反酸、嗳气、腹胀
- 胃溃疡：周期性上腹疼痛、餐后痛、黑便
- 急性肠炎：腹泻（稀水便）、腹痛、恶心、发热

**3. 心血管疾病**
- 高血压：头痛、头晕、耳鸣、视力模糊，常无症状
- 冠心病：胸痛（心绞痛）、胸闷、气短
- 心律失常：心悸、心跳不规则、乏力、头晕

**4. 内分泌疾病**
- 糖尿病：多饮、多尿、多食、体重下降、皮肤瘙痒
- 甲状腺功能亢进：心悸、多汗、消瘦、情绪激动、手抖
- 甲状腺功能减退：乏力、嗜睡、怕冷、体重增加

**5. 神经系统疾病**
- 头痛：偏头痛、紧张性头痛、丛集性头痛
- 眩晕：良性阵发性位置性眩晕、梅尼埃病
- 脑供血不足：头晕、记忆力下降、肢体麻木

**6. 泌尿系统疾病**
- 尿路感染：尿频、尿急、尿痛、下腹疼痛
- 肾炎：血尿、蛋白尿、水肿、高血压

**7. 血液系统疾病**
- 贫血：乏力、头晕、心悸、面色苍白

### 诊断流程
1. 询问病史：症状起始时间、持续时间、严重程度、伴随症状
2. 体格检查：体温、血压、心肺听诊、腹部触诊
3. 辅助检查：血常规、尿常规、心电图、X光、超声等

### 治疗原则
1. 对症治疗：缓解症状
2. 病因治疗：根治病因
3. 一般治疗：休息、饮食调理
4. 药物治疗：遵医嘱按时服药
5. 随访复查：定期复查评估疗效
`;

const PROXY_URL = "http://localhost:8000/api/chat";

async function callChatAPI(message, model = "deepseek", imageData = null) {
  const payload = { message, model };
  if (imageData) payload.image = imageData;

  const response = await fetch(PROXY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || `API Error: ${response.status}`);
  }

  const data = await response.json();
  return data.response || "抱歉，我没有收到回复。";
}

function createUserMessage(content) {
  return { role: "user", content };
}

function createAssistantMessage(content) {
  return { role: "assistant", content };
}

const NPC_TYPES = {
  NURSE: "nurse",
  PATIENT: "patient",
  DOCTOR: "doctor",
  PHARMACIST: "pharmacist",
};

const NPC_STATES = {
  IDLE: "idle",
  WALKING: "walking",
  WAITING: "waiting",
  IN_CONVERSATION: "in_conversation",
  IN_TREATMENT: "in_treatment",
};

function createNPC(id, type, x, y, floor, config = {}) {
  return {
    id,
    type,
    x: x * TILE,
    y: y * TILE,
    floor,
    width: CHARACTER_FOOT_RADIUS * 2,
    height: CHARACTER_FOOT_RADIUS * 2,
    speed: type === NPC_TYPES.PATIENT ? 60 : 40,
    state: NPC_STATES.IDLE,
    targetX: null,
    targetY: null,
    name: config.name || getDefaultName(type),
    department: config.department || null,
    ticket: null,
    conversationHistory: [],
    walkTimer: 0,
    walkInterval: 3000 + Math.random() * 4000,
    bodyColor: getBodyColor(type),
    headColor: getHeadColor(type),
    ...config,
  };
}

function getDefaultName(type) {
  const names = {
    [NPC_TYPES.NURSE]: "护士小李",
    [NPC_TYPES.PATIENT]: "患者",
    [NPC_TYPES.DOCTOR]: "医生",
    [NPC_TYPES.PHARMACIST]: "药师",
  };
  return names[type] || "NPC";
}

function getBodyColor(type) {
  const colors = {
    [NPC_TYPES.NURSE]: "#e88fb0",
    [NPC_TYPES.PATIENT]: "#a8d8a8",
    [NPC_TYPES.DOCTOR]: "#7eb8da",
    [NPC_TYPES.PHARMACIST]: "#c9a8e8",
  };
  return colors[type] || "#888888";
}

function getHeadColor(type) {
  const colors = {
    [NPC_TYPES.NURSE]: "#f6d4c0",
    [NPC_TYPES.PATIENT]: "#f6d4c0",
    [NPC_TYPES.DOCTOR]: "#f6d4c0",
    [NPC_TYPES.PHARMACIST]: "#f6d4c0",
  };
  return colors[type] || "#f6d4c0";
}

function updateNPC(npc, delta, staticCollisions, doors, walkableBounds) {
  npc.walkTimer += delta * 1000;

  switch (npc.state) {
    case NPC_STATES.IDLE:
      if (npc.walkTimer >= npc.walkInterval) {
        startRandomWalk(npc, walkableBounds);
      }
      break;

    case NPC_STATES.WALKING:
      moveTowardTarget(npc, delta, staticCollisions, doors);
      break;

    case NPC_STATES.WAITING:
    case NPC_STATES.IN_CONVERSATION:
    case NPC_STATES.IN_TREATMENT:
      break;
  }
}

function startRandomWalk(npc, walkableBounds) {
  if (!walkableBounds || walkableBounds.length === 0) {
    npc.walkTimer = 0;
    npc.walkInterval = 3000 + Math.random() * 4000;
    return;
  }

  const bound = walkableBounds[Math.floor(Math.random() * walkableBounds.length)];
  const targetX = bound.x + Math.random() * bound.w;
  const targetY = bound.y + Math.random() * bound.h;

  npc.targetX = targetX;
  npc.targetY = targetY;
  npc.state = NPC_STATES.WALKING;
  npc.walkTimer = 0;
}

function moveTowardTarget(npc, delta, staticCollisions, doors) {
  if (npc.targetX === null || npc.targetY === null) {
    npc.state = NPC_STATES.IDLE;
    npc.walkTimer = 0;
    return;
  }

  const dx = npc.targetX - npc.x;
  const dy = npc.targetY - npc.y;
  const distance = Math.hypot(dx, dy);

  if (distance < 5) {
    npc.x = npc.targetX;
    npc.y = npc.targetY;
    npc.state = NPC_STATES.IDLE;
    npc.targetX = null;
    npc.targetY = null;
    npc.walkTimer = 0;
    npc.walkInterval = 3000 + Math.random() * 4000;
    return;
  }

  const moveX = (dx / distance) * npc.speed * delta;
  const moveY = (dy / distance) * npc.speed * delta;

  const nextX = npc.x + moveX;
  const nextY = npc.y + moveY;

  if (canNPCMoveTo(nextX, nextY, npc.floor, staticCollisions, doors)) {
    npc.x = nextX;
    npc.y = nextY;
  } else {
    npc.state = NPC_STATES.IDLE;
    npc.targetX = null;
    npc.targetY = null;
    npc.walkTimer = 0;
  }
}

function canNPCMoveTo(x, y, floor, staticCollisions, doors) {
  const foot = { x, y, r: CHARACTER_FOOT_RADIUS };
  const collisions = [
    ...staticCollisions.filter((item) => item.floor === floor),
    ...doors.filter((door) => door.floor === floor && !door.open).map((door) => door.collider),
  ];

  return !collisions.some((wall) => {
    const closestX = Math.max(wall.x, Math.min(foot.x, wall.x + wall.w));
    const closestY = Math.max(wall.y, Math.min(foot.y, wall.y + wall.h));
    const distanceSq = (foot.x - closestX) ** 2 + (foot.y - closestY) ** 2;
    return distanceSq < foot.r * foot.r;
  });
}

function drawNPC(ctx, npc, project, drawQuad, makePrismFaces) {
  const base = project(npc.x, npc.y, 0, npc.floor);
  const top = project(npc.x, npc.y, CHARACTER_BODY_HEIGHT, npc.floor);

  ctx.fillStyle = palette.shadow;
  ctx.beginPath();
  ctx.ellipse(base.x, base.y + 9, CHARACTER_FOOT_RADIUS + 4, CHARACTER_FOOT_RADIUS, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = palette.playerLeg;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(base.x - 4, base.y + 2);
  ctx.lineTo(base.x - 6, base.y + 14);
  ctx.moveTo(base.x + 4, base.y + 2);
  ctx.lineTo(base.x + 6, base.y + 14);
  ctx.stroke();

  ctx.strokeStyle = npc.bodyColor;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(base.x, base.y - 2);
  ctx.lineTo(top.x, top.y + 6);
  ctx.stroke();

  ctx.fillStyle = npc.headColor;
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, CHARACTER_HEAD_RADIUS, 0, Math.PI * 2);
  ctx.fill();

  if (npc.state === NPC_STATES.IN_CONVERSATION || npc.state === NPC_STATES.WAITING) {
    const labelPoint = project(npc.x, npc.y, CHARACTER_BODY_HEIGHT + 20, npc.floor);
    ctx.fillStyle = "rgba(22, 15, 28, 0.88)";
    const labelWidth = ctx.measureText(npc.name).width + 16;
    ctx.fillRect(labelPoint.x - labelWidth / 2, labelPoint.y - 10, labelWidth, 18);
    ctx.fillStyle = "#fff";
    ctx.font = "11px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText(npc.name, labelPoint.x, labelPoint.y + 3);
  }

  if (npc.ticket) {
    const ticketPoint = project(npc.x + 10, npc.y - 10, CHARACTER_BODY_HEIGHT + 10, npc.floor);
    ctx.fillStyle = "#ffeb3b";
    ctx.beginPath();
    ctx.arc(ticketPoint.x, ticketPoint.y, 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#000";
    ctx.font = "bold 10px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText(npc.ticket.number, ticketPoint.x, ticketPoint.y + 3);
  }
}

function initNPCs() {
  return [
    createNPC("nurse-1", NPC_TYPES.NURSE, 24.5, 16, 1, { name: "护士小李", state: NPC_STATES.IDLE }),
    createNPC("nurse-2", NPC_TYPES.NURSE, 7, 17.5, 1, { name: "护士小王", state: NPC_STATES.IDLE }),
    createNPC("doctor-1", NPC_TYPES.DOCTOR, 20, 6, 1, { name: "内科医生", department: "内科", state: NPC_STATES.IDLE }),
    createNPC("doctor-2", NPC_TYPES.DOCTOR, 33, 6, 1, { name: "外科医生", department: "外科", state: NPC_STATES.IDLE }),
    createNPC("pharmacist-1", NPC_TYPES.PHARMACIST, 40, 17, 1, { name: "药师老张", state: NPC_STATES.IDLE }),
    createNPC("patient-1", NPC_TYPES.PATIENT, 25, 17, 1, { name: "患者甲", state: NPC_STATES.IDLE }),
    createNPC("patient-2", NPC_TYPES.PATIENT, 27, 18, 1, { name: "患者乙", state: NPC_STATES.IDLE }),
    createNPC("patient-3", NPC_TYPES.PATIENT, 23, 18, 1, { name: "患者丙", state: NPC_STATES.IDLE }),
    createNPC("patient-4", NPC_TYPES.PATIENT, 30, 16, 1, { name: "患者丁", state: NPC_STATES.IDLE }),
    createNPC("patient-5", NPC_TYPES.PATIENT, 15, 17, 1, { name: "患者戊", state: NPC_STATES.IDLE }),
  ];
}

function getWalkableBounds(rooms) {
  return rooms
    .filter((room) => room.kind === "hall" || room.kind === "triage")
    .map((room) => ({
      x: room.x * TILE + TILE,
      y: room.y * TILE + TILE,
      w: room.w * TILE - TILE * 2,
      h: room.h * TILE - TILE * 2,
    }));
}

const QUEUE_DEPARTMENTS = {
  INTERNAL: { id: "internal", name: "内科", roomKind: "consultation" },
  SURGERY: { id: "surgery", name: "外科", roomKind: "consultation" },
  PEDIATRICS: { id: "pediatrics", name: "儿科", roomKind: "consultation" },
  EMERGENCY: { id: "emergency", name: "急诊", roomKind: "triage", priority: true },
  EYE: { id: "eye", name: "眼科", roomKind: "consultation" },
  ORTHO: { id: "ortho", name: "骨科", roomKind: "consultation" },
  PHARMACY: { id: "pharmacy", name: "药房", roomKind: "pharmacy" },
  LAB: { id: "lab", name: "检验科", roomKind: "lab" },
};

function createQueueManager() {
  const deptIds = Object.values(QUEUE_DEPARTMENTS).map((d) => d.id);
  return {
    queues: Object.fromEntries(deptIds.map((id) => [id, []])),
    currentTicket: Object.fromEntries(deptIds.map((id) => [id, 0])),
    calledTicket: Object.fromEntries(deptIds.map((id) => [id, null])),
    calledUntil: Object.fromEntries(deptIds.map((id) => [id, 0])),
    lastCallAt: Object.fromEntries(deptIds.map((id) => [id, 0])),
    history: [],
    playerTicket: null,
  };
}

function generateTicketNumber(queueManager, departmentId) {
  queueManager.currentTicket[departmentId]++;
  const ticketNum = queueManager.currentTicket[departmentId];
  return {
    number: ticketNum,
    departmentId,
    departmentName: QUEUE_DEPARTMENTS[departmentId].name,
    timestamp: Date.now(),
    status: "waiting",
  };
}

function addToQueue(queueManager, npc, departmentId) {
  if (npc.type !== NPC_TYPES.PATIENT) return null;

  const ticket = generateTicketNumber(queueManager, departmentId);
  ticket.patientId = npc.id;
  npc.ticket = ticket;
  npc.state = "waiting";

  queueManager.queues[departmentId].push(ticket);

  return ticket;
}

function addPlayerToQueue(queueManager, departmentId) {
  const ticket = generateTicketNumber(queueManager, departmentId);
  ticket.patientId = "player";
  queueManager.playerTicket = ticket;
  queueManager.queues[departmentId].push(ticket);
  return ticket;
}

function callNext(queueManager, departmentId) {
  const queue = queueManager.queues[departmentId];
  if (queue.length === 0) return null;

  const emergencyQueue = queueManager.queues.emergency;
  if (departmentId !== "emergency" && emergencyQueue.length > 0) {
    return callNext(queueManager, "emergency");
  }

  const ticket = queue.shift();
  ticket.status = "called";
  queueManager.calledTicket[departmentId] = ticket;
  const now = Date.now();
  const isPlayer = ticket.patientId === "player";
  queueManager.calledUntil[departmentId] = now + (isPlayer ? 120000 : 5000);
  queueManager.lastCallAt[departmentId] = now;

  return ticket;
}

function completeTicket(queueManager, departmentId, ticket) {
  if (ticket) {
    ticket.status = "completed";
    queueManager.history.push(ticket);
    queueManager.calledTicket[departmentId] = null;
  }
}

function updateQueueCalls(queueManager, nowMs) {
  for (const dept of Object.values(QUEUE_DEPARTMENTS)) {
    const deptId = dept.id;
    const called = queueManager.calledTicket[deptId];
    if (called && nowMs >= queueManager.calledUntil[deptId]) {
      completeTicket(queueManager, deptId, called);
    }
    if (!queueManager.calledTicket[deptId] && queueManager.queues[deptId].length > 0) {
      if (nowMs - queueManager.lastCallAt[deptId] >= 5000) {
        callNext(queueManager, deptId);
      }
    }
  }
}

function getQueuePosition(queueManager, ticket) {
  const queue = queueManager.queues[ticket.departmentId];
  const index = queue.findIndex((t) => t.number === ticket.number && t.patientId === ticket.patientId);
  return index >= 0 ? index + 1 : null;
}

function getWaitingCount(queueManager, departmentId) {
  return queueManager.queues[departmentId].length;
}

function isAnyQueueEmpty(queueManager) {
  return Object.values(queueManager.queues).some((queue) => queue.length === 0);
}

function drawQueueBoard(ctx, canvas, queueManager, playerDeptId = null) {
  const panelWidth = 300;
  const panelHeight = 240;
  const panelX = canvas.width - panelWidth - 18;
  const panelY = canvas.height - panelHeight - 18;

  ctx.fillStyle = "rgba(16, 11, 24, 0.92)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(110, 232, 255, 0.72)";
  ctx.lineWidth = 2;
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.fillStyle = "#a8f8ff";
  ctx.font = "bold 14px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("排队叫号显示", panelX + panelWidth / 2, panelY + 22);

  const departments = Object.values(QUEUE_DEPARTMENTS);
  const rowHeight = 28;
  let y = panelY + 48;

  for (const dept of departments) {
    const waiting = getWaitingCount(queueManager, dept.id);
    const called = queueManager.calledTicket[dept.id];
    const calledNum = called ? `【${called.number}】` : "---";
    const isPlayerDept = playerDeptId === dept.id;

    if (isPlayerDept) {
      ctx.fillStyle = "rgba(131, 255, 201, 0.15)";
      ctx.fillRect(panelX + 6, y - 14, panelWidth - 12, 22);
    }

    ctx.textAlign = "left";
    ctx.font = "12px 'Segoe UI'";
    ctx.fillStyle = dept.priority ? "#ff6b6b" : "#f2ebff";
    ctx.fillText(`${isPlayerDept ? "★ " : ""}${dept.name}`, panelX + 12, y);

    ctx.textAlign = "right";
    ctx.fillStyle = "#83ffc9";
    ctx.fillText(`等待: ${waiting}人`, panelX + panelWidth - 100, y);

    ctx.fillStyle = "#ffeb3b";
    ctx.fillText(`叫号: ${calledNum}`, panelX + panelWidth - 12, y);

    y += rowHeight;
  }
}

function drawRegistrationPanel(ctx, canvas, player, nearbyNPC) {
  if (!nearbyNPC || nearbyNPC.type !== NPC_TYPES.NURSE) return;

  const panelWidth = 300;
  const panelHeight = 180;
  const panelX = (canvas.width - panelWidth) / 2;
  const panelY = canvas.height / 2 - panelHeight / 2 - 50;

  ctx.fillStyle = "rgba(16, 11, 24, 0.95)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(255, 182, 193, 0.8)";
  ctx.lineWidth = 2;
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.fillStyle = "#ffb6c1";
  ctx.font = "bold 16px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("💉 挂号窗口 - 请选择科室", panelX + panelWidth / 2, panelY + 28);

  const departments = [
    { key: "internal", label: "1. 内科", color: "#7eb8da" },
    { key: "surgery", label: "2. 外科", color: "#da7e7e" },
    { key: "pediatrics", label: "3. 儿科", color: "#b8da7e" },
    { key: "emergency", label: "4. 急诊", color: "#ff6b6b" },
  ];

  let y = panelY + 60;
  for (const dept of departments) {
    ctx.fillStyle = "#f2ebff";
    ctx.font = "14px 'Segoe UI'";
    ctx.textAlign = "left";
    ctx.fillText(dept.label, panelX + 20, y);

    ctx.fillStyle = dept.color;
    ctx.font = "11px 'Segoe UI'";
    ctx.fillText(QUEUE_DEPARTMENTS[dept.key].name, panelX + 100, y);
    y += 28;
  }

  ctx.fillStyle = "#cfc6db";
  ctx.font = "11px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("按数字键 1-4 选择科室，或按 E 与护士对话", panelX + panelWidth / 2, panelY + panelHeight - 12);
}

function createDialogSystem() {
  return {
    isOpen: false,
    currentNPC: null,
    messages: [],
    inputText: "",
    isLoading: false,
    conversationContexts: {},
    recommendedDepts: [],
    buttonRects: [],
  };
}

function openDialog(dialogSystem, npc) {
  dialogSystem.isOpen = true;
  dialogSystem.currentNPC = npc;
  dialogSystem.inputText = "";
  dialogSystem.recommendedDepts = [];
  dialogSystem.buttonRects = [];

  if (!dialogSystem.conversationContexts[npc.id]) {
    dialogSystem.conversationContexts[npc.id] = [];
  }

  npc.state = "in_conversation";
}

function closeDialog(dialogSystem) {
  if (dialogSystem.currentNPC) {
    dialogSystem.currentNPC.state = "idle";
  }
  dialogSystem.isOpen = false;
  dialogSystem.currentNPC = null;
  dialogSystem.inputText = "";
  dialogSystem.recommendedDepts = [];
  dialogSystem.buttonRects = [];
}

function addMessage(dialogSystem, role, content) {
  dialogSystem.messages.push({ role, content, timestamp: Date.now() });
}

function getConversationHistory(dialogSystem, npcId) {
  return dialogSystem.conversationContexts[npcId] || [];
}

function saveConversation(dialogSystem, npcId, messages) {
  dialogSystem.conversationContexts[npcId] = messages;
}

function buildContextMessage(dialogSystem, npcId) {
  const history = getConversationHistory(dialogSystem, npcId);
  if (history.length === 0) return "";

  let context = "对话历史：\n";
  for (const msg of history.slice(-6)) {
    const speaker = msg.role === "user" ? "患者" : npcId.includes("nurse") ? "护士" : "医生";
    context += `${speaker}: ${msg.content}\n`;
  }
  return context;
}

async function sendMessage(dialogSystem, content, npc, apiCaller, options = {}) {
  if (!content.trim() || dialogSystem.isLoading) return;

  addMessage(dialogSystem, "user", content);
  const userMsg = createUserMessage(content);
  dialogSystem.isLoading = true;

  const context = buildContextMessage(dialogSystem, npc.id);
  const fullContent = context + "患者说: " + content;

  let systemPrompt;
  if (npc.type === NPC_TYPES.NURSE) {
    systemPrompt = getNurseSystemPrompt();
  } else if (npc.type === NPC_TYPES.DOCTOR) {
    systemPrompt = getDoctorSystemPrompt();
  } else if (npc.type === NPC_TYPES.PHARMACIST) {
    systemPrompt = getPharmacistSystemPrompt();
  } else {
    systemPrompt = getNurseSystemPrompt();
  }

  try {
    const response = await (apiCaller
      ? apiCaller([createUserMessage(fullContent)], systemPrompt)
      : callChatAPI(fullContent, options.model, options.imageData));
    addMessage(dialogSystem, "assistant", response);

    const assistantMsg = createAssistantMessage(response);
    const history = getConversationHistory(dialogSystem, npc.id);
    history.push(userMsg, assistantMsg);
    saveConversation(dialogSystem, npc.id, history);

    if (npc.type === NPC_TYPES.NURSE) {
      dialogSystem.recommendedDepts = extractDepartments(response);
    }

    return response;
  } catch (error) {
    addMessage(dialogSystem, "assistant", "抱歉，网络出现了问题，请稍后再试。");
    return "error";
  } finally {
    dialogSystem.isLoading = false;
  }
}

function extractDepartments(text) {
  const mapping = [
    { key: "internal", patterns: ["内科"] },
    { key: "surgery", patterns: ["外科"] },
    { key: "pediatrics", patterns: ["儿科"] },
    { key: "emergency", patterns: ["急诊", "急救"] },
    { key: "eye", patterns: ["眼科", "眼睛"] },
    { key: "ortho", patterns: ["骨科", "关节", "骨"] },
  ];

  const found = [];
  for (const item of mapping) {
    if (item.patterns.some((p) => text.includes(p))) {
      found.push(item.key);
    }
  }

  return found;
}

function getNurseSystemPrompt() {
  return `你是一位医院分诊台的智能护士，名字叫“小医”。你需要：
1. 礼貌地问候患者，询问症状
2. 根据症状建议合适的科室（内科、外科、儿科、眼科等）
3. 如遇紧急情况，提醒患者去急诊
4. 保持专业、耐心、友好
5. 回答简明扼要，一般不超过3句话
6. 可以提供一些基本健康建议

当前医院科室：
- 内科：常见疾病、感冒发烧、慢性病
- 外科：需要手术的疾病、创伤
- 儿科：14岁以下儿童
- 眼科：眼睛相关疾病
- 骨科：骨骼、关节疾病
- 急诊：紧急情况、危重病人`;
}

function getDoctorSystemPrompt() {
  return `你是一位专业的医生，名字叫“Dr.林”。你需要：
1. 详细询问患者的症状和病史
2. 提供专业的医疗建议
3. 如需进一步检查，建议患者做相应检查
4. 开具处方或建议住院治疗
5. 保持专业、温和的态度
6. 回答要专业但通俗易懂`;
}

function getPharmacistSystemPrompt() {
  return `你是一位医院的药师，名字叫“老张”。你需要：
1. 审核处方，确保用药安全
2. 向患者说明药物的用法用量
3. 提醒患者注意药物副作用
4. 保持专业、耐心的态度
5. 回答简明扼要`;
}

function drawDialogBox(ctx, canvas, dialogSystem, deptLabels = {}) {
  if (!dialogSystem.isOpen) return;

  const boxWidth = 500;
  const boxHeight = 350;
  const boxX = (canvas.width - boxWidth) / 2;
  const boxY = canvas.height - boxHeight - 80;

  ctx.fillStyle = "rgba(16, 11, 24, 0.96)";
  ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.8)";
  ctx.lineWidth = 2;
  ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);

  const npcName = dialogSystem.currentNPC?.name || "NPC";
  ctx.fillStyle = "#a8f8ff";
  ctx.font = "bold 16px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(`与 ${npcName} 对话`, boxX + boxWidth / 2, boxY + 26);

  ctx.strokeStyle = "rgba(168, 248, 255, 0.3)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(boxX + 10, boxY + 40);
  ctx.lineTo(boxX + boxWidth - 10, boxY + 40);
  ctx.stroke();

  const messagesY = boxY + 55;
  const messagesHeight = boxHeight - 120;
  ctx.save();
  ctx.beginPath();
  ctx.rect(boxX + 10, messagesY, boxWidth - 20, messagesHeight);
  ctx.clip();

  let y = messagesY + 15;
  const maxWidth = boxWidth - 50;

  for (const msg of dialogSystem.messages.slice(-8)) {
    const isUser = msg.role === "user";
    const x = isUser ? boxX + boxWidth - 30 : boxX + 20;
    const bgColor = isUser ? "rgba(78, 168, 222, 0.3)" : "rgba(232, 143, 176, 0.3)";
    const textColor = isUser ? "#e8f4ff" : "#ffe8f0";

    ctx.font = "13px 'Segoe UI'";
    const lines = wrapText(ctx, msg.content, maxWidth);
    const lineHeight = 18;
    const bgHeight = lines.length * lineHeight + 12;
    const bgWidth = Math.min(maxWidth, ctx.measureText(msg.content).width + 20) + 10;

    ctx.fillStyle = bgColor;
    const bgX = isUser ? boxX + boxWidth - 20 - bgWidth : x - 10;
    ctx.fillRect(bgX, y - 10, bgWidth, bgHeight);

    ctx.fillStyle = textColor;
    ctx.textAlign = isUser ? "right" : "left";
    for (const line of lines) {
      ctx.fillText(line, isUser ? boxX + boxWidth - 25 : x + 5, y + 5);
      y += lineHeight;
    }
    y += 8;
  }

  ctx.restore();

  dialogSystem.buttonRects = [];
  if (dialogSystem.recommendedDepts.length > 0) {
    const btnY = boxY + boxHeight - 84;
    const btnW = 96;
    const btnH = 26;
    const gap = 10;
    const totalW = dialogSystem.recommendedDepts.length * btnW + (dialogSystem.recommendedDepts.length - 1) * gap;
    let startX = boxX + (boxWidth - totalW) / 2;

    dialogSystem.recommendedDepts.forEach((deptId, index) => {
      const rect = { x: startX, y: btnY, w: btnW, h: btnH, deptId };
      dialogSystem.buttonRects.push(rect);
      ctx.fillStyle = "rgba(131, 255, 201, 0.18)";
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
      ctx.strokeStyle = "rgba(131, 255, 201, 0.8)";
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      ctx.fillStyle = "#83ffc9";
      ctx.font = "12px 'Segoe UI'";
      ctx.textAlign = "center";
      const label = deptLabels[deptId] || deptId;
      ctx.fillText(`${index + 1}. ${label}`, rect.x + rect.w / 2, rect.y + 17);
      startX += btnW + gap;
    });
  }

  if (dialogSystem.isLoading) {
    ctx.fillStyle = "#83ffc9";
    ctx.font = "12px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText("AI 正在思考...", boxX + boxWidth / 2, boxY + boxHeight - 50);
  }

  ctx.fillStyle = "rgba(30, 20, 40, 0.9)";
  ctx.fillRect(boxX + 10, boxY + boxHeight - 45, boxWidth - 20, 35);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.5)";
  ctx.strokeRect(boxX + 10, boxY + boxHeight - 45, boxWidth - 20, 35);

  ctx.fillStyle = "#f2ebff";
  ctx.font = "12px 'Segoe UI'";
  ctx.textAlign = "left";
  ctx.fillText("输入:", boxX + 20, boxY + boxHeight - 22);

  ctx.fillStyle = "#fff";
  ctx.font = "13px 'Segoe UI'";
  const inputDisplay = dialogSystem.inputText || "（中文输入请直接打字，Enter发送，Esc退出）";
  ctx.fillText(inputDisplay, boxX + 55, boxY + boxHeight - 22);
}

function wrapText(ctx, text, maxWidth) {
  const words = text.split("");
  const lines = [];
  let currentLine = "";

  for (const char of words) {
    const testLine = currentLine + char;
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && currentLine.length > 0) {
      lines.push(currentLine);
      currentLine = char;
    } else {
      currentLine = testLine;
    }
  }

  if (currentLine.length > 0) {
    lines.push(currentLine);
  }

  return lines.length > 0 ? lines : [""];
}

function handleDialogInput(dialogSystem, event) {
  if (event.key === "Enter" && !dialogSystem.isLoading) {
    const text = dialogSystem.inputText.trim();
    if (text) {
      return { action: "send", text };
    }
  } else if (event.key === "Backspace") {
    dialogSystem.inputText = dialogSystem.inputText.slice(0, -1);
  } else if (event.key === "Escape") {
    return { action: "close" };
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
    dialogSystem.inputText += event.key;
  }

  return null;
}

const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const floorStateLabel = document.getElementById("floor-state");
const imeInput = document.getElementById("dialog-ime");
const modelSelect = document.getElementById("model-select");
const imageInput = document.getElementById("image-input");
const imageStatus = document.getElementById("image-status");

const keys = new Set();
const camera = { x: 0, y: 0 };

const player = {
  x: 8 * TILE,
  y: 10 * TILE,
  floor: 1,
  width: CHARACTER_FOOT_RADIUS * 2,
  height: CHARACTER_FOOT_RADIUS * 2,
  speed: 180,
};

let activeFloor = 1;
let stairCooldownUntil = 0;
let playerDeptId = null;
let isComposing = false;
let playerCall = { active: false, deptId: null, until: 0, lastSeen: 0 };
let currentImageData = null;

const floorSpawns = {
  1: { x: 8 * TILE, y: 10 * TILE },
  2: { x: 18 * TILE, y: 16 * TILE },
};

const stairs = [
  { id: "stair-1f", floor: 1, x: 22.4, y: 18.0, w: 2, h: 2, toFloor: 2, exitX: 22.9, exitY: 18.7 },
  { id: "stair-2f", floor: 2, x: 22.4, y: 18.0, w: 2, h: 2, toFloor: 1, exitX: 23.1, exitY: 18.7 },
];

const npcHeadImage = new Image();
let npcHeadReady = false;
npcHeadImage.onload = () => { npcHeadReady = true; };
npcHeadImage.src = "./img/head_photo-head@1x.png";

const rooms = [
  { floor: 1, x: 3, y: 4, w: 13, h: 8, kind: "registration" },
  { floor: 1, x: 17, y: 4, w: 12, h: 8, kind: "consultation" },
  { floor: 1, x: 30, y: 4, w: 12, h: 8, kind: "consultation" },
  { floor: 1, x: 3, y: 14, w: 17, h: 10, kind: "triage" },
  { floor: 1, x: 21, y: 13, w: 15, h: 11, kind: "hall" },
  { floor: 1, x: 37, y: 14, w: 9, h: 10, kind: "pharmacy" },
  { floor: 2, x: 4, y: 5, w: 12, h: 8, kind: "ward" },
  { floor: 2, x: 17, y: 4, w: 11, h: 9, kind: "ward" },
  { floor: 2, x: 29, y: 4, w: 12, h: 9, kind: "icu" },
  { floor: 2, x: 4, y: 15, w: 13, h: 10, kind: "lab" },
  { floor: 2, x: 18, y: 14, w: 14, h: 10, kind: "hall" },
  { floor: 2, x: 33, y: 15, w: 12, h: 10, kind: "office" },
];

const doorSpecs = [
  { roomIndex: 0, side: "right", offset: 2.5, length: 2, label: "REG-A" },
  { roomIndex: 0, side: "bottom", offset: 5.5, length: 2, label: "REG-B" },
  { roomIndex: 1, side: "left", offset: 2.5, length: 2, label: "CONS-1A" },
  { roomIndex: 1, side: "bottom", offset: 4.5, length: 2, label: "CONS-1B" },
  { roomIndex: 2, side: "left", offset: 2.5, length: 2, label: "CONS-2A" },
  { roomIndex: 2, side: "bottom", offset: 4.5, length: 2, label: "CONS-2B" },
  { roomIndex: 3, side: "top", offset: 6, length: 2, label: "TRIAGE-A" },
  { roomIndex: 3, side: "right", offset: 4.5, length: 2, label: "TRIAGE-B" },
  { roomIndex: 4, side: "left", offset: 4.5, length: 2, label: "LOBBY-W" },
  { roomIndex: 4, side: "right", offset: 4.5, length: 2, label: "LOBBY-E" },
  { roomIndex: 4, side: "bottom", offset: 5, length: 2, label: "LOBBY-S" },
  { roomIndex: 5, side: "left", offset: 4, length: 2, label: "PHARM-A" },
  { roomIndex: 5, side: "top", offset: 3.5, length: 2, label: "PHARM-B" },
  { roomIndex: 6, side: "right", offset: 3, length: 2, label: "WARD-A" },
  { roomIndex: 6, side: "bottom", offset: 4.5, length: 2, label: "WARD-B" },
  { roomIndex: 7, side: "left", offset: 3, length: 2, label: "WARD-C" },
  { roomIndex: 7, side: "bottom", offset: 4, length: 2, label: "WARD-D" },
  { roomIndex: 8, side: "left", offset: 3, length: 2, label: "ICU-A" },
  { roomIndex: 8, side: "bottom", offset: 5, length: 2, label: "ICU-B" },
  { roomIndex: 9, side: "top", offset: 5, length: 2, label: "LAB-A" },
  { roomIndex: 9, side: "right", offset: 4.5, length: 2, label: "LAB-B" },
  { roomIndex: 10, side: "left", offset: 4, length: 2, label: "HALL-2W" },
  { roomIndex: 10, side: "right", offset: 4, length: 2, label: "HALL-2E" },
  { roomIndex: 11, side: "left", offset: 4, length: 2, label: "OFFICE-A" },
  { roomIndex: 11, side: "top", offset: 4, length: 2, label: "OFFICE-B" },
];

const props = [
  { floor: 1, x: 5.2, y: 5.3, w: 3.4, h: 1.2, type: "reception", z: 22 },
  { floor: 1, x: 9.4, y: 6.0, w: 1.2, h: 1.2, type: "screen", z: 24 },
  { floor: 1, x: 18.2, y: 5.3, w: 2.1, h: 1.1, type: "desk", z: 20 },
  { floor: 1, x: 21.0, y: 5.3, w: 1.2, h: 1.2, type: "plant", z: 24 },
  { floor: 1, x: 31.2, y: 5.3, w: 2.1, h: 1.1, type: "desk", z: 20 },
  { floor: 1, x: 33.9, y: 5.3, w: 1.2, h: 1.2, type: "plant", z: 24 },
  { floor: 1, x: 6.2, y: 16.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 10.0, y: 16.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 24.2, y: 15.4, w: 3.8, h: 1.4, type: "reception", z: 22 },
  { floor: 1, x: 39.0, y: 17.3, w: 2.1, h: 1.2, type: "sofa", z: 18 },
  { floor: 2, x: 6.2, y: 6.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 9.7, y: 6.2, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 19.2, y: 5.8, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 22.6, y: 5.8, w: 2.4, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 31.2, y: 5.8, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 35.0, y: 5.8, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 2, x: 6.2, y: 18.0, w: 1.2, h: 1.2, type: "screen", z: 24 },
  { floor: 2, x: 10.0, y: 18.0, w: 2.7, h: 1.1, type: "cabinet", z: 26 },
  { floor: 2, x: 34.2, y: 18.0, w: 3.0, h: 1.1, type: "desk", z: 20 },
  { floor: 2, x: 38.1, y: 18.0, w: 1.2, h: 1.2, type: "plant", z: 24 },
];

const ROOM_KIND_LABELS = {
  registration: "Registration",
  consultation: "Consultation",
  triage: "Triage",
  pharmacy: "Pharmacy",
  ward: "Ward",
  lab: "Lab",
  icu: "ICU",
  office: "Office",
  hall: "Lobby",
};

const DEPT_TARGETS = {
  internal: { floor: 1, roomIndex: 1, label: "内科诊室" },
  surgery: { floor: 1, roomIndex: 2, label: "外科诊室" },
  pediatrics: { floor: 1, roomIndex: 1, label: "儿科诊室" },
  emergency: { floor: 1, roomIndex: 3, label: "急诊分诊" },
  eye: { floor: 1, roomIndex: 1, label: "眼科诊室" },
  ortho: { floor: 1, roomIndex: 2, label: "骨科诊室" },
  pharmacy: { floor: 1, roomIndex: 5, label: "药房" },
  lab: { floor: 2, roomIndex: 9, label: "检验科" },
};

const npcs = initNPCs();
const queueManager = createQueueManager();
const dialogSystem = createDialogSystem();
const walkableBounds = getWalkableBounds(rooms);

let nearbyNPC = null;
let showRegistrationPanel = false;
let registrationTargetNPC = null;

function roomBounds(room) {
  return { x: room.x * TILE, y: room.y * TILE, w: room.w * TILE, h: room.h * TILE };
}

function roomCenter(room) {
  const rect = roomBounds(room);
  return { x: rect.x + rect.w * 0.5, y: rect.y + rect.h * 0.5 };
}

function rectsIntersect(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function playerRect(nextX = player.x, nextY = player.y) {
  return { x: nextX - player.width / 2, y: nextY - player.height / 2, w: player.width, h: player.height };
}

function zForFloor(localZ, floor) {
  return localZ + FLOOR_BASE_Z[floor] - FLOOR_BASE_Z[activeFloor];
}

function project(x, y, z = 0, floor = activeFloor) {
  const dx = x - camera.x;
  const dy = y - camera.y;
  return { x: canvas.width / 2 + (dx - dy) * ISO_X, y: canvas.height / 2 + (dx + dy) * ISO_Y - zForFloor(z, floor) };
}

function drawQuad(points, fillStyle, strokeStyle = palette.wallEdge) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length; index += 1) ctx.lineTo(points[index].x, points[index].y);
  ctx.closePath();
  ctx.fillStyle = fillStyle;
  ctx.fill();
  if (strokeStyle) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

function makePrismFaces(x, y, w, h, z, floor) {
  const a = project(x, y, 0, floor);
  const b = project(x + w, y, 0, floor);
  const c = project(x + w, y + h, 0, floor);
  const d = project(x, y + h, 0, floor);
  const at = project(x, y, z, floor);
  const bt = project(x + w, y, z, floor);
  const ct = project(x + w, y + h, z, floor);
  const dt = project(x, y + h, z, floor);
  return { top: [at, bt, ct, dt], south: [d, c, ct, dt], east: [b, c, ct, bt] };
}

function buildDoor(spec, index) {
  const room = rooms[spec.roomIndex];
  const rect = roomBounds(room);
  const length = spec.length * TILE;
  const offset = spec.offset * TILE;

  if (spec.side === "top" || spec.side === "bottom") {
    const openingX = rect.x + offset;
    const openingY = spec.side === "top" ? rect.y : rect.y + rect.h - WALL_THICKNESS;
    return {
      id: `door-${index}`,
      floor: room.floor,
      roomKind: room.kind,
      ...spec,
      open: false,
      opening: { x: openingX, y: openingY, w: length, h: WALL_THICKNESS },
      collider: { x: openingX, y: openingY + (WALL_THICKNESS - DOOR_THICKNESS) / 2, w: length, h: DOOR_THICKNESS },
      pivot: { x: openingX + length / 2, y: openingY + WALL_THICKNESS / 2 },
    };
  }

  const openingX = spec.side === "left" ? rect.x : rect.x + rect.w - WALL_THICKNESS;
  const openingY = rect.y + offset;
  return {
    id: `door-${index}`,
    floor: room.floor,
    roomKind: room.kind,
    ...spec,
    open: false,
    opening: { x: openingX, y: openingY, w: WALL_THICKNESS, h: length },
    collider: { x: openingX + (WALL_THICKNESS - DOOR_THICKNESS) / 2, y: openingY, w: DOOR_THICKNESS, h: length },
    pivot: { x: openingX + WALL_THICKNESS / 2, y: openingY + length / 2 },
  };
}

const doors = doorSpecs.map(buildDoor);

function buildRoomWallSegments(roomIndex) {
  const room = rooms[roomIndex];
  const rect = roomBounds(room);
  const roomDoors = doors.filter((door) => door.roomIndex === roomIndex);
  const segments = [];

  function carve(total, fixed, horizontal, openings) {
    const sorted = openings
      .map((door) => ({
        start: horizontal ? door.opening.x - rect.x : door.opening.y - rect.y,
        size: horizontal ? door.opening.w : door.opening.h,
      }))
      .sort((a, b) => a.start - b.start);

    let cursor = 0;
    for (const opening of sorted) {
      if (opening.start > cursor) {
        if (horizontal) segments.push({ floor: room.floor, x: rect.x + cursor, y: fixed, w: opening.start - cursor, h: WALL_THICKNESS });
        else segments.push({ floor: room.floor, x: fixed, y: rect.y + cursor, w: WALL_THICKNESS, h: opening.start - cursor });
      }
      cursor = opening.start + opening.size;
    }
    if (cursor < total) {
      if (horizontal) segments.push({ floor: room.floor, x: rect.x + cursor, y: fixed, w: total - cursor, h: WALL_THICKNESS });
      else segments.push({ floor: room.floor, x: fixed, y: rect.y + cursor, w: WALL_THICKNESS, h: total - cursor });
    }
  }

  carve(rect.w, rect.y, true, roomDoors.filter((door) => door.side === "top"));
  carve(rect.w, rect.y + rect.h - WALL_THICKNESS, true, roomDoors.filter((door) => door.side === "bottom"));
  carve(rect.h, rect.x, false, roomDoors.filter((door) => door.side === "left"));
  carve(rect.h, rect.x + rect.w - WALL_THICKNESS, false, roomDoors.filter((door) => door.side === "right"));
  return segments;
}

const roomWallSegments = rooms.flatMap((_, index) => buildRoomWallSegments(index));

function buildCollisionRects() {
  const colliders = [];
  for (const segment of roomWallSegments) colliders.push(segment);
  for (const prop of props) colliders.push({ floor: prop.floor, x: prop.x * TILE, y: prop.y * TILE, w: prop.w * TILE, h: prop.h * TILE });
  return colliders;
}

const staticCollisions = buildCollisionRects();

function currentFloorDoors() {
  return doors.filter((door) => door.floor === activeFloor);
}

function doorCollidersForFloor(floor) {
  return doors.filter((door) => door.floor === floor && !door.open).map((door) => door.collider);
}

function canMoveTo(nextX, nextY, floor = activeFloor) {
  const rect = playerRect(nextX, nextY);
  if (rect.x < 0 || rect.y < 0 || rect.x + rect.w > WORLD.width || rect.y + rect.h > WORLD.height) return false;

  const foot = { x: nextX, y: nextY, r: CHARACTER_FOOT_RADIUS };
  const collisions = [...staticCollisions.filter((item) => item.floor === floor), ...doorCollidersForFloor(floor)];
  return !collisions.some((wall) => {
    const closestX = Math.max(wall.x, Math.min(foot.x, wall.x + wall.w));
    const closestY = Math.max(wall.y, Math.min(foot.y, wall.y + wall.h));
    const distanceSq = (foot.x - closestX) ** 2 + (foot.y - closestY) ** 2;
    return distanceSq < foot.r * foot.r;
  });
}

function distanceToDoor(door) {
  return Math.hypot(player.x - door.pivot.x, player.y - door.pivot.y);
}

function nearestDoor(maxDistance = DOOR_SENSOR_DISTANCE) {
  let bestDoor = null;
  let bestDistance = Infinity;
  for (const door of currentFloorDoors()) {
    const distance = distanceToDoor(door);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestDoor = door;
    }
  }
  return bestDistance <= maxDistance ? bestDoor : null;
}

function updateDoors() {
  for (const door of currentFloorDoors()) {
    const distance = distanceToDoor(door);
    if (distance <= DOOR_SENSOR_DISTANCE) {
      door.open = true;
      continue;
    }
    if (distance >= DOOR_CLOSE_DISTANCE && !rectsIntersect(playerRect(), door.collider)) door.open = false;
  }
}

function activeStairForPlayer() {
  return stairs
    .filter((stair) => stair.floor === activeFloor)
    .find((stair) => {
      const x = stair.x * TILE;
      const y = stair.y * TILE;
      const w = stair.w * TILE;
      const h = stair.h * TILE;
      return player.x >= x && player.x <= x + w && player.y >= y && player.y <= y + h;
    });
}

function findNearestWalkable(x, y, floor) {
  if (canMoveTo(x, y, floor)) return { x, y };

  for (let radius = 12; radius <= 120; radius += 12) {
    for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 8) {
      const nx = x + Math.cos(angle) * radius;
      const ny = y + Math.sin(angle) * radius;
      if (canMoveTo(nx, ny, floor)) return { x: nx, y: ny };
    }
  }

  return floorSpawns[floor] || floorSpawns[1];
}

function drawRoomFloor(room, dimmed) {
  const rect = roomBounds(room);
  const quad = [
    project(rect.x, rect.y, 0, room.floor),
    project(rect.x + rect.w, rect.y, 0, room.floor),
    project(rect.x + rect.w, rect.y + rect.h, 0, room.floor),
    project(rect.x, rect.y + rect.h, 0, room.floor),
  ];
  drawQuad(quad, room.kind === "hall" ? palette.hallFloor : palette.roomFloor, dimmed ? "rgba(0,0,0,0.12)" : "rgba(255,255,255,0.08)");
}

function drawWall(segment) {
  const prism = makePrismFaces(segment.x, segment.y, segment.w, segment.h, WALL_HEIGHT, segment.floor);
  drawQuad(prism.top, palette.wallTop);
  if (segment.h <= WALL_THICKNESS) drawQuad(prism.south, palette.wallFront);
  if (segment.w <= WALL_THICKNESS) drawQuad(prism.east, palette.wallSide);
}

function drawDoor(door, activeDoor) {
  const horizontal = door.side === "top" || door.side === "bottom";
  const opening = door.opening;
  const frame = makePrismFaces(opening.x, opening.y, opening.w, opening.h, 22, door.floor);
  drawQuad(frame.top, "#7e97a7", "rgba(255,255,255,0.12)");
  if (opening.h <= WALL_THICKNESS) drawQuad(frame.south, "#688091");
  else drawQuad(frame.east, "#688091");

  const shrink = door.open ? 0.42 : 1;
  if (horizontal) {
    const width = opening.w * shrink;
    const y = opening.y + (opening.h - DOOR_THICKNESS) / 2;
    drawQuad(makePrismFaces(opening.x, y, width * 0.5, DOOR_THICKNESS, 20, door.floor).top, palette.doorGlass);
    drawQuad(makePrismFaces(opening.x + opening.w - width * 0.5, y, width * 0.5, DOOR_THICKNESS, 20, door.floor).top, palette.doorGlass);
  } else {
    const height = opening.h * shrink;
    const x = opening.x + (opening.w - DOOR_THICKNESS) / 2;
    drawQuad(makePrismFaces(x, opening.y, DOOR_THICKNESS, height * 0.5, 20, door.floor).top, palette.doorGlass);
    drawQuad(makePrismFaces(x, opening.y + opening.h - height * 0.5, DOOR_THICKNESS, height * 0.5, 20, door.floor).top, palette.doorGlass);
  }

  const sensor = project(door.pivot.x, door.pivot.y, 24, door.floor);
  ctx.fillStyle = palette.doorSensor;
  ctx.beginPath();
  ctx.arc(sensor.x, sensor.y, activeDoor?.id === door.id ? 5 : 3, 0, Math.PI * 2);
  ctx.fill();
}

function drawStair(stair) {
  const x = stair.x * TILE;
  const y = stair.y * TILE;
  const w = stair.w * TILE;
  const h = stair.h * TILE;
  const platform = makePrismFaces(x, y, w, h, 14, stair.floor);
  const step = makePrismFaces(x + 4, y + 4, w - 8, h - 8, 9, stair.floor);

  drawQuad(platform.top, "#8f7a95", "rgba(255,255,255,0.16)");
  drawQuad(platform.south, "#705c77");
  drawQuad(platform.east, "#654f6b");
  drawQuad(step.top, "#a690ad", "rgba(255,255,255,0.1)");

  const tip = project(x + w * 0.5, y + h * 0.5, 20, stair.floor);
  ctx.fillStyle = "rgba(219, 246, 255, 0.9)";
  ctx.font = "12px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(`Stairs to ${stair.toFloor}F`, tip.x, tip.y);
}

function drawProp(prop) {
  const x = prop.x * TILE;
  const y = prop.y * TILE;
  const w = prop.w * TILE;
  const h = prop.h * TILE;
  const prism = makePrismFaces(x, y, w, h, prop.z, prop.floor);
  const colors = {
    bed: { top: "#8bc6da", front: "#6e99aa", side: "#638a9a" },
    desk: { top: "#866149", front: "#6d4b35", side: "#5b3c2b" },
    sofa: { top: "#9a805c", front: "#816b4b", side: "#705d41" },
    plant: { top: "#79b275", front: "#5b8b57", side: "#4b7648" },
    screen: { top: "#a7f0ec", front: "#6ac7c2", side: "#58aea9" },
    cabinet: { top: "#a281a0", front: "#8b6b89", side: "#765a74" },
    reception: { top: "#9d7087", front: "#865c74", side: "#724e63" },
  };
  const color = colors[prop.type];
  drawQuad(prism.top, color.top);
  drawQuad(prism.south, color.front);
  drawQuad(prism.east, color.side);
}

function drawCharacterBody(x, y, floor, bodyColor = palette.playerBody) {
  const base = project(x, y, 0, floor);
  const top = project(x, y, CHARACTER_BODY_HEIGHT, floor);
  ctx.fillStyle = palette.shadow;
  ctx.beginPath();
  ctx.ellipse(base.x, base.y + 9, CHARACTER_FOOT_RADIUS + 4, CHARACTER_FOOT_RADIUS, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = palette.playerLeg;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(base.x - 4, base.y + 2);
  ctx.lineTo(base.x - 6, base.y + 14);
  ctx.moveTo(base.x + 4, base.y + 2);
  ctx.lineTo(base.x + 6, base.y + 14);
  ctx.stroke();
  ctx.strokeStyle = bodyColor;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(base.x, base.y - 2);
  ctx.lineTo(top.x, top.y + 6);
  ctx.stroke();
  return top;
}

function drawDefaultHead(top) {
  ctx.fillStyle = palette.playerHead;
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, CHARACTER_HEAD_RADIUS, 0, Math.PI * 2);
  ctx.fill();
}

function drawTexturedHead(top) {
  const radius = CHARACTER_HEAD_RADIUS + 2;
  const size = 22;
  const dx = top.x - size / 2;
  const dy = top.y - 14;
  ctx.save();
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, radius, 0, Math.PI * 2);
  ctx.clip();
  if (npcHeadReady) ctx.drawImage(npcHeadImage, dx, dy, size, size);
  else drawDefaultHead(top);
  ctx.restore();
}

function drawPlayer() {
  const top = drawCharacterBody(player.x, player.y, player.floor);
  drawTexturedHead(top);
}

function characterDepth(x, y) {
  return x + y + CHARACTER_FOOT_RADIUS;
}

function drawLabels() {
  ctx.fillStyle = palette.label;
  ctx.font = "13px 'Segoe UI'";
  ctx.textAlign = "center";
  for (const room of rooms.filter((item) => item.floor === activeFloor)) {
    const rect = roomBounds(room);
    const point = project(rect.x + rect.w * 0.5, rect.y + rect.h * 0.5, 6, room.floor);
    ctx.fillText(ROOM_KIND_LABELS[room.kind], point.x, point.y);
  }
}

function drawMinimap() {
  const size = 180;
  const scale = 0.11;
  const left = canvas.width - size - 18;
  const top = 18;
  ctx.fillStyle = "rgba(20, 15, 27, 0.72)";
  ctx.fillRect(left, top, size, size);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(left, top, size, size);

  for (const room of rooms.filter((item) => item.floor === activeFloor)) {
    const rect = roomBounds(room);
    ctx.fillStyle = room.kind === "hall" ? "#8a7188" : "#705970";
    ctx.fillRect(left + rect.x * scale, top + rect.y * scale, rect.w * scale, rect.h * scale);
  }

  for (const door of currentFloorDoors()) {
    ctx.fillStyle = door.open ? "#8df1ff" : "#65879a";
    ctx.fillRect(left + door.opening.x * scale, top + door.opening.y * scale, Math.max(2, door.opening.w * scale), Math.max(2, door.opening.h * scale));
  }

  for (const stair of stairs.filter((item) => item.floor === activeFloor)) {
    ctx.fillStyle = "#f0d98b";
    ctx.fillRect(left + stair.x * TILE * scale, top + stair.y * TILE * scale, stair.w * TILE * scale, stair.h * TILE * scale);
  }

  for (const npc of npcs.filter((n) => n.floor === activeFloor)) {
    ctx.fillStyle = npc.type === NPC_TYPES.NURSE ? "#ff69b4" : npc.type === NPC_TYPES.DOCTOR ? "#4169e1" : "#32cd32";
    ctx.beginPath();
    ctx.arc(left + npc.x * scale, top + npc.y * scale, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.fillStyle = "#4ed7ff";
  ctx.beginPath();
  ctx.arc(left + player.x * scale, top + player.y * scale, 4, 0, Math.PI * 2);
  ctx.fill();
}

function drawHudHint(door) {
  if (!door) return;
  const point = project(door.pivot.x, door.pivot.y, 52, door.floor);
  const label = door.open ? `${door.label} Auto Open` : `${door.label} Standby`;
  ctx.fillStyle = "rgba(22, 15, 28, 0.88)";
  ctx.fillRect(point.x - 54, point.y - 12, 108, 22);
  ctx.strokeStyle = "rgba(255, 230, 180, 0.75)";
  ctx.strokeRect(point.x - 54, point.y - 12, 108, 22);
  ctx.fillStyle = "#fff4d9";
  ctx.font = "12px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 4);
}

function drawNPCIndicator() {
  if (!nearbyNPC || dialogSystem.isOpen) return;

  const npc = nearbyNPC;
  const indicatorPoint = project(npc.x, npc.y - 30, CHARACTER_BODY_HEIGHT + 35, npc.floor);

  ctx.fillStyle = "rgba(22, 15, 28, 0.92)";
  ctx.fillRect(indicatorPoint.x - 80, indicatorPoint.y - 12, 160, 24);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.8)";
  ctx.strokeRect(indicatorPoint.x - 80, indicatorPoint.y - 12, 160, 24);

  const actionText = npc.type === NPC_TYPES.NURSE
    ? "按 E 与护士对话"
    : npc.type === NPC_TYPES.DOCTOR
      ? "按 E 与医生对话"
      : npc.type === NPC_TYPES.PHARMACIST
        ? "按 E 与药师对话"
        : "";
  if (actionText) {
    ctx.fillStyle = "#a8f8ff";
    ctx.font = "12px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText(actionText, indicatorPoint.x, indicatorPoint.y + 5);
  }
}

function drawHelpPanel() {
  const panelWidth = 280;
  const panelHeight = 100;
  const panelX = 18;
  const panelY = canvas.height - panelHeight - 18;

  ctx.fillStyle = "rgba(16, 11, 24, 0.88)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.5)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.fillStyle = "#a8f8ff";
  ctx.font = "bold 12px 'Segoe UI'";
  ctx.textAlign = "left";
  ctx.fillText("操作说明", panelX + 12, panelY + 18);

  ctx.fillStyle = "#f2ebff";
  ctx.font = "11px 'Segoe UI'";
  ctx.fillText("WASD/方向键 - 移动", panelX + 12, panelY + 38);
  ctx.fillText("E - 与NPC对话", panelX + 12, panelY + 54);
  ctx.fillText("空格 - 打开挂号", panelX + 12, panelY + 70);
  ctx.fillText("ESC - 关闭对话框", panelX + 12, panelY + 86);
}

function getDeptTarget(deptId) {
  const target = DEPT_TARGETS[deptId];
  if (!target) return null;
  const room = rooms[target.roomIndex];
  if (!room) return null;
  const center = roomCenter(room);
  return { x: center.x, y: center.y, floor: target.floor, label: target.label };
}

function drawPlayerCallPopup(nowMs) {
  if (!playerCall.active) return;
  const remainingMs = Math.max(0, playerCall.until - nowMs);
  if (remainingMs <= 0) return;

  const panelWidth = 360;
  const panelHeight = 90;
  const panelX = (canvas.width - panelWidth) / 2;
  const panelY = 24;

  ctx.fillStyle = "rgba(20, 12, 28, 0.92)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(255, 224, 170, 0.8)";
  ctx.lineWidth = 2;
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  const target = getDeptTarget(playerCall.deptId);
  const label = target ? target.label : "诊室";
  const minutes = String(Math.floor(remainingMs / 60000)).padStart(2, "0");
  const seconds = String(Math.floor((remainingMs % 60000) / 1000)).padStart(2, "0");

  ctx.fillStyle = "#ffe9c7";
  ctx.font = "bold 14px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(`叫号到您了：请前往 ${label}`, panelX + panelWidth / 2, panelY + 30);
  ctx.font = "12px 'Segoe UI'";
  ctx.fillText(`请在 ${minutes}:${seconds} 内到达`, panelX + panelWidth / 2, panelY + 54);
  if (target && target.floor !== player.floor) {
    ctx.fillText(`需要到 ${target.floor}F`, panelX + panelWidth / 2, panelY + 74);
  }
}

function drawPathGuidance(nowMs) {
  if (!playerCall.active) return;
  const target = getDeptTarget(playerCall.deptId);
  if (!target) return;

  if (target.floor !== player.floor) {
    return;
  }

  const targetPoint = project(target.x, target.y, 12, target.floor);
  const playerPoint = project(player.x, player.y, 12, player.floor);
  const pulse = 6 + 3 * Math.sin(nowMs / 300);

  ctx.strokeStyle = "rgba(131, 255, 201, 0.6)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(playerPoint.x, playerPoint.y - 10);
  ctx.lineTo(targetPoint.x, targetPoint.y - 10);
  ctx.stroke();

  ctx.fillStyle = "rgba(131, 255, 201, 0.3)";
  ctx.beginPath();
  ctx.arc(targetPoint.x, targetPoint.y - 10, 18 + pulse, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#83ffc9";
  ctx.font = "12px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("目的地", targetPoint.x, targetPoint.y - 24 - pulse);
}

function drawFloorLayer(floor, activeDoor, dimmed) {
  ctx.save();
  if (dimmed) ctx.globalAlpha = 0.35;
  for (const room of rooms.filter((item) => item.floor === floor)) drawRoomFloor(room, dimmed);

  const drawables = [];
  for (const segment of roomWallSegments.filter((item) => item.floor === floor)) {
    drawables.push({ depth: segment.x + segment.y + segment.w + segment.h, draw: () => drawWall(segment) });
  }
  for (const door of doors.filter((item) => item.floor === floor)) {
    drawables.push({ depth: door.opening.x + door.opening.y + door.opening.w + door.opening.h + 2, draw: () => drawDoor(door, activeDoor) });
  }
  for (const stair of stairs.filter((item) => item.floor === floor)) {
    drawables.push({ depth: stair.x * TILE + stair.y * TILE + stair.w * TILE + stair.h * TILE + 6, draw: () => drawStair(stair) });
  }
  for (const prop of props.filter((item) => item.floor === floor)) {
    drawables.push({ depth: prop.x * TILE + prop.y * TILE + prop.w * TILE + prop.h * TILE + 8, draw: () => drawProp(prop) });
  }

  for (const npc of npcs.filter((n) => n.floor === floor)) {
    drawables.push({ depth: characterDepth(npc.x, npc.y), draw: () => drawNPC(ctx, npc, project, drawQuad, makePrismFaces) });
  }

  if (player.floor === floor) drawables.push({ depth: characterDepth(player.x, player.y), draw: drawPlayer });

  drawables.sort((a, b) => a.depth - b.depth);
  drawables.forEach((entry) => entry.draw());
  ctx.restore();

  if (dimmed) {
    ctx.fillStyle = palette.inactiveMask;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
}

function updateFloorHud() {
  if (floorStateLabel) floorStateLabel.textContent = `Current Floor: ${activeFloor}F`;
}

function switchFloor(nextFloor, targetPosition) {
  if (nextFloor === activeFloor || FLOOR_BASE_Z[nextFloor] === undefined) return;
  floorSpawns[activeFloor] = { x: player.x, y: player.y };
  activeFloor = nextFloor;
  player.floor = nextFloor;
  const spawn = targetPosition || floorSpawns[nextFloor] || floorSpawns[1];
  const safe = findNearestWalkable(spawn.x, spawn.y, nextFloor);
  player.x = safe.x;
  player.y = safe.y;
  updateFloorHud();
}

function tryStairTransfer(nowMs) {
  if (nowMs < stairCooldownUntil) return;
  const stair = activeStairForPlayer();
  if (!stair) return;

  switchFloor(stair.toFloor, { x: stair.exitX * TILE, y: stair.exitY * TILE });
  stairCooldownUntil = nowMs + STAIR_TRIGGER_COOLDOWN_MS;
}

function findNearbyNPC() {
  const interactDistance = 50;
  let closest = null;
  let closestDist = Infinity;

  for (const npc of npcs) {
    if (npc.floor !== player.floor) continue;
    const dist = Math.hypot(player.x - npc.x, player.y - npc.y);
    if (dist < interactDistance && dist < closestDist) {
      closest = npc;
      closestDist = dist;
    }
  }

  return closest;
}

function handleRegistrationKey(key) {
  const keyMap = { Digit1: "internal", Digit2: "surgery", Digit3: "pediatrics", Digit4: "emergency" };
  const deptId = keyMap[key];

  if (deptId && registrationTargetNPC) {
    addToQueue(queueManager, registrationTargetNPC, deptId);
    closeDialog(dialogSystem);
    showRegistrationPanel = false;
    registrationTargetNPC = null;
    return true;
  }
  return false;
}

function enqueuePlayer(deptId) {
  addPlayerToQueue(queueManager, deptId);
  playerDeptId = deptId;
  closeDialog(dialogSystem);
  if (imeInput) {
    imeInput.classList.remove("is-active");
    imeInput.blur();
  }
}

async function handleInteract() {
  if (dialogSystem.isOpen) return;

  const npc = findNearbyNPC();
  if (!npc) return;

  openDialog(dialogSystem, npc);
  const greetTail = "很高兴见到你，nice to meet you。";
  if (npc.type === NPC_TYPES.NURSE) {
    dialogSystem.messages = [
      { role: "assistant", content: `您好！我是护士小李，请问您有什么不舒服的地方？${greetTail}`, timestamp: Date.now() },
    ];
  } else if (npc.type === NPC_TYPES.DOCTOR) {
    dialogSystem.messages = [
      { role: "assistant", content: `您好！我是${npc.name}，请坐，有什么可以帮您的？${greetTail}`, timestamp: Date.now() },
    ];
  } else if (npc.type === NPC_TYPES.PHARMACIST) {
    dialogSystem.messages = [
      { role: "assistant", content: `您好！我是药师老张，请问需要取药吗？${greetTail}`, timestamp: Date.now() },
    ];
  }

  if (imeInput) {
    imeInput.value = "";
    imeInput.classList.add("is-active");
    setTimeout(() => imeInput.focus(), 0);
  }
}

async function handleDialogSend() {
  if (dialogSystem.isLoading || !dialogSystem.inputText.trim()) return;

  const text = dialogSystem.inputText;
  dialogSystem.inputText = "";
  if (imeInput) imeInput.value = "";

  const model = modelSelect ? modelSelect.value : "deepseek";
  const response = await sendMessage(dialogSystem, text, dialogSystem.currentNPC, null, {
    model,
    imageData: currentImageData,
  });
  if (response === "error") {
    console.log("Dialog send error");
  }
}

function update(delta, nowMs) {
  const blockMovement = dialogSystem.isOpen;

  if (!blockMovement) {
    updateDoors();
    let moveX = 0;
    let moveY = 0;
    if (keys.has("ArrowUp") || keys.has("KeyW")) moveY -= 1;
    if (keys.has("ArrowDown") || keys.has("KeyS")) moveY += 1;
    if (keys.has("ArrowLeft") || keys.has("KeyA")) moveX -= 1;
    if (keys.has("ArrowRight") || keys.has("KeyD")) moveX += 1;

    if (moveX !== 0 || moveY !== 0) {
      const length = Math.hypot(moveX, moveY);
      const velocityX = (moveX / length) * player.speed * delta;
      const velocityY = (moveY / length) * player.speed * delta;
      if (canMoveTo(player.x + velocityX, player.y)) player.x += velocityX;
      if (canMoveTo(player.x, player.y + velocityY)) player.y += velocityY;
    }

    camera.x += (player.x - camera.x - 180) * 0.08;
    camera.y += (player.y - camera.y - 140) * 0.08;
    tryStairTransfer(nowMs);
  }

  nearbyNPC = findNearbyNPC();

  for (const npc of npcs) {
    updateNPC(npc, delta, staticCollisions, doors, walkableBounds);
  }

  updateQueueCalls(queueManager, nowMs);

  for (const dept of Object.values(QUEUE_DEPARTMENTS)) {
    const called = queueManager.calledTicket[dept.id];
    if (called && called.patientId === "player") {
      playerCall = {
        active: true,
        deptId: dept.id,
        until: queueManager.calledUntil[dept.id],
        lastSeen: nowMs,
      };
      break;
    }
  }

  if (playerCall.active && nowMs >= playerCall.until) {
    playerCall.active = false;
  }
}

function render() {
  const activeDoor = nearestDoor();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#130f18";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const inactiveFloor = activeFloor === 1 ? 2 : 1;
  drawFloorLayer(inactiveFloor, null, true);
  drawFloorLayer(activeFloor, activeDoor, false);
  drawLabels();
  drawHudHint(activeDoor);
  drawMinimap();
  drawNPCIndicator();
  drawHelpPanel();
  drawQueueBoard(ctx, canvas, queueManager, playerDeptId);
  drawPathGuidance(performance.now());
  drawPlayerCallPopup(performance.now());

  if (dialogSystem.isOpen) {
    const deptLabels = Object.fromEntries(Object.values(QUEUE_DEPARTMENTS).map((d) => [d.id, d.name]));
    drawDialogBox(ctx, canvas, dialogSystem, deptLabels);
  }

  if (showRegistrationPanel && registrationTargetNPC) {
    drawRegistrationPanel(ctx, canvas, player, registrationTargetNPC);
  }
}

let lastTime = performance.now();

window.addEventListener("keydown", async (event) => {
  if (event.code === "Escape") {
    if (dialogSystem.isOpen) {
      closeDialog(dialogSystem);
      if (imeInput) {
        imeInput.classList.remove("is-active");
        imeInput.blur();
      }
    }
    showRegistrationPanel = false;
    return;
  }

  if (dialogSystem.isOpen) {
    if (event.key === "Enter" && !isComposing) {
      event.preventDefault();
      await handleDialogSend();
    } else if (event.code.startsWith("Digit")) {
      const index = Number(event.code.replace("Digit", "")) - 1;
      if (dialogSystem.recommendedDepts[index]) {
        enqueuePlayer(dialogSystem.recommendedDepts[index]);
      }
    }
    return;
  }

  if (event.code === "KeyE") {
    event.preventDefault();
    await handleInteract();
    return;
  }

  if (event.code === "Space") {
    const nurse = findNearbyNPC();
    if (nurse && nurse.type === NPC_TYPES.NURSE) {
      registrationTargetNPC = nurse;
      showRegistrationPanel = true;
    }
    return;
  }

  if (showRegistrationPanel) {
    if (handleRegistrationKey(event.code)) {
      return;
    }
  }

  keys.add(event.code);
});

window.addEventListener("keyup", (event) => keys.delete(event.code));

canvas.addEventListener("click", (event) => {
  if (!dialogSystem.isOpen || dialogSystem.buttonRects.length === 0) return;
  const rect = canvas.getBoundingClientRect();
  const x = (event.clientX - rect.left) * (canvas.width / rect.width);
  const y = (event.clientY - rect.top) * (canvas.height / rect.height);

  for (const btn of dialogSystem.buttonRects) {
    if (x >= btn.x && x <= btn.x + btn.w && y >= btn.y && y <= btn.y + btn.h) {
      enqueuePlayer(btn.deptId);
      break;
    }
  }
});

window.addEventListener("resize", () => {
  const ratio = 16 / 9;
  const width = Math.min(window.innerWidth, 1400);
  const height = Math.min(window.innerHeight, 800);
  if (width / height > ratio) {
    canvas.style.width = `${height * ratio}px`;
    canvas.style.height = `${height}px`;
  } else {
    canvas.style.width = `${width}px`;
    canvas.style.height = `${width / ratio}px`;
  }
});

if (imeInput) {
  imeInput.addEventListener("compositionstart", () => {
    isComposing = true;
  });

  imeInput.addEventListener("compositionend", () => {
    isComposing = false;
    dialogSystem.inputText = imeInput.value;
  });

  imeInput.addEventListener("input", () => {
    dialogSystem.inputText = imeInput.value;
  });

  imeInput.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !isComposing) {
      event.preventDefault();
      await handleDialogSend();
    } else if (event.key === "Escape") {
      closeDialog(dialogSystem);
      imeInput.classList.remove("is-active");
      imeInput.blur();
    }
  });
}

if (imageInput) {
  imageInput.addEventListener("change", () => {
    const file = imageInput.files && imageInput.files[0];
    if (!file) {
      currentImageData = null;
      if (imageStatus) imageStatus.textContent = "未选择图片";
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      currentImageData = reader.result;
      if (imageStatus) imageStatus.textContent = "已选择图片";
    };
    reader.readAsDataURL(file);
  });
}

function loop(now) {
  const delta = Math.min((now - lastTime) / 1000, 1 / 30);
  lastTime = now;
  update(delta, now);
  render();
  requestAnimationFrame(loop);
}

updateFloorHud();
window.dispatchEvent(new Event("resize"));
requestAnimationFrame(loop);
