const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const floorStateLabel = document.getElementById("floor-state");

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

const keys = new Set();
const camera = { x: 0, y: 0 };

const palette = {
  roomFloor: "#705970",
  hallFloor: "#a67ba6",
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

const player = {
  x: 8 * TILE,
  y: 10 * TILE,
  floor: 1,
  width: CHARACTER_FOOT_RADIUS * 2,
  height: CHARACTER_FOOT_RADIUS * 2,
  speed: 180,
};

const npc = { x: 21 * TILE, y: 16 * TILE, floor: 1 };
const floorSpawns = {
  1: { x: 8 * TILE, y: 10 * TILE },
  2: { x: 18 * TILE, y: 16 * TILE },
};
let activeFloor = 1;
let stairCooldownUntil = 0;

const stairs = [
  { id: "stair-1f", floor: 1, x: 22.4, y: 18.0, w: 2, h: 2, toFloor: 2, exitX: 22.9, exitY: 18.7 },
  { id: "stair-2f", floor: 2, x: 22.4, y: 18.0, w: 2, h: 2, toFloor: 1, exitX: 23.1, exitY: 18.7 },
];

const npcHeadImage = new Image();
let npcHeadReady = false;
npcHeadImage.onload = () => {
  npcHeadReady = true;
};
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
  registration: "挂号处",
  consultation: "诊室",
  triage: "分诊区",
  pharmacy: "药房",
  ward: "病房",
  lab: "实验室",
  icu: "ICU",
  office: "办公室",
  hall: "大厅",
};

function roomBounds(room) {
  return { x: room.x * TILE, y: room.y * TILE, w: room.w * TILE, h: room.h * TILE };
}

const triggerZones = rooms.map((room, index) => {
  const bounds = roomBounds(room);
  return {
    id: `zone-${index}`,
    floor: room.floor,
    label: ROOM_KIND_LABELS[room.kind] ?? room.kind,
    x: bounds.x,
    y: bounds.y,
    w: bounds.w,
    h: bounds.h,
  };
});

const zoneState = {
  currentZoneId: null,
  currentZoneLabel: "室外",
  currentFloor: player.floor,
  enteredAtMs: 0,
  staySeconds: 0,
  lastEventText: "暂无触发",
  lastEventAtMs: 0,
};

const taskBoard = {
  title: "医院任务",
  tasks: [
    { text: "到挂号处登记", done: true },
    { text: "前往诊室就诊", done: false },
    { text: "到药房取药", done: false },
    { text: "将样本送至二层实验室", done: false },
    { text: "向护士站汇报状态", done: false },
  ],
};

function deriveTriageInteractPoint() {
  const triageRoom = rooms.find((room) => room.floor === 1 && room.kind === "triage");
  if (!triageRoom) {
    return { x: 10.6 * TILE, y: 17.4 * TILE, floor: 1, radius: 56 };
  }

  const triageRect = roomBounds(triageRoom);
  const roomCenterX = triageRect.x + triageRect.w * 0.5;
  const roomCenterY = triageRect.y + triageRect.h * 0.5;

  const desk = props
    .filter((prop) => prop.floor === triageRoom.floor && prop.type === "reception")
    .find((prop) => {
      const x = prop.x * TILE;
      const y = prop.y * TILE;
      const w = prop.w * TILE;
      const h = prop.h * TILE;
      return x >= triageRect.x && x + w <= triageRect.x + triageRect.w && y >= triageRect.y && y + h <= triageRect.y + triageRect.h;
    });

  const interactX = desk ? (desk.x + desk.w * 0.5) * TILE : roomCenterX;
  const interactY = desk ? (desk.y + desk.h * 0.5 + 0.6) * TILE : roomCenterY;
  const radius = Math.min(92, Math.max(52, Math.round(Math.min(triageRect.w, triageRect.h) * 0.16)));

  return {
    x: interactX,
    y: interactY,
    floor: triageRoom.floor,
    radius,
  };
}

const triageInteractPoint = deriveTriageInteractPoint();
const privateApiConfig = window.HOS_PRIVATE_API || {};
const backendState = {
  baseUrl: privateApiConfig.baseUrl || "http://127.0.0.1:8787",
  apiKey: privateApiConfig.apiKey || "mock-key-001",
  connected: false,
  lastPollAt: 0,
  polling: false,
  submitting: false,
  lastError: "",
};

const triageUi = {
  open: false,
  modal: document.getElementById("triageModal"),
  form: document.getElementById("triageForm"),
  cancelBtn: document.getElementById("triageCancelBtn"),
  fields: {
    symptoms: document.getElementById("symptoms"),
    temp: document.getElementById("temp_c"),
    heartRate: document.getElementById("heart_rate"),
    systolic: document.getElementById("systolic_bp"),
    diastolic: document.getElementById("diastolic_bp"),
    pain: document.getElementById("pain_score"),
  },
  painDisplay: document.getElementById("painDisplay"),
};
const triageDialogueUi = {
  open: false,
  awaitingResult: false,
  modal: document.getElementById("triageDialogueModal"),
  status: document.getElementById("triageDialogueStatus"),
  messages: document.getElementById("triageDialogueMessages"),
  levelBadge: document.getElementById("triageLevelBadge"),
  deptBadge: document.getElementById("triageDeptBadge"),
  evidenceList: document.getElementById("triageEvidenceList"),
  closeBtn: document.getElementById("triageDialogueCloseBtn"),
  lastRenderedAt: "",
};

function mapPatientStateToTask(patient) {
  const activeStates = new Set(["正在分诊", "等待问诊", "问诊中", "待复诊"]);
  return {
    text: `${patient.name} | ${patient.state} | ${patient.location ?? "-"}`,
    done: !activeStates.has(patient.state),
  };
}

async function pollBackendStatuses(force = false) {
  const now = performance.now();
  if (!force && now - backendState.lastPollAt < 2200) return;
  if (backendState.polling) return;

  backendState.polling = true;
  backendState.lastPollAt = now;
  try {
    const response = await fetch(`${backendState.baseUrl}/api/statuses`, {
      headers: { "X-API-Key": backendState.apiKey },
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    const patients = Array.isArray(data.patients) ? data.patients.slice(0, 6) : [];

    taskBoard.title = "实时病人状态";
    taskBoard.tasks = patients.map(mapPatientStateToTask);
    if (taskBoard.tasks.length === 0) {
      taskBoard.tasks = [{ text: "暂无病人状态", done: false }];
    }
    backendState.connected = true;
    backendState.lastError = "";
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "backend offline";
    taskBoard.title = "实时病人状态（离线）";
    taskBoard.tasks = [{ text: "后端未连接，显示本地占位状态", done: false }];
  } finally {
    backendState.polling = false;
  }
}

function canInteractWithTriageDesk() {
  if (player.floor !== triageInteractPoint.floor) return false;
  return Math.hypot(player.x - triageInteractPoint.x, player.y - triageInteractPoint.y) <= triageInteractPoint.radius;
}

function openTriageModal() {
  if (!triageUi.modal || triageUi.open) return;
  triageUi.open = true;
  triageUi.modal.classList.remove("hidden");
  triageUi.modal.setAttribute("aria-hidden", "false");
  keys.clear();
  if (triageUi.fields.symptoms) {
    triageUi.fields.symptoms.focus();
    triageUi.fields.symptoms.selectionStart = triageUi.fields.symptoms.value.length;
    triageUi.fields.symptoms.selectionEnd = triageUi.fields.symptoms.value.length;
  }
}

function closeTriageModal() {
  if (!triageUi.modal) return;
  triageUi.open = false;
  triageUi.modal.classList.add("hidden");
  triageUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function setDialogueBadge(level, department, priority) {
  if (!triageDialogueUi.levelBadge || !triageDialogueUi.deptBadge) return;
  triageDialogueUi.levelBadge.className = "triage-badge";
  if (priority === "H") triageDialogueUi.levelBadge.classList.add("triage-badge--high");
  else if (priority === "M") triageDialogueUi.levelBadge.classList.add("triage-badge--medium");
  else if (priority === "L") triageDialogueUi.levelBadge.classList.add("triage-badge--low");
  else triageDialogueUi.levelBadge.classList.add("triage-badge--muted");

  triageDialogueUi.levelBadge.textContent = level ? `分诊等级 ${level}` : "分级待定";
  triageDialogueUi.deptBadge.textContent = department ? `建议科室 ${department}` : "科室待定";
}

function renderDialogueMessages(messages) {
  if (!triageDialogueUi.messages) return;
  triageDialogueUi.messages.innerHTML = messages
    .map(
      (message) => `
        <article class="triage-message triage-message--${message.role}">
          <span class="triage-message__label">${message.label}</span>
          <div class="triage-message__body">${message.body}</div>
        </article>
      `
    )
    .join("");
  triageDialogueUi.messages.scrollTop = triageDialogueUi.messages.scrollHeight;
}

function renderDialogueEvidence(evidence) {
  if (!triageDialogueUi.evidenceList) return;
  if (!Array.isArray(evidence) || evidence.length === 0) {
    triageDialogueUi.evidenceList.innerHTML = "";
    return;
  }
  triageDialogueUi.evidenceList.innerHTML = evidence
    .map((item) => `<span class="triage-evidence-chip">${item.title || item.id || "命中规则"}</span>`)
    .join("");
}

function openTriageDialogueLegacy(initialPayload) {
  return initialPayload;
}

function closeTriageDialogue() {
  if (!triageDialogueUi.modal) return;
  triageDialogueUi.open = false;
  triageDialogueUi.awaitingResult = false;
  triageDialogueUi.modal.classList.add("hidden");
  triageDialogueUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function syncTriageDialogueLegacy(patient) {
  return patient;
}

function buildTriagePayloadFromForm() {
  const symptoms = triageUi.fields.symptoms?.value?.trim() || "未填写";
  const temp = Number.parseFloat(triageUi.fields.temp?.value ?? "37.8");
  const heartRate = Number.parseInt(triageUi.fields.heartRate?.value ?? "105", 10);
  const systolic = Number.parseInt(triageUi.fields.systolic?.value ?? "132", 10);
  const diastolic = Number.parseInt(triageUi.fields.diastolic?.value ?? "86", 10);
  const pain = Number.parseInt(triageUi.fields.pain?.value ?? "5", 10);

  return {
    patient_id: "P-self",
    name: "你(玩家)",
    symptoms,
    vitals: {
      temp_c: Number.isFinite(temp) ? temp : 37.8,
      heart_rate: Number.isFinite(heartRate) ? heartRate : 105,
      systolic_bp: Number.isFinite(systolic) ? systolic : 132,
      diastolic_bp: Number.isFinite(diastolic) ? diastolic : 86,
      pain_score: Number.isFinite(pain) ? Math.max(0, Math.min(10, pain)) : 5,
    },
    location: zoneState.currentZoneLabel,
    floor: player.floor,
  };
}

async function submitTriageFromModal() {
  if (backendState.submitting || !canInteractWithTriageDesk()) return;
  backendState.submitting = true;
  try {
    const payload = buildTriagePayloadFromForm();
    const response = await fetch(`${backendState.baseUrl}/api/triage/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": backendState.apiKey },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    closeTriageModal();
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "triage submit failed";
  } finally {
    backendState.submitting = false;
  }
}

function submitTriageRequest() {
  if (backendState.submitting || triageUi.open || !canInteractWithTriageDesk()) return;
  openTriageModal();
}

function pointInZone(x, y, zone) {
  return x >= zone.x && x <= zone.x + zone.w && y >= zone.y && y <= zone.y + zone.h;
}

function findCurrentZone(x, y, floor) {
  for (const zone of triggerZones) {
    if (zone.floor !== floor) {
      continue;
    }
    if (pointInZone(x, y, zone)) {
      return zone;
    }
  }
  return null;
}

function recordZoneEvent(text, nowMs) {
  zoneState.lastEventText = text;
  zoneState.lastEventAtMs = nowMs;
  console.log(`[ZoneTrigger] ${text} @ (${Math.round(player.x)}, ${Math.round(player.y)}) F${player.floor}`);
}

function updateZoneTriggers(nowMs) {
  const zone = findCurrentZone(player.x, player.y, player.floor);
  const nextZoneId = zone ? zone.id : null;
  const nextZoneLabel = zone ? zone.label : "室外";

  if (player.floor !== zoneState.currentFloor) {
    zoneState.currentFloor = player.floor;
    zoneState.currentZoneId = nextZoneId;
    zoneState.currentZoneLabel = nextZoneLabel;
    zoneState.enteredAtMs = nowMs;
    zoneState.staySeconds = 0;
    if (nextZoneId !== null) {
      recordZoneEvent(`进入 ${nextZoneLabel}`, nowMs);
    } else {
      recordZoneEvent("移动到室外", nowMs);
    }
    return;
  }

  if (nextZoneId !== zoneState.currentZoneId) {
    if (zoneState.currentZoneId !== null) {
      recordZoneEvent(`离开 ${zoneState.currentZoneLabel}`, nowMs);
    }
    if (nextZoneId !== null) {
      recordZoneEvent(`进入 ${nextZoneLabel}`, nowMs);
      zoneState.enteredAtMs = nowMs;
    } else {
      zoneState.enteredAtMs = 0;
      recordZoneEvent("移动到室外", nowMs);
    }
    zoneState.currentZoneId = nextZoneId;
    zoneState.currentZoneLabel = nextZoneLabel;
    zoneState.staySeconds = 0;
    return;
  }

  if (zoneState.currentZoneId !== null) {
    zoneState.staySeconds = Math.max(0, (nowMs - zoneState.enteredAtMs) / 1000);
  } else {
    zoneState.staySeconds = 0;
  }
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

function currentDoorColliders() {
  return currentFloorDoors().filter((door) => !door.open).map((door) => door.collider);
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
  const quad = [project(rect.x, rect.y, 0, room.floor), project(rect.x + rect.w, rect.y, 0, room.floor), project(rect.x + rect.w, rect.y + rect.h, 0, room.floor), project(rect.x, rect.y + rect.h, 0, room.floor)];
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

function drawCharacterBody(x, y, floor) {
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
  ctx.strokeStyle = palette.playerBody;
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

function drawNpc() {
  const top = drawCharacterBody(npc.x, npc.y, npc.floor);
  drawDefaultHead(top);
}

function characterDepth(x, y) {
  return x + y + CHARACTER_FOOT_RADIUS;
}

function drawLabels() {
  const labels = {
    registration: "挂号处",
    consultation: "诊室",
    triage: "分诊区",
    pharmacy: "药房",
    ward: "病房",
    lab: "实验室",
    icu: "ICU",
    office: "办公室",
    hall: "大厅",
  };

  ctx.fillStyle = palette.label;
  ctx.font = "13px 'Segoe UI'";
  ctx.textAlign = "center";
  for (const room of rooms.filter((item) => item.floor === activeFloor)) {
    const rect = roomBounds(room);
    const point = project(rect.x + rect.w * 0.5, rect.y + rect.h * 0.5, 6, room.floor);
    ctx.fillText(labels[room.kind], point.x, point.y);
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
    ctx.fillStyle = room.kind === "hall" ? "#a67ba6" : "#705970";
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

function drawTriageHint() {
  if (!canInteractWithTriageDesk()) return;
  const point = project(triageInteractPoint.x, triageInteractPoint.y, 48, triageInteractPoint.floor);
  const label = backendState.submitting ? "正在提交分诊..." : triageUi.open ? "填写分诊信息..." : "按 E 开始分诊";
  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 176;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(8, 20, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = backendState.submitting
    ? `rgba(255, 198, 124, ${Math.min(0.95, pulse + 0.2)})`
    : `rgba(112, 234, 255, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);

  ctx.fillStyle = backendState.submitting ? "#ffe4bd" : "#ecfbff";
  ctx.font = "600 13px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 5);
}

function drawTaskBoard() {
  const panelWidth = 430;
  const rowHeight = 20;
  const panelHeight = 38 + rowHeight * taskBoard.tasks.length;
  const panelX = (canvas.width - panelWidth) / 2;
  const panelY = 16;

  ctx.fillStyle = "rgba(16, 11, 24, 0.86)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(255, 241, 184, 0.72)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.textAlign = "left";
  ctx.font = "14px 'Segoe UI'";
  ctx.fillStyle = backendState.connected ? "#fff4d9" : "#ffd3d3";
  ctx.fillText(taskBoard.title, panelX + 12, panelY + 22);
  ctx.font = "11px 'Segoe UI'";
  ctx.fillStyle = backendState.connected ? "#8ef0be" : "#ff9f9f";
  ctx.fillText(backendState.connected ? "API online" : `API offline (${backendState.lastError})`, panelX + panelWidth - 165, panelY + 22);

  ctx.font = "13px 'Segoe UI'";
  for (let index = 0; index < taskBoard.tasks.length; index += 1) {
    const task = taskBoard.tasks[index];
    const y = panelY + 42 + index * rowHeight;
    const marker = task.done ? "[x]" : "[ ]";
    ctx.fillStyle = task.done ? "#83ffc9" : "#f2ebff";
    ctx.fillText(`${marker} ${task.text}`, panelX + 12, y);
  }
}

function drawZoneStatusPanel() {
  const panelWidth = 360;
  const panelHeight = 136;
  const panelX = 18;
  const panelY = canvas.height - panelHeight - 18;
  const nowMs = performance.now();
  const recentEventAge = nowMs - zoneState.lastEventAtMs;

  ctx.fillStyle = "rgba(16, 11, 24, 0.86)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(110, 232, 255, 0.72)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.textAlign = "left";
  ctx.font = "13px 'Segoe UI'";
  ctx.fillStyle = "#a8f8ff";
  ctx.fillText("Zone Trigger Debug", panelX + 12, panelY + 22);

  ctx.fillStyle = "#f2ebff";
  ctx.fillText(`Pos: (${Math.round(player.x)}, ${Math.round(player.y)})`, panelX + 12, panelY + 46);
  ctx.fillText(`Zone: ${zoneState.currentZoneLabel} (F${player.floor})`, panelX + 12, panelY + 68);
  ctx.fillText(`Stay: ${zoneState.currentZoneId ? zoneState.staySeconds.toFixed(1) : "0.0"}s`, panelX + 12, panelY + 90);
  ctx.fillStyle = canInteractWithTriageDesk() ? "#8ef0be" : "#f2ebff";
  ctx.fillText(`Triage: ${canInteractWithTriageDesk() ? "可交互" : "不可交互"}`, panelX + 12, panelY + 112);

  ctx.fillStyle = recentEventAge <= 1200 ? "#82ffd1" : "#cfc6db";
  ctx.fillText(`Last: ${zoneState.lastEventText}`, panelX + 12, panelY + 130);
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
  if (player.floor === floor) drawables.push({ depth: characterDepth(player.x, player.y), draw: drawPlayer });
  if (npc.floor === floor) drawables.push({ depth: characterDepth(npc.x, npc.y), draw: drawNpc });

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

function update(delta, nowMs) {
  pollBackendStatuses(false);
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
  updateZoneTriggers(nowMs);
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
  drawTriageHint();
  drawTaskBoard();
  drawMinimap();
  drawZoneStatusPanel();
}

function mapPatientStateToTask(patient) {
  const activeStates = new Set(["正在分诊", "等待问诊", "问诊中", "待复诊"]);
  const triageText = patient.triage?.level ? ` | L${patient.triage.level}` : "";
  return {
    text: `${patient.name} | ${patient.state} | ${patient.location ?? "-"}${triageText}`,
    done: !activeStates.has(patient.state),
  };
}

async function pollBackendStatuses(force = false) {
  const now = performance.now();
  if (!force && now - backendState.lastPollAt < 2200) return;
  if (backendState.polling) return;

  backendState.polling = true;
  backendState.lastPollAt = now;
  try {
    const response = await fetch(`${backendState.baseUrl}/api/statuses`, {
      headers: { "X-API-Key": backendState.apiKey },
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = await response.json();
    const patients = Array.isArray(data.patients) ? data.patients.slice(0, 6) : [];
    const selfPatient = patients.find((patient) => patient.id === "P-self");

    taskBoard.title = "实时病人状态";
    taskBoard.tasks = patients.map(mapPatientStateToTask);
    if (taskBoard.tasks.length === 0) {
      taskBoard.tasks = [{ text: "暂无病人状态", done: false }];
    }
    backendState.connected = true;
    backendState.lastError = "";
    syncTriageDialogue(selfPatient);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "backend offline";
    taskBoard.title = "实时病人状态（离线）";
    taskBoard.tasks = [{ text: "后端未连接，显示本地占位状态", done: false }];
  } finally {
    backendState.polling = false;
  }
}

function openTriageDialogue(initialPayload) {
  if (!triageDialogueUi.modal) return;
  triageDialogueUi.open = true;
  triageDialogueUi.awaitingResult = true;
  triageDialogueUi.lastRenderedAt = "";
  triageDialogueUi.modal.classList.remove("hidden");
  triageDialogueUi.modal.setAttribute("aria-hidden", "false");
  if (triageDialogueUi.status) {
    triageDialogueUi.status.textContent = "Triage card submitted. The triage agent is reviewing the case now.";
  }
  setDialogueBadge("", "", "");
  renderDialogueEvidence([]);
  renderDialogueMessages([
    {
      role: "user",
      label: "Patient",
      body: `Symptoms: ${initialPayload.symptoms}\nTemp: ${initialPayload.vitals.temp_c} C\nHeart rate: ${initialPayload.vitals.heart_rate} bpm\nPain: ${initialPayload.vitals.pain_score}/10`,
    },
    {
      role: "assistant",
      label: "Triage Agent",
      body: "I have received the triage card and I am generating a recommendation based on the symptoms and rules.",
    },
  ]);
  keys.clear();
}

function syncTriageDialogue(patient) {
  if (!triageDialogueUi.open || !patient || !patient.triage) return;
  const renderedAt = `${patient.updatedAt}|${patient.triage.level}|${patient.location}|${patient.triage.note}`;
  if (triageDialogueUi.lastRenderedAt === renderedAt) return;

  triageDialogueUi.lastRenderedAt = renderedAt;
  triageDialogueUi.awaitingResult = false;
  if (triageDialogueUi.status) {
    triageDialogueUi.status.textContent = `Triage complete. Current recommendation: ${patient.location || "Pending department"}.`;
  }
  setDialogueBadge(patient.triage.level, patient.location, patient.priority);
  const recentUserTurns = patient.memory?.short_term_memory?.turns
    ?.filter((turn) => turn.role === "user")
    .map((turn) => turn.content) || [];
  renderDialogueMessages([
    {
      role: "user",
      label: "Patient",
      body: recentUserTurns.length > 0 ? `Recent symptoms: ${recentUserTurns.join("; ")}` : `${patient.name || "Patient"} has submitted triage information.`,
    },
    {
      role: "assistant",
      label: "Triage Agent",
      body: `Recommended level: ${patient.triage.level}\nRecommended department: ${patient.location || "Pending department"}\nAdvice: ${patient.triage.note || "No additional note."}`,
    },
  ]);
  renderDialogueEvidence(patient.triageEvidence || []);
}

async function submitTriageFromModal() {
  if (backendState.submitting || !canInteractWithTriageDesk()) return;
  backendState.submitting = true;
  try {
    const payload = buildTriagePayloadFromForm();
    const response = await fetch(`${backendState.baseUrl}/api/triage/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": backendState.apiKey },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    closeTriageModal();
    openTriageDialogue(payload);
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "triage submit failed";
  } finally {
    backendState.submitting = false;
  }
}

function submitTriageRequest() {
  if (backendState.submitting || triageUi.open || triageDialogueUi.open || !canInteractWithTriageDesk()) return;
  openTriageModal();
}

let lastTime = performance.now();
updateZoneTriggers(lastTime);

function loop(now) {
  const delta = Math.min((now - lastTime) / 1000, 1 / 30);
  lastTime = now;
  update(delta, now);
  render();
  requestAnimationFrame(loop);
}

window.addEventListener("keydown", (event) => {
  if (triageDialogueUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeTriageDialogue();
      event.preventDefault();
    }
    return;
  }

  if (triageUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeTriageModal();
      event.preventDefault();
    }
    return;
  }

  keys.add(event.code);
  if (event.code === "KeyE" && !event.repeat) {
    submitTriageRequest();
    event.preventDefault();
  }
});

window.addEventListener("keyup", (event) => keys.delete(event.code));

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

updateFloorHud();
pollBackendStatuses(true);
window.dispatchEvent(new Event("resize"));

if (triageUi.form) {
  triageUi.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitTriageFromModal();
  });
}

if (triageUi.cancelBtn) {
  triageUi.cancelBtn.addEventListener("click", () => {
    closeTriageModal();
  });
}

if (triageUi.modal) {
  triageUi.modal.addEventListener("click", (event) => {
    if (event.target === triageUi.modal) closeTriageModal();
  });
}

if (triageDialogueUi.closeBtn) {
  triageDialogueUi.closeBtn.addEventListener("click", () => {
    closeTriageDialogue();
  });
}

if (triageDialogueUi.modal) {
  triageDialogueUi.modal.addEventListener("click", (event) => {
    if (event.target === triageDialogueUi.modal) closeTriageDialogue();
  });
}

if (triageUi.fields.pain && triageUi.painDisplay) {
  triageUi.painDisplay.textContent = triageUi.fields.pain.value;
  triageUi.fields.pain.addEventListener("input", (event) => {
    triageUi.painDisplay.textContent = event.target.value;
  });
}

requestAnimationFrame(loop);

triageDialogueUi.form = document.getElementById("triageDialogueForm");
triageDialogueUi.input = document.getElementById("triageDialogueInput");
triageDialogueUi.sendBtn = document.getElementById("triageDialogueSendBtn");

const triageConversationState = {
  patientId: "P-self",
  sessionId: "session-main",
  sending: false,
};

function escapeDialogueHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderDialogueMessages(messages) {
  if (!triageDialogueUi.messages) return;
  triageDialogueUi.messages.innerHTML = messages
    .map(
      (message) => `
        <article class="triage-message triage-message--${message.role}">
          <span class="triage-message__label">${escapeDialogueHtml(message.label)}</span>
          <div class="triage-message__body">${escapeDialogueHtml(message.body)}</div>
        </article>
      `
    )
    .join("");
  triageDialogueUi.messages.scrollTop = triageDialogueUi.messages.scrollHeight;
}

function openTriageDialogue(initialPayload) {
  if (!triageDialogueUi.modal) return;
  triageDialogueUi.open = true;
  triageDialogueUi.awaitingResult = true;
  triageDialogueUi.lastRenderedAt = "";
  triageDialogueUi.modal.classList.remove("hidden");
  triageDialogueUi.modal.setAttribute("aria-hidden", "false");
  if (triageDialogueUi.status) {
    triageDialogueUi.status.textContent = "分诊卡已提交，分诊 agent 正在先做初步判断，并准备继续追问。";
  }
  setDialogueBadge("", "", "");
  renderDialogueEvidence([]);
  renderDialogueMessages([
    {
      role: "user",
      label: "患者",
      body: `症状：${initialPayload.symptoms}\n体温：${initialPayload.vitals.temp_c}°C\n心率：${initialPayload.vitals.heart_rate} bpm\n疼痛：${initialPayload.vitals.pain_score}/10`,
    },
    {
      role: "assistant",
      label: "分诊 Agent",
      body: "我先基于问诊卡做一个初步判断，接下来会继续追问还不够明确的信息。",
    },
  ]);
  if (triageDialogueUi.input) triageDialogueUi.input.value = "";
  keys.clear();
}

function syncTriageDialogue(patient) {
  if (!triageDialogueUi.open || !patient) return;
  const dialogue = patient.dialogue || {};
  const triage = patient.triage || {};
  const renderedAt = `${patient.updatedAt}|${dialogue.status || ""}|${triage.level || ""}|${triage.note || ""}`;
  if (triageDialogueUi.lastRenderedAt === renderedAt) return;

  triageDialogueUi.lastRenderedAt = renderedAt;
  triageDialogueUi.awaitingResult = false;

  if (triageDialogueUi.status) {
    if (dialogue.status === "needs_more_info") {
      triageDialogueUi.status.textContent = "分诊 agent 还需要补充一些信息，答得越具体，建议会越准确。";
    } else if (dialogue.status === "triaged") {
      triageDialogueUi.status.textContent = `分诊建议已更新：建议前往 ${patient.location || "待定科室"}。`;
    } else {
      triageDialogueUi.status.textContent = "正在同步最新分诊结果。";
    }
  }

  setDialogueBadge(triage.level, patient.location, patient.priority);

  const turns = patient.memory?.short_term_memory?.turns || [];
  const messages = turns.map((turn) => ({
    role: turn.role === "assistant" ? "assistant" : "user",
    label: turn.role === "assistant" ? "分诊 Agent" : "患者",
    body: turn.content || "",
  }));

  if (messages.length === 0 && dialogue.assistant_message) {
    messages.push({ role: "assistant", label: "分诊 Agent", body: dialogue.assistant_message });
  }

  renderDialogueMessages(messages);
  renderDialogueEvidence(patient.triageEvidence || []);
}

async function submitTriageFromModal() {
  if (backendState.submitting || !canInteractWithTriageDesk()) return;
  backendState.submitting = true;
  try {
    const payload = buildTriagePayloadFromForm();
    payload.session_id = triageConversationState.sessionId;
    const response = await fetch(`${backendState.baseUrl}/api/triage/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": backendState.apiKey },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    closeTriageModal();
    openTriageDialogue(payload);
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "triage submit failed";
  } finally {
    backendState.submitting = false;
  }
}

async function submitTriageDialogueReply() {
  if (triageConversationState.sending || !triageDialogueUi.input) return;
  const message = triageDialogueUi.input.value.trim();
  if (!message) return;

  triageConversationState.sending = true;
  if (triageDialogueUi.sendBtn) triageDialogueUi.sendBtn.disabled = true;
  try {
    const response = await fetch(`${backendState.baseUrl}/api/triage/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": backendState.apiKey },
      body: JSON.stringify({
        patient_id: triageConversationState.patientId,
        session_id: triageConversationState.sessionId,
        name: "你(玩家)",
        message,
      }),
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    triageDialogueUi.input.value = "";
    const data = await response.json();
    if (data.patient) syncTriageDialogue(data.patient);
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "triage chat failed";
    if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = `对话发送失败：${backendState.lastError}`;
    }
  } finally {
    triageConversationState.sending = false;
    if (triageDialogueUi.sendBtn) triageDialogueUi.sendBtn.disabled = false;
  }
}

if (triageDialogueUi.form) {
  triageDialogueUi.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitTriageDialogueReply();
  });
}

// ===== Queue merge layer (ported from replace branch, adapted to current main flow) =====
const QUEUE_DEPARTMENTS = {
  internal: { id: "internal", name: "Internal" },
  surgery: { id: "surgery", name: "Surgery" },
  pediatrics: { id: "pediatrics", name: "Pediatrics" },
  emergency: { id: "emergency", name: "Emergency", priority: true },
  fever: { id: "fever", name: "Fever Clinic" },
};

function createQueueManager() {
  const deptIds = Object.keys(QUEUE_DEPARTMENTS);
  return {
    queues: Object.fromEntries(deptIds.map((id) => [id, []])),
    currentTicket: Object.fromEntries(deptIds.map((id) => [id, 0])),
    calledTicket: Object.fromEntries(deptIds.map((id) => [id, null])),
    calledUntil: Object.fromEntries(deptIds.map((id) => [id, 0])),
    lastCallAt: Object.fromEntries(deptIds.map((id) => [id, 0])),
    playerTicket: null,
    history: [],
  };
}

function generateTicketNumber(queueManager, departmentId) {
  queueManager.currentTicket[departmentId] += 1;
  return {
    number: queueManager.currentTicket[departmentId],
    departmentId,
    departmentName: QUEUE_DEPARTMENTS[departmentId].name,
    timestamp: Date.now(),
    status: "waiting",
  };
}

function addPlayerToQueue(queueManager, departmentId) {
  if (!queueManager.queues[departmentId]) return null;
  const existing = queueManager.playerTicket;
  if (existing && existing.status === "waiting" && existing.departmentId === departmentId) {
    return existing;
  }
  const ticket = generateTicketNumber(queueManager, departmentId);
  ticket.patientId = "player";
  queueManager.playerTicket = ticket;
  queueManager.queues[departmentId].push(ticket);
  return ticket;
}

function callNext(queueManager, departmentId) {
  const queue = queueManager.queues[departmentId];
  if (!queue || queue.length === 0) return null;

  const emergencyQueue = queueManager.queues.emergency;
  if (departmentId !== "emergency" && emergencyQueue && emergencyQueue.length > 0) {
    return callNext(queueManager, "emergency");
  }

  const ticket = queue.shift();
  ticket.status = "called";
  queueManager.calledTicket[departmentId] = ticket;
  const now = Date.now();
  queueManager.calledUntil[departmentId] = now + (ticket.patientId === "player" ? 120000 : 5000);
  queueManager.lastCallAt[departmentId] = now;
  return ticket;
}

function completeTicket(queueManager, departmentId, ticket) {
  if (!ticket) return;
  ticket.status = "completed";
  queueManager.calledTicket[departmentId] = null;
  queueManager.history.push(ticket);
  if (queueManager.playerTicket && queueManager.playerTicket.number === ticket.number) {
    queueManager.playerTicket = null;
  }
}

function updateQueueCalls(queueManager, nowMs) {
  for (const deptId of Object.keys(QUEUE_DEPARTMENTS)) {
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

function getWaitingCount(queueManager, departmentId) {
  return queueManager.queues[departmentId]?.length || 0;
}

function getQueuePosition(queueManager, ticket) {
  if (!ticket || !queueManager.queues[ticket.departmentId]) return null;
  const index = queueManager.queues[ticket.departmentId].findIndex(
    (item) => item.number === ticket.number && item.patientId === ticket.patientId
  );
  return index >= 0 ? index + 1 : null;
}

function drawQueueBoard(ctx, canvas, queueManager) {
  const panelWidth = 320;
  const panelHeight = 236;
  const panelX = canvas.width - panelWidth - 16;
  const panelY = canvas.height - panelHeight - 16;

  ctx.fillStyle = "rgba(14, 16, 28, 0.9)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(125, 233, 255, 0.74)";
  ctx.lineWidth = 2;
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.fillStyle = "#c9f4ff";
  ctx.font = "bold 14px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText("Queue Board", panelX + panelWidth / 2, panelY + 22);

  let y = panelY + 50;
  for (const dept of Object.values(QUEUE_DEPARTMENTS)) {
    const waiting = getWaitingCount(queueManager, dept.id);
    const called = queueManager.calledTicket[dept.id];
    const calledNo = called ? called.number : "-";
    const isPlayerDept = queueManager.playerTicket?.departmentId === dept.id;

    if (isPlayerDept) {
      ctx.fillStyle = "rgba(132, 255, 201, 0.14)";
      ctx.fillRect(panelX + 6, y - 14, panelWidth - 12, 22);
    }

    ctx.fillStyle = dept.priority ? "#ff8f8f" : "#f0ecff";
    ctx.font = "12px 'Segoe UI'";
    ctx.textAlign = "left";
    ctx.fillText(`${isPlayerDept ? "* " : ""}${dept.name}`, panelX + 12, y);

    ctx.fillStyle = "#8ef0be";
    ctx.textAlign = "right";
    ctx.fillText(`Waiting ${waiting}`, panelX + panelWidth - 108, y);

    ctx.fillStyle = "#ffe99c";
    ctx.fillText(`Called ${calledNo}`, panelX + panelWidth - 12, y);
    y += 28;
  }

  const playerTicket = queueManager.playerTicket;
  const footerY = panelY + panelHeight - 26;
  ctx.textAlign = "left";
  ctx.font = "11px 'Segoe UI'";
  if (playerTicket) {
    const pos = getQueuePosition(queueManager, playerTicket);
    const called = queueManager.calledTicket[playerTicket.departmentId];
    if (called && called.patientId === "player") {
      ctx.fillStyle = "#ffe1a8";
      ctx.fillText(`Your ticket ${playerTicket.number}: called`, panelX + 12, footerY);
    } else {
      ctx.fillStyle = "#cfd8ff";
      ctx.fillText(
        `Ticket ${playerTicket.number} | ${playerTicket.departmentName} | Ahead ${pos ?? 0}`,
        panelX + 12,
        footerY
      );
    }
  } else {
    ctx.fillStyle = "#9fb0c0";
    ctx.fillText("Not queued yet", panelX + 12, footerY);
  }
}

function mapQueueDepartmentFromTriage(patient) {
  const location = (patient?.location || "").toLowerCase();
  const priority = patient?.priority;
  if (location.includes("emergency") || priority === "H") return "emergency";
  if (location.includes("fever")) return "fever";
  if (location.includes("surgery")) return "surgery";
  if (location.includes("pediatrics")) return "pediatrics";
  return "internal";
}

const queueManager = createQueueManager();
let queueSeeded = false;
let lastAutoQueuedAt = 0;

function seedQueueIfNeeded() {
  if (queueSeeded) return;
  queueSeeded = true;
  const seedList = [
    ["internal", 3],
    ["surgery", 2],
    ["pediatrics", 1],
    ["fever", 1],
    ["emergency", 1],
  ];
  for (const [deptId, count] of seedList) {
    for (let i = 0; i < count; i += 1) {
      const ticket = generateTicketNumber(queueManager, deptId);
      ticket.patientId = `seed-${deptId}-${i + 1}`;
      queueManager.queues[deptId].push(ticket);
    }
  }
}

function syncPlayerQueueFromPatient(patient) {
  if (!patient || !patient.triage) return;
  const dialogueStatus = patient.dialogue?.status;
  const now = Date.now();
  if (dialogueStatus !== "triaged" || now - lastAutoQueuedAt < 1200) return;
  const targetDept = mapQueueDepartmentFromTriage(patient);
  const current = queueManager.playerTicket;
  if (current && current.status === "waiting" && current.departmentId === targetDept) return;
  addPlayerToQueue(queueManager, targetDept);
  lastAutoQueuedAt = now;
}

const __originalSyncTriageDialogue = syncTriageDialogue;
syncTriageDialogue = function patchedSyncTriageDialogue(patient) {
  __originalSyncTriageDialogue(patient);
  syncPlayerQueueFromPatient(patient);
};

const __originalPollBackendStatuses = pollBackendStatuses;
pollBackendStatuses = async function patchedPollBackendStatuses(force = false) {
  seedQueueIfNeeded();
  return __originalPollBackendStatuses(force);
};

const __originalUpdate = update;
update = function patchedUpdate(delta, nowMs) {
  __originalUpdate(delta, nowMs);
  updateQueueCalls(queueManager, nowMs);
};

const __originalRender = render;
render = function patchedRender() {
  __originalRender();
  drawQueueBoard(ctx, canvas, queueManager);
};

// ===== Random NPC generation layer (frontend-only merge) =====
const MERGED_NPC_TYPES = {
  PATIENT: "patient",
  STAFF: "staff",
};

const MERGED_NPC_STATES = {
  IDLE: "idle",
  WALKING: "walking",
  WAITING: "waiting",
};

function createMergedNpc(id, type, floor, x, y, options = {}) {
  return {
    id,
    type,
    floor,
    x,
    y,
    state: options.state || MERGED_NPC_STATES.IDLE,
    speed: options.speed || (type === MERGED_NPC_TYPES.PATIENT ? 42 : 48),
    targetX: null,
    targetY: null,
    walkTimer: 0,
    walkInterval: 2200 + Math.random() * 3500,
    bodyColor: options.bodyColor || (type === MERGED_NPC_TYPES.PATIENT ? "#6ed3b1" : "#7bb2f0"),
    headColor: options.headColor || "#f0c9b7",
    name: options.name || (type === MERGED_NPC_TYPES.PATIENT ? "Patient" : "Staff"),
  };
}

function getSpawnAreasForMergedNpcs() {
  return rooms
    .filter((room) => room.kind === "hall" || room.kind === "triage")
    .map((room) => ({ room, bounds: roomBounds(room) }));
}

function randomPointInBounds(bounds, padding = 22) {
  const minX = bounds.x + padding;
  const minY = bounds.y + padding;
  const maxX = bounds.x + bounds.w - padding;
  const maxY = bounds.y + bounds.h - padding;
  return {
    x: minX + Math.random() * Math.max(1, maxX - minX),
    y: minY + Math.random() * Math.max(1, maxY - minY),
  };
}

function initMergedRandomNpcs(count = 10) {
  const areas = getSpawnAreasForMergedNpcs();
  const list = [];
  for (let i = 0; i < count; i += 1) {
    const area = areas[i % areas.length];
    if (!area) break;
    let point = randomPointInBounds(area.bounds);
    let tries = 0;
    while (!canMoveTo(point.x, point.y, area.room.floor) && tries < 20) {
      point = randomPointInBounds(area.bounds);
      tries += 1;
    }
    list.push(
      createMergedNpc(`merged-npc-${i + 1}`, MERGED_NPC_TYPES.PATIENT, area.room.floor, point.x, point.y, {
        name: `Patient-${i + 1}`,
      })
    );
  }
  return list;
}

function pickMergedNpcTarget(npc) {
  const candidateRooms = rooms.filter((room) => room.floor === npc.floor && (room.kind === "hall" || room.kind === "triage"));
  if (candidateRooms.length === 0) return;
  const room = candidateRooms[Math.floor(Math.random() * candidateRooms.length)];
  const bounds = roomBounds(room);
  let point = randomPointInBounds(bounds);
  let tries = 0;
  while (!canMoveTo(point.x, point.y, npc.floor) && tries < 20) {
    point = randomPointInBounds(bounds);
    tries += 1;
  }
  npc.targetX = point.x;
  npc.targetY = point.y;
  npc.state = MERGED_NPC_STATES.WALKING;
}

function updateMergedNpc(npc, delta) {
  npc.walkTimer += delta * 1000;

  if (npc.state !== MERGED_NPC_STATES.WAITING && npc.walkTimer >= npc.walkInterval && npc.targetX === null) {
    pickMergedNpcTarget(npc);
    npc.walkTimer = 0;
  }

  if (npc.targetX === null || npc.targetY === null || npc.state !== MERGED_NPC_STATES.WALKING) return;

  const dx = npc.targetX - npc.x;
  const dy = npc.targetY - npc.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 3) {
    npc.x = npc.targetX;
    npc.y = npc.targetY;
    npc.targetX = null;
    npc.targetY = null;
    npc.state = MERGED_NPC_STATES.IDLE;
    npc.walkTimer = 0;
    npc.walkInterval = 2200 + Math.random() * 3500;
    return;
  }

  const vx = (dx / dist) * npc.speed * delta;
  const vy = (dy / dist) * npc.speed * delta;
  const nx = npc.x + vx;
  const ny = npc.y + vy;
  if (canMoveTo(nx, ny, npc.floor)) {
    npc.x = nx;
    npc.y = ny;
  } else {
    npc.targetX = null;
    npc.targetY = null;
    npc.state = MERGED_NPC_STATES.IDLE;
    npc.walkTimer = 0;
  }
}

function drawMergedNpc(npc, alpha = 1) {
  const base = project(npc.x, npc.y, 0, npc.floor);
  const top = project(npc.x, npc.y, CHARACTER_BODY_HEIGHT - 2, npc.floor);

  ctx.save();
  ctx.globalAlpha *= alpha;

  ctx.fillStyle = "rgba(0,0,0,0.25)";
  ctx.beginPath();
  ctx.ellipse(base.x, base.y + 8, CHARACTER_FOOT_RADIUS + 3, CHARACTER_FOOT_RADIUS - 1, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = npc.bodyColor;
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.moveTo(base.x, base.y - 1);
  ctx.lineTo(top.x, top.y + 6);
  ctx.stroke();

  ctx.fillStyle = npc.headColor;
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, CHARACTER_HEAD_RADIUS - 1, 0, Math.PI * 2);
  ctx.fill();

  if (npc.state === MERGED_NPC_STATES.WAITING) {
    ctx.fillStyle = "#ffe99c";
    ctx.font = "10px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText("Waiting", top.x, top.y - 16);
  }

  ctx.restore();
}

const mergedRandomNpcs = initMergedRandomNpcs(10);

const __originalDrawFloorLayer = drawFloorLayer;
drawFloorLayer = function patchedDrawFloorLayerWithMergedNpcs(floor, activeDoor, dimmed) {
  __originalDrawFloorLayer(floor, activeDoor, dimmed);
  const alpha = dimmed ? 0.35 : 1;
  for (const npcItem of mergedRandomNpcs) {
    if (npcItem.floor !== floor) continue;
    drawMergedNpc(npcItem, alpha);
  }
};

const __queuePatchedUpdate = update;
update = function patchedUpdateWithMergedNpcs(delta, nowMs) {
  __queuePatchedUpdate(delta, nowMs);
  for (const npcItem of mergedRandomNpcs) {
    updateMergedNpc(npcItem, delta);
  }
};
