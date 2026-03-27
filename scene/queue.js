import { NPC_TYPES } from "./npc.js";

export const QUEUE_DEPARTMENTS = {
  INTERNAL: { id: "internal", name: "内科", roomKind: "consultation" },
  SURGERY: { id: "surgery", name: "外科", roomKind: "consultation" },
  PEDIATRICS: { id: "pediatrics", name: "儿科", roomKind: "consultation" },
  EMERGENCY: { id: "emergency", name: "急诊", roomKind: "triage", priority: true },
  EYE: { id: "eye", name: "眼科", roomKind: "consultation" },
  ORTHO: { id: "ortho", name: "骨科", roomKind: "consultation" },
  PHARMACY: { id: "pharmacy", name: "药房", roomKind: "pharmacy" },
  LAB: { id: "lab", name: "检验科", roomKind: "lab" },
};

export function createQueueManager() {
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

export function generateTicketNumber(queueManager, departmentId) {
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

export function addToQueue(queueManager, npc, departmentId) {
  if (npc.type !== NPC_TYPES.PATIENT) return null;

  const ticket = generateTicketNumber(queueManager, departmentId);
  ticket.patientId = npc.id;
  npc.ticket = ticket;
  npc.state = "waiting";

  queueManager.queues[departmentId].push(ticket);

  return ticket;
}

export function addPlayerToQueue(queueManager, departmentId) {
  const ticket = generateTicketNumber(queueManager, departmentId);
  ticket.patientId = "player";
  queueManager.playerTicket = ticket;
  queueManager.queues[departmentId].push(ticket);
  return ticket;
}

export function callNext(queueManager, departmentId) {
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

export function completeTicket(queueManager, departmentId, ticket) {
  if (ticket) {
    ticket.status = "completed";
    queueManager.history.push(ticket);
    queueManager.calledTicket[departmentId] = null;
  }
}

export function updateQueueCalls(queueManager, nowMs) {
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

export function getQueuePosition(queueManager, ticket) {
  const queue = queueManager.queues[ticket.departmentId];
  const index = queue.findIndex((t) => t.number === ticket.number && t.patientId === ticket.patientId);
  return index >= 0 ? index + 1 : null;
}

export function getWaitingCount(queueManager, departmentId) {
  return queueManager.queues[departmentId].length;
}

export function isAnyQueueEmpty(queueManager) {
  return Object.values(queueManager.queues).some((queue) => queue.length === 0);
}

export function drawQueueBoard(ctx, canvas, queueManager, playerDeptId = null) {
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

export function drawRegistrationPanel(ctx, canvas, player, nearbyNPC) {
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
