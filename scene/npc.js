import { TILE, CHARACTER_FOOT_RADIUS, CHARACTER_BODY_HEIGHT, CHARACTER_HEAD_RADIUS, palette } from "./constants.js";

export const NPC_TYPES = {
  NURSE: "nurse",
  PATIENT: "patient",
  DOCTOR: "doctor",
  PHARMACIST: "pharmacist",
};

export const NPC_STATES = {
  IDLE: "idle",
  WALKING: "walking",
  WAITING: "waiting",
  IN_CONVERSATION: "in_conversation",
  IN_TREATMENT: "in_treatment",
};

export function createNPC(id, type, x, y, floor, config = {}) {
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

export function updateNPC(npc, delta, staticCollisions, doors, walkableBounds) {
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

export function drawNPC(ctx, npc, project, drawQuad, makePrismFaces) {
  const base = project(npc.x, npc.y, 0, npc.floor);
  const top = project(npc.x, npc.y, CHARACTER_BODY_HEIGHT, npc.floor);

  if (npc.name === "内科医生") {
    ctx.fillStyle = "rgba(255, 255, 0, 0.5)";
    ctx.beginPath();
    ctx.ellipse(base.x, base.y + 9, CHARACTER_FOOT_RADIUS + 10, CHARACTER_FOOT_RADIUS + 4, 0, 0, Math.PI * 2);
    ctx.fill();
  }

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

export function initNPCs() {
  return [
    createNPC("nurse-1", NPC_TYPES.NURSE, 24.5, 16, 1, { name: "护士小李", state: NPC_STATES.IDLE }),
    createNPC("nurse-2", NPC_TYPES.NURSE, 7, 17.5, 1, { name: "护士小王", state: NPC_STATES.IDLE }),
    createNPC("doctor-1", NPC_TYPES.DOCTOR, 20, 6, 1, { name: "内科医生", department: "internal", state: NPC_STATES.IDLE }),
    createNPC("doctor-2", NPC_TYPES.DOCTOR, 33, 6, 1, { name: "外科医生", department: "surgery", state: NPC_STATES.IDLE }),
    createNPC("pharmacist-1", NPC_TYPES.PHARMACIST, 40, 17, 1, { name: "药师老张", state: NPC_STATES.IDLE }),
    createNPC("patient-1", NPC_TYPES.PATIENT, 25, 17, 1, { name: "患者甲", state: NPC_STATES.IDLE }),
    createNPC("patient-2", NPC_TYPES.PATIENT, 27, 18, 1, { name: "患者乙", state: NPC_STATES.IDLE }),
    createNPC("patient-3", NPC_TYPES.PATIENT, 23, 18, 1, { name: "患者丙", state: NPC_STATES.IDLE }),
    createNPC("patient-4", NPC_TYPES.PATIENT, 30, 16, 1, { name: "患者丁", state: NPC_STATES.IDLE }),
    createNPC("patient-5", NPC_TYPES.PATIENT, 15, 17, 1, { name: "患者戊", state: NPC_STATES.IDLE }),
  ];
}

export function getWalkableBounds(rooms) {
  return rooms
    .filter((room) => room.kind === "hall" || room.kind === "triage")
    .map((room) => ({
      x: room.x * TILE + TILE,
      y: room.y * TILE + TILE,
      w: room.w * TILE - TILE * 2,
      h: room.h * TILE - TILE * 2,
    }));
}
