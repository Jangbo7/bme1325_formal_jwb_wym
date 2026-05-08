import { createBackendClient } from "../agent/client.js";
import { createAgentStore, buildDialogueMessages } from "../agent/store.js";
import { buildTriagePayloadFromFormValues } from "../agent/triage-form.js";
import { renderDialogueEvidence as renderDialogueEvidenceView, renderDialogueMessages as renderDialogueMessagesView, setDialogueBadges } from "../agent/triage-dialogue.js";
import { createQueueRuntime } from "../queue/runtime.js";
import { createNpcRuntime } from "../npc/runtime.js";
import { createFixedNpcRuntime } from "../npc/fixed-runtime.js";
import { createTaskBoardPresenter } from "../ui/task-board.js";
import { renderNpcDialogue } from "../ui/npc-dialogue.js";

const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");
const floorStateLabel = document.getElementById("floor-state");
const hudHelpToggle = document.getElementById("hudHelpToggle");
const hudHelpPanel = document.getElementById("hudHelpPanel");
const hudTasksToggle = document.getElementById("hudTasksToggle");
const hudLabelsToggle = document.getElementById("hudLabelsToggle");
const hudDebugToggle = document.getElementById("hudDebugToggle");

const TILE = 32;
const WALL_THICKNESS = TILE * 0.5;
const DOOR_THICKNESS = 12;
const WALL_HEIGHT = 58;
const DOOR_SENSOR_DISTANCE = 64;
const DOOR_CLOSE_DISTANCE = 96;
const CHARACTER_FOOT_RADIUS = 7;
const CHARACTER_BODY_HEIGHT = 32;
const CHARACTER_HEAD_RADIUS = 8;
const WORLD = { width: 84 * TILE, height: 54 * TILE };
const FLOOR_BASE_Z = { 1: 0 };

const keys = new Set();
const camera = { x: 0, y: 0 };
let fixedNpcRuntime = null;
const overlayState = {
  helpOpen: false,
  tasksOpen: false,
  labelsOpen: false,
  debugOpen: false,
};

const palette = {
  grassA: "#86bf5e",
  grassB: "#7ab356",
  grassC: "#93c96d",
  dirt: "#b98a57",
  path: "#c9b184",
  roomFloor: "#dfcfaa",
  hallFloor: "#e8d7b6",
  roomTrim: "#c09d6c",
  wallFront: "#b97e4f",
  wallSide: "#9f683f",
  wallTop: "#d8b07c",
  wallEdge: "rgba(99, 57, 29, 0.45)",
  bed: "#8ebed3",
  desk: "#9c7248",
  sofa: "#8fae69",
  plant: "#6fa154",
  screen: "#9fd2d8",
  cabinet: "#b9a17e",
  reception: "#c58d57",
  doorFrame: "#8d5c37",
  doorGlass: "#b7d7dc",
  doorSensor: "#ffd46a",
  playerBody: "#4b79d8",
  playerAccent: "#9ec7ff",
  playerHead: "#f6d4c0",
  playerHair: "#6a4a2f",
  playerLeg: "#3f4d67",
  shadow: "rgba(44, 30, 18, 0.22)",
  label: "rgba(74, 46, 25, 0.86)",
  inactiveMask: "rgba(15, 15, 18, 0.48)",
  uiPanel: "rgba(47, 31, 20, 0.8)",
  uiStroke: "rgba(251, 230, 179, 0.82)",
};

const player = {
  x: 14 * TILE,
  y: 18 * TILE,
  floor: 1,
  width: CHARACTER_FOOT_RADIUS * 2,
  height: CHARACTER_FOOT_RADIUS * 2,
  speed: 180,
  facing: "down",
};

const floorSpawns = {
  1: { x: 14 * TILE, y: 18 * TILE },
};
let activeFloor = 1;

const npcHeadImage = new Image();
let npcHeadReady = false;
npcHeadImage.onload = () => {
  npcHeadReady = true;
};
npcHeadImage.src = "./img/head_photo-head@1x.png";

const rooms = [
  { floor: 1, x: 4, y: 5, w: 13, h: 9, kind: "registration" },
  { floor: 1, x: 18, y: 5, w: 14, h: 9, kind: "triage" },
  { floor: 1, x: 33, y: 5, w: 14, h: 9, kind: "consultation" },
  { floor: 1, x: 48, y: 5, w: 14, h: 9, kind: "consultation" },
  { floor: 1, x: 63, y: 5, w: 13, h: 9, kind: "pharmacy" },
  { floor: 1, x: 8, y: 17, w: 18, h: 12, kind: "hall" },
  { floor: 1, x: 27, y: 17, w: 15, h: 11, kind: "lab" },
  { floor: 1, x: 43, y: 17, w: 15, h: 11, kind: "icu" },
  { floor: 1, x: 59, y: 17, w: 14, h: 11, kind: "ward" },
  { floor: 1, x: 10, y: 32, w: 16, h: 11, kind: "office" },
  { floor: 1, x: 27, y: 32, w: 16, h: 11, kind: "empty_room" },
  { floor: 1, x: 44, y: 32, w: 15, h: 11, kind: "empty_room" },
  { floor: 1, x: 60, y: 32, w: 14, h: 11, kind: "empty_room" },
  { floor: 1, x: 31, y: 45, w: 22, h: 7, kind: "hall" },
];

const doorSpecs = [
  { roomIndex: 0, side: "bottom", offset: 5.4, length: 2.2, label: "REG-A" },
  { roomIndex: 1, side: "bottom", offset: 6.0, length: 2.2, label: "TRIAGE-A" },
  { roomIndex: 2, side: "bottom", offset: 5.8, length: 2.2, label: "CONS-1" },
  { roomIndex: 3, side: "bottom", offset: 5.8, length: 2.2, label: "CONS-2" },
  { roomIndex: 4, side: "bottom", offset: 5.2, length: 2.2, label: "PHARM-A" },
  { roomIndex: 5, side: "top", offset: 7.4, length: 2.2, label: "HALL-N" },
  { roomIndex: 5, side: "right", offset: 4.8, length: 2.0, label: "HALL-E" },
  { roomIndex: 6, side: "top", offset: 5.8, length: 2.2, label: "LAB-A" },
  { roomIndex: 7, side: "top", offset: 5.8, length: 2.2, label: "ICU-A" },
  { roomIndex: 8, side: "top", offset: 5.2, length: 2.2, label: "WARD-A" },
  { roomIndex: 9, side: "top", offset: 5.8, length: 2.2, label: "OFFICE-A" },
  { roomIndex: 10, side: "top", offset: 5.8, length: 2.2, label: "RESERVE-A" },
  { roomIndex: 11, side: "top", offset: 5.4, length: 2.2, label: "RESERVE-B" },
  { roomIndex: 12, side: "top", offset: 5.2, length: 2.2, label: "RESERVE-C" },
  { roomIndex: 13, side: "top", offset: 9.4, length: 2.4, label: "SOUTH-HALL" },
];

const props = [
  { floor: 1, x: 6.2, y: 7.1, w: 4.4, h: 1.4, type: "reception", z: 22 },
  { floor: 1, x: 12.1, y: 7.2, w: 1.4, h: 1.4, type: "screen", z: 24 },
  { floor: 1, x: 20.8, y: 7.4, w: 3.6, h: 1.4, type: "reception", z: 22 },
  { floor: 1, x: 26.2, y: 8.0, w: 1.4, h: 1.4, type: "screen", z: 24 },
  { floor: 1, x: 36.1, y: 7.2, w: 2.4, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 40.0, y: 7.2, w: 2.4, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 50.2, y: 7.2, w: 2.4, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 54.1, y: 7.2, w: 2.4, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 65.5, y: 7.2, w: 3.4, h: 1.2, type: "cabinet", z: 22 },
  { floor: 1, x: 70.4, y: 8.1, w: 1.4, h: 1.4, type: "plant", z: 24 },
  { floor: 1, x: 14.2, y: 20.4, w: 3.8, h: 1.4, type: "reception", z: 22 },
  { floor: 1, x: 20.0, y: 24.2, w: 2.3, h: 1.2, type: "sofa", z: 18 },
  { floor: 1, x: 31.2, y: 20.2, w: 1.4, h: 1.4, type: "screen", z: 24 },
  { floor: 1, x: 34.5, y: 20.1, w: 3.0, h: 1.2, type: "cabinet", z: 24 },
  { floor: 1, x: 46.5, y: 20.1, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 50.4, y: 20.1, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 61.5, y: 20.1, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 65.4, y: 20.1, w: 2.5, h: 1.2, type: "bed", z: 18 },
  { floor: 1, x: 14.0, y: 35.3, w: 2.8, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 18.0, y: 35.3, w: 1.4, h: 1.4, type: "plant", z: 24 },
  { floor: 1, x: 30.0, y: 35.5, w: 3.4, h: 1.3, type: "sofa", z: 18 },
  { floor: 1, x: 34.4, y: 35.7, w: 1.4, h: 1.4, type: "plant", z: 24 },
  { floor: 1, x: 47.2, y: 35.6, w: 3.4, h: 1.3, type: "sofa", z: 18 },
  { floor: 1, x: 50.8, y: 35.5, w: 2.4, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 63.2, y: 35.5, w: 3.0, h: 1.2, type: "cabinet", z: 22 },
  { floor: 1, x: 66.8, y: 35.5, w: 1.4, h: 1.4, type: "plant", z: 24 },
];

const ROOM_KIND_LABELS = {
  registration: "Registration",
  consultation: "Consultation",
  triage: "Triage",
  pharmacy: "Doctor Entry",
  ward: "Ward",
  lab: "Lab",
  icu: "ICU",
  office: "Office",
  hall: "Hall",
  empty_room: "Reserved",
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
  currentZoneLabel: "Unknown",
  currentFloor: player.floor,
  enteredAtMs: 0,
  staySeconds: 0,
  lastEventText: "No zone event yet",
  lastEventAtMs: 0,
};

const taskBoard = {
  title: "Patient Workflow",
  tasks: [
    { text: "Go to the triage desk", done: true },
    { text: "Complete triage intake", done: false },
    { text: "Wait for queue assignment", done: false },
    { text: "Follow the highlighted destination", done: false },
    { text: "Enter the consultation room when called", done: false },
  ],
};

const runtimeDebug = {
  frames: 0,
  lastLoopAt: 0,
  lastRenderAt: 0,
  pollSuccessCount: 0,
  pollFailureCount: 0,
  lastPollResult: "pending",
  lastError: "",
};

function deriveRoomInteractPoint(roomKind, fallback, options = {}) {
  const targetRoom = rooms.find((room) => room.floor === fallback.floor && room.kind === roomKind)
    || rooms.find((room) => room.kind === roomKind);

  if (!targetRoom) {
    return { ...fallback };
  }

  const roomRect = roomBounds(targetRoom);
  const roomCenterX = roomRect.x + roomRect.w * 0.5;
  const roomCenterY = roomRect.y + roomRect.h * 0.5;

  let interactX = roomCenterX;
  let interactY = roomCenterY;

  if (options.preferReception) {
    const desk = props
      .filter((prop) => prop.floor === targetRoom.floor && prop.type === "reception")
      .find((prop) => {
        const x = prop.x * TILE;
        const y = prop.y * TILE;
        const w = prop.w * TILE;
        const h = prop.h * TILE;
        return x >= roomRect.x && x + w <= roomRect.x + roomRect.w && y >= roomRect.y && y + h <= roomRect.y + roomRect.h;
      });
    if (desk) {
      interactX = (desk.x + desk.w * 0.5) * TILE;
      interactY = (desk.y + desk.h * 0.5 + 0.6) * TILE;
    }
  }

  const radius = Math.min(92, Math.max(52, Math.round(Math.min(roomRect.w, roomRect.h) * 0.16)));
  return {
    x: interactX,
    y: interactY,
    floor: targetRoom.floor,
    radius,
  };
}

function deriveTriageInteractPoint() {
  return deriveRoomInteractPoint("triage", { x: 25.2 * TILE, y: 11.4 * TILE, floor: 1, radius: 64 }, { preferReception: true });
}

function deriveRegistrationInteractPoint() {
  return deriveRoomInteractPoint("registration", { x: 11.2 * TILE, y: 11.2 * TILE, floor: 1, radius: 64 }, { preferReception: true });
}

function deriveDoctorEntryInteractPoint() {
  return deriveRoomInteractPoint("pharmacy", { x: 69.2 * TILE, y: 11.2 * TILE, floor: 1, radius: 64 }, {});
}

const triageInteractPoint = deriveTriageInteractPoint();
const registrationInteractPoint = deriveRegistrationInteractPoint();
const doctorEntryInteractPoint = deriveDoctorEntryInteractPoint();
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
const backendClient = createBackendClient({ baseUrl: backendState.baseUrl, apiKey: backendState.apiKey });
const agentStore = createAgentStore();
const queueRuntime = createQueueRuntime();
const taskBoardPresenter = createTaskBoardPresenter(taskBoard);

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

function canInteractWithTriageDesk() {
  if (player.floor !== triageInteractPoint.floor) return false;
  return Math.hypot(player.x - triageInteractPoint.x, player.y - triageInteractPoint.y) <= triageInteractPoint.radius;
}

function canInteractWithRegistrationDesk() {
  if (player.floor !== registrationInteractPoint.floor) return false;
  return Math.hypot(player.x - registrationInteractPoint.x, player.y - registrationInteractPoint.y) <= registrationInteractPoint.radius;
}

function canInteractWithDoctorEntry() {
  if (player.floor !== doctorEntryInteractPoint.floor) return false;
  return Math.hypot(player.x - doctorEntryInteractPoint.x, player.y - doctorEntryInteractPoint.y) <= doctorEntryInteractPoint.radius;
}

function pushStatusHint(text) {
  zoneState.lastEventText = text;
  zoneState.lastEventAtMs = performance.now();
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
  setDialogueBadges(triageDialogueUi.levelBadge, triageDialogueUi.deptBadge, level, department, priority);
}

function renderDialogueMessages(messages) {
  renderDialogueMessagesView(triageDialogueUi.messages, messages);
}

function renderDialogueEvidence(evidence) {
  renderDialogueEvidenceView(triageDialogueUi.evidenceList, evidence);
}

function buildTriagePayloadFromForm() {
  return buildTriagePayloadFromFormValues({
    fields: triageUi.fields,
    zoneLabel: zoneState.currentZoneLabel,
    floor: player.floor,
    patientId: triageConversationState.patientId,
  });
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
  const nextZoneLabel = zone ? zone.label : "Unknown";

  if (player.floor !== zoneState.currentFloor) {
    zoneState.currentFloor = player.floor;
    zoneState.currentZoneId = nextZoneId;
    zoneState.currentZoneLabel = nextZoneLabel;
    zoneState.enteredAtMs = nowMs;
    zoneState.staySeconds = 0;
    if (nextZoneId !== null) {
      recordZoneEvent(`Entered ${nextZoneLabel}`, nowMs);
    } else {
      recordZoneEvent("Left all zones", nowMs);
    }
    return;
  }

  if (nextZoneId !== zoneState.currentZoneId) {
    if (zoneState.currentZoneId !== null) {
      recordZoneEvent(`Exited ${zoneState.currentZoneLabel}`, nowMs);
    }
    if (nextZoneId !== null) {
      recordZoneEvent(`Entered ${nextZoneLabel}`, nowMs);
      zoneState.enteredAtMs = nowMs;
    } else {
      zoneState.enteredAtMs = 0;
      recordZoneEvent("Left all zones", nowMs);
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
  return {
    x: x - camera.x + canvas.width / 2,
    y: y - camera.y + canvas.height / 2 - zForFloor(z, floor),
  };
}

function drawRect(rect, fillStyle, strokeStyle = palette.wallEdge, lineWidth = 1) {
  ctx.fillStyle = fillStyle;
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
  if (strokeStyle) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
  }
}

function worldRectToScreenRect(x, y, w, h, floor = activeFloor, lift = 0) {
  const point = project(x, y, lift, floor);
  return {
    x: Math.round(point.x),
    y: Math.round(point.y),
    w: Math.round(w),
    h: Math.round(h),
  };
}

function drawPixelDot(x, y, color, alpha = 1) {
  ctx.save();
  ctx.globalAlpha *= alpha;
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), 2, 2);
  ctx.restore();
}

function drawRoomTiles(roomRect, colorA, colorB, worldOriginX = 0, worldOriginY = 0) {
  for (let tileX = 0; tileX < roomRect.w; tileX += TILE) {
    for (let tileY = 0; tileY < roomRect.h; tileY += TILE) {
      const worldTileX = worldOriginX + tileX;
      const worldTileY = worldOriginY + tileY;
      const noiseSeed = Math.sin(worldTileX * 0.021 + worldTileY * 0.017);
      const mix = 0.35 + (noiseSeed + 1) * 0.25;
      ctx.fillStyle = mix > 0.55 ? colorA : colorB;
      ctx.fillRect(roomRect.x + tileX, roomRect.y + tileY, TILE, TILE);
      if ((tileX + tileY) % (TILE * 3) === 0) {
        ctx.fillStyle = "rgba(255,255,255,0.08)";
        ctx.fillRect(roomRect.x + tileX + 6, roomRect.y + tileY + 6, 4, 4);
      }
      if ((tileX * 3 + tileY) % (TILE * 5) === 0) {
        ctx.fillStyle = "rgba(122,92,50,0.06)";
        ctx.fillRect(roomRect.x + tileX + 18, roomRect.y + tileY + 18, 5, 5);
      }
    }
  }
}

function drawRoomBorder(roomRect, floorColor) {
  ctx.fillStyle = floorColor;
  ctx.fillRect(roomRect.x, roomRect.y, roomRect.w, roomRect.h);
  ctx.strokeStyle = palette.roomTrim;
  ctx.lineWidth = 2;
  ctx.strokeRect(roomRect.x + 1, roomRect.y + 1, roomRect.w - 2, roomRect.h - 2);
}

function drawGroundBackdrop() {
  ctx.fillStyle = palette.grassA;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (let x = 0; x < canvas.width + TILE; x += TILE) {
    for (let y = 0; y < canvas.height + TILE; y += TILE) {
      const tileX = Math.floor(x / TILE);
      const tileY = Math.floor(y / TILE);
      const hash = Math.sin(tileX * 12.9898 + tileY * 78.233) * 43758.5453;
      const noise = hash - Math.floor(hash);
      ctx.fillStyle = noise > 0.76 ? palette.grassC : noise > 0.36 ? palette.grassA : palette.grassB;
      ctx.fillRect(x, y, TILE, TILE);
      drawPixelDot(x + 5, y + 7, "rgba(255,255,255,0.09)");
      drawPixelDot(x + 18, y + 16, "rgba(71,115,44,0.3)");
      drawPixelDot(x + 11, y + 23, "rgba(108,162,70,0.22)");
      if ((tileX * 3 + tileY * 5) % 7 === 0) {
        ctx.fillStyle = "rgba(102, 154, 66, 0.22)";
        ctx.fillRect(x + 9, y + 20, 10, 3);
        ctx.fillRect(x + 19, y + 9, 3, 10);
      }
      if ((tileX + tileY * 2) % 11 === 0) {
        ctx.fillStyle = "rgba(72, 126, 49, 0.2)";
        ctx.fillRect(x + 4, y + 14, 4, 8);
        ctx.fillRect(x + 24, y + 11, 3, 7);
      }
    }
  }
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
  const roomRect = worldRectToScreenRect(rect.x, rect.y, rect.w, rect.h, room.floor);
  const fillA = room.kind === "hall" ? palette.hallFloor : palette.roomFloor;
  const fillB = room.kind === "hall" ? "#e2cca0" : "#d5c191";
  drawRoomBorder(roomRect, fillA);
  drawRoomTiles(roomRect, fillA, fillB, rect.x, rect.y);

  if (dimmed) {
    ctx.fillStyle = "rgba(0, 0, 0, 0.08)";
    ctx.fillRect(roomRect.x, roomRect.y, roomRect.w, roomRect.h);
  }
}

function drawWall(segment) {
  const rect = worldRectToScreenRect(segment.x, segment.y, segment.w, segment.h, segment.floor);
  drawRect(rect, palette.wallTop, palette.wallEdge, 2);
  ctx.fillStyle = segment.h <= WALL_THICKNESS ? palette.wallFront : palette.wallSide;
  if (segment.h <= WALL_THICKNESS) {
    ctx.fillRect(rect.x, rect.y + Math.max(2, rect.h - 6), rect.w, 4);
  } else {
    ctx.fillRect(rect.x + Math.max(2, rect.w - 6), rect.y, 4, rect.h);
  }
}

function drawDoor(door, activeDoor) {
  const opening = worldRectToScreenRect(door.opening.x, door.opening.y, door.opening.w, door.opening.h, door.floor);
  drawRect(opening, palette.doorFrame, palette.wallEdge, 1);

  const inset = 2;
  const panelRect = {
    x: opening.x + inset,
    y: opening.y + inset,
    w: Math.max(4, opening.w - inset * 2),
    h: Math.max(4, opening.h - inset * 2),
  };
  if (!door.open) {
    drawRect(panelRect, palette.doorGlass, "rgba(255,255,255,0.25)", 1);
  } else if (opening.w >= opening.h) {
    drawRect({ x: panelRect.x, y: panelRect.y, w: Math.max(4, Math.round(panelRect.w * 0.34)), h: panelRect.h }, palette.doorGlass, null, 0);
    drawRect({ x: panelRect.x + Math.round(panelRect.w * 0.66), y: panelRect.y, w: Math.max(4, Math.round(panelRect.w * 0.34)), h: panelRect.h }, palette.doorGlass, null, 0);
  } else {
    drawRect({ x: panelRect.x, y: panelRect.y, w: panelRect.w, h: Math.max(4, Math.round(panelRect.h * 0.34)) }, palette.doorGlass, null, 0);
    drawRect({ x: panelRect.x, y: panelRect.y + Math.round(panelRect.h * 0.66), w: panelRect.w, h: Math.max(4, Math.round(panelRect.h * 0.34)) }, palette.doorGlass, null, 0);
  }

  const sensor = project(door.pivot.x, door.pivot.y, 0, door.floor);
  ctx.fillStyle = palette.doorSensor;
  ctx.beginPath();
  ctx.arc(sensor.x, sensor.y, activeDoor?.id === door.id ? 5 : 3, 0, Math.PI * 2);
  ctx.fill();
}

function drawProp(prop) {
  const x = prop.x * TILE;
  const y = prop.y * TILE;
  const w = prop.w * TILE;
  const h = prop.h * TILE;
  const rect = worldRectToScreenRect(x, y, w, h, prop.floor);
  const colors = {
    bed: { main: "#8ebed3", edge: "#5a8094", detail: "#e8f2f5" },
    desk: { main: "#9c7248", edge: "#6d4b2a", detail: "#c79b63" },
    sofa: { main: "#8fae69", edge: "#587540", detail: "#bfd598" },
    plant: { main: "#6fa154", edge: "#456b36", detail: "#99d381" },
    screen: { main: "#9fd2d8", edge: "#5c868f", detail: "#dff4f6" },
    cabinet: { main: "#b9a17e", edge: "#7e654b", detail: "#dfcfb0" },
    reception: { main: "#c58d57", edge: "#875a34", detail: "#e5be88" },
  };
  const color = colors[prop.type];
  drawRect(rect, color.main, color.edge, 2);
  ctx.fillStyle = color.detail;
  ctx.fillRect(rect.x + 4, rect.y + 4, Math.max(6, rect.w - 8), Math.max(6, rect.h - 8));

  if (prop.type === "bed") {
    ctx.fillStyle = "#f6f1e8";
    ctx.fillRect(rect.x + 4, rect.y + 4, Math.max(8, rect.w * 0.45), rect.h - 8);
  } else if (prop.type === "plant") {
    ctx.fillStyle = "#7b4e2d";
    ctx.fillRect(rect.x + rect.w / 2 - 5, rect.y + rect.h / 2 - 5, 10, 10);
    ctx.fillStyle = "#87c465";
    ctx.beginPath();
    ctx.arc(rect.x + rect.w / 2, rect.y + rect.h / 2 - 3, 10, 0, Math.PI * 2);
    ctx.fill();
  } else if (prop.type === "screen") {
    ctx.fillStyle = "#dff8ff";
    ctx.fillRect(rect.x + 5, rect.y + 5, rect.w - 10, rect.h - 10);
  }
}

function drawCharacterBody(x, y, floor, colors = {}, facing = "down") {
  const screen = project(x, y, 0, floor);
  const px = Math.round(screen.x);
  const py = Math.round(screen.y);
  const shadowColor = colors.shadowColor || palette.shadow;
  const legColor = colors.legColor || palette.playerLeg;
  const bodyColor = colors.bodyColor || palette.playerBody;
  const accentColor = colors.accentColor || palette.playerAccent;
  const skinColor = colors.skinColor || palette.playerHead;
  const hairColor = colors.hairColor || palette.playerHair;

  ctx.fillStyle = shadowColor;
  ctx.beginPath();
  ctx.ellipse(px, py + 12, 12, 6, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = legColor;
  ctx.fillRect(px - 8, py + 6, 5, 12);
  ctx.fillRect(px + 3, py + 6, 5, 12);
  ctx.fillRect(px - 10, py + 15, 7, 3);
  ctx.fillRect(px + 3, py + 15, 7, 3);

  ctx.fillStyle = bodyColor;
  ctx.fillRect(px - 11, py - 13, 22, 20);
  ctx.fillStyle = accentColor;
  ctx.fillRect(px - 9, py - 11, 18, 7);
  ctx.fillRect(px - 3, py - 4, 6, 11);

  if (facing === "left") {
    ctx.fillStyle = accentColor;
    ctx.fillRect(px - 15, py - 10, 4, 10);
  } else if (facing === "right") {
    ctx.fillStyle = accentColor;
    ctx.fillRect(px + 11, py - 10, 4, 10);
  }

  ctx.fillStyle = skinColor;
  ctx.fillRect(px - 8, py - 25, 16, 15);
  ctx.fillStyle = hairColor;
  ctx.fillRect(px - 8, py - 25, 16, 5);
  if (facing !== "up") {
    const eyeY = py - 20;
    ctx.fillStyle = "rgba(255,255,255,0.96)";
    if (facing === "left") {
      ctx.fillRect(px - 7, eyeY, 4, 4);
    } else if (facing === "right") {
      ctx.fillRect(px + 3, eyeY, 4, 4);
    } else {
      ctx.fillRect(px - 7, eyeY, 4, 4);
      ctx.fillRect(px + 3, eyeY, 4, 4);
    }

    ctx.fillStyle = "#2f2117";
    if (facing === "left") {
      ctx.fillRect(px - 6, eyeY + 1, 2, 2);
    } else if (facing === "right") {
      ctx.fillRect(px + 4, eyeY + 1, 2, 2);
    } else {
      ctx.fillRect(px - 6, eyeY + 1, 2, 2);
      ctx.fillRect(px + 4, eyeY + 1, 2, 2);
      ctx.fillStyle = "#8f5b3e";
      ctx.fillRect(px - 2, py - 14, 4, 2);
    }
  }
  if (facing === "left") {
    ctx.fillStyle = hairColor;
    ctx.fillRect(px - 10, py - 23, 3, 8);
  } else if (facing === "right") {
    ctx.fillStyle = hairColor;
    ctx.fillRect(px + 7, py - 23, 3, 8);
  }

  return { x: px, y: py - 18 };
}

function drawDefaultHead(top, fillColor = palette.playerHead) {
  ctx.fillStyle = fillColor;
  ctx.fillRect(top.x - 9, top.y - 8, 18, 18);
}

function drawTexturedHead(top, facing = "down") {
  const size = 20;
  const dx = top.x - size / 2;
  const dy = top.y - 8;
  ctx.save();
  ctx.beginPath();
  ctx.rect(top.x - 10, top.y - 8, 20, 20);
  ctx.clip();
  if (npcHeadReady) ctx.drawImage(npcHeadImage, dx, dy, size, size);
  else drawDefaultHead(top);
  ctx.restore();

  if (facing !== "up") {
    const eyeY = top.y - 1;
    ctx.save();
    ctx.fillStyle = "rgba(255,255,255,0.98)";
    if (facing === "left") {
      ctx.fillRect(top.x - 7, eyeY, 4, 4);
      ctx.fillStyle = "#2f2117";
      ctx.fillRect(top.x - 6, eyeY + 1, 2, 2);
    } else if (facing === "right") {
      ctx.fillRect(top.x + 3, eyeY, 4, 4);
      ctx.fillStyle = "#2f2117";
      ctx.fillRect(top.x + 4, eyeY + 1, 2, 2);
    } else {
      ctx.fillRect(top.x - 7, eyeY, 4, 4);
      ctx.fillRect(top.x + 3, eyeY, 4, 4);
      ctx.fillStyle = "#2f2117";
      ctx.fillRect(top.x - 6, eyeY + 1, 2, 2);
      ctx.fillRect(top.x + 4, eyeY + 1, 2, 2);
      ctx.fillStyle = "#8f5b3e";
      ctx.fillRect(top.x - 2, top.y + 6, 4, 2);
    }
    ctx.restore();
  }
}

function drawPlayer() {
  const top = drawCharacterBody(player.x, player.y, player.floor, {
    hairColor: palette.playerHair,
    skinColor: palette.playerHead,
  }, player.facing);
  drawTexturedHead(top, player.facing);
}

function drawFixedNpcLabel(npc, top) {
  const name = npc.name || "Resident";
  const role = npc.roleLabel || "";
  const lines = role ? [name, role] : [name];
  ctx.save();
  ctx.textAlign = "center";
  ctx.fillStyle = "rgba(10, 10, 16, 0.84)";
  ctx.strokeStyle = npc.accentColor || "#9ec8ff";
  ctx.lineWidth = 1;
  ctx.font = "600 11px 'Segoe UI'";
  const nameWidth = ctx.measureText(lines[0]).width;
  const roleWidth = role ? ctx.measureText(lines[1]).width : 0;
  const boxWidth = Math.max(nameWidth, roleWidth) + 18;
  const boxHeight = role ? 30 : 20;
  const boxX = top.x - boxWidth / 2;
  const boxY = top.y - 46;
  ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
  ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);
  ctx.fillStyle = "#f6eff8";
  ctx.fillText(lines[0], top.x, boxY + 13);
  if (role) {
    ctx.font = "10px 'Segoe UI'";
    ctx.fillStyle = npc.accentColor || "#9ec8ff";
    ctx.fillText(lines[1], top.x, boxY + 25);
  }
  ctx.restore();
}

function drawFixedNpc(npc) {
  ctx.save();
  const top = drawCharacterBody(npc.x, npc.y, npc.floor, {
    legColor: "#564942",
    bodyColor: npc.accentColor,
    accentColor: npc.bodyColor,
    shadowColor: "rgba(0, 0, 0, 0.24)",
    skinColor: npc.headColor,
    hairColor: "rgba(60, 40, 26, 0.8)",
  });
  if (overlayState.labelsOpen) drawFixedNpcLabel(npc, top);
  ctx.restore();
}

function characterDepth(x, y) {
  return x + y + CHARACTER_FOOT_RADIUS;
}

function drawLabels() {
  if (!overlayState.labelsOpen) return;

  const labels = {
    registration: "Registration",
    consultation: "Consultation",
    triage: "Triage",
    pharmacy: "Doctor Entry",
    ward: "Ward",
    lab: "Lab",
    icu: "ICU",
    office: "Office",
    hall: "Hall",
  };

  ctx.fillStyle = palette.label;
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  for (const room of rooms.filter((item) => item.floor === activeFloor)) {
    const rect = roomBounds(room);
    const point = project(rect.x + rect.w * 0.5, rect.y + rect.h * 0.5, 0, room.floor);
    ctx.fillStyle = "rgba(255, 247, 224, 0.86)";
    ctx.fillRect(point.x - 52, point.y - 14, 104, 24);
    ctx.strokeStyle = "rgba(145, 106, 64, 0.75)";
    ctx.strokeRect(point.x - 52, point.y - 14, 104, 24);
    ctx.fillStyle = palette.label;
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
  ctx.strokeStyle = "rgba(145, 106, 64, 0.7)";
  ctx.strokeRect(left, top, size, size);

  for (const room of rooms.filter((item) => item.floor === activeFloor)) {
    const rect = roomBounds(room);
    ctx.fillStyle = room.kind === "hall" ? "#e7d1a1" : "#d4bc8d";
    ctx.fillRect(left + rect.x * scale, top + rect.y * scale, rect.w * scale, rect.h * scale);
  }

  for (const door of currentFloorDoors()) {
    ctx.fillStyle = door.open ? "#91d884" : "#8d5c37";
    ctx.fillRect(left + door.opening.x * scale, top + door.opening.y * scale, Math.max(2, door.opening.w * scale), Math.max(2, door.opening.h * scale));
  }

  ctx.fillStyle = "#4b79d8";
  ctx.beginPath();
  ctx.arc(left + player.x * scale, top + player.y * scale, 4, 0, Math.PI * 2);
  ctx.fill();
}

function drawHudHint(door) {
  if (!door) return;
  const point = project(door.pivot.x, door.pivot.y, 0, door.floor);
  const label = door.open ? `${door.label} Auto Open` : `${door.label} Standby`;
  ctx.fillStyle = "rgba(67, 45, 28, 0.9)";
  ctx.fillRect(point.x - 54, point.y - 12, 108, 22);
  ctx.strokeStyle = "rgba(251, 230, 179, 0.88)";
  ctx.strokeRect(point.x - 54, point.y - 12, 108, 22);
  ctx.fillStyle = "#fff4d9";
  ctx.font = "600 12px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 4);
}

function drawTriageHint() {
  if (!canInteractWithTriageDesk()) return;
  const point = project(triageInteractPoint.x, triageInteractPoint.y, 0, triageInteractPoint.floor);
  const label = backendState.submitting
    ? "Submitting triage..."
    : triageUi.open
      ? "Complete the triage form..."
      : hasStartedTriageConversation()
        ? "Press E to continue triage chat"
        : "Press E to start triage";
  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 176;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = backendState.submitting
    ? `rgba(255, 198, 124, ${Math.min(0.95, pulse + 0.2)})`
    : `rgba(112, 234, 255, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);

  ctx.fillStyle = backendState.submitting ? "#ffe4bd" : "#fff5dd";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 5);
}

function drawRegistrationHint() {
  if (!canInteractWithRegistrationDesk()) return;
  const point = project(registrationInteractPoint.x, registrationInteractPoint.y, 0, registrationInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visitState = selfPatient?.visit_state || "";

  let label = "Press E to register";
  if (backendState.submitting) {
    label = "Submitting registration...";
  } else if (visitState === "registered" || visitState === "waiting_consultation" || visitState === "in_consultation") {
    label = "Registration already completed";
  } else if (visitState !== "triaged") {
    label = "Finish triage before registration";
  }

  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 220;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = backendState.submitting
    ? `rgba(255, 198, 124, ${Math.min(0.95, pulse + 0.2)})`
    : `rgba(112, 234, 255, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);

  ctx.fillStyle = backendState.submitting ? "#ffe4bd" : "#fff5dd";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 5);
}

function drawDoctorEntryHint() {
  if (!canInteractWithDoctorEntry()) return;
  const point = project(doctorEntryInteractPoint.x, doctorEntryInteractPoint.y, 0, doctorEntryInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visit = getCurrentVisit();
  const visitState = visit?.state || selfPatient?.visit_state || "";
  const lifecycle = selfPatient?.lifecycle_state || "";

  let label = "Follow workflow: triage -> register -> wait";
  if (backendState.submitting) {
    label = "Synchronizing doctor entry...";
  } else if (visitState === "in_consultation" || lifecycle === "in_consultation") {
    label = hasStartedDoctorConversation(selfPatient, visit)
      ? "Press E to continue doctor consultation"
      : "Press E to start doctor consultation";
  } else if (visitState === "waiting_consultation" && lifecycle === "called") {
    label = "Press E to enter consultation";
  } else if (visitState === "registered" || lifecycle === "queued") {
    label = "Waiting for queue call (10s)";
  } else if (visitState === "triaged") {
    label = "Complete registration first";
  } else if (visitState === "waiting_test") {
    label = "Consultation finished. Entering diagnostic stage";
  } else if (visitState === "waiting_payment") {
    label = "Consultation finished. Proceed to payment";
  }

  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 272;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = backendState.submitting
    ? `rgba(255, 198, 124, ${Math.min(0.95, pulse + 0.2)})`
    : `rgba(112, 234, 255, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);

  ctx.fillStyle = backendState.submitting ? "#ffe4bd" : "#fff5dd";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 5);
}

function drawFixedNpcHint() {
  if (!fixedNpcRuntime || npcDialogueUi.open || fixedNpcRuntime?.isDialogueOpen?.()) return;
  const nearest = fixedNpcRuntime.getNearestInteractableNpc(player);
  if (!nearest) return;

  const point = project(nearest.x, nearest.y, 0, nearest.floor);
  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = Math.max(220, Math.min(320, 160 + nearest.name.length * 8));
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.save();
  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = nearest.accentColor || "#9ec8ff";
  ctx.lineWidth = 2;
  ctx.globalAlpha = Math.min(1, pulse + 0.28);
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.fillStyle = "#fff5dd";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(`Press E to talk with ${nearest.name}`, point.x, point.y + 5);
  ctx.restore();
}

function getRoomCenterPoint(roomKind) {
  const room = rooms.find((item) => item.kind === roomKind);
  if (!room) return null;
  const rect = roomBounds(room);
  return {
    floor: room.floor,
    roomKind,
    x: rect.x + rect.w * 0.5,
    y: rect.y + rect.h * 0.5,
    w: rect.w,
    h: rect.h,
  };
}

function getObjectiveTarget() {
  const patient = getCurrentSelfPatient();
  const visit = getCurrentVisit();
  const visitState = visit?.state || patient?.visit_state || "";
  const lifecycle = patient?.lifecycle_state || "";
  const hasTriageRecord = Boolean(
    patient?.triage?.level
    || patient?.triage?.note
    || (Array.isArray(patient?.triage_evidence) && patient.triage_evidence.length > 0)
    || (Array.isArray(patient?.triageEvidence) && patient.triageEvidence.length > 0)
  );

  if (!hasTriageRecord && !triageConversationState.sessionId) {
    return { label: "Go to Triage", point: triageInteractPoint, room: getRoomCenterPoint("triage") };
  }

  if (!patient || !visitState || visitState === "arrived" || visitState === "triaging" || visitState === "waiting_followup") {
    return { label: "Go to Triage", point: triageInteractPoint, room: getRoomCenterPoint("triage") };
  }
  if (visitState === "triaged") {
    return { label: "Go to Registration", point: registrationInteractPoint, room: getRoomCenterPoint("registration") };
  }
  if (visitState === "registered" || lifecycle === "queued") {
    const room = getRoomCenterPoint("hall");
    return { label: "Wait in Hall", point: room, room };
  }
  if (visitState === "waiting_consultation" || lifecycle === "called" || visitState === "in_consultation" || lifecycle === "in_consultation") {
    return { label: "Go to Doctor", point: doctorEntryInteractPoint, room: getRoomCenterPoint("pharmacy") };
  }
  if (visitState === "waiting_test") {
    const room = getRoomCenterPoint("lab");
    return { label: "Go to Lab", point: room, room };
  }
  if (visitState === "waiting_payment") {
    return { label: "Return to Registration", point: registrationInteractPoint, room: getRoomCenterPoint("registration") };
  }
  return { label: "Explore the Campus", point: getRoomCenterPoint("hall"), room: getRoomCenterPoint("hall") };
}

function drawObjectiveDirectionArrow(targetPoint, pulse, worldDistance) {
  const playerScreen = project(player.x, player.y, 0, player.floor);
  const dx = targetPoint.x - playerScreen.x;
  const dy = targetPoint.y - playerScreen.y;
  const screenDistance = Math.hypot(dx, dy);
  const edgePadding = 54;
  const offscreen = targetPoint.x < edgePadding
    || targetPoint.x > canvas.width - edgePadding
    || targetPoint.y < edgePadding
    || targetPoint.y > canvas.height - edgePadding;

  if (!offscreen && worldDistance < 420 && screenDistance < 280) return;

  const angle = Math.atan2(dy, dx);
  const centerX = canvas.width * 0.5;
  const centerY = canvas.height * 0.5;
  const ringRadius = Math.min(canvas.width, canvas.height) * 0.43;
  const edgeX = Math.max(edgePadding, Math.min(canvas.width - edgePadding, centerX + Math.cos(angle) * ringRadius));
  const edgeY = Math.max(edgePadding, Math.min(canvas.height - edgePadding, centerY + Math.sin(angle) * ringRadius));

  ctx.save();
  ctx.translate(edgeX, edgeY);
  ctx.rotate(angle);
  ctx.strokeStyle = `rgba(255, 247, 201, ${Math.min(1, 0.85 + pulse * 0.2)})`;
  ctx.fillStyle = `rgba(255, 173, 82, ${Math.min(1, 0.86 + pulse * 0.15)})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(21, 0);
  ctx.lineTo(-12, -11);
  ctx.lineTo(-12, -5);
  ctx.lineTo(-24, -5);
  ctx.lineTo(-24, 5);
  ctx.lineTo(-12, 5);
  ctx.lineTo(-12, 11);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();

  const nearPlayerX = playerScreen.x + Math.cos(angle) * 34;
  const nearPlayerY = playerScreen.y + Math.sin(angle) * 34;
  ctx.save();
  ctx.translate(nearPlayerX, nearPlayerY);
  ctx.rotate(angle);
  ctx.fillStyle = `rgba(255, 198, 105, ${Math.min(1, 0.78 + pulse * 0.2)})`;
  ctx.strokeStyle = `rgba(255, 245, 202, ${Math.min(1, 0.85 + pulse * 0.18)})`;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(12, 0);
  ctx.lineTo(-4, -8);
  ctx.lineTo(-4, 8);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawObjectiveHighlight() {
  const target = getObjectiveTarget();
  if (!target?.point) return;
  const pulse = 0.55 + Math.sin(performance.now() * 0.008) * 0.3;
  const worldDistance = Math.hypot(player.x - target.point.x, player.y - target.point.y);

  if (target.room) {
    const roomLeft = target.room.x - target.room.w / 2;
    const roomTop = target.room.y - target.room.h / 2;
    const rect = worldRectToScreenRect(roomLeft, roomTop, target.room.w, target.room.h, target.room.floor);
    ctx.save();
    ctx.strokeStyle = `rgba(255, 187, 73, ${Math.min(1, 0.45 + pulse * 0.28)})`;
    ctx.lineWidth = 12;
    ctx.strokeRect(rect.x - 8, rect.y - 8, rect.w + 16, rect.h + 16);
    ctx.strokeStyle = `rgba(255, 245, 170, ${Math.min(1, 0.82 + pulse * 0.15)})`;
    ctx.lineWidth = 6;
    ctx.strokeRect(rect.x - 4, rect.y - 4, rect.w + 8, rect.h + 8);
    ctx.restore();
  }

  const point = project(target.point.x, target.point.y, 0, target.point.floor);
  ctx.save();
  ctx.strokeStyle = `rgba(255, 244, 189, ${Math.min(1, 0.9 + pulse * 0.1)})`;
  ctx.fillStyle = `rgba(255, 190, 88, ${0.26 + pulse * 0.18})`;
  ctx.lineWidth = 5;
  ctx.beginPath();
  ctx.arc(point.x, point.y, 26 + pulse * 9, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.strokeStyle = `rgba(255, 159, 64, ${Math.min(1, 0.7 + pulse * 0.2)})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(point.x, point.y, 37 + pulse * 8, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "rgba(77, 50, 28, 0.92)";
  ctx.fillRect(point.x - 78, point.y - 52, 156, 26);
  ctx.strokeStyle = "rgba(255, 228, 183, 0.9)";
  ctx.lineWidth = 2;
  ctx.strokeRect(point.x - 78, point.y - 52, 156, 26);
  ctx.fillStyle = "#fff7e5";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(target.label, point.x, point.y - 34);
  ctx.restore();

  drawObjectiveDirectionArrow(point, pulse, worldDistance);
}

function drawTaskBoard() {
  if (!overlayState.tasksOpen) return;

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

function drawRuntimeDebugPanel() {
  if (!overlayState.debugOpen) return;

  const panelWidth = 360;
  const panelHeight = 122;
  const panelX = 18;
  const panelY = 18;
  const now = performance.now();
  const loopDelta = runtimeDebug.lastLoopAt ? Math.max(0, now - runtimeDebug.lastLoopAt).toFixed(0) : "-";
  const renderDelta = runtimeDebug.lastRenderAt ? Math.max(0, now - runtimeDebug.lastRenderAt).toFixed(0) : "-";

  ctx.fillStyle = "rgba(16, 11, 24, 0.86)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(255, 179, 122, 0.72)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.textAlign = "left";
  ctx.font = "13px 'Segoe UI'";
  ctx.fillStyle = "#ffd9a6";
  ctx.fillText("Runtime Debug", panelX + 12, panelY + 22);

  ctx.font = "12px 'Segoe UI'";
  ctx.fillStyle = "#f2ebff";
  ctx.fillText(`Frames: ${runtimeDebug.frames}`, panelX + 12, panelY + 46);
  ctx.fillText(`Loop delta: ${loopDelta} ms`, panelX + 12, panelY + 66);
  ctx.fillText(`Render delta: ${renderDelta} ms`, panelX + 12, panelY + 86);
  ctx.fillText(`Polls: ok ${runtimeDebug.pollSuccessCount} / fail ${runtimeDebug.pollFailureCount}`, panelX + 180, panelY + 46);
  ctx.fillText(`Last poll: ${runtimeDebug.lastPollResult}`, panelX + 180, panelY + 66);
  ctx.fillStyle = runtimeDebug.lastError ? "#ffb0b0" : "#9fd9b7";
  ctx.fillText(`Last error: ${runtimeDebug.lastError || "none"}`, panelX + 12, panelY + 108);
}

function drawZoneStatusPanel() {
  if (!overlayState.debugOpen) return;

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
  ctx.fillText(`Triage: ${canInteractWithTriageDesk() ? "Available" : "Move closer"}`, panelX + 12, panelY + 112);

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
  for (const prop of props.filter((item) => item.floor === floor)) {
    drawables.push({ depth: prop.x * TILE + prop.y * TILE + prop.w * TILE + prop.h * TILE + 8, draw: () => drawProp(prop) });
  }
  if (player.floor === floor) drawables.push({ depth: characterDepth(player.x, player.y), draw: drawPlayer });
  if (fixedNpcRuntime) {
    for (const npc of fixedNpcRuntime.getNpcs()) {
      if (npc.floor !== floor) continue;
      drawables.push({ depth: characterDepth(npc.x, npc.y), draw: () => drawFixedNpc(npc) });
    }
  }

  drawables.sort((a, b) => a.depth - b.depth);
  drawables.forEach((entry) => entry.draw());
  ctx.restore();

  if (dimmed) {
    ctx.fillStyle = palette.inactiveMask;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
}

function updateFloorHud() {
  if (floorStateLabel) floorStateLabel.textContent = "Current Zone: Main Campus";
}

function syncHudToggleButton(button, active, ariaName = "pressed") {
  if (!button) return;
  button.classList.toggle("is-active", active);
  button.setAttribute(`aria-${ariaName}`, String(active));
}

function syncOverlayUi() {
  if (hudHelpPanel) hudHelpPanel.classList.toggle("hidden", !overlayState.helpOpen);
  syncHudToggleButton(hudHelpToggle, overlayState.helpOpen, "expanded");
  syncHudToggleButton(hudTasksToggle, overlayState.tasksOpen);
  syncHudToggleButton(hudLabelsToggle, overlayState.labelsOpen);
  syncHudToggleButton(hudDebugToggle, overlayState.debugOpen);
}

function closeOverlayPanels() {
  const hadOpenPanel = overlayState.helpOpen || overlayState.tasksOpen || overlayState.labelsOpen || overlayState.debugOpen;
  overlayState.helpOpen = false;
  overlayState.tasksOpen = false;
  overlayState.labelsOpen = false;
  overlayState.debugOpen = false;
  syncOverlayUi();
  return hadOpenPanel;
}

function bindHudControls() {
  hudHelpToggle?.addEventListener("click", () => {
    overlayState.helpOpen = !overlayState.helpOpen;
    syncOverlayUi();
  });

  hudTasksToggle?.addEventListener("click", () => {
    overlayState.tasksOpen = !overlayState.tasksOpen;
    syncOverlayUi();
  });

  hudLabelsToggle?.addEventListener("click", () => {
    overlayState.labelsOpen = !overlayState.labelsOpen;
    syncOverlayUi();
  });

  hudDebugToggle?.addEventListener("click", () => {
    overlayState.debugOpen = !overlayState.debugOpen;
    syncOverlayUi();
  });

  syncOverlayUi();
}

function update(delta, nowMs) {
  pollBackendStatuses(false);
  updateDoors();
  fixedNpcRuntime?.update?.(delta);

  if (npcDialogueUi.open || fixedNpcRuntime?.isDialogueOpen?.()) {
    updateZoneTriggers(nowMs);
    return;
  }

  let moveX = 0;
  let moveY = 0;
  if (keys.has("ArrowUp") || keys.has("KeyW")) moveY -= 1;
  if (keys.has("ArrowDown") || keys.has("KeyS")) moveY += 1;
  if (keys.has("ArrowLeft") || keys.has("KeyA")) moveX -= 1;
  if (keys.has("ArrowRight") || keys.has("KeyD")) moveX += 1;

  if (moveX < 0) player.facing = "left";
  else if (moveX > 0) player.facing = "right";
  else if (moveY < 0) player.facing = "up";
  else if (moveY > 0) player.facing = "down";

  if (moveX !== 0 || moveY !== 0) {
    const length = Math.hypot(moveX, moveY);
    const velocityX = (moveX / length) * player.speed * delta;
    const velocityY = (moveY / length) * player.speed * delta;
    if (canMoveTo(player.x + velocityX, player.y)) player.x += velocityX;
    if (canMoveTo(player.x, player.y + velocityY)) player.y += velocityY;
  }

  camera.x += (player.x - camera.x) * 0.12;
  camera.y += (player.y - camera.y) * 0.12;
  updateZoneTriggers(nowMs);
}

function render() {
  const activeDoor = nearestDoor();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawGroundBackdrop();
  drawFloorLayer(activeFloor, activeDoor, false);
  drawLabels();
  drawObjectiveHighlight();
  drawHudHint(activeDoor);
  drawRegistrationHint();
  drawTriageHint();
  drawDoctorEntryHint();
  drawFixedNpcHint();
  drawTaskBoard();
  drawMinimap();
  drawRuntimeDebugPanel();
  drawZoneStatusPanel();
  syncNpcDialogue();
  runtimeDebug.lastRenderAt = performance.now();
}
triageDialogueUi.form = document.getElementById("triageDialogueForm");
triageDialogueUi.input = document.getElementById("triageDialogueInput");
triageDialogueUi.sendBtn = document.getElementById("triageDialogueSendBtn");

const doctorDialogueUi = {
  open: false,
  modal: document.getElementById("doctorDialogueModal"),
  status: document.getElementById("doctorDialogueStatus"),
  messages: document.getElementById("doctorDialogueMessages"),
  evidenceList: document.getElementById("doctorEvidenceList"),
  closeBtn: document.getElementById("doctorDialogueCloseBtn"),
  form: document.getElementById("doctorDialogueForm"),
  input: document.getElementById("doctorDialogueInput"),
  sendBtn: document.getElementById("doctorDialogueSendBtn"),
  agentBadge: document.getElementById("doctorAgentBadge"),
  visitBadge: document.getElementById("doctorVisitBadge"),
  lastRenderedAt: "",
};

const passiveNpcDefinitions = [
  { id: "guest-a", name: "Ari", roleLabel: "Visitor", roomKind: "empty_room", roomIndex: 0, placement: { x: 0.32, y: 0.42 }, bodyColor: "#b889f0", accentColor: "#d9c2ff", headColor: "#f4d8ca" },
  { id: "guest-b", name: "Milo", roleLabel: "Patient", roomKind: "empty_room", roomIndex: 1, placement: { x: 0.64, y: 0.48 }, bodyColor: "#76c59d", accentColor: "#bdeccf", headColor: "#f2cfbb" },
  { id: "guest-c", name: "Tess", roleLabel: "Waiting", roomKind: "empty_room", roomIndex: 2, placement: { x: 0.42, y: 0.62 }, bodyColor: "#d7aa60", accentColor: "#f4d28d", headColor: "#f4d5bf" },
];

const npcDialogueUi = {
  open: false,
  modal: document.getElementById("npcDialogueModal"),
  title: document.getElementById("npcDialogueTitle"),
  status: document.getElementById("npcDialogueStatus"),
  roleBadge: document.getElementById("npcDialogueRoleBadge"),
  roomBadge: document.getElementById("npcDialogueRoomBadge"),
  prompt: document.getElementById("npcDialoguePrompt"),
  options: document.getElementById("npcDialogueOptions"),
  hint: document.getElementById("npcDialogueHint"),
  closeBtn: document.getElementById("npcDialogueCloseBtn"),
  advanceBtn: document.getElementById("npcDialogueAdvanceBtn"),
  lastRenderedAt: "",
};

const visitSessionState = {
  visit: null,
};

function getClientId() {
  const params = new URLSearchParams(window.location.search);
  const shouldResume = params.get("resume") === "1";

  if (shouldResume) {
    let clientId = localStorage.getItem("client_id");
    if (!clientId) {
      clientId = crypto.randomUUID();
      localStorage.setItem("client_id", clientId);
    }
    return clientId;
  }

  localStorage.removeItem("client_id");
  return crypto.randomUUID();
}

const clientId = getClientId();
const patientId = `P-${clientId}`;

const triageConversationState = {
  patientId: patientId,
  visitId: null,
  sessionId: null,
  sending: false,
};

const doctorConversationState = {
  patientId: patientId,
  visitId: null,
  sessionId: null,
  sending: false,
  activeAgentType: "internal_medicine",
};

function getCurrentSelfPatient() {
  const patient = agentStore.lastPatient;
  return patient && patient.id === triageConversationState.patientId ? patient : null;
}

function getCurrentVisit() {
  return visitSessionState.visit || null;
}

function isTriageStage(visitState) {
  return ["arrived", "triaging", "waiting_followup", "triaged", null, undefined, ""].includes(visitState);
}

function hasStartedTriageConversation(patient = getCurrentSelfPatient()) {
  if (!patient) return false;
  if (Array.isArray(patient?.dialogue?.turns) && patient.dialogue.turns.length > 0) return true;
  if (patient?.dialogue?.status && patient.dialogue.status !== "idle") return true;
  return patient?.state && patient.state !== "Untriaged";
}

function getDoctorSessionIdFromContext(patient = getCurrentSelfPatient(), visit = getCurrentVisit()) {
  const patientSessionId = String(patient?.session_id || "");
  const visitSessionId = visit?.data?.internal_medicine_session_id || null;
  if (visitSessionId) return visitSessionId;

  if (visit?.active_agent_type === "internal_medicine" && doctorConversationState.sessionId) {
    return doctorConversationState.sessionId;
  }

  if (doctorConversationState.sessionId) return doctorConversationState.sessionId;
  return patientSessionId.startsWith("im-session-") ? patientSessionId : null;
}

function hasStartedDoctorConversation(patient = getCurrentSelfPatient(), visit = getCurrentVisit()) {
  return Boolean(getDoctorSessionIdFromContext(patient, visit));
}

function buildDoctorDialogueMessages(dialogue, fallbackText = "Doctor consultation started.") {
  const turns = dialogue?.turns || [];
  if (Array.isArray(turns) && turns.length > 0) {
    return turns.map((turn) => {
      const isFinal = turn.role === "assistant" && turn?.metadata?.message_type === "final";
      return {
        role: turn.role === "assistant" ? "assistant" : "user",
        label: turn.role === "assistant" ? (isFinal ? "Final Plan" : "Doctor Agent / Internal Medicine") : "Patient",
        body: turn.content || "",
        type: turn.role === "assistant" ? (isFinal ? "final" : "followup") : "user",
      };
    });
  }

  return [
    {
      role: "assistant",
      label: "Doctor Agent / Internal Medicine",
      body: dialogue?.assistant_message || fallbackText,
      type: dialogue?.message_type || "followup",
    },
  ];
}

function setDoctorDialogueBadges(visitState) {
  if (doctorDialogueUi.agentBadge) {
    doctorDialogueUi.agentBadge.textContent = "Doctor Agent";
  }
  if (doctorDialogueUi.visitBadge) {
    doctorDialogueUi.visitBadge.textContent = visitState ? `Visit: ${visitState}` : "Visit Pending";
  }
}

function syncNpcDialogue() {
  if (!npcDialogueUi.modal || !npcDialogueUi.open) return;
  if (!fixedNpcRuntime?.isDialogueOpen?.()) {
    closeNpcDialogueModal();
    return;
  }
  const snapshot = fixedNpcRuntime.getDialogueSnapshot();
  const renderKey = [
    snapshot.open ? "open" : "closed",
    snapshot.npc?.id || "",
    snapshot.node?.type || "",
    snapshot.node?.text || "",
    snapshot.selectedOptionIndex ?? 0,
    snapshot.options.map((option) => option.label).join("|"),
  ].join("::");
  if (npcDialogueUi.lastRenderedAt === renderKey) return;
  npcDialogueUi.lastRenderedAt = renderKey;
  renderNpcDialogue(npcDialogueUi, snapshot);
}

function openNpcDialogueModal() {
  if (!npcDialogueUi.modal) return;
  npcDialogueUi.open = true;
  npcDialogueUi.lastRenderedAt = "";
  npcDialogueUi.modal.classList.remove("hidden");
  npcDialogueUi.modal.setAttribute("aria-hidden", "false");
  keys.clear();
  syncNpcDialogue();
}

function closeNpcDialogueModal() {
  if (!npcDialogueUi.modal) return;
  npcDialogueUi.open = false;
  npcDialogueUi.lastRenderedAt = "";
  npcDialogueUi.modal.classList.add("hidden");
  npcDialogueUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
  fixedNpcRuntime?.closeDialogue?.();
}

function advanceNpcDialogue() {
  if (!fixedNpcRuntime?.isDialogueOpen?.()) return;
  fixedNpcRuntime.advanceDialogue();
  if (!fixedNpcRuntime.isDialogueOpen()) {
    closeNpcDialogueModal();
    return;
  }
  syncNpcDialogue();
}

function chooseNpcDialogueOption(index) {
  if (!fixedNpcRuntime?.isDialogueOpen?.()) return;
  fixedNpcRuntime.chooseOption(index);
  if (!fixedNpcRuntime.isDialogueOpen()) {
    closeNpcDialogueModal();
    return;
  }
  syncNpcDialogue();
}

// Canonical triage dialogue lifecycle block. Keep one top-level definition per function name.
function openExistingTriageDialogue(patient = getCurrentSelfPatient()) {
  if (!triageDialogueUi.modal || !patient) return;
  triageDialogueUi.open = true;
  triageDialogueUi.awaitingResult = false;
  triageDialogueUi.lastRenderedAt = "";
  triageDialogueUi.modal.classList.remove("hidden");
  triageDialogueUi.modal.setAttribute("aria-hidden", "false");
  if (triageDialogueUi.input) triageDialogueUi.input.value = "";
  keys.clear();
  syncTriageDialogue(patient);
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
      body: `Symptoms: ${initialPayload.symptoms}
Temp: ${initialPayload.vitals.temp_c} C
Heart rate: ${initialPayload.vitals.heart_rate} bpm
Pain: ${initialPayload.vitals.pain_score}/10`,
    },
    {
      role: "assistant",
      label: "Triage Agent",
      body: "I have received the triage card and I am generating a recommendation based on the symptoms and rules.",
    },
  ]);
  if (triageDialogueUi.input) triageDialogueUi.input.value = "";
  keys.clear();
}

function openDoctorDialogue(data = null) {
  if (!doctorDialogueUi.modal) return;
  doctorDialogueUi.open = true;
  doctorDialogueUi.lastRenderedAt = "";
  doctorDialogueUi.modal.classList.remove("hidden");
  doctorDialogueUi.modal.setAttribute("aria-hidden", "false");
  if (doctorDialogueUi.input) doctorDialogueUi.input.value = "";
  keys.clear();
  syncDoctorDialogue(data || null);
}

function closeTriageDialogue() {
  if (!triageDialogueUi.modal) return;
  triageDialogueUi.open = false;
  triageDialogueUi.awaitingResult = false;
  triageDialogueUi.modal.classList.add("hidden");
  triageDialogueUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function closeDoctorDialogue() {
  if (!doctorDialogueUi.modal) return;
  doctorDialogueUi.open = false;
  doctorDialogueUi.modal.classList.add("hidden");
  doctorDialogueUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function syncDoctorDialogue(data) {
  if (!doctorDialogueUi.open) return;
  const payload = data || {};
  const patient = payload.patient || getCurrentSelfPatient();
  const dialogue = payload.dialogue || patient?.dialogue || {};
  const visitState = payload.visit_state || getCurrentVisit()?.state || patient?.visit_state || null;
  const renderKey = `${payload.session_id || doctorConversationState.sessionId || ""}|${visitState || ""}|${dialogue.status || ""}|${dialogue.assistant_message || ""}|${Array.isArray(dialogue.turns) ? dialogue.turns.length : 0}`;
  if (doctorDialogueUi.lastRenderedAt === renderKey) return;
  doctorDialogueUi.lastRenderedAt = renderKey;

  if (doctorDialogueUi.status) {
    if (visitState === "waiting_test") {
      doctorDialogueUi.status.textContent = "Consultation completed. You are now in the diagnostic stage.";
    } else if (visitState === "waiting_payment" || dialogue.status === "completed") {
      doctorDialogueUi.status.textContent = "Consultation completed. Proceed to the payment step.";
    } else if (dialogue.status === "awaiting_patient_reply") {
      doctorDialogueUi.status.textContent = "The doctor agent needs one more detail from you.";
    } else if (dialogue.status === "failed") {
      doctorDialogueUi.status.textContent = "Consultation update failed. You can send another message.";
    } else {
      doctorDialogueUi.status.textContent = "Internal medicine consultation in progress.";
    }
  }

  setDoctorDialogueBadges(visitState);
  renderDialogueMessagesView(
    doctorDialogueUi.messages,
    buildDoctorDialogueMessages(dialogue, "The doctor agent is ready for consultation.")
  );
  renderDialogueEvidenceView(doctorDialogueUi.evidenceList, patient?.triage_evidence || []);

  const isClosed = visitState === "waiting_test" || visitState === "waiting_payment" || dialogue.status === "completed";
  if (doctorDialogueUi.sendBtn) doctorDialogueUi.sendBtn.disabled = isClosed || doctorConversationState.sending;
  if (doctorDialogueUi.input) doctorDialogueUi.input.disabled = isClosed;
}

async function openExistingDoctorDialogue() {
  const sessionId = getDoctorSessionIdFromContext();
  if (!sessionId) {
    pushStatusHint("No active doctor consultation session was found.");
    return;
  }
  doctorConversationState.sessionId = sessionId;
  try {
    const data = await backendClient.getInternalMedicineSession(sessionId);
    if (data?.patient) {
      agentStore.syncPatient(data.patient);
    }
    if (data?.visit_id) {
      doctorConversationState.visitId = data.visit_id;
    }
    openDoctorDialogue(data);
  } catch (error) {
    backendState.lastError = error?.message || "doctor dialogue load failed";
    pushStatusHint(`Doctor dialogue load failed: ${backendState.lastError}`);
  }
}

async function ensureVisitContext() {
  if (triageConversationState.visitId) return triageConversationState.visitId;
  const data = await backendClient.createVisit({
    patient_id: triageConversationState.patientId,
    name: "You (Player)",
  });
  const visitId = data?.visit?.id;
  if (visitId) {
    triageConversationState.visitId = visitId;
    doctorConversationState.visitId = visitId;
  }
  return triageConversationState.visitId;
}

async function submitRegistrationRequest() {
  if (backendState.submitting || !canInteractWithRegistrationDesk()) return;
  backendState.submitting = true;
  try {
    const visitId = await ensureVisitContext();
    if (!visitId) {
      pushStatusHint("Unable to start registration: visit session is missing.");
      return;
    }
    const data = await backendClient.registerVisit(visitId);
    if (data.patient) {
      agentStore.syncPatient(data.patient);
      syncTriageDialogue(data.patient);
    }
    pushStatusHint(data.ready_for_consultation ? "Registration done. You are already ready for doctor entry." : "Registration completed. Waiting queue countdown started (10s).");
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "registration failed";
    if (backendState.lastError.includes("409")) {
      pushStatusHint("Registration is locked: complete triage first.");
    } else {
      pushStatusHint(`Registration failed: ${backendState.lastError}`);
    }
  } finally {
    backendState.submitting = false;
  }
}

async function submitEnterConsultationRequest() {
  if (backendState.submitting || !canInteractWithDoctorEntry()) return;
  backendState.submitting = true;
  try {
    const visitId = await ensureVisitContext();
    if (!visitId) {
      pushStatusHint("Doctor entry unavailable: visit session is missing.");
      return;
    }
    const data = await backendClient.enterConsultation(visitId);
    if (data.patient) {
      agentStore.syncPatient(data.patient);
      syncTriageDialogue(data.patient);
    }
    doctorConversationState.visitId = visitId;
    pushStatusHint("Entered consultation stage. Press E again to start doctor consultation.");
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "enter consultation failed";
    if (backendState.lastError.includes("409")) {
      pushStatusHint("Doctor entry locked: wait for queue call.");
    } else {
      pushStatusHint(`Doctor entry failed: ${backendState.lastError}`);
    }
  } finally {
    backendState.submitting = false;
  }
}

async function submitCreateDoctorSessionRequest() {
  if (backendState.submitting || doctorConversationState.sending) return;
  const selfPatient = getCurrentSelfPatient();
  const visit = getCurrentVisit();
  const visitId = visit?.id || selfPatient?.visit_id || doctorConversationState.visitId;
  if (!visitId) {
    pushStatusHint("Doctor consultation cannot start: visit session is missing.");
    return;
  }

  backendState.submitting = true;
  try {
    const data = await backendClient.createInternalMedicineSession({
      patient_id: doctorConversationState.patientId,
      name: "You (Player)",
      visit_id: visitId,
    });
    doctorConversationState.sessionId = data.session_id || doctorConversationState.sessionId;
    doctorConversationState.visitId = data.visit_id || visitId;
    if (data.patient) {
      agentStore.syncPatient(data.patient);
    }
    openDoctorDialogue(data);
    pushStatusHint("Doctor consultation started.");
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "doctor consultation create failed";
    if (backendState.lastError.includes("409")) {
      pushStatusHint("Doctor consultation is only available after entering consultation.");
    } else {
      pushStatusHint(`Doctor consultation failed: ${backendState.lastError}`);
    }
  } finally {
    backendState.submitting = false;
  }
}

function submitEActionRequest() {
  if (backendState.submitting || triageUi.open || triageDialogueUi.open || doctorDialogueUi.open || npcDialogueUi.open || fixedNpcRuntime?.isDialogueOpen?.()) return;

  if (fixedNpcRuntime?.tryInteract?.(player)) {
    openNpcDialogueModal();
    return;
  }

  if (canInteractWithRegistrationDesk()) {
    submitRegistrationRequest();
    return;
  }

  if (canInteractWithTriageDesk()) {
    const selfPatient = getCurrentSelfPatient();
    const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || null;
    if (!isTriageStage(visitState)) {
      pushStatusHint("Triage already completed for this visit.");
      return;
    }
    if (hasStartedTriageConversation()) {
      openExistingTriageDialogue();
      return;
    }
    openTriageModal();
    return;
  }

  if (canInteractWithDoctorEntry()) {
    const selfPatient = getCurrentSelfPatient();
    const visit = getCurrentVisit();
    const visitState = visit?.state || selfPatient?.visit_state || "";
    const lifecycle = selfPatient?.lifecycle_state || "";

    if (visitState === "in_consultation" || lifecycle === "in_consultation") {
      if (hasStartedDoctorConversation(selfPatient, visit)) {
        openExistingDoctorDialogue();
      } else {
        submitCreateDoctorSessionRequest();
      }
      return;
    }

    if (visitState === "waiting_payment") {
      pushStatusHint("Consultation already completed. Proceed to payment.");
      return;
    }
    if (visitState === "waiting_test") {
      pushStatusHint("Consultation already completed. Proceed to diagnostic stage.");
      return;
    }

    submitEnterConsultationRequest();
  }
}

function syncTriageDialogue(patient) {
  if (!triageDialogueUi.open || !patient) return;
  agentStore.syncPatient(patient);
  const dialogue = patient.dialogue || {};
  const triage = patient.triage || {};
  const renderedAt = `${patient.updated_at || patient.updatedAt || ""}|${dialogue.status || ""}|${triage.level || ""}|${triage.note || ""}`;
  if (triageDialogueUi.lastRenderedAt === renderedAt) return;
  triageDialogueUi.lastRenderedAt = renderedAt;
  triageDialogueUi.awaitingResult = false;

  if (triageDialogueUi.status) {
    if (dialogue.status === "awaiting_patient_reply") {
      triageDialogueUi.status.textContent = "The triage agent needs a bit more information.";
    } else if (dialogue.status === "triaged") {
      triageDialogueUi.status.textContent = `Triage recommendation updated: ${patient.location || "Pending department"}.`;
    } else {
      triageDialogueUi.status.textContent = "Synchronizing the latest triage result.";
    }
  }

  setDialogueBadge(triage.level, patient.location, patient.priority);
  const fallback = patient?.name ? `${patient.name} submitted triage information.` : "Patient submitted triage information.";
  renderDialogueMessages(buildDialogueMessages(patient, fallback));
  renderDialogueEvidence(patient.triage_evidence || patient.triageEvidence || []);
}

async function pollBackendStatuses(force = false) {
  const now = performance.now();
  if (!force && now - backendState.lastPollAt < 2200) return;
  if (backendState.polling) return;

  backendState.polling = true;
  backendState.lastPollAt = now;
  try {
    const [patientData, queueData] = await Promise.all([
      backendClient.listPatients(),
      backendClient.listQueues(),
    ]);
    const patients = Array.isArray(patientData.patients) ? patientData.patients : [];
    let selfPatient = patients.find((patient) => patient.id === triageConversationState.patientId) || null;
    agentStore.syncQueues(queueData.queues || []);

    const visitIdForProgress = selfPatient?.visit_id || triageConversationState.visitId;
    if (visitIdForProgress) {
      try {
        const progressData = await backendClient.progressVisit(visitIdForProgress);
        if (progressData?.patient) {
          selfPatient = progressData.patient;
        }
        if (progressData?.visit?.id) {
          triageConversationState.visitId = progressData.visit.id;
          doctorConversationState.visitId = progressData.visit.id;
        }
      } catch (_progressError) {
        // keep polling resilient when progress endpoint is temporarily unavailable
      }
    }

    queueRuntime.syncFromApi(queueData.queues || [], triageConversationState.patientId);

    let visit = null;
    if (selfPatient?.visit_id) {
      try {
        const visitData = await backendClient.getVisit(selfPatient.visit_id);
        visit = visitData?.visit || null;
      } catch (_visitError) {
        visit = {
          id: selfPatient.visit_id,
          state: selfPatient.visit_state || null,
          current_node: null,
          current_department: selfPatient.location || null,
          active_agent_type: null,
          data: {},
        };
      }
    }

    visitSessionState.visit = visit;
    const queueTicket = selfPatient?.queue_ticket || queueRuntime.state.playerTicket || null;
    taskBoardPresenter.syncVisitSession({
      patient: selfPatient,
      visit,
      queueTicket,
    });

    if (selfPatient) {
      agentStore.syncPatient(selfPatient);
      if (selfPatient.visit_id) {
        triageConversationState.visitId = selfPatient.visit_id;
        doctorConversationState.visitId = selfPatient.visit_id;
      }
      let restoredDoctorSessionId = visit?.data?.internal_medicine_session_id || null;
      if (!restoredDoctorSessionId && !visit) {
        const patientSessionId = String(selfPatient.session_id || "");
        restoredDoctorSessionId = patientSessionId.startsWith("im-session-") ? patientSessionId : null;
      }
      if (restoredDoctorSessionId) {
        doctorConversationState.sessionId = restoredDoctorSessionId;
      }
      syncTriageDialogue(selfPatient);
    }

    if (doctorDialogueUi.open && doctorConversationState.sessionId) {
      try {
        const doctorData = await backendClient.getInternalMedicineSession(doctorConversationState.sessionId);
        if (doctorData?.patient) {
          agentStore.syncPatient(doctorData.patient);
        }
        syncDoctorDialogue(doctorData);
      } catch (_doctorError) {
        // keep doctor modal state stable during transient fetch errors
      }
    }

    backendState.connected = true;
    backendState.lastError = "";
    runtimeDebug.pollSuccessCount += 1;
    runtimeDebug.lastPollResult = selfPatient ? "ok:self" : "ok:no-self-patient";
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "backend offline";
    runtimeDebug.pollFailureCount += 1;
    runtimeDebug.lastPollResult = "failed";
    runtimeDebug.lastError = backendState.lastError;
    taskBoardPresenter.syncOffline("Backend unavailable, visit session not synchronized.");
  } finally {
    backendState.polling = false;
  }
}

async function submitTriageFromModal() {
  if (backendState.submitting || !canInteractWithTriageDesk()) return;
  backendState.submitting = true;
  try {
    const visitId = await ensureVisitContext();
    const payload = buildTriagePayloadFromForm();
    payload.session_id = triageConversationState.sessionId;
    if (visitId) payload.visit_id = visitId;
    const data = await backendClient.createTriageSession(payload);
    triageConversationState.sessionId = data.session_id || triageConversationState.sessionId;
    triageConversationState.visitId = data.visit_id || triageConversationState.visitId;
    doctorConversationState.visitId = triageConversationState.visitId;
    closeTriageModal();
    openTriageDialogue(payload);
    const responsePatient = data.patient && data.dialogue
      ? { ...data.patient, dialogue: data.dialogue }
      : data.patient;
    if (responsePatient) {
      agentStore.syncPatient(responsePatient);
      syncTriageDialogue(responsePatient);
    } else if (triageDialogueUi.status) {
      triageDialogueUi.awaitingResult = false;
      triageDialogueUi.status.textContent = "Triage response was empty. Please retry the triage card.";
    }
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "triage submit failed";
    triageDialogueUi.awaitingResult = false;
    if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = `Triage submit failed: ${backendState.lastError}`;
    }
    pushStatusHint(`Triage submit failed: ${backendState.lastError}`);
  } finally {
    backendState.submitting = false;
  }
}

async function submitTriageDialogueReply() {
  if (triageConversationState.sending || !triageDialogueUi.input) return;
  if (!triageConversationState.sessionId) {
    if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = "No active triage session was found. Please submit a new triage card.";
    }
    pushStatusHint("No active triage session. Start triage again.");
    return;
  }
  const message = triageDialogueUi.input.value.trim();
  if (!message) return;

  triageConversationState.sending = true;
  if (triageDialogueUi.sendBtn) triageDialogueUi.sendBtn.disabled = true;
  if (triageDialogueUi.status) {
    triageDialogueUi.status.textContent = "Sending your reply to the triage agent...";
  }
  try {
    const data = await backendClient.sendTriageMessage(triageConversationState.sessionId, {
      patient_id: triageConversationState.patientId,
      visit_id: triageConversationState.visitId,
      name: "You (Player)",
      message,
    });
    triageDialogueUi.input.value = "";
    triageConversationState.visitId = data.visit_id || triageConversationState.visitId;
    doctorConversationState.visitId = triageConversationState.visitId;
    const responsePatient = data.patient && data.dialogue
      ? { ...data.patient, dialogue: data.dialogue }
      : data.patient;
    if (responsePatient) {
      agentStore.syncPatient(responsePatient);
      syncTriageDialogue(responsePatient);
    } else if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = "Triage response was empty. You can send the reply again.";
    }
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "triage chat failed";
    triageDialogueUi.awaitingResult = false;
    if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = `Dialogue send failed: ${backendState.lastError}`;
    }
    pushStatusHint(`Triage dialogue failed: ${backendState.lastError}`);
  } finally {
    triageConversationState.sending = false;
    if (triageDialogueUi.sendBtn) triageDialogueUi.sendBtn.disabled = false;
  }
}

async function submitDoctorDialogueReply() {
  if (doctorConversationState.sending || !doctorDialogueUi.input || !doctorConversationState.sessionId) return;
  const message = doctorDialogueUi.input.value.trim();
  if (!message) return;

  doctorConversationState.sending = true;
  if (doctorDialogueUi.sendBtn) doctorDialogueUi.sendBtn.disabled = true;
  try {
    const data = await backendClient.sendInternalMedicineMessage(doctorConversationState.sessionId, {
      patient_id: doctorConversationState.patientId,
      name: "You (Player)",
      visit_id: doctorConversationState.visitId || getCurrentVisit()?.id || null,
      message,
    });
    doctorDialogueUi.input.value = "";
    doctorConversationState.visitId = data.visit_id || doctorConversationState.visitId;
    if (data.patient) {
      agentStore.syncPatient(data.patient);
    }
    syncDoctorDialogue(data);
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "doctor dialogue failed";
    if (doctorDialogueUi.status) {
      doctorDialogueUi.status.textContent = `Dialogue send failed: ${backendState.lastError}`;
    }
  } finally {
    doctorConversationState.sending = false;
    if (doctorDialogueUi.sendBtn) {
      const patient = getCurrentSelfPatient();
      const visitState = getCurrentVisit()?.state || patient?.visit_state;
      const isClosed = visitState === "waiting_test" || visitState === "waiting_payment";
      doctorDialogueUi.sendBtn.disabled = isClosed;
    }
  }
}

function submitTriageRequest() {
  submitEActionRequest();
}

fixedNpcRuntime = createFixedNpcRuntime({
  rooms,
  roomBounds,
  canMoveTo,
  extraDefinitions: passiveNpcDefinitions,
});

const npcRuntime = createNpcRuntime({
  rooms,
  roomBounds,
  canMoveTo,
  project,
  constants: {
    CHARACTER_BODY_HEIGHT,
    CHARACTER_FOOT_RADIUS,
    CHARACTER_HEAD_RADIUS,
  },
});

const __moduleDrawFloorLayer = drawFloorLayer;
drawFloorLayer = function modulePatchedDrawFloorLayer(floor, activeDoor, dimmed) {
  __moduleDrawFloorLayer(floor, activeDoor, dimmed);
  npcRuntime.draw(ctx, floor, dimmed ? 0.35 : 1);
};

const __moduleUpdate = update;
update = function modulePatchedUpdate(delta, nowMs) {
  __moduleUpdate(delta, nowMs);
  npcRuntime.update(delta);
};

const __moduleRender = render;
render = function modulePatchedRender() {
  __moduleRender();
  queueRuntime.draw(ctx, canvas);
};

let lastTime = performance.now();
updateZoneTriggers(lastTime);

function loop(now) {
  runtimeDebug.frames += 1;
  runtimeDebug.lastLoopAt = now;
  const delta = Math.min((now - lastTime) / 1000, 1 / 30);
  lastTime = now;
  try {
    update(delta, now);
    render();
    runtimeDebug.lastError = "";
  } catch (error) {
    runtimeDebug.lastError = error?.message || String(error);
    console.error("loop failure", error);
    try {
      render();
    } catch (_renderError) {
      // keep requestAnimationFrame alive even if render also fails
    }
  }
  requestAnimationFrame(loop);
}

window.addEventListener("keydown", (event) => {
  if (!event.repeat && event.code === "Escape" && closeOverlayPanels()) {
    event.preventDefault();
    return;
  }

  if (npcDialogueUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeNpcDialogueModal();
      event.preventDefault();
      return;
    }

    if (event.code === "ArrowUp" || event.code === "ArrowLeft") {
      fixedNpcRuntime?.moveSelection?.(-1);
      syncNpcDialogue();
      event.preventDefault();
      return;
    }

    if (event.code === "ArrowDown" || event.code === "ArrowRight") {
      fixedNpcRuntime?.moveSelection?.(1);
      syncNpcDialogue();
      event.preventDefault();
      return;
    }

    if ((event.code === "KeyE" || event.code === "Enter" || event.code === "Space") && !event.repeat) {
      advanceNpcDialogue();
      event.preventDefault();
      return;
    }

    return;
  }

  if (doctorDialogueUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeDoctorDialogue();
      event.preventDefault();
    }
    return;
  }

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

window.addEventListener("error", (event) => {
  runtimeDebug.lastError = event?.message || "window error";
  console.error("window error", event?.error || event);
});

window.addEventListener("unhandledrejection", (event) => {
  runtimeDebug.lastError = event?.reason?.message || String(event?.reason || "unhandled rejection");
  console.error("unhandled rejection", event?.reason || event);
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

if (triageDialogueUi.form) {
  triageDialogueUi.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitTriageDialogueReply();
  });
}

if (doctorDialogueUi.closeBtn) {
  doctorDialogueUi.closeBtn.addEventListener("click", () => {
    closeDoctorDialogue();
  });
}

if (doctorDialogueUi.modal) {
  doctorDialogueUi.modal.addEventListener("click", (event) => {
    if (event.target === doctorDialogueUi.modal) closeDoctorDialogue();
  });
}

if (doctorDialogueUi.form) {
  doctorDialogueUi.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitDoctorDialogueReply();
  });
}

if (npcDialogueUi.closeBtn) {
  npcDialogueUi.closeBtn.addEventListener("click", () => {
    closeNpcDialogueModal();
  });
}

if (npcDialogueUi.advanceBtn) {
  npcDialogueUi.advanceBtn.addEventListener("click", () => {
    advanceNpcDialogue();
  });
}

if (npcDialogueUi.options) {
  npcDialogueUi.options.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("button[data-option-index]");
    if (!button) return;
    const index = Number(button.dataset.optionIndex);
    chooseNpcDialogueOption(Number.isFinite(index) ? index : 0);
  });
}

if (npcDialogueUi.modal) {
  npcDialogueUi.modal.addEventListener("click", (event) => {
    if (event.target === npcDialogueUi.modal) {
      closeNpcDialogueModal();
    }
  });
}

if (triageUi.fields.pain && triageUi.painDisplay) {
  triageUi.painDisplay.textContent = triageUi.fields.pain.value;
  triageUi.fields.pain.addEventListener("input", (event) => {
    triageUi.painDisplay.textContent = event.target.value;
  });
}

bindHudControls();
updateFloorHud();
pollBackendStatuses(true);
window.dispatchEvent(new Event("resize"));
requestAnimationFrame(loop);
