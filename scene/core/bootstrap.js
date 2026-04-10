import { createBackendClient } from "../agent/client.js";
import { createAgentStore, buildDialogueMessages } from "../agent/store.js";
import { buildTriagePayloadFromFormValues } from "../agent/triage-form.js";
import { renderDialogueEvidence as renderDialogueEvidenceView, renderDialogueMessages as renderDialogueMessagesView, setDialogueBadges } from "../agent/triage-dialogue.js";
import { createQueueRuntime } from "../queue/runtime.js";
import { createNpcRuntime } from "../npc/runtime.js";
import { createTaskBoardPresenter } from "../ui/task-board.js";

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
    { text: "Arrive at the triage desk", done: true },
    { text: "Complete triage intake", done: false },
    { text: "Wait for queue assignment", done: false },
    { text: "Follow the queue board for the next step", done: false },
    { text: "Enter the consultation room when called", done: false },
  ],
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
  return deriveRoomInteractPoint("triage", { x: 10.6 * TILE, y: 17.4 * TILE, floor: 1, radius: 56 }, { preferReception: true });
}

function deriveRegistrationInteractPoint() {
  return deriveRoomInteractPoint("registration", { x: 8.6 * TILE, y: 7.4 * TILE, floor: 1, radius: 56 }, { preferReception: true });
}

function deriveDoctorEntryInteractPoint() {
  return deriveRoomInteractPoint("pharmacy", { x: 40.8 * TILE, y: 18.4 * TILE, floor: 1, radius: 56 }, {});
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

function legacyMapPatientStateToTask(patient) {
  return {
    text: `${patient.name} | ${patient.state} | ${patient.location ?? "-"}`,
    done: false,
  };
}

async function legacyPollBackendStatuses() {
  return;
}

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
  return buildTriagePayloadFromFormValues({
    fields: triageUi.fields,
    zoneLabel: zoneState.currentZoneLabel,
    floor: player.floor,
  });
}

async function legacySubmitTriageFromModal() {
  return;
}

function legacySubmitTriageRequest() {
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

function drawRegistrationHint() {
  if (!canInteractWithRegistrationDesk()) return;
  const point = project(registrationInteractPoint.x, registrationInteractPoint.y, 48, registrationInteractPoint.floor);
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

function drawDoctorEntryHint() {
  if (!canInteractWithDoctorEntry()) return;
  const point = project(doctorEntryInteractPoint.x, doctorEntryInteractPoint.y, 48, doctorEntryInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visitState = selfPatient?.visit_state || "";
  const lifecycle = selfPatient?.lifecycle_state || "";

  let label = "Follow workflow: triage -> register -> wait";
  if (backendState.submitting) {
    label = "Entering consultation...";
  } else if (visitState === "in_consultation" || lifecycle === "in_consultation") {
    label = "Already in consultation";
  } else if (visitState === "waiting_consultation" && lifecycle === "called") {
    label = "Press E to enter consultation";
  } else if (visitState === "registered" || lifecycle === "queued") {
    label = "Waiting for queue call (10s)";
  } else if (visitState === "triaged") {
    label = "Complete registration first";
  }

  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 232;
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
  drawRegistrationHint();
  drawTriageHint();
  drawDoctorEntryHint();
  drawTaskBoard();
  drawMinimap();
  drawZoneStatusPanel();
}
triageDialogueUi.form = document.getElementById("triageDialogueForm");
triageDialogueUi.input = document.getElementById("triageDialogueInput");
triageDialogueUi.sendBtn = document.getElementById("triageDialogueSendBtn");

const triageConversationState = {
  patientId: "P-self",
  visitId: null,
  sessionId: "session-main",
  sending: false,
};

function getCurrentSelfPatient() {
  const patient = agentStore.lastPatient;
  return patient && patient.id === triageConversationState.patientId ? patient : null;
}

function hasStartedTriageConversation(patient = getCurrentSelfPatient()) {
  if (!patient) return false;
  if (Array.isArray(patient?.dialogue?.turns) && patient.dialogue.turns.length > 0) return true;
  if (patient?.dialogue?.status && patient.dialogue.status !== "idle") return true;
  return patient?.state && patient.state !== "Untriaged";
}

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
      body: `Symptoms: ${initialPayload.symptoms}\nTemp: ${initialPayload.vitals.temp_c} C\nHeart rate: ${initialPayload.vitals.heart_rate} bpm\nPain: ${initialPayload.vitals.pain_score}/10`,
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

async function ensureVisitContext() {
  if (triageConversationState.visitId) return triageConversationState.visitId;
  const data = await backendClient.createVisit({
    patient_id: triageConversationState.patientId,
    name: "You (Player)",
  });
  const visitId = data?.visit?.id;
  if (visitId) {
    triageConversationState.visitId = visitId;
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
    pushStatusHint("Entered consultation stage.");
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

function submitEActionRequest() {
  if (backendState.submitting || triageUi.open || triageDialogueUi.open) return;

  if (canInteractWithRegistrationDesk()) {
    submitRegistrationRequest();
    return;
  }

  if (canInteractWithTriageDesk()) {
    if (hasStartedTriageConversation()) {
      openExistingTriageDialogue();
      return;
    }
    openTriageModal();
    return;
  }

  if (canInteractWithDoctorEntry()) {
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
        };
      }
    }

    const queueTicket = selfPatient?.queue_ticket || queueRuntime.state.playerTicket || null;
    taskBoardPresenter.syncVisitSession({
      patient: selfPatient,
      visit,
      queueTicket,
    });

    if (selfPatient) {
      agentStore.syncPatient(selfPatient);
      if (selfPatient.visit_id) triageConversationState.visitId = selfPatient.visit_id;
      syncTriageDialogue(selfPatient);
    }
    backendState.connected = true;
    backendState.lastError = "";
  } catch (error) {
    backendState.connected = false;
    backendState.lastError = error?.message || "backend offline";
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
    closeTriageModal();
    openTriageDialogue(payload);
    if (data.patient) {
      agentStore.syncPatient(data.patient);
      syncTriageDialogue(data.patient);
    }
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
    const data = await backendClient.sendTriageMessage(triageConversationState.sessionId, {
      patient_id: triageConversationState.patientId,
      name: "You (Player)",
      message,
    });
    triageDialogueUi.input.value = "";
    triageConversationState.visitId = data.visit_id || triageConversationState.visitId;
    if (data.patient) {
      agentStore.syncPatient(data.patient);
      syncTriageDialogue(data.patient);
    }
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "triage chat failed";
    if (triageDialogueUi.status) {
      triageDialogueUi.status.textContent = `Dialogue send failed: ${backendState.lastError}`;
    }
  } finally {
    triageConversationState.sending = false;
    if (triageDialogueUi.sendBtn) triageDialogueUi.sendBtn.disabled = false;
  }
}

function submitTriageRequest() {
  submitEActionRequest();
}

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

if (triageUi.fields.pain && triageUi.painDisplay) {
  triageUi.painDisplay.textContent = triageUi.fields.pain.value;
  triageUi.fields.pain.addEventListener("input", (event) => {
    triageUi.painDisplay.textContent = event.target.value;
  });
}

updateFloorHud();
pollBackendStatuses(true);
window.dispatchEvent(new Event("resize"));
requestAnimationFrame(loop);










