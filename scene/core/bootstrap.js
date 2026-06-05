import { createBackendClient } from "../agent/client.js";
import { createAgentStore, buildDialogueMessages } from "../agent/store.js";
import { createEventSubscriber } from "../agent/event-subscriber.js";
import { createStateDebugPanel } from "./state-debug-panel.js";
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
const hudRestartBtn = document.getElementById("hudRestartBtn");
const hudResumeBtn = document.getElementById("hudResumeBtn");
const hudHelpToggle = document.getElementById("hudHelpToggle");
const hudRuntimeToggle = document.getElementById("hudRuntimeToggle");
const hudHelpPanel = document.getElementById("hudHelpPanel");
const hudRuntimePanel = document.getElementById("hudRuntimePanel");
const hudTasksToggle = document.getElementById("hudTasksToggle");
const hudLabelsToggle = document.getElementById("hudLabelsToggle");
const hudDebugToggle = document.getElementById("hudDebugToggle");
const hudRuntimeStopBtn = document.getElementById("hudRuntimeStopBtn");
const hudRuntimeResetBtn = document.getElementById("hudRuntimeResetBtn");
const hudRuntimeStatus = document.getElementById("hudRuntimeStatus");
const hudRuntimeMode = document.getElementById("hudRuntimeMode");
const hudRuntimeSpawn = document.getElementById("hudRuntimeSpawn");
const hudRuntimeStep = document.getElementById("hudRuntimeStep");
const hudRuntimeMax = document.getElementById("hudRuntimeMax");
const hudRuntimeLlmProbability = document.getElementById("hudRuntimeLlmProbability");
const hudRuntimeDragHandle = document.getElementById("hudRuntimeDragHandle");
const hudQueueToggle = document.getElementById("hudQueueToggle");
const hudPatientsToggle = document.getElementById("hudPatientsToggle");
const hudRuntimeStatsToggle = document.getElementById("hudRuntimeStatsToggle");
const hudRuntimeStatsPanel = document.getElementById("hudRuntimeStatsPanel");
const hudRuntimeStatsDragHandle = document.getElementById("hudRuntimeStatsDragHandle");
const hudRuntimeStatsContent = document.getElementById("hudRuntimeStatsContent");
const hudNpcRouteButtons = Array.from(document.querySelectorAll("[data-route-target]"));

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
  runtimeOpen: false,
  tasksOpen: false,
  labelsOpen: false,
  debugOpen: false,
  queueOpen: true,
  patientsOpen: true,
  runtimeStatsOpen: false,
};

const palette = {
  grassA: "#86bf5e",
  grassB: "#7ab356",
  grassC: "#93c96d",
  dirt: "#b98a57",
  path: "#c9b184",
  roomFloor: "#e6d9bb",
  hallFloor: "#efe3c8",
  roomTrim: "#b69263",
  roomFloorAccent: "#d9c49a",
  wallFront: "#c48c5e",
  wallSide: "#a86f45",
  wallTop: "#dfbc8f",
  wallEdge: "rgba(99, 57, 29, 0.45)",
  wallHighlight: "rgba(255, 234, 194, 0.45)",
  bed: "#8ebed3",
  desk: "#9c7248",
  sofa: "#8fae69",
  plant: "#6fa154",
  screen: "#9fd2d8",
  cabinet: "#b9a17e",
  reception: "#c58d57",
  doorFrame: "#8f6844",
  doorPanel: "#e6dfcf",
  doorGlass: "#bddfe6",
  doorRail: "#6f7b86",
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
  { floor: 1, x: 63, y: 5, w: 13, h: 9, kind: "doctor_entry" },
  { floor: 1, x: 8, y: 17, w: 18, h: 12, kind: "hall" },
  { floor: 1, x: 27, y: 17, w: 15, h: 11, kind: "lab" },
  { floor: 1, x: 43, y: 17, w: 15, h: 11, kind: "icu" },
  { floor: 1, x: 59, y: 17, w: 14, h: 11, kind: "ward" },
  { floor: 1, x: 10, y: 32, w: 16, h: 11, kind: "office" },
  { floor: 1, x: 27, y: 32, w: 16, h: 11, kind: "empty_room" },
  { floor: 1, x: 44, y: 32, w: 15, h: 11, kind: "empty_room" },
  { floor: 1, x: 60, y: 32, w: 14, h: 11, kind: "pharmacy_pickup" },
  { floor: 1, x: 31, y: 45, w: 22, h: 7, kind: "hall" },
];

const doorSpecs = [
  { roomIndex: 0, side: "bottom", offset: 5.4, length: 2.2, label: "REG-A" },
  { roomIndex: 1, side: "bottom", offset: 6.0, length: 2.2, label: "TRIAGE-A" },
  { roomIndex: 2, side: "bottom", offset: 5.8, length: 2.2, label: "CONS-1" },
  { roomIndex: 3, side: "bottom", offset: 5.8, length: 2.2, label: "CONS-2" },
  { roomIndex: 4, side: "bottom", offset: 5.2, length: 2.2, label: "DOC-ENTRY" },
  { roomIndex: 5, side: "top", offset: 7.4, length: 2.2, label: "HALL-N" },
  { roomIndex: 5, side: "right", offset: 4.8, length: 2.0, label: "HALL-E" },
  { roomIndex: 6, side: "top", offset: 5.8, length: 2.2, label: "LAB-A" },
  { roomIndex: 7, side: "top", offset: 5.8, length: 2.2, label: "ICU-A" },
  { roomIndex: 8, side: "top", offset: 5.2, length: 2.2, label: "WARD-A" },
  { roomIndex: 9, side: "top", offset: 5.8, length: 2.2, label: "OFFICE-A" },
  { roomIndex: 10, side: "top", offset: 5.8, length: 2.2, label: "RESERVE-A" },
  { roomIndex: 11, side: "top", offset: 5.4, length: 2.2, label: "RESERVE-B" },
  { roomIndex: 12, side: "top", offset: 5.2, length: 2.2, label: "PHARM-PICKUP" },
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
  { floor: 1, x: 67.0, y: 35.4, w: 2.5, h: 1.2, type: "desk", z: 20 },
  { floor: 1, x: 70.2, y: 35.5, w: 1.4, h: 1.4, type: "plant", z: 24 },
];

const ROOM_KIND_LABELS = {
  registration: "Registration",
  consultation: "Consultation",
  triage: "Triage",
  doctor_entry: "Doctor Entry",
  pharmacy_pickup: "Pharmacy",
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

const INTERIOR_BASE_X = 12 * TILE;
const INTERIOR_BASE_Y = 8 * TILE;

const indoorRoomTemplates = {
  registration: {
    label: "Registration Room",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 20 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.5 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4 * TILE, w: 4 * TILE, h: 2 * TILE, type: "reception" },
      { x: INTERIOR_BASE_X + 6 * TILE, y: INTERIOR_BASE_Y + 3 * TILE, w: 2 * TILE, h: 1.2 * TILE, type: "plant" },
      { x: INTERIOR_BASE_X + 5 * TILE, y: INTERIOR_BASE_Y + 8 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to submit registration",
    statusHint: "Entered Registration Room. Press E to register, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  triage: {
    label: "Triage Room",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 22 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4 * TILE, w: 4 * TILE, h: 2 * TILE, type: "reception" },
      { x: INTERIOR_BASE_X + 7 * TILE, y: INTERIOR_BASE_Y + 3.4 * TILE, w: 1.4 * TILE, h: 1.4 * TILE, type: "screen" },
      { x: INTERIOR_BASE_X + 6 * TILE, y: INTERIOR_BASE_Y + 8.2 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to open triage intake",
    statusHint: "Entered Triage Room. Press E to start triage, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  doctor_entry: {
    label: "Doctor Entry Hall",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 22 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4 * TILE, w: 4 * TILE, h: 2 * TILE, type: "desk" },
      { x: INTERIOR_BASE_X + 6 * TILE, y: INTERIOR_BASE_Y + 3.5 * TILE, w: 2.8 * TILE, h: 1.2 * TILE, type: "cabinet" },
      { x: INTERIOR_BASE_X + 6.2 * TILE, y: INTERIOR_BASE_Y + 8.2 * TILE, w: 3.4 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to continue consultation flow",
    statusHint: "Entered Doctor Entry Hall. Press E near the desk, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  lab: {
    label: "Laboratory",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 24 * TILE, h: 13 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 17 * TILE, y: INTERIOR_BASE_Y + 7 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 5 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 15 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 4 * TILE, h: 1.8 * TILE, type: "screen" },
      { x: INTERIOR_BASE_X + 7 * TILE, y: INTERIOR_BASE_Y + 3.4 * TILE, w: 3.4 * TILE, h: 1.2 * TILE, type: "cabinet" },
      { x: INTERIOR_BASE_X + 8 * TILE, y: INTERIOR_BASE_Y + 8.4 * TILE, w: 2.5 * TILE, h: 1.2 * TILE, type: "desk" },
    ],
    actionLabel: "Press E to continue test stage",
    statusHint: "Entered Laboratory. Press E near the station, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  icu: {
    label: "ICU Room",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 24 * TILE, h: 13 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 17 * TILE, y: INTERIOR_BASE_Y + 7 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 5 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 15 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "bed" },
      { x: INTERIOR_BASE_X + 10 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "bed" },
      { x: INTERIOR_BASE_X + 6.8 * TILE, y: INTERIOR_BASE_Y + 8.5 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "screen" },
    ],
    actionLabel: "Press E to consult ICU",
    statusHint: "Entered ICU Room. Press E near the station, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  consultation: {
    label: "Consultation Room",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 22 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 4 * TILE, h: 1.8 * TILE, type: "desk" },
      { x: INTERIOR_BASE_X + 6.5 * TILE, y: INTERIOR_BASE_Y + 8.3 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "sofa" },
      { x: INTERIOR_BASE_X + 8.2 * TILE, y: INTERIOR_BASE_Y + 3.8 * TILE, w: 1.4 * TILE, h: 1.4 * TILE, type: "plant" },
    ],
    actionLabel: "Press E to consult or talk",
    statusHint: "Entered Consultation Room. Press E near the desk, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  pharmacy_pickup: {
    label: "Pharmacy",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 22 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4 * TILE, w: 4 * TILE, h: 2 * TILE, type: "cabinet" },
      { x: INTERIOR_BASE_X + 10.5 * TILE, y: INTERIOR_BASE_Y + 4.4 * TILE, w: 2.8 * TILE, h: 1.2 * TILE, type: "desk" },
      { x: INTERIOR_BASE_X + 6.5 * TILE, y: INTERIOR_BASE_Y + 8.3 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to pick up medication",
    statusHint: "Entered Pharmacy. Press E near the counter, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  office: {
    label: "Office",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 22 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 16 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 4 * TILE, h: 1.8 * TILE, type: "desk" },
      { x: INTERIOR_BASE_X + 7 * TILE, y: INTERIOR_BASE_Y + 3.4 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "cabinet" },
      { x: INTERIOR_BASE_X + 8 * TILE, y: INTERIOR_BASE_Y + 8.3 * TILE, w: 3.4 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to talk to staff",
    statusHint: "Entered Office. Press E near the desk, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  ward: {
    label: "Ward",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 24 * TILE, h: 13 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 17 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 5 * TILE, y: INTERIOR_BASE_Y + 11 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 14 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "bed" },
      { x: INTERIOR_BASE_X + 10 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "bed" },
      { x: INTERIOR_BASE_X + 6.5 * TILE, y: INTERIOR_BASE_Y + 8.5 * TILE, w: 3.2 * TILE, h: 1.2 * TILE, type: "sofa" },
    ],
    actionLabel: "Press E to talk to staff",
    statusHint: "Entered Ward. Press E near the station, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
  empty_room: {
    label: "Reserve Room",
    room: { x: INTERIOR_BASE_X, y: INTERIOR_BASE_Y, w: 20 * TILE, h: 12 * TILE },
    interactPoint: { x: INTERIOR_BASE_X + 15 * TILE, y: INTERIOR_BASE_Y + 7.2 * TILE, floor: 1, radius: 72 },
    exitPoint: { x: INTERIOR_BASE_X + 3 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1, radius: 72 },
    spawn: { x: INTERIOR_BASE_X + 4 * TILE, y: INTERIOR_BASE_Y + 10 * TILE, floor: 1 },
    furniture: [
      { x: INTERIOR_BASE_X + 12 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 3 * TILE, h: 1.2 * TILE, type: "sofa" },
      { x: INTERIOR_BASE_X + 7.5 * TILE, y: INTERIOR_BASE_Y + 4.2 * TILE, w: 1.4 * TILE, h: 1.4 * TILE, type: "plant" },
    ],
    actionLabel: "Press E to look around",
    statusHint: "Entered Reserve Room. Press E near the desk, Q to return.",
    exitHint: "Press E at EXIT or Q to return.",
  },
};

const microScene = {
  mode: "campus",
  returnPoint: null,
  gate: {
    x: 4 * TILE,
    y: 23 * TILE,
    floor: 1,
    radius: 80,
  },
  indoor: {
    activeRoomKind: null,
    template: null,
  },
  annex: {
    room: {
      x: 38 * TILE,
      y: 8 * TILE,
      w: 28 * TILE,
      h: 18 * TILE,
    },
    exitPoint: {
      x: 38 * TILE + 4 * TILE,
      y: 8 * TILE + 15 * TILE,
      floor: 1,
      radius: 80,
    },
    npcList: [
      { x: 38 * TILE + 8 * TILE, y: 8 * TILE + 5 * TILE, name: "Lena", role: "Visitor", color: "#e9a96d" },
      { x: 38 * TILE + 18 * TILE, y: 8 * TILE + 6 * TILE, name: "Kai", role: "Waiting", color: "#78c49f" },
      { x: 38 * TILE + 12 * TILE, y: 8 * TILE + 12 * TILE, name: "Mina", role: "Guest", color: "#8eb4f2" },
    ],
  },
};

const SESSION_STORAGE_KEYS = {
  activeClientId: "scene_active_client_id",
  lastClientId: "scene_last_client_id",
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

const integrationState = {
  medicalRecordTimeline: null,
  hospitalRuntime: null,
  departmentRuntime: null,
  departments: null,
  openEmrHealth: null,
  icuPatients: null,
  lastRuntimeRefreshAt: 0,
  lastMedicalRecordVisitId: null,
  lastMedicalRecordSummaryKey: "",
  runtimeControlBusy: false,
};

const runtimePanelState = {
  dragging: false,
  pointerId: null,
  startClientX: 0,
  startClientY: 0,
  startLeft: 0,
  startTop: 0,
};

const runtimeStatsPanelState = {
  dragging: false,
  pointerId: null,
  startClientX: 0,
  startClientY: 0,
  startLeft: 0,
  startTop: 0,
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
  return deriveRoomInteractPoint("doctor_entry", { x: 69.2 * TILE, y: 11.2 * TILE, floor: 1, radius: 64 }, {});
}

function derivePharmacyPickupInteractPoint() {
  return deriveRoomInteractPoint("pharmacy_pickup", { x: 67.2 * TILE, y: 37.4 * TILE, floor: 1, radius: 64 }, {});
}

function deriveMainGatePoint() {
  return {
    x: microScene.gate.x,
    y: microScene.gate.y,
    floor: microScene.gate.floor,
  };
}

const triageInteractPoint = deriveTriageInteractPoint();
const registrationInteractPoint = deriveRegistrationInteractPoint();
const doctorEntryInteractPoint = deriveDoctorEntryInteractPoint();
const pharmacyPickupInteractPoint = derivePharmacyPickupInteractPoint();
const mainGatePoint = deriveMainGatePoint();
const labInteractPoint = deriveRoomInteractPoint("lab", { x: 34.5 * TILE, y: 22.5 * TILE, floor: 1, radius: 64 }, {});
const privateApiConfig = window.HOS_PRIVATE_API || {};
const backendState = {
  baseUrl: privateApiConfig.baseUrl || "http://127.0.0.1:8787",
  apiKey: privateApiConfig.apiKey || "mock-key-001",
  connected: false,
  streamConnected: false,
  lastPollAt: 0,
  polling: false,
  submitting: false,
  lastError: "",
};
const backendClient = createBackendClient({ baseUrl: backendState.baseUrl, apiKey: backendState.apiKey });
const agentStore = createAgentStore();
let latestSceneSnapshot = null;
const debugQueryParams = new URLSearchParams(window.location.search);
const stateDebugEnabledByParam = debugQueryParams.get("stateDebug") === "1";
const isLocalSceneHost = ["127.0.0.1", "localhost"].includes(window.location.hostname);
const stateDebugEnabled = privateApiConfig.stateDebug === true || stateDebugEnabledByParam || isLocalSceneHost;
const eventSubscriber = createEventSubscriber({
  baseUrl: backendState.baseUrl,
  onStatusChange: ({ status, error }) => {
    backendState.streamConnected = status === "connected";
    if (status === "disconnected" && error) {
      runtimeDebug.lastError = error;
    }
  },
  onEvent: (envelope) => {
    const eventType = envelope?.event_type || "";
    const matchesPatient = envelope?.patient_id && envelope.patient_id === triageConversationState.patientId;
    if (matchesPatient || eventType.startsWith("encounter.")) {
      if (eventType === "encounter.opened") {
        pushStatusHint("Encounter opened.");
      } else if (eventType === "patient.registered") {
        pushStatusHint("Registration synchronized from event stream.");
      } else if (eventType === "patient.triaged") {
        pushStatusHint("Triage completed (event).");
      } else if (eventType === "patient.transferred") {
        pushStatusHint("Encounter transferred.");
      } else if (eventType === "encounter.consultation_started") {
        pushStatusHint("Consultation started (event).");
      } else if (eventType === "encounter.consultation_completed") {
        pushStatusHint("Consultation completed (event).");
      } else {
        console.info("[scene:event-placeholder]", eventType, envelope);
      }
      pollBackendStatuses(true);
    }
  },
});
const stateDebugPanel = createStateDebugPanel({
  enabled: stateDebugEnabled,
  backendClient,
  onHint: (text) => pushStatusHint(text),
  ensureEncounter: () => ensureVisitContext(),
});
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
const registrationUi = {
  open: false,
  modal: document.getElementById("registrationModal"),
  form: document.getElementById("registrationForm"),
  cancelBtn: document.getElementById("registrationCancelBtn"),
  fields: {
    name: document.getElementById("registrationName"),
    sex: document.getElementById("registrationSex"),
    age: document.getElementById("registrationAge"),
    idNumber: document.getElementById("registrationIdNumber"),
  },
};
const restartConfirmUi = {
  open: false,
  modal: document.getElementById("restartConfirmModal"),
  okBtn: document.getElementById("restartConfirmOkBtn"),
  cancelBtn: document.getElementById("restartConfirmCancelBtn"),
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

function canInteractWithRegistrationRoomDesk() {
  const template = microScene.indoor.template;
  if (microScene.mode !== "indoor_room" || microScene.indoor.activeRoomKind !== "registration" || !template) return false;
  if (player.floor !== template.interactPoint.floor) return false;
  return Math.hypot(player.x - template.interactPoint.x, player.y - template.interactPoint.y) <= template.interactPoint.radius;
}

function canSubmitRegistrationFromCurrentContext() {
  return canInteractWithRegistrationDesk() || canInteractWithRegistrationRoomDesk();
}

function canInteractWithRegistrationRoomExit() {
  const template = microScene.indoor.template;
  if (microScene.mode !== "indoor_room" || !template) return false;
  if (player.floor !== template.exitPoint.floor) return false;
  return Math.hypot(player.x - template.exitPoint.x, player.y - template.exitPoint.y) <= template.exitPoint.radius;
}

function canInteractWithAnnexGate() {
  if (microScene.mode !== "campus") return false;
  if (player.floor !== microScene.gate.floor) return false;
  return Math.hypot(player.x - microScene.gate.x, player.y - microScene.gate.y) <= microScene.gate.radius;
}

function canInteractWithAnnexExit() {
  if (microScene.mode !== "annex_room") return false;
  if (player.floor !== microScene.annex.exitPoint.floor) return false;
  return Math.hypot(player.x - microScene.annex.exitPoint.x, player.y - microScene.annex.exitPoint.y) <= microScene.annex.exitPoint.radius;
}

function enterIndoorRoom(roomKind) {
  const template = indoorRoomTemplates[roomKind];
  if (!template || microScene.mode === "indoor_room") return;
  microScene.returnPoint = { x: player.x, y: player.y, floor: player.floor };
  microScene.mode = "indoor_room";
  microScene.indoor.activeRoomKind = roomKind;
  microScene.indoor.template = template;
  const spawn = template.spawn;
  const safe = findNearestWalkable(spawn.x, spawn.y, spawn.floor);
  player.x = safe.x;
  player.y = safe.y;
  player.floor = spawn.floor;
  camera.x = player.x;
  camera.y = player.y;
  updateFloorHud();
  pushStatusHint(template.statusHint || "Entered room. Press E to interact, Q to return.");
}

function enterAnnexRoom() {
  if (microScene.mode === "annex_room") return;
  microScene.returnPoint = { x: player.x, y: player.y, floor: player.floor };
  microScene.mode = "annex_room";
  const spawn = {
    x: microScene.annex.room.x + TILE * 5,
    y: microScene.annex.room.y + microScene.annex.room.h - TILE * 3,
    floor: 1,
  };
  const safe = findNearestWalkable(spawn.x, spawn.y, spawn.floor);
  player.x = safe.x;
  player.y = safe.y;
  player.floor = spawn.floor;
  camera.x = player.x;
  camera.y = player.y;
  updateFloorHud();
  pushStatusHint("Entered Annex Yard. Press E at EXIT to return.");
}

function leaveRegistrationRoom() {
  if (microScene.mode !== "indoor_room") return;
  const fallback = floorSpawns[1];
  const target = microScene.returnPoint || { x: fallback.x, y: fallback.y, floor: 1 };
  const safe = findNearestWalkable(target.x, target.y, target.floor || 1);
  player.x = safe.x;
  player.y = safe.y;
  player.floor = target.floor || 1;
  microScene.mode = "campus";
  microScene.indoor.activeRoomKind = null;
  microScene.indoor.template = null;
  camera.x = player.x;
  camera.y = player.y;
  updateFloorHud();
  pushStatusHint("Returned to Main Campus.");
}

function leaveAnnexRoom() {
  if (microScene.mode !== "annex_room") return;
  const fallback = floorSpawns[1];
  const target = microScene.returnPoint || { x: fallback.x, y: fallback.y, floor: 1 };
  const safe = findNearestWalkable(target.x, target.y, target.floor || 1);
  player.x = safe.x;
  player.y = safe.y;
  player.floor = target.floor || 1;
  microScene.mode = "campus";
  camera.x = player.x;
  camera.y = player.y;
  updateFloorHud();
  pushStatusHint("Returned to Main Campus.");
}

function canInteractWithDoctorEntry() {
  if (player.floor !== doctorEntryInteractPoint.floor) return false;
  return Math.hypot(player.x - doctorEntryInteractPoint.x, player.y - doctorEntryInteractPoint.y) <= doctorEntryInteractPoint.radius;
}

function canInteractWithPharmacyPickup() {
  if (player.floor !== pharmacyPickupInteractPoint.floor) return false;
  return Math.hypot(player.x - pharmacyPickupInteractPoint.x, player.y - pharmacyPickupInteractPoint.y) <= pharmacyPickupInteractPoint.radius;
}

function canInteractWithLab() {
  if (player.floor !== labInteractPoint.floor) return false;
  return Math.hypot(player.x - labInteractPoint.x, player.y - labInteractPoint.y) <= labInteractPoint.radius;
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

function truncateText(value, maxLength = 160) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3))}...`;
}

function mapRuntimeNodeToRoomKind(nodeId) {
  if (!nodeId) return "hall";
  if (nodeId === "testing") return "lab";
  if (nodeId === "payment") return "registration";
  if (nodeId === "pharmacy") return "pharmacy_pickup";
  if (nodeId === "internal") return "doctor_entry";
  if (nodeId === "surgery") return "consultation";
  if (nodeId === "rehabilitation") return "ward";
  if (nodeId === "ward") return "ward";
  if (String(nodeId).includes("consult_room")) return "consultation";
  if (String(nodeId).includes("procedure")) return "lab";
  return rooms.some((room) => room.kind === nodeId) ? nodeId : "hall";
}

function buildHospitalScenePatients() {
  const snapshot = integrationState.hospitalRuntime;
  if (!snapshot || !Array.isArray(snapshot.nodes)) return [];

  const items = [];
  for (const nodeView of snapshot.nodes) {
    const nodeId = nodeView?.node?.node_id || "";
    const roomKind = mapRuntimeNodeToRoomKind(nodeId);
    for (const patient of nodeView?.patients || []) {
      if (String(patient.visit_state || "") === "completed") continue;
      items.push({
        patientId: patient.patient_id,
        roomKind: mapRuntimeNodeToRoomKind(patient.current_room_node_id || patient.current_node_id || nodeId) || roomKind,
        finished: Boolean(patient.finished || patient.visit_state === "completed"),
        priority: patient.visit_state === "in_icu_rescue" ? "H" : "M",
        visitState: patient.visit_state || "",
        currentNodeId: patient.current_node_id || nodeId,
        targetNodeId: patient.target_node_id || "",
        displayLabel: patient.npc_id || patient.patient_id,
        statusSummary: truncateText(patient.department_status || patient.department_flow_status || patient.visit_state || "moving", 18),
      });
    }
  }
  return items;
}

function summarizeVisitStage(visitState) {
  const state = String(visitState || "");
  if (["arrived", "triaging", "waiting_followup", "triaged"].includes(state)) return "triage";
  if (["registered", "waiting_consultation"].includes(state)) return "queue";
  if (state === "in_consultation") return "consult1";
  if (["waiting_test", "waiting_test_payment", "test_payment_completed", "in_test", "waiting_return_consultation", "results_ready"].includes(state)) return "testing";
  if (state === "in_second_consultation") return "consult2";
  if (["diagnosis_finalized", "waiting_payment", "medical_payment_completed"].includes(state)) return "payment";
  if (state === "admitted") return "ward";
  if (state === "waiting_pharmacy") return "pharmacy";
  if (state === "completed") return "completed";
  return state || "unknown";
}

function buildRuntimePatientDetails(snapshot) {
  const details = [];
  for (const node of snapshot?.nodes || []) {
    for (const patient of node.patients || []) {
      if (String(patient.visit_state || "") === "completed") continue;
      details.push({
        label: patient.npc_id || patient.patient_id,
        patientId: patient.patient_id,
        roomKind: mapRuntimeNodeToRoomKind(patient.current_room_node_id || patient.current_node_id || node.node.node_id),
        visitState: patient.visit_state || "",
        stage: summarizeVisitStage(patient.visit_state),
        currentNodeId: patient.current_node_id || node.node.node_id,
        targetNodeId: patient.target_node_id || "",
        lastAction: patient.last_action || "-",
        departmentStatus: patient.department_status || patient.department_flow_status || "-",
      });
    }
  }
  details.sort((a, b) => a.label.localeCompare(b.label));
  return details;
}

function runtimeStageClass(stage) {
  if (stage === "triage") return "hud__runtime-stage--triage";
  if (stage === "queue") return "hud__runtime-stage--queue";
  if (stage === "consult1" || stage === "consult2") return "hud__runtime-stage--consult";
  if (stage === "testing") return "hud__runtime-stage--testing";
  if (stage === "payment") return "hud__runtime-stage--payment";
  if (stage === "pharmacy") return "hud__runtime-stage--pharmacy";
  if (stage === "completed") return "hud__runtime-stage--completed";
  return "hud__runtime-stage--unknown";
}

function createRuntimeStatsBlock(title, lines = []) {
  const block = document.createElement("div");
  block.className = "hud__runtime-stats-block";
  const titleEl = document.createElement("div");
  titleEl.className = "hud__runtime-stats-title";
  titleEl.textContent = title;
  block.appendChild(titleEl);
  for (const line of lines) {
    const lineEl = document.createElement("div");
    lineEl.className = "hud__runtime-stats-line";
    lineEl.textContent = line;
    block.appendChild(lineEl);
  }
  return block;
}

function updateRuntimeHudStatus() {
  if (!hudRuntimeStatus) return;
  const snapshot = integrationState.hospitalRuntime;
  const payload = getRuntimeStartPayloadFromHud();
  const tuning = `Config: Mode=${payload.mode} | Spawn=${payload.spawn_interval_seconds}s | Step=${payload.step_interval_seconds}s | Max=${payload.max_active_patients} | LLM=${payload.llm_probability ?? "-"}`;
  if (!snapshot) {
    hudRuntimeStatus.textContent = integrationState.runtimeControlBusy
      ? `Runtime request in progress... | ${tuning}`
      : `Runtime status unknown. ${tuning}`;
    return;
  }
  const runningText = snapshot.running ? "running" : "stopped";
  hudRuntimeStatus.textContent = `Runtime ${runningText} | mode ${snapshot.mode || "unknown"} | active ${snapshot.active_count ?? 0} | spawned ${snapshot.total_spawned ?? 0} | blocked ${snapshot.blocked_count ?? 0} | llm_probability=${snapshot.llm_probability ?? "-"} | ${tuning}`;
}

function getRuntimeStartPayloadFromHud() {
  const mode = hudRuntimeMode?.value || "intelligent_agent";
  const spawnInterval = Number(hudRuntimeSpawn?.value || 4);
  const stepInterval = Number(hudRuntimeStep?.value || 2);
  const maxActivePatients = Number(hudRuntimeMax?.value || 20);
  const llmProbabilityRaw = hudRuntimeLlmProbability?.value ?? "";
  const llmProbabilityNumber = Number(llmProbabilityRaw);
  return {
    mode,
    spawn_interval_seconds: Number.isFinite(spawnInterval) ? Math.max(0, spawnInterval) : 4,
    step_interval_seconds: Number.isFinite(stepInterval) ? Math.max(0.1, stepInterval) : 2,
    max_active_patients: Number.isFinite(maxActivePatients) ? Math.max(1, Math.round(maxActivePatients)) : 20,
    llm_probability: llmProbabilityRaw === "" || !Number.isFinite(llmProbabilityNumber)
      ? null
      : Math.max(0, Math.min(1, llmProbabilityNumber)),
  };
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

function drawRegistrationRoomScene() {
  const template = microScene.indoor.template;
  if (!template) return;
  ctx.fillStyle = "#b68952";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const roomScreen = worldRectToScreenRect(template.room.x, template.room.y, template.room.w, template.room.h, 1);
  drawRoomBorder(roomScreen, "#e6d4b0");
  drawRoomTiles(roomScreen, "#e6d4b0", "#dcc79d", template.room.x, template.room.y);

  const wallTop = 8;
  ctx.fillStyle = palette.wallTop;
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y - wallTop, roomScreen.w + wallTop * 2, wallTop);
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y + roomScreen.h, roomScreen.w + wallTop * 2, wallTop);
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y, wallTop, roomScreen.h);
  ctx.fillRect(roomScreen.x + roomScreen.w, roomScreen.y, wallTop, roomScreen.h);

  for (const furniture of template.furniture || []) {
    drawProp({
      floor: 1,
      x: furniture.x / TILE,
      y: furniture.y / TILE,
      w: furniture.w / TILE,
      h: furniture.h / TILE,
      type: furniture.type,
    });
  }

  const glowPoint = project(template.interactPoint.x, template.interactPoint.y, 0, 1);
  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.2;
  ctx.save();
  ctx.strokeStyle = `rgba(255, 236, 170, ${Math.min(1, pulse + 0.2)})`;
  ctx.fillStyle = `rgba(255, 192, 96, ${0.2 + pulse * 0.15})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(glowPoint.x, glowPoint.y, 20 + pulse * 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "rgba(62, 41, 22, 0.92)";
  ctx.fillRect(glowPoint.x - 120, glowPoint.y - 48, 240, 26);
  ctx.strokeStyle = "rgba(255, 231, 176, 0.92)";
  ctx.lineWidth = 2;
  ctx.strokeRect(glowPoint.x - 120, glowPoint.y - 48, 240, 26);
  ctx.fillStyle = "#fff7e5";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(template.actionLabel || "Press E to interact, Q to return", glowPoint.x, glowPoint.y - 30);
  ctx.restore();

  const exitPoint = project(template.exitPoint.x, template.exitPoint.y, 0, 1);
  ctx.save();
  ctx.strokeStyle = "rgba(155, 237, 199, 0.92)";
  ctx.fillStyle = "rgba(91, 187, 136, 0.22)";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.roundRect(exitPoint.x - 34, exitPoint.y - 22, 68, 44, 10);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#eafff2";
  ctx.font = "700 12px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText("EXIT", exitPoint.x, exitPoint.y + 4);
  ctx.restore();
}

function drawAnnexRoomScene() {
  ctx.fillStyle = "#8aa66a";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const room = microScene.annex.room;
  const roomScreen = worldRectToScreenRect(room.x, room.y, room.w, room.h, 1);
  drawRoomBorder(roomScreen, "#d4c097");
  drawRoomTiles(roomScreen, "#d4c097", "#cab287", room.x, room.y);

  const wallTop = 8;
  ctx.fillStyle = palette.wallTop;
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y - wallTop, roomScreen.w + wallTop * 2, wallTop);
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y + roomScreen.h, roomScreen.w + wallTop * 2, wallTop);
  ctx.fillRect(roomScreen.x - wallTop, roomScreen.y, wallTop, roomScreen.h);
  ctx.fillRect(roomScreen.x + roomScreen.w, roomScreen.y, wallTop, roomScreen.h);

  const subRooms = [
    { x: room.x + TILE * 2, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
    { x: room.x + TILE * 10, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
    { x: room.x + TILE * 18, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
    { x: room.x + TILE * 6, y: room.y + TILE * 9, w: TILE * 8, h: TILE * 5 },
    { x: room.x + TILE * 16, y: room.y + TILE * 10, w: TILE * 8, h: TILE * 4 },
  ];

  for (const subRoom of subRooms) {
    const rect = worldRectToScreenRect(subRoom.x, subRoom.y, subRoom.w, subRoom.h, 1);
    drawRect(rect, "#e1d2ad", "#9c7e55", 2);
  }

  for (const npc of microScene.annex.npcList) {
    drawCharacterBody(npc.x, npc.y, 1, {
      legColor: "#5f5449",
      bodyColor: npc.color,
      accentColor: "#f0ead7",
      skinColor: "#f1d1bb",
      hairColor: "#6a4a2f",
      shadowColor: "rgba(0, 0, 0, 0.22)",
    }, "down");
    const top = project(npc.x, npc.y, 0, 1);
    ctx.save();
    ctx.fillStyle = "rgba(67, 45, 28, 0.86)";
    ctx.fillRect(top.x - 36, top.y - 54, 72, 18);
    ctx.strokeStyle = "rgba(255, 230, 179, 0.82)";
    ctx.strokeRect(top.x - 36, top.y - 54, 72, 18);
    ctx.fillStyle = "#fff7e5";
    ctx.font = "600 10px 'Trebuchet MS'";
    ctx.textAlign = "center";
    ctx.fillText(npc.name, top.x, top.y - 41);
    ctx.restore();
  }

  const exitPoint = project(microScene.annex.exitPoint.x, microScene.annex.exitPoint.y, 0, 1);
  ctx.save();
  ctx.strokeStyle = "rgba(155, 237, 199, 0.92)";
  ctx.fillStyle = "rgba(91, 187, 136, 0.22)";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.roundRect(exitPoint.x - 34, exitPoint.y - 22, 68, 44, 10);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#eafff2";
  ctx.font = "700 12px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText("EXIT", exitPoint.x, exitPoint.y + 4);
  ctx.restore();
}

function drawAnnexGateStructure() {
  if (microScene.mode !== "campus") return;

  const gateWidth = TILE * 5.1;
  const postWidth = TILE * 0.72;
  const beamHeight = TILE * 0.84;
  const openingHeight = TILE * 2.1;
  const postHeight = beamHeight + openingHeight + TILE * 0.18;
  const gateLeft = microScene.gate.x - gateWidth * 0.5;
  const openingTop = microScene.gate.y - openingHeight * 0.5;
  const gateTop = openingTop - beamHeight;
  const bannerX = gateLeft + postWidth + TILE * 0.18;
  const bannerWidth = gateWidth - postWidth * 2 - TILE * 0.36;

  const approachRect = worldRectToScreenRect(
    gateLeft + gateWidth - 150,
    openingTop + TILE * 0.06,
    TILE * 4.6,
    openingHeight - TILE * 0.12,
    microScene.gate.floor
  );
  drawRect(approachRect, "#b99163", "#7d5737", 2);
  ctx.fillStyle = "rgba(224, 205, 160, 0.55)";
  for (let offset = 8; offset < approachRect.w - 8; offset += 14) {
    ctx.fillRect(approachRect.x + offset, approachRect.y + 5, 4, Math.max(8, approachRect.h - 10));
  }

  const leftPost = worldRectToScreenRect(
    gateLeft,
    gateTop,
    postWidth,
    postHeight,
    microScene.gate.floor
  );
  const rightPost = worldRectToScreenRect(
    gateLeft + gateWidth - postWidth,
    gateTop,
    postWidth,
    postHeight,
    microScene.gate.floor
  );
  const beam = worldRectToScreenRect(
    gateLeft,
    gateTop,
    gateWidth,
    beamHeight,
    microScene.gate.floor
  );
  const banner = worldRectToScreenRect(
    bannerX,
    gateTop + TILE * 0.35,
    bannerWidth,
    TILE * 0.8,
    microScene.gate.floor
  );

  drawRect(leftPost, "#b97e4f", "#6b4327", 2);
  drawRect(rightPost, "#b97e4f", "#6b4327", 2);
  drawRect(beam, "#d7b07b", "#785335", 2);
  drawRect(banner, "#5b8e47", "#274420", 2);

  ctx.fillStyle = "#efdcae";
  ctx.fillRect(leftPost.x + 5, leftPost.y + 6, Math.max(6, leftPost.w - 10), Math.max(8, leftPost.h - 14));
  ctx.fillRect(rightPost.x + 5, rightPost.y + 6, Math.max(6, rightPost.w - 10), Math.max(8, rightPost.h - 14));

  const pulse = 0.55 + Math.sin(performance.now() * 0.01) * 0.2;
  ctx.save();
  ctx.strokeStyle = `rgba(255, 228, 158, ${Math.min(1, 0.8 + pulse * 0.25)})`;
  ctx.lineWidth = 5;
  ctx.strokeRect(banner.x - 4, banner.y - 4, banner.w + 8, banner.h + 8);
  ctx.restore();

  ctx.save();
  ctx.fillStyle = "#f7f1da";
  ctx.font = "700 12px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText("MAIN GATE", banner.x + banner.w / 2, banner.y + banner.h / 2 + 4);
  ctx.restore();

  const beacon = project(microScene.gate.x, microScene.gate.y, 0, microScene.gate.floor);
  ctx.save();
  ctx.strokeStyle = `rgba(255, 243, 188, ${Math.min(1, 0.88 + pulse * 0.1)})`;
  ctx.fillStyle = `rgba(255, 176, 79, ${0.22 + pulse * 0.2})`;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(beacon.x, beacon.y, 18 + pulse * 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
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
  let collisions = [...staticCollisions.filter((item) => item.floor === floor), ...doorCollidersForFloor(floor)];
  if (microScene.mode === "indoor_room" && microScene.indoor.template) {
    const room = microScene.indoor.template.room;
    const wall = 10;
    const blockers = (microScene.indoor.template.furniture || []).map((item) => ({
      floor,
      x: item.x,
      y: item.y,
      w: item.w,
      h: item.h,
    }));
    collisions = [
      { floor, x: room.x - wall, y: room.y - wall, w: room.w + wall * 2, h: wall },
      { floor, x: room.x - wall, y: room.y + room.h, w: room.w + wall * 2, h: wall },
      { floor, x: room.x - wall, y: room.y, w: wall, h: room.h },
      { floor, x: room.x + room.w, y: room.y, w: wall, h: room.h },
      ...blockers,
    ];
  } else if (microScene.mode === "annex_room") {
    const room = microScene.annex.room;
    const wall = 10;
    const blockers = [
      { floor, x: room.x - wall, y: room.y - wall, w: room.w + wall * 2, h: wall },
      { floor, x: room.x - wall, y: room.y + room.h, w: room.w + wall * 2, h: wall },
      { floor, x: room.x - wall, y: room.y, w: wall, h: room.h },
      { floor, x: room.x + room.w, y: room.y, w: wall, h: room.h },
      { floor, x: room.x + TILE * 2, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
      { floor, x: room.x + TILE * 10, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
      { floor, x: room.x + TILE * 18, y: room.y + TILE * 2, w: TILE * 7, h: TILE * 5 },
      { floor, x: room.x + TILE * 6, y: room.y + TILE * 9, w: TILE * 8, h: TILE * 5 },
      { floor, x: room.x + TILE * 16, y: room.y + TILE * 10, w: TILE * 8, h: TILE * 4 },
    ];
    collisions = blockers;
  }
  return !collisions.some((wall) => {
    const closestX = Math.max(wall.x, Math.min(foot.x, wall.x + wall.w));
    const closestY = Math.max(wall.y, Math.min(foot.y, wall.y + wall.h));
    const distanceSq = (foot.x - closestX) ** 2 + (foot.y - closestY) ** 2;
    return distanceSq < foot.r * foot.r;
  });
}

function distanceToDoorFromPoint(door, point) {
  return Math.hypot(point.x - door.pivot.x, point.y - door.pivot.y);
}

function distanceToDoor(door) {
  return distanceToDoorFromPoint(door, player);
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
  const sensorPoints = [
    { x: player.x, y: player.y, floor: player.floor },
    ...(fixedNpcRuntime?.getNpcs?.() || []).map((npc) => ({ x: npc.x, y: npc.y, floor: npc.floor })),
    ...(npcRuntime?.getNpcs?.() || []).map((npc) => ({ x: npc.x, y: npc.y, floor: npc.floor })),
  ];
  for (const door of currentFloorDoors()) {
    const nearestSensorDistance = sensorPoints
      .filter((point) => point.floor === door.floor)
      .reduce((best, point) => Math.min(best, distanceToDoorFromPoint(door, point)), Infinity);
    if (nearestSensorDistance <= DOOR_SENSOR_DISTANCE) {
      door.open = true;
      continue;
    }
    if (nearestSensorDistance >= DOOR_CLOSE_DISTANCE && !rectsIntersect(playerRect(), door.collider)) door.open = false;
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
  const fillB = room.kind === "hall" ? "#ead6b0" : palette.roomFloorAccent;
  drawRoomBorder(roomRect, fillA);
  drawRoomTiles(roomRect, fillA, fillB, rect.x, rect.y);

  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 2;
  ctx.strokeRect(roomRect.x + 6, roomRect.y + 6, roomRect.w - 12, roomRect.h - 12);
  ctx.restore();

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
    ctx.fillStyle = palette.wallHighlight;
    ctx.fillRect(rect.x + 3, rect.y + 2, Math.max(6, rect.w - 6), 3);
  } else {
    ctx.fillRect(rect.x + Math.max(2, rect.w - 6), rect.y, 4, rect.h);
    ctx.fillStyle = palette.wallHighlight;
    ctx.fillRect(rect.x + 2, rect.y + 3, 3, Math.max(6, rect.h - 6));
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
  if (opening.w >= opening.h) {
    const leftPanelWidth = Math.max(4, Math.round(panelRect.w * 0.46));
    const rightPanelWidth = Math.max(4, Math.round(panelRect.w * 0.46));
    const openGap = door.open ? Math.round(panelRect.w * 0.28) : 0;
    const leftPanel = { x: panelRect.x, y: panelRect.y, w: leftPanelWidth, h: panelRect.h };
    const rightPanel = { x: panelRect.x + panelRect.w - rightPanelWidth, y: panelRect.y, w: rightPanelWidth, h: panelRect.h };
    if (door.open) {
      leftPanel.x -= Math.round(openGap * 0.5);
      rightPanel.x += Math.round(openGap * 0.5);
    }
    drawRect(leftPanel, palette.doorPanel, palette.doorRail, 1);
    drawRect(rightPanel, palette.doorPanel, palette.doorRail, 1);
    ctx.fillStyle = palette.doorGlass;
    ctx.fillRect(leftPanel.x + 3, leftPanel.y + 3, Math.max(3, leftPanel.w - 6), Math.max(4, leftPanel.h - 6));
    ctx.fillRect(rightPanel.x + 3, rightPanel.y + 3, Math.max(3, rightPanel.w - 6), Math.max(4, rightPanel.h - 6));
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.fillRect(leftPanel.x + 4, leftPanel.y + 4, Math.max(2, leftPanel.w - 12), 2);
    ctx.fillRect(rightPanel.x + 4, rightPanel.y + 4, Math.max(2, rightPanel.w - 12), 2);
  } else {
    const topPanelHeight = Math.max(4, Math.round(panelRect.h * 0.46));
    const bottomPanelHeight = Math.max(4, Math.round(panelRect.h * 0.46));
    const openGap = door.open ? Math.round(panelRect.h * 0.28) : 0;
    const topPanel = { x: panelRect.x, y: panelRect.y, w: panelRect.w, h: topPanelHeight };
    const bottomPanel = { x: panelRect.x, y: panelRect.y + panelRect.h - bottomPanelHeight, w: panelRect.w, h: bottomPanelHeight };
    if (door.open) {
      topPanel.y -= Math.round(openGap * 0.5);
      bottomPanel.y += Math.round(openGap * 0.5);
    }
    drawRect(topPanel, palette.doorPanel, palette.doorRail, 1);
    drawRect(bottomPanel, palette.doorPanel, palette.doorRail, 1);
    ctx.fillStyle = palette.doorGlass;
    ctx.fillRect(topPanel.x + 3, topPanel.y + 3, Math.max(4, topPanel.w - 6), Math.max(3, topPanel.h - 6));
    ctx.fillRect(bottomPanel.x + 3, bottomPanel.y + 3, Math.max(4, bottomPanel.w - 6), Math.max(3, bottomPanel.h - 6));
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.fillRect(topPanel.x + 4, topPanel.y + 4, Math.max(2, topPanel.w - 8), 2);
    ctx.fillRect(bottomPanel.x + 4, bottomPanel.y + 4, Math.max(2, bottomPanel.w - 8), 2);
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
  const hairStyle = colors.hairStyle || "default";

  ctx.fillStyle = shadowColor;
  ctx.beginPath();
  ctx.ellipse(px, py + 14, 11, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = legColor;
  ctx.fillRect(px - 6, py + 9, 4, 10);
  ctx.fillRect(px + 2, py + 9, 4, 10);
  ctx.fillRect(px - 8, py + 18, 6, 3);
  ctx.fillRect(px + 2, py + 18, 6, 3);

  ctx.fillStyle = bodyColor;
  ctx.fillRect(px - 9, py - 6, 18, 18);
  ctx.fillStyle = skinColor;
  ctx.fillRect(px - 3, py - 10, 6, 6);
  ctx.fillStyle = accentColor;
  ctx.fillRect(px - 7, py - 2, 14, 4);
  ctx.fillRect(px - 2, py + 2, 4, 10);
  ctx.fillStyle = "#f7f3ea";
  ctx.fillRect(px - 2, py - 2, 4, 5);
  ctx.fillStyle = accentColor;
  ctx.fillRect(px - 10, py + 2, 3, 8);
  ctx.fillRect(px + 7, py + 2, 3, 8);

  if (facing === "left") {
    ctx.fillStyle = accentColor;
    ctx.fillRect(px - 12, py, 3, 8);
  } else if (facing === "right") {
    ctx.fillStyle = accentColor;
    ctx.fillRect(px + 9, py, 3, 8);
  }

  ctx.fillStyle = skinColor;
  ctx.fillRect(px - 9, py - 24, 18, 16);
  if (hairStyle === "baogaitou") {
    ctx.fillStyle = colors.hatColor || accentColor;
    ctx.fillRect(px - 12, py - 29, 24, 5);
    ctx.fillRect(px - 10, py - 24, 20, 4);
    ctx.fillRect(px - 11, py - 20, 22, 5);
    ctx.fillRect(px - 10, py - 16, 5, 4);
    ctx.fillRect(px + 5, py - 16, 5, 4);
  } else if (hairStyle === "bald") {
    // Intentionally no hair layers for the player.
  } else {
    ctx.fillStyle = hairColor;
    ctx.fillRect(px - 10, py - 25, 20, 6);
    ctx.fillRect(px - 10, py - 19, 4, 7);
    ctx.fillRect(px + 6, py - 19, 4, 7);
  }
  if (hairStyle === "long_side_bangs") {
    ctx.fillRect(px - 12, py - 24, 24, 3);
    ctx.fillRect(px - 12, py - 18, 3, 8);
    ctx.fillRect(px + 9, py - 18, 3, 8);
    ctx.fillRect(px - 8, py - 12, 16, 3);
  }
  ctx.fillStyle = colors.hatColor || accentColor;
  if (hairStyle !== "baogaitou") {
    ctx.fillRect(px - 11, py - 27, 22, 3);
    ctx.fillRect(px - 8, py - 30, 16, 4);
  }
  if (facing !== "up") {
    const eyeY = py - 18;
    ctx.fillStyle = "#2b2018";
    if (facing === "left") {
      ctx.fillRect(px - 6, eyeY, 2, 2);
    } else if (facing === "right") {
      ctx.fillRect(px + 4, eyeY, 2, 2);
    } else {
      ctx.fillRect(px - 6, eyeY, 2, 2);
      ctx.fillRect(px + 4, eyeY, 2, 2);
      ctx.fillStyle = "#8f5b3e";
      ctx.fillRect(px - 1, py - 12, 2, 2);
    }
  }
  if (facing === "left") {
    if (hairStyle === "baogaitou") {
      ctx.fillStyle = colors.hatColor || accentColor;
      ctx.fillRect(px - 14, py - 27, 8, 16);
      ctx.fillRect(px - 10, py - 29, 18, 5);
      ctx.fillRect(px - 8, py - 22, 11, 5);
      ctx.fillRect(px + 4, py - 20, 6, 10);
      ctx.fillRect(px + 1, py - 14, 5, 4);
    } else if (hairStyle === "bald") {
      // No side hair.
    } else if (hairStyle === "long_side_bangs") {
      ctx.fillStyle = hairColor;
      ctx.fillRect(px - 14, py - 24, 7, 13);
      ctx.fillRect(px - 10, py - 26, 8, 5);
      ctx.fillRect(px + 1, py - 25, 7, 4);
      ctx.fillRect(px + 6, py - 18, 4, 8);
    } else {
      ctx.fillStyle = hairColor;
      ctx.fillRect(px - 12, py - 23, 6, 11);
      ctx.fillRect(px - 7, py - 24, 5, 4);
      ctx.fillRect(px + 2, py - 24, 6, 3);
    }
  } else if (facing === "right") {
    if (hairStyle === "baogaitou") {
      ctx.fillStyle = colors.hatColor || accentColor;
      ctx.fillRect(px + 6, py - 27, 8, 16);
      ctx.fillRect(px - 8, py - 29, 18, 5);
      ctx.fillRect(px - 3, py - 22, 11, 5);
      ctx.fillRect(px - 10, py - 20, 6, 10);
      ctx.fillRect(px - 6, py - 14, 5, 4);
    } else if (hairStyle === "bald") {
      // No side hair.
    } else if (hairStyle === "long_side_bangs") {
      ctx.fillStyle = hairColor;
      ctx.fillRect(px + 7, py - 24, 7, 13);
      ctx.fillRect(px + 2, py - 26, 8, 5);
      ctx.fillRect(px - 8, py - 25, 7, 4);
      ctx.fillRect(px - 10, py - 18, 4, 8);
    } else {
      ctx.fillStyle = hairColor;
      ctx.fillRect(px + 6, py - 23, 6, 11);
      ctx.fillRect(px + 2, py - 24, 5, 4);
      ctx.fillRect(px - 8, py - 24, 6, 3);
    }
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
  drawCharacterBody(player.x, player.y, player.floor, {
    hairColor: palette.playerHair,
    skinColor: palette.playerHead,
    hairStyle: "default",
  }, player.facing);
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
    doctor_entry: "Doctor Entry",
    pharmacy_pickup: "Pharmacy",
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

  if (microScene.mode === "campus") {
    ctx.fillStyle = "#6fcf97";
    ctx.fillRect(left + (microScene.gate.x - 10) * scale, top + (microScene.gate.y - 10) * scale, 20 * scale, 20 * scale);
    ctx.strokeStyle = "#fff0b9";
    ctx.lineWidth = 2;
    ctx.strokeRect(left + (microScene.gate.x - 12) * scale, top + (microScene.gate.y - 12) * scale, 24 * scale, 24 * scale);
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
  if (microScene.mode !== "campus") return;
  if (!canInteractWithRegistrationDesk()) return;
  const point = project(registrationInteractPoint.x, registrationInteractPoint.y, 0, registrationInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visitState = selfPatient?.visit_state || "";

  let label = "Press E to fill registration profile";
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
  } else if (isInitialConsultationState(visitState) || isSecondConsultationState(visitState) || lifecycle === "in_consultation") {
    label = hasStartedDoctorConversation(selfPatient, visit)
      ? "Press E to continue doctor consultation"
      : "Press E to start doctor consultation";
  } else if (visitState === "waiting_consultation" && lifecycle === "called") {
    label = "Press E to enter consultation";
  } else if (visitState === "registered" || lifecycle === "queued") {
    label = "Waiting for queue call (10s)";
  } else if (visitState === "triaged") {
    label = "Complete registration first";
  } else if (visitState === "in_icu_rescue") {
    label = "High risk route: proceed to ICU rescue area (placeholder)";
  } else if (visitState === "in_emergency") {
    label = "High risk route: proceed to emergency area (placeholder)";
  } else if (visitState === "waiting_test") {
    label = "Test ordered. Go to Lab for test payment";
  } else if (visitState === "waiting_test_payment") {
    label = "Complete test payment at Lab";
  } else if (visitState === "test_payment_completed") {
    label = "Payment done. Start exam at Lab";
  } else if (visitState === "in_test") {
    label = "Exam in progress. Complete exam at Lab";
  } else if (visitState === "waiting_return_consultation") {
    label = "Exam done. Generate result at Lab";
  } else if (visitState === "results_ready") {
    label = "Result ready. Queue second consultation";
  } else if (visitState === "waiting_second_consultation") {
    label = "Return to Doctor for second consultation";
  } else if (visitState === "diagnosis_finalized") {
    label = "Diagnosis finalized. Proceed to payment";
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

function drawPharmacyPickupHint() {
  if (!canInteractWithPharmacyPickup()) return;
  const point = project(pharmacyPickupInteractPoint.x, pharmacyPickupInteractPoint.y, 0, pharmacyPickupInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";

  let label = "Pharmacy standby";
  if (backendState.submitting) {
    label = "Synchronizing pharmacy...";
  } else if (visitState === "waiting_pharmacy") {
    label = "Press E to pick up medication";
  } else if (visitState === "completed") {
    label = "Medication already picked up";
  } else if (visitState === "waiting_payment" || visitState === "diagnosis_finalized") {
    label = "Complete payment first";
  } else {
    label = "Pharmacy opens after checkout";
  }

  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 246;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = backendState.submitting
    ? `rgba(255, 198, 124, ${Math.min(0.95, pulse + 0.2)})`
    : `rgba(138, 238, 182, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);

  ctx.fillStyle = backendState.submitting ? "#ffe4bd" : "#effff5";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText(label, point.x, point.y + 5);
}

function drawLabHint() {
  if (!canInteractWithLab()) return;
  const point = project(labInteractPoint.x, labInteractPoint.y, 0, labInteractPoint.floor);
  const selfPatient = getCurrentSelfPatient();
  const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";

  let label = "Lab station is standby";
  if (backendState.submitting) {
    label = "Synchronizing lab stage...";
  } else if (visitState === "waiting_test") {
    label = "Press E to request test payment";
  } else if (visitState === "waiting_test_payment") {
    label = "Press E to pay for test";
  } else if (visitState === "test_payment_completed") {
    label = "Press E to start exam";
  } else if (visitState === "in_test") {
    label = "Press E to finish exam";
  } else if (visitState === "waiting_return_consultation") {
    label = "Press E to publish test result";
  } else if (visitState === "results_ready") {
    label = "Press E to queue second consultation";
  } else if (visitState === "waiting_second_consultation") {
    label = "Press R to review test report";
  } else {
    label = "Finish doctor consultation first";
  }

  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 286;
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

function drawAnnexGateHint() {
  if (microScene.mode !== "campus") return;
  if (!canInteractWithAnnexGate()) return;
  const point = project(microScene.gate.x, microScene.gate.y, 0, microScene.gate.floor);
  const pulse = 0.55 + Math.sin(performance.now() * 0.012) * 0.18;
  const boxWidth = 232;
  const boxHeight = 28;
  const boxLeft = point.x - boxWidth / 2;
  const boxTop = point.y - boxHeight / 2;

  ctx.fillStyle = "rgba(67, 45, 28, 0.94)";
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = `rgba(128, 240, 193, ${Math.min(0.95, pulse + 0.22)})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.fillStyle = "#effff5";
  ctx.font = "600 13px 'Trebuchet MS'";
  ctx.textAlign = "center";
  ctx.fillText("Press E to enter Annex Yard", point.x, point.y + 5);
}

function getRegistrationRoomCenterPoint() {
  const template = microScene.indoor.template || indoorRoomTemplates.registration;
  return {
    floor: 1,
    roomKind: template.label,
    x: template.room.x + template.room.w * 0.5,
    y: template.room.y + template.room.h * 0.5,
    w: template.room.w,
    h: template.room.h,
  };
}

function getRegistrationRoomExitPoint() {
  const template = microScene.indoor.template || indoorRoomTemplates.registration;
  return {
    x: template.exitPoint.x,
    y: template.exitPoint.y,
    floor: 1,
  };
}

function getAnnexRoomCenterPoint() {
  return {
    floor: 1,
    roomKind: "annex_room",
    x: microScene.annex.room.x + microScene.annex.room.w * 0.5,
    y: microScene.annex.room.y + microScene.annex.room.h * 0.5,
    w: microScene.annex.room.w,
    h: microScene.annex.room.h,
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

  if (microScene.mode === "annex_room") {
    return { label: "Press E at EXIT to Return", point: microScene.annex.exitPoint, room: getAnnexRoomCenterPoint() };
  }

  if (!hasTriageRecord && !triageConversationState.sessionId) {
    return { label: "Go to Triage", point: triageInteractPoint, room: getRoomCenterPoint("triage") };
  }

  if (!patient || !visitState || visitState === "arrived" || visitState === "triaging" || visitState === "waiting_followup") {
    if (microScene.mode === "indoor_room") {
      return { label: "Press Q to Return to Campus", point: getRegistrationRoomExitPoint(), room: getRegistrationRoomCenterPoint() };
    }
    return { label: "Go to Triage", point: triageInteractPoint, room: getRoomCenterPoint("triage") };
  }
  if (visitState === "triaged") {
    if (microScene.mode === "indoor_room" && microScene.indoor.activeRoomKind === "registration") {
      return { label: "Register at Desk", point: microScene.indoor.template?.interactPoint, room: getRegistrationRoomCenterPoint() };
    }
    return { label: "Go to Registration Room", point: registrationInteractPoint, room: getRoomCenterPoint("registration") };
  }
  if (microScene.mode === "indoor_room" && (visitState === "registered" || visitState === "waiting_consultation" || visitState === "in_consultation")) {
    return { label: "Press Q to Return to Hall", point: getRegistrationRoomExitPoint(), room: getRegistrationRoomCenterPoint() };
  }
  if (visitState === "registered" || lifecycle === "queued") {
    const room = getRoomCenterPoint("hall");
    return { label: "Wait in Hall", point: room, room };
  }
  if (visitState === "waiting_consultation" || lifecycle === "called" || visitState === "in_consultation" || lifecycle === "in_consultation") {
    return { label: "Go to Doctor", point: doctorEntryInteractPoint, room: getRoomCenterPoint("doctor_entry") };
  }
  if (visitState === "in_icu_rescue") {
    const room = getRoomCenterPoint("icu");
    return { label: "Go to ICU Rescue (Placeholder)", point: room, room };
  }
  if (visitState === "in_emergency") {
    const room = getRoomCenterPoint("triage");
    return { label: "Go to Emergency (Placeholder)", point: room, room };
  }
  if (visitState === "waiting_test") {
    const room = getRoomCenterPoint("lab");
    return { label: "Go to Lab", point: room, room };
  }
  if (visitState === "waiting_test_payment" || visitState === "test_payment_completed" || visitState === "in_test" || visitState === "waiting_return_consultation" || visitState === "results_ready") {
    const room = getRoomCenterPoint("lab");
    return { label: "Handle Test Stage at Lab", point: room, room };
  }
  if (visitState === "waiting_second_consultation" || visitState === "in_second_consultation") {
    return { label: "Go to Doctor (Second Consultation)", point: doctorEntryInteractPoint, room: getRoomCenterPoint("doctor_entry") };
  }
  if (visitState === "diagnosis_finalized") {
    return { label: "Proceed to Payment", point: registrationInteractPoint, room: getRoomCenterPoint("registration") };
  }
  if (visitState === "waiting_payment") {
    return { label: "Return to Registration", point: registrationInteractPoint, room: getRoomCenterPoint("registration") };
  }
  if (visitState === "waiting_pharmacy") {
    return { label: "Go to South Pharmacy", point: pharmacyPickupInteractPoint, room: getRoomCenterPoint("pharmacy_pickup") };
  }
  if (visitState === "completed") {
    return { label: "Visit Completed", point: getRoomCenterPoint("pharmacy_pickup") || getRoomCenterPoint("hall"), room: getRoomCenterPoint("pharmacy_pickup") || getRoomCenterPoint("hall") };
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
  const inRegistrationRoom = microScene.mode === "indoor_room";

  if (target.room && !inRegistrationRoom) {
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

  const panelWidth = 560;
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
  ctx.fillText(backendState.connected ? "API online" : `API offline (${backendState.lastError})`, panelX + panelWidth - 190, panelY + 22);

  ctx.font = "13px 'Segoe UI'";
  for (let index = 0; index < taskBoard.tasks.length; index += 1) {
    const task = taskBoard.tasks[index];
    const y = panelY + 42 + index * rowHeight;
    const marker = task.done ? "[x]" : "[ ]";
    ctx.fillStyle = task.done ? "#83ffc9" : "#f2ebff";
    ctx.fillText(truncateText(`${marker} ${task.text}`, 74), panelX + 12, y);
  }
}

function drawRuntimeDebugPanel() {
  if (!overlayState.debugOpen) return;

  const panelWidth = 460;
  const panelHeight = 176;
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
  ctx.fillText(`Polls: ok ${runtimeDebug.pollSuccessCount} / fail ${runtimeDebug.pollFailureCount}`, panelX + 210, panelY + 46);
  ctx.fillText(`Last poll: ${runtimeDebug.lastPollResult}`, panelX + 210, panelY + 66);
  ctx.fillText(
    `Record entries: ${integrationState.medicalRecordTimeline?.summary?.entry_count ?? 0}`,
    panelX + 210,
    panelY + 86
  );
  ctx.fillText(
    `Dept runtime: ${integrationState.departmentRuntime?.active_count ?? 0} active`,
    panelX + 12,
    panelY + 108
  );
  ctx.fillText(
    `Hospital runtime: ${integrationState.hospitalRuntime?.active_count ?? 0} active`,
    panelX + 12,
    panelY + 128
  );
  ctx.fillText(
    `ICU pool: ${integrationState.icuPatients?.patients?.length ?? 0} | OpenEMR: ${integrationState.openEmrHealth ? "known" : "n/a"}`,
    panelX + 12,
    panelY + 148
  );
  ctx.fillStyle = runtimeDebug.lastError ? "#ffb0b0" : "#9fd9b7";
  ctx.fillText(`Last error: ${truncateText(runtimeDebug.lastError || "none", 58)}`, panelX + 12, panelY + 168);
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

function drawOtherPatientsPanel() {
  if (!overlayState.debugOpen || !overlayState.patientsOpen) return;
  const patients = latestSceneSnapshot?.other_patients || [];
  const panelWidth = 430;
  const rowHeight = 18;
  const visibleRows = Math.min(8, Math.max(1, patients.length || 1));
  const panelHeight = 38 + visibleRows * rowHeight;
  const panelX = canvas.width - panelWidth - 18;
  const panelY = canvas.height - panelHeight - 18;

  ctx.fillStyle = "rgba(16, 11, 24, 0.86)";
  ctx.fillRect(panelX, panelY, panelWidth, panelHeight);
  ctx.strokeStyle = "rgba(174, 129, 255, 0.72)";
  ctx.strokeRect(panelX, panelY, panelWidth, panelHeight);

  ctx.textAlign = "left";
  ctx.font = "13px 'Segoe UI'";
  ctx.fillStyle = "#d8b8ff";
  ctx.fillText("Other Patients", panelX + 12, panelY + 22);

  if (!patients.length) {
    ctx.font = "12px 'Segoe UI'";
    ctx.fillStyle = "#f2ebff";
    ctx.fillText("No other active patients in current scene snapshot.", panelX + 12, panelY + 46);
    return;
  }

  ctx.font = "12px 'Segoe UI'";
  patients.slice(0, 8).forEach((patient, index) => {
    const y = panelY + 44 + index * rowHeight;
    ctx.fillStyle = patient.priority === "H" ? "#ffb0b0" : patient.priority === "L" ? "#b9ffd2" : "#f2ebff";
    ctx.fillText(
      truncateText(`${patient.name} | ${patient.visit_state || patient.lifecycle_state || "-"} | ${patient.location || "-"} | ${patient.active_agent_type || "none"}`, 60),
      panelX + 12,
      y
    );
  });
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
  if (!floorStateLabel) return;
  floorStateLabel.textContent = microScene.mode === "indoor_room"
    ? `Current Zone: ${microScene.indoor.template?.label || "Interior"}`
    : microScene.mode === "annex_room"
      ? "Current Zone: Annex Yard"
      : "Current Zone: Main Campus";
}

function openRestartConfirmModal() {
  if (!restartConfirmUi.modal || restartConfirmUi.open) return;
  restartConfirmUi.open = true;
  restartConfirmUi.modal.classList.remove("hidden");
  restartConfirmUi.modal.setAttribute("aria-hidden", "false");
  keys.clear();
}

function closeRestartConfirmModal() {
  if (!restartConfirmUi.modal) return;
  restartConfirmUi.open = false;
  restartConfirmUi.modal.classList.add("hidden");
  restartConfirmUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function syncHudToggleButton(button, active, ariaName = "pressed") {
  if (!button) return;
  button.classList.toggle("is-active", active);
  button.setAttribute(`aria-${ariaName}`, String(active));
}

function syncOverlayUi() {
  if (hudHelpPanel) hudHelpPanel.classList.toggle("hidden", !overlayState.helpOpen);
  if (hudRuntimePanel) hudRuntimePanel.classList.toggle("hidden", !overlayState.runtimeOpen);
  if (hudRuntimeStatsPanel) hudRuntimeStatsPanel.classList.toggle("hidden", !overlayState.runtimeStatsOpen);
  syncHudToggleButton(hudHelpToggle, overlayState.helpOpen, "expanded");
  syncHudToggleButton(hudRuntimeToggle, overlayState.runtimeOpen);
  syncHudToggleButton(hudTasksToggle, overlayState.tasksOpen);
  syncHudToggleButton(hudLabelsToggle, overlayState.labelsOpen);
  syncHudToggleButton(hudDebugToggle, overlayState.debugOpen);
  syncHudToggleButton(hudQueueToggle, overlayState.queueOpen);
  syncHudToggleButton(hudPatientsToggle, overlayState.patientsOpen);
  syncHudToggleButton(hudRuntimeStatsToggle, overlayState.runtimeStatsOpen);
  if (hudResumeBtn) {
    const hasLastSession = Boolean(localStorage.getItem(SESSION_STORAGE_KEYS.lastClientId));
    hudResumeBtn.disabled = !hasLastSession;
    hudResumeBtn.setAttribute("aria-disabled", String(!hasLastSession));
  }
}

function closeOverlayPanels() {
  const hadOpenPanel = overlayState.helpOpen || overlayState.runtimeOpen || overlayState.tasksOpen || overlayState.labelsOpen || overlayState.debugOpen;
  overlayState.helpOpen = false;
  overlayState.runtimeOpen = false;
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

  hudRuntimeToggle?.addEventListener("click", () => {
    overlayState.runtimeOpen = !overlayState.runtimeOpen;
    syncOverlayUi();
    if (overlayState.runtimeOpen) {
      refreshIntegrationRuntime(true);
    }
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

  hudQueueToggle?.addEventListener("click", () => {
    overlayState.queueOpen = !overlayState.queueOpen;
    syncOverlayUi();
  });

  hudPatientsToggle?.addEventListener("click", () => {
    overlayState.patientsOpen = !overlayState.patientsOpen;
    syncOverlayUi();
  });

  hudRuntimeStatsToggle?.addEventListener("click", () => {
    overlayState.runtimeStatsOpen = !overlayState.runtimeStatsOpen;
    syncOverlayUi();
    if (overlayState.runtimeStatsOpen) {
      updateRuntimeStatsPanel();
    }
  });

  hudRestartBtn?.addEventListener("click", () => {
    openRestartConfirmModal();
  });

  hudResumeBtn?.addEventListener("click", () => {
    const lastClientId = localStorage.getItem(SESSION_STORAGE_KEYS.lastClientId);
    if (!lastClientId) {
      pushStatusHint("No saved previous run is available.");
      syncOverlayUi();
      return;
    }
    localStorage.setItem(SESSION_STORAGE_KEYS.activeClientId, lastClientId);
    window.location.search = "?resume=1";
  });

  hudNpcRouteButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.routeTarget;
      if (!target) return;
      const routed = npcRuntime.routeGuideNpcsTo?.(target) || 0;
      if (routed > 0) {
        pushStatusHint(`${routed} route NPCs are moving to ${ROOM_KIND_LABELS[target] || target}.`);
      } else {
        pushStatusHint(`No route NPC could be sent to ${ROOM_KIND_LABELS[target] || target}.`);
      }
    });
  });

  hudRuntimeStopBtn?.addEventListener("click", () => {
    controlHospitalRuntime("stop");
  });
  hudRuntimeResetBtn?.addEventListener("click", () => {
    controlHospitalRuntime("reset");
  });

  [hudRuntimeMode, hudRuntimeSpawn, hudRuntimeStep, hudRuntimeMax, hudRuntimeLlmProbability].forEach((element) => {
    element?.addEventListener("input", () => {
      updateRuntimeHudStatus();
    });
    element?.addEventListener("change", () => {
      updateRuntimeHudStatus();
    });
  });

  updateRuntimeHudStatus();
  updateRuntimeStatsPanel();
  syncOverlayUi();
}

function bindRuntimePanelDrag() {
  if (!hudRuntimePanel || !hudRuntimeDragHandle) return;

  hudRuntimeDragHandle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    runtimePanelState.dragging = true;
    runtimePanelState.pointerId = event.pointerId;
    runtimePanelState.startClientX = event.clientX;
    runtimePanelState.startClientY = event.clientY;
    const rect = hudRuntimePanel.getBoundingClientRect();
    hudRuntimePanel.style.position = "fixed";
    hudRuntimePanel.style.left = `${rect.left}px`;
    hudRuntimePanel.style.top = `${rect.top}px`;
    hudRuntimePanel.style.right = "auto";
    hudRuntimePanel.style.bottom = "auto";
    runtimePanelState.startLeft = rect.left;
    runtimePanelState.startTop = rect.top;
    hudRuntimeDragHandle.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });

  hudRuntimeDragHandle.addEventListener("pointermove", (event) => {
    if (!runtimePanelState.dragging || runtimePanelState.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - runtimePanelState.startClientX;
    const deltaY = event.clientY - runtimePanelState.startClientY;
    const nextLeft = Math.max(8, Math.min(window.innerWidth - 220, runtimePanelState.startLeft + deltaX));
    const nextTop = Math.max(8, Math.min(window.innerHeight - 120, runtimePanelState.startTop + deltaY));
    hudRuntimePanel.style.left = `${nextLeft}px`;
    hudRuntimePanel.style.top = `${nextTop}px`;
  });

  function endDrag(event) {
    if (runtimePanelState.pointerId !== null && event.pointerId !== undefined && runtimePanelState.pointerId !== event.pointerId) return;
    runtimePanelState.dragging = false;
    runtimePanelState.pointerId = null;
  }

  hudRuntimeDragHandle.addEventListener("pointerup", endDrag);
  hudRuntimeDragHandle.addEventListener("pointercancel", endDrag);
}

function bindRuntimeStatsPanelDrag() {
  if (!hudRuntimeStatsPanel || !hudRuntimeStatsDragHandle) return;

  hudRuntimeStatsDragHandle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    runtimeStatsPanelState.dragging = true;
    runtimeStatsPanelState.pointerId = event.pointerId;
    runtimeStatsPanelState.startClientX = event.clientX;
    runtimeStatsPanelState.startClientY = event.clientY;
    const rect = hudRuntimeStatsPanel.getBoundingClientRect();
    hudRuntimeStatsPanel.style.position = "fixed";
    hudRuntimeStatsPanel.style.left = `${rect.left}px`;
    hudRuntimeStatsPanel.style.top = `${rect.top}px`;
    hudRuntimeStatsPanel.style.right = "auto";
    hudRuntimeStatsPanel.style.bottom = "auto";
    runtimeStatsPanelState.startLeft = rect.left;
    runtimeStatsPanelState.startTop = rect.top;
    hudRuntimeStatsDragHandle.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });

  hudRuntimeStatsDragHandle.addEventListener("pointermove", (event) => {
    if (!runtimeStatsPanelState.dragging || runtimeStatsPanelState.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - runtimeStatsPanelState.startClientX;
    const deltaY = event.clientY - runtimeStatsPanelState.startClientY;
    const nextLeft = Math.max(8, Math.min(window.innerWidth - 220, runtimeStatsPanelState.startLeft + deltaX));
    const nextTop = Math.max(8, Math.min(window.innerHeight - 120, runtimeStatsPanelState.startTop + deltaY));
    hudRuntimeStatsPanel.style.left = `${nextLeft}px`;
    hudRuntimeStatsPanel.style.top = `${nextTop}px`;
  });

  function endDrag(event) {
    if (runtimeStatsPanelState.pointerId !== null && event.pointerId !== undefined && runtimeStatsPanelState.pointerId !== event.pointerId) return;
    runtimeStatsPanelState.dragging = false;
    runtimeStatsPanelState.pointerId = null;
  }

  hudRuntimeStatsDragHandle.addEventListener("pointerup", endDrag);
  hudRuntimeStatsDragHandle.addEventListener("pointercancel", endDrag);
}

function update(delta, nowMs) {
  pollBackendStatuses(false);
  updateDoors();
  fixedNpcRuntime?.update?.(delta);

  if (npcDialogueUi.open || triageUi.open || registrationUi.open || triageDialogueUi.open || doctorDialogueUi.open || fixedNpcRuntime?.isDialogueOpen?.()) {
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
  if (microScene.mode === "campus") {
    updateZoneTriggers(nowMs);
  }
}

function render() {
  if (microScene.mode === "annex_room") {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawAnnexRoomScene();
    drawPlayer();
    drawObjectiveHighlight();
    drawTaskBoard();
    drawRuntimeDebugPanel();
    drawZoneStatusPanel();
    drawOtherPatientsPanel();
    runtimeDebug.lastRenderAt = performance.now();
    return;
  }

  if (microScene.mode === "indoor_room") {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawRegistrationRoomScene();
    drawPlayer();
    drawObjectiveHighlight();
    drawTaskBoard();
    drawRuntimeDebugPanel();
    drawZoneStatusPanel();
    drawOtherPatientsPanel();
    runtimeDebug.lastRenderAt = performance.now();
    return;
  }

  const activeDoor = nearestDoor();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawGroundBackdrop();
  drawFloorLayer(activeFloor, activeDoor, false);
  drawAnnexGateStructure();
  drawLabels();
  drawObjectiveHighlight();
  drawHudHint(activeDoor);
  drawRegistrationHint();
  drawAnnexGateHint();
  drawTriageHint();
  drawLabHint();
  drawDoctorEntryHint();
  drawPharmacyPickupHint();
  drawFixedNpcHint();
  drawTaskBoard();
  drawMinimap();
  drawRuntimeDebugPanel();
  drawZoneStatusPanel();
  drawOtherPatientsPanel();
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

const testReportUi = {
  open: false,
  modal: document.getElementById("testReportModal"),
  status: document.getElementById("testReportStatus"),
  categoryBadge: document.getElementById("testReportCategoryBadge"),
  timeBadge: document.getElementById("testReportTimeBadge"),
  items: document.getElementById("testReportItems"),
  body: document.getElementById("testReportBody"),
  closeBtn: document.getElementById("testReportCloseBtn"),
};

const pharmacyPickupUi = {
  open: false,
  reviewed: false,
  modal: document.getElementById("pharmacyPickupModal"),
  status: document.getElementById("pharmacyPickupStatus"),
  visitBadge: document.getElementById("pharmacyPickupVisitBadge"),
  stepBadge: document.getElementById("pharmacyPickupStepBadge"),
  items: document.getElementById("pharmacyPickupItems"),
  body: document.getElementById("pharmacyPickupBody"),
  closeBtn: document.getElementById("pharmacyPickupCloseBtn"),
  confirmBtn: document.getElementById("pharmacyPickupConfirmBtn"),
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
  const forceNew = params.get("fresh") === "1" || params.get("newSession") === "1";
  const resumeSaved = params.get("resume") === "1";
  const activeKey = SESSION_STORAGE_KEYS.activeClientId;
  const lastKey = SESSION_STORAGE_KEYS.lastClientId;
  let clientId = localStorage.getItem(activeKey);

  if (resumeSaved) {
    const savedClientId = localStorage.getItem(lastKey);
    if (savedClientId) {
      localStorage.setItem(activeKey, savedClientId);
      return savedClientId;
    }
  }

  if (forceNew) {
    const previous = localStorage.getItem(activeKey);
    if (previous) {
      localStorage.setItem(lastKey, previous);
    }
    clientId = crypto.randomUUID();
    localStorage.setItem(activeKey, clientId);
    return clientId;
  }

  if (!clientId) {
    clientId = crypto.randomUUID();
    localStorage.setItem(activeKey, clientId);
  }
  return clientId;
}

function openRegistrationModal() {
  if (!registrationUi.modal || registrationUi.open) return;
  const currentName = getCurrentSelfPatient()?.name || "You (Player)";
  if (registrationUi.fields.name && !registrationUi.fields.name.value.trim()) {
    registrationUi.fields.name.value = currentName;
  }
  if (registrationUi.fields.idNumber && !registrationUi.fields.idNumber.value.trim()) {
    registrationUi.fields.idNumber.value = "TEMP-REG-0001";
  }
  registrationUi.open = true;
  registrationUi.modal.classList.remove("hidden");
  registrationUi.modal.setAttribute("aria-hidden", "false");
  keys.clear();
  if (registrationUi.fields.name) {
    registrationUi.fields.name.focus();
    registrationUi.fields.name.selectionStart = registrationUi.fields.name.value.length;
    registrationUi.fields.name.selectionEnd = registrationUi.fields.name.value.length;
  }
}

function closeRegistrationModal() {
  if (!registrationUi.modal) return;
  registrationUi.open = false;
  registrationUi.modal.classList.add("hidden");
  registrationUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function buildRegistrationPayloadFromForm() {
  const defaultName = getCurrentSelfPatient()?.name || "You (Player)";
  const safeAge = Number(registrationUi.fields.age?.value || 30);
  return {
    name: (registrationUi.fields.name?.value || defaultName).trim() || defaultName,
    sex: (registrationUi.fields.sex?.value || "unknown").trim() || "unknown",
    age: Number.isFinite(safeAge) ? Math.max(0, Math.min(120, Math.round(safeAge))) : 30,
    id_number: (registrationUi.fields.idNumber?.value || "TEMP-REG-0001").trim() || "TEMP-REG-0001",
  };
}

const clientId = getClientId();
const normalizedClientHex = String(clientId || "").replace(/[^0-9a-fA-F]/g, "").toLowerCase();
const patientId = `P-${(normalizedClientHex || crypto.randomUUID().replace(/-/g, "")).slice(0, 8)}`;

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

function getCurrentSceneSnapshot() {
  return latestSceneSnapshot || agentStore.lastSceneSnapshot || null;
}

function getCurrentConsultationAgentType(snapshot = getCurrentSceneSnapshot(), patient = getCurrentSelfPatient(), visit = getCurrentVisit()) {
  return snapshot?.ui_flags?.consultation_agent_type
    || visit?.active_agent_type
    || patient?.active_agent_type
    || doctorConversationState.activeAgentType
    || "internal_medicine";
}

function buildDoctorDialoguePayloadFromSceneSnapshot(snapshot = getCurrentSceneSnapshot()) {
  const activeDialogue = snapshot?.active_dialogue || null;
  const selfPatient = snapshot?.self_patient || getCurrentSelfPatient();
  const activeVisit = snapshot?.active_visit || getCurrentVisit();
  const visitState = activeVisit?.state || selfPatient?.visit_state || null;
  if (visitState === "in_icu_rescue") {
    const currentPatient = getCurrentSelfPatient() || selfPatient;
    return buildIcuDialoguePayloadFromPatient(currentPatient, doctorConversationState.sessionId || currentPatient?.session_id || null);
  }
  const isSecondRoundState = ["in_second_consultation", "diagnosis_finalized", "waiting_payment"].includes(visitState);
  const round2SessionId = activeVisit?.data?.internal_medicine_round2_session_id || null;
  const consultationAgentType = getCurrentConsultationAgentType(snapshot, selfPatient, activeVisit);
  const sessionRefKey = consultationAgentType === "surgery"
    ? (isSecondRoundState ? "surgery_round2_session_id" : "surgery_session_id")
    : (isSecondRoundState ? "internal_medicine_round2_session_id" : "internal_medicine_session_id");
  if (!activeDialogue || activeDialogue.agent_type !== consultationAgentType) {
    return {
      patient: selfPatient,
      dialogue: isSecondRoundState && !round2SessionId ? {} : (selfPatient?.dialogue || {}),
      visit_id: activeVisit?.id || selfPatient?.visit_id || null,
      visit_state: visitState,
      session_id: activeVisit?.data?.[sessionRefKey] || doctorConversationState.sessionId || null,
      agent_type: consultationAgentType,
    };
  }
  return {
    patient: selfPatient,
    dialogue: {
      status: activeDialogue.status,
      assistant_message: activeDialogue.assistant_message,
      missing_fields: activeDialogue.missing_fields || [],
      turns: activeDialogue.turns || [],
      question_focus: activeDialogue.question_focus || null,
      message_type: activeDialogue.message_type || "followup",
    },
    visit_id: activeVisit?.id || selfPatient?.visit_id || null,
    visit_state: activeVisit?.state || selfPatient?.visit_state || null,
    session_id: activeDialogue.session_id || doctorConversationState.sessionId || null,
    agent_type: consultationAgentType,
  };
}

function applySceneSnapshot(snapshot) {
  const previousPatient = agentStore.lastPatient;
  latestSceneSnapshot = snapshot || null;
  agentStore.syncSceneSnapshot(snapshot);

  const selfPatient = snapshot?.self_patient || null;
  const visit = snapshot?.active_visit || null;
  const visitState = visit?.state || selfPatient?.visit_state || "";

  if (
    visitState === "in_icu_rescue"
    && previousPatient
    && previousPatient.id === selfPatient?.id
    && previousPatient.dialogue
  ) {
    agentStore.lastPatient = {
      ...selfPatient,
      dialogue: previousPatient.dialogue,
      dialogue_source_agent: "icu",
      active_agent_type: "icu",
      session_id: doctorConversationState.sessionId || previousPatient.session_id || selfPatient?.session_id || null,
    };
  }

  visitSessionState.visit = visit;
  queueRuntime.syncFromApi(snapshot?.queues || [], triageConversationState.patientId);
  npcRuntime?.syncHospitalPatients?.(buildHospitalScenePatients());
  taskBoardPresenter.syncSceneSnapshot(snapshot);

  if (!selfPatient) {
    return null;
  }

  const encounterId = selfPatient.encounter_id || selfPatient.visit_id || visit?.id || null;
  if (encounterId) {
    triageConversationState.visitId = encounterId;
    doctorConversationState.visitId = encounterId;
    stateDebugPanel.setEncounterId(encounterId);
  }

  if (snapshot?.active_dialogue?.agent_type === "triage" && snapshot.active_dialogue.session_id) {
    triageConversationState.sessionId = snapshot.active_dialogue.session_id;
  }

  const visitStateForSession = visit?.state || selfPatient?.visit_state || "";
  const isSecondRoundState = ["in_second_consultation", "diagnosis_finalized", "waiting_payment"].includes(visitStateForSession);
  let restoredDoctorSessionId = null;
  if (visitStateForSession === "in_icu_rescue") {
    restoredDoctorSessionId = doctorConversationState.sessionId || selfPatient?.session_id || null;
    doctorConversationState.activeAgentType = "icu";
  } else if (isSecondRoundState) {
    restoredDoctorSessionId = visit?.data?.internal_medicine_round2_session_id || null;
  } else {
    restoredDoctorSessionId = visit?.data?.internal_medicine_session_id || null;
    doctorConversationState.activeAgentType = "internal_medicine";
  }
  if (snapshot?.active_dialogue?.agent_type === "internal_medicine" && snapshot.active_dialogue.session_id) {
    restoredDoctorSessionId = snapshot.active_dialogue.session_id;
  }
  if (!restoredDoctorSessionId && !isSecondRoundState) {
    const patientSessionId = String(selfPatient.session_id || "");
    restoredDoctorSessionId = patientSessionId.startsWith("im-session-") ? patientSessionId : null;
  }
  if (restoredDoctorSessionId) {
    doctorConversationState.sessionId = restoredDoctorSessionId;
  } else if (isSecondRoundState) {
    doctorConversationState.sessionId = null;
  }

  if (triageDialogueUi.open) {
    syncTriageDialogue(selfPatient);
  }
  if (doctorDialogueUi.open) {
    syncDoctorDialogue(buildDoctorDialoguePayloadFromSceneSnapshot(snapshot));
  }

  taskBoardPresenter.syncIntegratedView({
    snapshot,
    medicalRecordTimeline: integrationState.medicalRecordTimeline,
    hospitalRuntime: integrationState.hospitalRuntime,
    departmentRuntime: integrationState.departmentRuntime,
    departments: integrationState.departments,
    openEmrHealth: integrationState.openEmrHealth,
    icuPatients: integrationState.icuPatients,
  });

  return { selfPatient, visit, queueTicket: snapshot?.active_queue_ticket || null };
}

function isInitialConsultationState(visitState) {
  return visitState === "in_consultation";
}

function isSecondConsultationState(visitState) {
  return visitState === "in_second_consultation";
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
  const visitState = visit?.state || patient?.visit_state || "";
  const isSecondRound = ["in_second_consultation", "diagnosis_finalized", "waiting_payment"].includes(visitState);
  const consultationAgentType = getCurrentConsultationAgentType(getCurrentSceneSnapshot(), patient, visit);
  if (isSecondRound) {
    return consultationAgentType === "surgery"
      ? (visit?.data?.surgery_round2_session_id || null)
      : (visit?.data?.internal_medicine_round2_session_id || null);
  }
  const visitSessionId = consultationAgentType === "surgery"
    ? (visit?.data?.surgery_session_id || null)
    : (visit?.data?.internal_medicine_session_id || null);
  if (visitSessionId) return visitSessionId;

  if (visit?.active_agent_type === consultationAgentType && doctorConversationState.sessionId) {
    return doctorConversationState.sessionId;
  }

  if (doctorConversationState.sessionId) return doctorConversationState.sessionId;
  if (consultationAgentType === "surgery") {
    return patientSessionId.startsWith("surgery-session-") ? patientSessionId : null;
  }
  return patientSessionId.startsWith("im-session-") ? patientSessionId : null;
}

function hasStartedDoctorConversation(patient = getCurrentSelfPatient(), visit = getCurrentVisit()) {
  return Boolean(getDoctorSessionIdFromContext(patient, visit));
}

function buildDoctorDialogueMessages(dialogue, fallbackText = "Doctor consultation started.", assistantLabel = "Doctor Agent / Internal Medicine") {
  const turns = dialogue?.turns || [];
  if (Array.isArray(turns) && turns.length > 0) {
    return turns.map((turn) => {
      const isFinal = turn.role === "assistant" && turn?.metadata?.message_type === "final";
      return {
        role: turn.role === "assistant" ? "assistant" : "user",
        label: turn.role === "assistant" ? (isFinal ? "Final Plan" : assistantLabel) : "Patient",
        body: turn.content || "",
        type: turn.role === "assistant" ? (isFinal ? "final" : "followup") : "user",
      };
    });
  }

  return [
    {
      role: "assistant",
      label: assistantLabel,
      body: dialogue?.assistant_message || fallbackText,
      type: dialogue?.message_type || "followup",
    },
  ];
}

function buildIcuDialoguePayloadFromPatient(patient, sessionId = null) {
  return {
    agent_type: "icu",
    patient,
    dialogue: patient?.dialogue || {},
    visit_id: patient?.visit_id || getCurrentVisit()?.id || null,
    visit_state: patient?.visit_state || getCurrentVisit()?.state || null,
    session_id: sessionId || patient?.session_id || null,
  };
}

function setDoctorDialogueBadges(visitState) {
  if (doctorDialogueUi.agentBadge) {
    doctorDialogueUi.agentBadge.textContent = visitState === "in_icu_rescue" ? "ICU Doctor Agent" : "Doctor Agent";
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

function closeTestReportModal() {
  if (!testReportUi.modal) return;
  testReportUi.open = false;
  testReportUi.modal.classList.add("hidden");
  testReportUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function closePharmacyPickupModal() {
  if (!pharmacyPickupUi.modal) return;
  pharmacyPickupUi.open = false;
  pharmacyPickupUi.reviewed = false;
  pharmacyPickupUi.modal.classList.add("hidden");
  pharmacyPickupUi.modal.setAttribute("aria-hidden", "true");
  keys.clear();
}

function openTestReportModal(report) {
  if (!testReportUi.modal || !report) return;
  testReportUi.open = true;
  testReportUi.modal.classList.remove("hidden");
  testReportUi.modal.setAttribute("aria-hidden", "false");
  keys.clear();
  if (testReportUi.categoryBadge) {
    testReportUi.categoryBadge.textContent = `Category: ${report.category_label || report.category_code || "-"}`;
  }
  if (testReportUi.timeBadge) {
    testReportUi.timeBadge.textContent = `Generated: ${report.generated_at || "-"}`;
  }
  if (testReportUi.items) {
    const items = Array.isArray(report.test_items) ? report.test_items : [];
    testReportUi.items.textContent = `Items: ${items.length ? items.join(", ") : "-"}`;
  }
  if (testReportUi.body) {
    testReportUi.body.textContent = report.report_text || JSON.stringify(report.report_summary || {}, null, 2);
  }
}

function openPharmacyPickupModal() {
  if (!pharmacyPickupUi.modal) return;
  const visit = getCurrentVisit();
  const items = getLatestMedicationList();
  pharmacyPickupUi.open = true;
  pharmacyPickupUi.reviewed = true;
  pharmacyPickupUi.modal.classList.remove("hidden");
  pharmacyPickupUi.modal.setAttribute("aria-hidden", "false");
  if (pharmacyPickupUi.status) {
    pharmacyPickupUi.status.textContent = items.length
      ? "Review the medication list and then confirm pickup."
      : "No explicit prescription list was found. Confirm pickup if the pharmacist has reviewed the order.";
  }
  if (pharmacyPickupUi.visitBadge) {
    pharmacyPickupUi.visitBadge.textContent = `Visit: ${visit?.state || "-"}`;
  }
  if (pharmacyPickupUi.stepBadge) {
    pharmacyPickupUi.stepBadge.textContent = "Step: review";
  }
  if (pharmacyPickupUi.items) {
    pharmacyPickupUi.items.textContent = `Items: ${items.length ? items.join(", ") : "-"}`;
  }
  if (pharmacyPickupUi.body) {
    pharmacyPickupUi.body.textContent = items.length
      ? items.map((item, index) => `${index + 1}. ${item}`).join("\n")
      : "No medication list available from the latest record entry.";
  }
  if (pharmacyPickupUi.confirmBtn) {
    pharmacyPickupUi.confirmBtn.disabled = false;
  }
  keys.clear();
}

function syncDoctorDialogue(data) {
  if (!doctorDialogueUi.open) return;
  const payload = data || {};
  const patient = payload.patient || getCurrentSelfPatient();
  const dialogue = payload.dialogue || patient?.dialogue || {};
  const visitState = payload.visit_state || getCurrentVisit()?.state || patient?.visit_state || null;
  const isIcuFlow = visitState === "in_icu_rescue" || payload.agent_type === "icu";
  const assistantLabel = isIcuFlow ? "ICU Doctor Agent" : "Doctor Agent / Internal Medicine";
  const renderKey = `${payload.session_id || doctorConversationState.sessionId || ""}|${visitState || ""}|${dialogue.status || ""}|${dialogue.assistant_message || ""}|${Array.isArray(dialogue.turns) ? dialogue.turns.length : 0}`;
  if (doctorDialogueUi.lastRenderedAt === renderKey) return;
  doctorDialogueUi.lastRenderedAt = renderKey;

  if (doctorDialogueUi.status) {
    if (isIcuFlow) {
      doctorDialogueUi.status.textContent = dialogue.status === "completed"
        ? "ICU consultation completed."
        : "ICU consultation in progress.";
    } else if (visitState === "waiting_test") {
      doctorDialogueUi.status.textContent = "First consultation completed. Please continue diagnostic steps at Lab.";
    } else if (visitState === "waiting_test_payment" || visitState === "test_payment_completed" || visitState === "in_test" || visitState === "waiting_return_consultation" || visitState === "results_ready") {
      doctorDialogueUi.status.textContent = "Diagnostic stage in progress. Return after report is ready.";
    } else if (visitState === "waiting_second_consultation") {
      doctorDialogueUi.status.textContent = "Report is ready. Press E at doctor entry to start second consultation.";
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
    buildDoctorDialogueMessages(
      dialogue,
      isIcuFlow ? "The ICU doctor agent is ready for consultation." : "The doctor agent is ready for consultation.",
      assistantLabel
    )
  );
  renderDialogueEvidenceView(doctorDialogueUi.evidenceList, patient?.triage_evidence || []);

  const canChat = isIcuFlow || isInitialConsultationState(visitState) || isSecondConsultationState(visitState);
  const isClosed = !canChat || dialogue.status === "completed";
  if (doctorDialogueUi.sendBtn) doctorDialogueUi.sendBtn.disabled = isClosed || doctorConversationState.sending;
  if (doctorDialogueUi.input) doctorDialogueUi.input.disabled = isClosed;
}

async function openExistingDoctorDialogue() {
  const selfPatient = getCurrentSelfPatient();
  const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";
  if (visitState === "in_icu_rescue") {
    const icuSessionId = selfPatient?.session_id || null;
    if (icuSessionId) {
      try {
        const data = await backendClient.getIcuSession(icuSessionId);
        if (data?.patient) {
          agentStore.syncPatient(data.patient);
        }
        openDoctorDialogue(buildIcuDialoguePayloadFromPatient(data?.patient || selfPatient, data?.session_id || icuSessionId));
        return;
      } catch (_error) {
        // fall back to create session below
      }
    }
    doctorConversationState.activeAgentType = "icu";
    await submitCreateIcuSessionRequest();
    return;
  }

  doctorConversationState.activeAgentType = getCurrentConsultationAgentType();
  const sessionId = getDoctorSessionIdFromContext();
  if (!sessionId) {
    pushStatusHint("No active doctor consultation session was found.");
    return;
  }
  doctorConversationState.sessionId = sessionId;
  const scenePayload = buildDoctorDialoguePayloadFromSceneSnapshot();
  if (scenePayload?.session_id === sessionId) {
    openDoctorDialogue(scenePayload);
    return;
  }
  try {
    const data = doctorConversationState.activeAgentType === "surgery"
      ? await backendClient.getSurgerySession(sessionId)
      : await backendClient.getInternalMedicineSession(sessionId);
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
  let visitId = null;
  try {
    const encounterData = await backendClient.createEncounter({
      patient_id: triageConversationState.patientId,
      name: "You (Player)",
    });
    visitId = encounterData?.encounter?.encounter_id || encounterData?.encounter?.id || null;
  } catch (_encounterError) {
    const data = await backendClient.createVisit({
      patient_id: triageConversationState.patientId,
      name: "You (Player)",
    });
    visitId = data?.visit?.id || null;
  }
  if (visitId) {
    triageConversationState.visitId = visitId;
    doctorConversationState.visitId = visitId;
    stateDebugPanel.setEncounterId(visitId);
  }
  return triageConversationState.visitId;
}

async function triggerEncounterEvent(event, context = {}) {
  const encounterId = await ensureVisitContext();
  if (!encounterId) {
    throw new Error("encounter id is missing");
  }
  const data = await backendClient.triggerEncounterEvent(encounterId, {
    event,
    context,
  });
  if (data?.encounter) {
    visitSessionState.visit = {
      id: data.encounter.encounter_id || data.encounter.id,
      state: String(data.encounter.state || "").toLowerCase(),
      current_node: data.encounter.current_node || null,
      current_department: data.encounter.current_department || null,
      active_agent_type: data.encounter.active_agent_type || null,
      data: data.encounter.data || {},
    };
  }
  return data;
}

async function openLatestSimulatedReportModal() {
  const visit = getCurrentVisit();
  const visitId = visit?.id || triageConversationState.visitId;
  if (!visitId) {
    pushStatusHint("No visit session available for report review.");
    return;
  }
  const embeddedReport = visit?.data?.simulated_report;
  if (embeddedReport && typeof embeddedReport === "object") {
    openTestReportModal(embeddedReport);
    return;
  }
  try {
    const data = await backendClient.getSimulatedReport(visitId);
    if (data?.report) {
      openTestReportModal(data.report);
      return;
    }
  } catch (_error) {
    // fall through to hint
  }
  pushStatusHint("Simulated report is not ready yet.");
}

async function refreshMedicalRecordTimeline(force = false, snapshot = getCurrentSceneSnapshot()) {
  const visit = getCurrentVisit();
  const visitId = visit?.id || triageConversationState.visitId;
  if (!visitId) {
    integrationState.medicalRecordTimeline = null;
    integrationState.lastMedicalRecordVisitId = null;
    integrationState.lastMedicalRecordSummaryKey = "";
    return null;
  }
  const summary = snapshot?.medical_record_summary || null;
  const summaryKey = summary
    ? `${summary.record_id || ""}|${summary.entry_count || 0}|${summary.updated_at || ""}`
    : `none|${visitId}`;
  const isSameTimeline = integrationState.lastMedicalRecordVisitId === visitId
    && integrationState.lastMedicalRecordSummaryKey === summaryKey
    && integrationState.medicalRecordTimeline;
  if (!force && isSameTimeline) {
    return integrationState.medicalRecordTimeline;
  }
  try {
    const timeline = await backendClient.getMedicalRecordTimeline(visitId);
    integrationState.medicalRecordTimeline = timeline;
    integrationState.lastMedicalRecordVisitId = visitId;
    integrationState.lastMedicalRecordSummaryKey = summaryKey;
    return timeline;
  } catch (_error) {
    integrationState.medicalRecordTimeline = null;
    integrationState.lastMedicalRecordVisitId = visitId;
    integrationState.lastMedicalRecordSummaryKey = summaryKey;
    return null;
  }
}

function inferCheckoutDisposition() {
  const entries = integrationState.medicalRecordTimeline?.entries || [];
  const latestEntry = entries.length > 0 ? entries[entries.length - 1] : null;
  const prescriptions = latestEntry?.content?.prescriptions;
  if (Array.isArray(prescriptions) && prescriptions.length > 0) {
    return "choose_pharmacy";
  }
  return "choose_outpatient_treatment";
}

function getLatestMedicationList() {
  const entries = integrationState.medicalRecordTimeline?.entries || [];
  const latestEntry = entries.length > 0 ? entries[entries.length - 1] : null;
  const content = latestEntry?.content || {};
  const prescriptions = Array.isArray(content.prescriptions) ? content.prescriptions : [];
  if (prescriptions.length > 0) {
    return prescriptions.map((item) => String(item).trim()).filter(Boolean);
  }
  const actions = Array.isArray(content.medication_or_action) ? content.medication_or_action : [];
  return actions.map((item) => String(item).trim()).filter(Boolean);
}

function buildRuntimeStatsText() {
  const snapshot = integrationState.hospitalRuntime;
  if (!snapshot) return "No runtime stats yet.";

  const phaseCounts = {
    triage: 0,
    queue: 0,
    consult1: 0,
    testing: 0,
    consult2: 0,
    payment: 0,
    pharmacy: 0,
    unknown: 0,
  };

  for (const node of snapshot.nodes || []) {
    for (const patient of node.patients || []) {
      const visitState = String(patient.visit_state || "");
      if (["arrived", "triaging", "waiting_followup", "triaged"].includes(visitState)) phaseCounts.triage += 1;
      else if (["registered", "waiting_consultation"].includes(visitState)) phaseCounts.queue += 1;
      else if (visitState === "in_consultation") phaseCounts.consult1 += 1;
      else if (["waiting_test", "waiting_test_payment", "test_payment_completed", "in_test", "waiting_return_consultation", "results_ready"].includes(visitState)) phaseCounts.testing += 1;
      else if (visitState === "in_second_consultation") phaseCounts.consult2 += 1;
      else if (["diagnosis_finalized", "waiting_payment", "medical_payment_completed"].includes(visitState)) phaseCounts.payment += 1;
      else if (visitState === "waiting_pharmacy") phaseCounts.pharmacy += 1;
      else phaseCounts.unknown += 1;
    }
  }

  const roomCounts = {};
  for (const detail of buildRuntimePatientDetails(snapshot)) {
    roomCounts[detail.roomKind] = (roomCounts[detail.roomKind] || 0) + 1;
  }
  const patientDetails = buildRuntimePatientDetails(snapshot);

  const lines = [
    `running: ${snapshot.running}`,
    `mode: ${snapshot.mode}`,
    `historical total spawned: ${snapshot.total_spawned ?? 0}`,
    `current active total: ${snapshot.active_count ?? 0}`,
    `dispatch count: ${snapshot.dispatch_count ?? 0}`,
    `blocked count: ${snapshot.blocked_count ?? 0}`,
    `last spawn: ${snapshot.last_spawn_at || "-"}`,
    `last tick: ${snapshot.last_tick_at || "-"}`,
    "",
    "phase states:",
    `triage=${phaseCounts.triage} | queue=${phaseCounts.queue} | consult1=${phaseCounts.consult1}`,
    `testing=${phaseCounts.testing} | consult2=${phaseCounts.consult2} | payment=${phaseCounts.payment}`,
    `pharmacy=${phaseCounts.pharmacy} | completed=${phaseCounts.completed || 0} | unknown=${phaseCounts.unknown}`,
    "",
    "room occupancy:",
    Object.keys(roomCounts).length
      ? Object.entries(roomCounts).map(([roomKind, count]) => `${roomKind}=${count}`).join(" | ")
      : "none",
    "",
    "node states:",
  ];

  for (const node of snapshot.nodes || []) {
    const summary = node.summary || {};
    lines.push(
      `${node.node.name}: active=${summary.active_count ?? 0} waiting=${summary.waiting_count ?? 0} called=${summary.called_count ?? 0} consult=${summary.in_consultation_count ?? 0} test=${summary.in_test_count ?? 0} finished=${summary.finished_count ?? 0}`
    );
  }

  lines.push("", "department states:");
  for (const department of snapshot.departments || []) {
    const summary = department.summary || {};
    lines.push(
      `${department.department_name}: active=${summary.active_count ?? 0} pending_reg=${summary.pending_registration_count ?? 0} wait1=${summary.waiting_round1_count ?? 0} wait2=${summary.waiting_round2_count ?? 0} consult1=${summary.in_consultation_round1_count ?? 0} consult2=${summary.in_consultation_round2_count ?? 0} test=${summary.in_test_count ?? 0} finished=${summary.finished_count ?? 0}`
    );
  }

  lines.push("", "patient details:");
  if (!patientDetails.length) {
    lines.push("none");
  } else {
    for (const patient of patientDetails.slice(0, 24)) {
      lines.push(
        `${patient.label}: room=${patient.roomKind} | stage=${patient.stage} | visit=${patient.visitState || "-"} | node=${patient.currentNodeId || "-"} -> ${patient.targetNodeId || "-"} | last=${patient.lastAction}`
      );
    }
    if (patientDetails.length > 24) {
      lines.push(`... ${patientDetails.length - 24} more patients`);
    }
  }

  return lines.join("\n");
}

function updateRuntimeStatsPanel() {
  if (!hudRuntimeStatsContent) return;
  const snapshot = integrationState.hospitalRuntime;
  hudRuntimeStatsContent.innerHTML = "";
  if (!snapshot) {
    hudRuntimeStatsContent.textContent = "No runtime stats yet.";
    return;
  }

  const phaseCounts = {
    triage: 0,
    queue: 0,
    consult1: 0,
    testing: 0,
    consult2: 0,
    payment: 0,
    pharmacy: 0,
    completed: 0,
    unknown: 0,
  };
  for (const detail of buildRuntimePatientDetails(snapshot)) {
    phaseCounts[detail.stage] = (phaseCounts[detail.stage] || 0) + 1;
  }

  const roomCounts = {};
  const patientDetails = buildRuntimePatientDetails(snapshot);
  for (const detail of patientDetails) {
    roomCounts[detail.roomKind] = (roomCounts[detail.roomKind] || 0) + 1;
  }

  hudRuntimeStatsContent.appendChild(createRuntimeStatsBlock("Overview", [
    `running: ${snapshot.running}`,
    `mode: ${snapshot.mode}`,
    `historical total spawned: ${snapshot.total_spawned ?? 0}`,
    `current active total: ${snapshot.active_count ?? 0}`,
    `dispatch count: ${snapshot.dispatch_count ?? 0}`,
    `blocked count: ${snapshot.blocked_count ?? 0}`,
    `last spawn: ${snapshot.last_spawn_at || "-"}`,
    `last tick: ${snapshot.last_tick_at || "-"}`,
  ]));

  hudRuntimeStatsContent.appendChild(createRuntimeStatsBlock("Phase States", [
    `triage=${phaseCounts.triage} | queue=${phaseCounts.queue} | consult1=${phaseCounts.consult1}`,
    `testing=${phaseCounts.testing} | consult2=${phaseCounts.consult2} | payment=${phaseCounts.payment}`,
    `pharmacy=${phaseCounts.pharmacy} | completed=${phaseCounts.completed} | unknown=${phaseCounts.unknown}`,
  ]));

  hudRuntimeStatsContent.appendChild(createRuntimeStatsBlock("Room Occupancy", [
    Object.keys(roomCounts).length
      ? Object.entries(roomCounts).map(([roomKind, count]) => `${roomKind}=${count}`).join(" | ")
      : "none",
  ]));

  hudRuntimeStatsContent.appendChild(createRuntimeStatsBlock("Node States", (snapshot.nodes || []).map((node) => {
    const summary = node.summary || {};
    return `${node.node.name}: active=${summary.active_count ?? 0} waiting=${summary.waiting_count ?? 0} called=${summary.called_count ?? 0} consult=${summary.in_consultation_count ?? 0} test=${summary.in_test_count ?? 0} finished=${summary.finished_count ?? 0}`;
  })));

  hudRuntimeStatsContent.appendChild(createRuntimeStatsBlock("Department States", (snapshot.departments || []).map((department) => {
    const summary = department.summary || {};
    return `${department.department_name}: active=${summary.active_count ?? 0} pending_reg=${summary.pending_registration_count ?? 0} wait1=${summary.waiting_round1_count ?? 0} wait2=${summary.waiting_round2_count ?? 0} consult1=${summary.in_consultation_round1_count ?? 0} consult2=${summary.in_consultation_round2_count ?? 0} test=${summary.in_test_count ?? 0} finished=${summary.finished_count ?? 0}`;
  })));

  const patientBlock = document.createElement("div");
  patientBlock.className = "hud__runtime-stats-block";
  const patientTitle = document.createElement("div");
  patientTitle.className = "hud__runtime-stats-title";
  patientTitle.textContent = "Patient Details";
  patientBlock.appendChild(patientTitle);

  const patientList = document.createElement("div");
  patientList.className = "hud__runtime-patient-list";
  if (!patientDetails.length) {
    const empty = document.createElement("div");
    empty.className = "hud__runtime-stats-line";
    empty.textContent = "none";
    patientList.appendChild(empty);
  } else {
    for (const patient of patientDetails.slice(0, 24)) {
      const card = document.createElement("div");
      card.className = "hud__runtime-patient";

      const topLine = document.createElement("div");
      topLine.className = "hud__runtime-patient-topline";

      const name = document.createElement("span");
      name.className = "hud__runtime-patient-name";
      name.textContent = patient.label;
      topLine.appendChild(name);

      const badge = document.createElement("span");
      badge.className = `hud__runtime-stage ${runtimeStageClass(patient.stage)}`;
      badge.textContent = patient.stage;
      topLine.appendChild(badge);

      card.appendChild(topLine);

      const detail1 = document.createElement("div");
      detail1.className = "hud__runtime-patient-detail";
      detail1.textContent = `room=${patient.roomKind} | visit=${patient.visitState || "-"} | node=${patient.currentNodeId || "-"}`;
      card.appendChild(detail1);

      const detail2 = document.createElement("div");
      detail2.className = "hud__runtime-patient-detail";
      detail2.textContent = `target=${patient.targetNodeId || "-"} | last=${patient.lastAction} | dept=${patient.departmentStatus}`;
      card.appendChild(detail2);

      patientList.appendChild(card);
    }
    if (patientDetails.length > 24) {
      const more = document.createElement("div");
      more.className = "hud__runtime-stats-line";
      more.textContent = `... ${patientDetails.length - 24} more patients`;
      patientList.appendChild(more);
    }
  }
  patientBlock.appendChild(patientList);
  hudRuntimeStatsContent.appendChild(patientBlock);
}

async function refreshIntegrationRuntime(force = false) {
  const now = performance.now();
  if (!force && now - integrationState.lastRuntimeRefreshAt < 500) {
    return integrationState;
  }
  integrationState.lastRuntimeRefreshAt = now;

  const results = await Promise.allSettled([
    backendClient.getHospitalRuntimeSnapshot(),
    backendClient.getDepartmentRuntimeSnapshot(),
    backendClient.listDepartments(),
    backendClient.getOpenEmrHealth(),
    backendClient.listIcuPatients(),
  ]);

  if (results[0].status === "fulfilled") integrationState.hospitalRuntime = results[0].value;
  if (results[1].status === "fulfilled") integrationState.departmentRuntime = results[1].value;
  if (results[2].status === "fulfilled") integrationState.departments = results[2].value;
  if (results[3].status === "fulfilled") integrationState.openEmrHealth = results[3].value;
  if (results[4].status === "fulfilled") integrationState.icuPatients = results[4].value;
  updateRuntimeHudStatus();
  updateRuntimeStatsPanel();
  npcRuntime?.syncHospitalPatients?.(buildHospitalScenePatients());
  return integrationState;
}

async function controlHospitalRuntime(action) {
  if (integrationState.runtimeControlBusy) return;
  integrationState.runtimeControlBusy = true;
  updateRuntimeHudStatus();
  try {
    if (action === "stop") {
      integrationState.hospitalRuntime = await backendClient.stopHospitalRuntime();
    } else if (action === "reset") {
      integrationState.hospitalRuntime = await backendClient.resetHospitalRuntime();
    }
    pushStatusHint(`Hospital runtime ${action} request completed.`);
    await refreshIntegrationRuntime(true);
    taskBoardPresenter.syncIntegratedView({
      snapshot: getCurrentSceneSnapshot(),
      medicalRecordTimeline: integrationState.medicalRecordTimeline,
      hospitalRuntime: integrationState.hospitalRuntime,
      departmentRuntime: integrationState.departmentRuntime,
      departments: integrationState.departments,
      openEmrHealth: integrationState.openEmrHealth,
      icuPatients: integrationState.icuPatients,
    });
  } catch (error) {
    backendState.lastError = error?.message || `hospital runtime ${action} failed`;
    pushStatusHint(`Hospital runtime ${action} failed: ${backendState.lastError}`);
  } finally {
    integrationState.runtimeControlBusy = false;
    updateRuntimeHudStatus();
  }
}

async function performFullRestart() {
  if (integrationState.runtimeControlBusy || backendState.submitting) return;
  integrationState.runtimeControlBusy = true;
  backendState.submitting = true;
  updateRuntimeHudStatus();
  try {
    await backendClient.resetHospitalRuntime();
    integrationState.hospitalRuntime = await backendClient.startHospitalRuntime(getRuntimeStartPayloadFromHud());
    integrationState.medicalRecordTimeline = null;
    integrationState.lastMedicalRecordVisitId = null;
    integrationState.lastMedicalRecordSummaryKey = "";
    integrationState.departmentRuntime = null;
    integrationState.icuPatients = null;
    integrationState.openEmrHealth = null;
    integrationState.lastRuntimeRefreshAt = 0;
    latestSceneSnapshot = null;
    visitSessionState.visit = null;
    agentStore.lastPatient = null;
    agentStore.lastSceneSnapshot = null;
    triageConversationState.visitId = null;
    triageConversationState.sessionId = null;
    doctorConversationState.visitId = null;
    doctorConversationState.sessionId = null;
    localStorage.setItem(SESSION_STORAGE_KEYS.lastClientId, localStorage.getItem(SESSION_STORAGE_KEYS.activeClientId) || "");
    localStorage.setItem(SESSION_STORAGE_KEYS.activeClientId, crypto.randomUUID());
    pushStatusHint("Restarted hospital runtime and player session.");
    window.location.search = "?fresh=1";
  } catch (error) {
    backendState.lastError = error?.message || "restart failed";
    pushStatusHint(`Restart failed: ${backendState.lastError}`);
  } finally {
    integrationState.runtimeControlBusy = false;
    backendState.submitting = false;
    updateRuntimeHudStatus();
  }
}

async function submitRegistrationRequest(registrationPayload) {
  if (backendState.submitting || !canSubmitRegistrationFromCurrentContext()) return;
  backendState.submitting = true;
  try {
    const visitId = await ensureVisitContext();
    if (!visitId) {
      pushStatusHint("Unable to start registration: visit session is missing.");
      return;
    }
    const data = await backendClient.registerVisit(visitId, registrationPayload);
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

async function submitCompleteAuxiliaryTestRequest() {
  if (backendState.submitting || !canInteractWithLab()) return;
  const selfPatient = getCurrentSelfPatient();
  const visitId = getCurrentVisit()?.id || selfPatient?.visit_id || triageConversationState.visitId;
  if (!visitId) {
    pushStatusHint("Diagnostic stage unavailable: visit session is missing.");
    return;
  }

  const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";
  const eventByState = {
    waiting_test: "request_test_payment",
    waiting_test_payment: "pay_test",
    test_payment_completed: "start_exam",
    in_test: "finish_exam",
    waiting_return_consultation: "results_ready",
    results_ready: "queue_second_consultation",
  };
  const event = eventByState[visitState] || null;
  if (!event) {
    pushStatusHint("Lab interaction is unavailable in this state.");
    return;
  }

  backendState.submitting = true;
  try {
    await triggerEncounterEvent(event, { source: "scene.lab.e_key" });
    if (event === "results_ready") {
      try {
        const reportData = await backendClient.getSimulatedReport(visitId);
        if (reportData?.report) {
          openTestReportModal(reportData.report);
        }
      } catch (_reportError) {
        // Keep state transition successful even if report fetch is temporarily unavailable.
      }
    }
    pushStatusHint(`Lab stage updated via event: ${event}`);
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "complete diagnostic stage failed";
    pushStatusHint(`Diagnostic stage failed: ${backendState.lastError}`);
  } finally {
    backendState.submitting = false;
  }
}

async function submitReadyPaymentRequest() {
  if (backendState.submitting) return;
  const visitId = getCurrentVisit()?.id || triageConversationState.visitId;
  if (!visitId) {
    pushStatusHint("Payment step unavailable: visit session is missing.");
    return;
  }

  backendState.submitting = true;
  try {
    const visitState = getCurrentVisit()?.state || getCurrentSelfPatient()?.visit_state || "";
    if (visitState === "diagnosis_finalized") {
      await backendClient.readyPayment(visitId);
      pushStatusHint("Medical payment requested. Proceed to checkout.");
    } else if (visitState === "waiting_payment") {
      await triggerEncounterEvent("pay_medical", { source: "scene.registration.payment_e_key" });
      await triggerEncounterEvent("plan_disposition", { source: "scene.registration.payment_e_key" });
      const dispositionEvent = inferCheckoutDisposition();
      await triggerEncounterEvent(dispositionEvent, { source: "scene.registration.payment_e_key" });
      await triggerEncounterEvent("complete_visit", { source: "scene.registration.payment_e_key" });
      pushStatusHint(dispositionEvent === "choose_pharmacy" ? "Checkout completed. Prescription pickup recorded." : "Checkout completed.");
    } else {
      pushStatusHint("Payment is unavailable in the current visit state.");
      return;
    }
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "payment transition failed";
    pushStatusHint(`Payment transition failed: ${backendState.lastError}`);
  } finally {
    backendState.submitting = false;
  }
}

async function submitPharmacyPickupRequest() {
  if (backendState.submitting || !canInteractWithPharmacyPickup()) return;
  const visitState = getCurrentVisit()?.state || getCurrentSelfPatient()?.visit_state || "";
  if (visitState !== "waiting_pharmacy") {
    pushStatusHint("Pharmacy pickup is unavailable in the current visit state.");
    return;
  }

  if (!pharmacyPickupUi.reviewed) {
    openPharmacyPickupModal();
    return;
  }

  backendState.submitting = true;
  try {
    await triggerEncounterEvent("complete_visit", { source: "scene.pharmacy_pickup.e_key" });
    pushStatusHint("Medication dispensed. Visit completed.");
    closePharmacyPickupModal();
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "pharmacy pickup failed";
    pushStatusHint(`Pharmacy pickup failed: ${backendState.lastError}`);
  } finally {
    backendState.submitting = false;
  }
}

async function submitCreateIcuSessionRequest() {
  if (backendState.submitting || doctorConversationState.sending) return;
  const selfPatient = getCurrentSelfPatient();
  if (!selfPatient) {
    pushStatusHint("ICU consultation cannot start: patient context is missing.");
    return;
  }

  backendState.submitting = true;
  try {
    const data = await backendClient.createIcuSession({
      patient_id: selfPatient.id,
      name: selfPatient.name || "You (Player)",
      symptoms: selfPatient?.triage?.note || "High risk ICU referral",
      chief_complaint: selfPatient?.triage?.note || "High risk ICU referral",
      location: "ICU",
      floor: 1,
    });
    doctorConversationState.sessionId = data.session_id || doctorConversationState.sessionId;
    doctorConversationState.activeAgentType = "icu";
    if (data?.patient) {
      agentStore.syncPatient(data.patient);
    }
    openDoctorDialogue(buildIcuDialoguePayloadFromPatient(data?.patient || selfPatient, data?.session_id || null));
    pushStatusHint("ICU consultation started.");
    await pollBackendStatuses(true);
  } catch (error) {
    backendState.lastError = error?.message || "icu consultation create failed";
    pushStatusHint(`ICU consultation failed: ${backendState.lastError}`);
  } finally {
    backendState.submitting = false;
  }
}

async function submitCreateDoctorSessionRequest() {
  if (backendState.submitting || doctorConversationState.sending) return;
  const selfPatient = getCurrentSelfPatient();
  const visit = getCurrentVisit();
  const visitState = visit?.state || selfPatient?.visit_state || "";
  if (visitState === "in_icu_rescue") {
    await submitCreateIcuSessionRequest();
    return;
  }
  const visitId = visit?.id || selfPatient?.visit_id || doctorConversationState.visitId;
  if (!visitId) {
    pushStatusHint("Doctor consultation cannot start: visit session is missing.");
    return;
  }

  backendState.submitting = true;
  try {
    const round = visitState === "in_second_consultation" ? 2 : 1;
    doctorConversationState.activeAgentType = getCurrentConsultationAgentType(getCurrentSceneSnapshot(), selfPatient, visit);
    const payload = {
      patient_id: doctorConversationState.patientId,
      name: "You (Player)",
      visit_id: visitId,
      round,
    };
    const data = doctorConversationState.activeAgentType === "surgery"
      ? await backendClient.createSurgerySession(payload)
      : await backendClient.createInternalMedicineSession(payload);
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
  if (backendState.submitting || triageUi.open || registrationUi.open || triageDialogueUi.open || doctorDialogueUi.open || testReportUi.open || npcDialogueUi.open || fixedNpcRuntime?.isDialogueOpen?.()) return;

  if (microScene.mode === "annex_room") {
    if (canInteractWithAnnexExit()) {
      leaveAnnexRoom();
    } else {
      pushStatusHint("Explore the annex yard or move to the EXIT door.");
    }
    return;
  }

  if (microScene.mode === "indoor_room") {
    if (canInteractWithRegistrationRoomExit()) {
      leaveRegistrationRoom();
      return;
    }
    const activeIndoorRoom = microScene.indoor.activeRoomKind;
    if (activeIndoorRoom === "registration" && canInteractWithRegistrationRoomDesk()) {
      openRegistrationModal();
      return;
    }
    if (activeIndoorRoom === "triage" && canInteractWithTriageDesk()) {
      if (hasStartedTriageConversation()) openExistingTriageDialogue();
      else openTriageModal();
      return;
    }
    if (activeIndoorRoom === "doctor_entry" && canInteractWithDoctorEntry()) {
      const selfPatient = getCurrentSelfPatient();
      const visit = getCurrentVisit();
      if (hasStartedDoctorConversation(selfPatient, visit)) openExistingDoctorDialogue();
      else submitCreateDoctorSessionRequest();
      return;
    }
    if (activeIndoorRoom === "lab" && canInteractWithLab()) {
      submitCompleteAuxiliaryTestRequest();
      return;
    }
    if (activeIndoorRoom === "pharmacy_pickup" && canInteractWithPharmacyPickup()) {
      submitPharmacyPickupRequest();
      return;
    }
    if (activeIndoorRoom === "icu" && canInteractWithDoctorEntry()) {
      submitCreateDoctorSessionRequest();
      return;
    }
    pushStatusHint("Move closer to the room workstation or exit door.");
    return;
  }

  if (fixedNpcRuntime?.tryInteract?.(player)) {
    openNpcDialogueModal();
    return;
  }

  if (canInteractWithAnnexGate()) {
    enterAnnexRoom();
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

  if (canInteractWithRegistrationDesk()) {
    const selfPatient = getCurrentSelfPatient();
    const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";
    if (visitState === "diagnosis_finalized" || visitState === "waiting_payment") {
      submitReadyPaymentRequest();
      return;
    }
    if (visitState !== "triaged") {
      pushStatusHint("Finish triage before entering registration.");
      return;
    }
    enterIndoorRoom("registration");
    return;
  }

  const nearbyDoor = nearestDoor();
  if (nearbyDoor && nearbyDoor.roomKind && indoorRoomTemplates[nearbyDoor.roomKind]) {
    enterIndoorRoom(nearbyDoor.roomKind);
    return;
  }

  if (canInteractWithLab()) {
    submitCompleteAuxiliaryTestRequest();
    return;
  }

  if (canInteractWithPharmacyPickup()) {
    submitPharmacyPickupRequest();
    return;
  }

  if (canInteractWithDoctorEntry()) {
    const selfPatient = getCurrentSelfPatient();
    const visit = getCurrentVisit();
    const visitState = visit?.state || selfPatient?.visit_state || "";
    const lifecycle = selfPatient?.lifecycle_state || "";

    if (isInitialConsultationState(visitState) || isSecondConsultationState(visitState) || lifecycle === "in_consultation") {
      if (hasStartedDoctorConversation(selfPatient, visit)) {
        openExistingDoctorDialogue();
      } else {
        submitCreateDoctorSessionRequest();
      }
      return;
    }

    if (visitState === "waiting_payment" || visitState === "diagnosis_finalized") {
      pushStatusHint("Consultation already completed. Proceed to payment.");
      return;
    }
    if (visitState === "waiting_pharmacy") {
      pushStatusHint("Proceed to the pharmacy pickup room.");
      return;
    }
    if (visitState === "waiting_second_consultation") {
      backendState.submitting = true;
      triggerEncounterEvent("start_second_consultation", { source: "scene.doctor_entry.e_key" })
        .then(() => {
          pushStatusHint("Second consultation started. Press E again to open doctor dialogue.");
          return pollBackendStatuses(true);
        })
        .catch((error) => {
          backendState.lastError = error?.message || "start second consultation failed";
          pushStatusHint(`Cannot start second consultation: ${backendState.lastError}`);
        })
        .finally(() => {
          backendState.submitting = false;
        });
      return;
    }
    if (visitState === "in_icu_rescue") {
      pushStatusHint("This visit has been routed to ICU rescue placeholder.");
      return;
    }
    if (visitState === "in_emergency") {
      pushStatusHint("This visit has been routed to emergency placeholder.");
      return;
    }
    if (["waiting_test", "waiting_test_payment", "test_payment_completed", "in_test", "waiting_return_consultation", "results_ready"].includes(visitState)) {
      pushStatusHint("Consultation is paused for diagnostic stage. Follow Lab guidance first.");
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
    let snapshot = await backendClient.getSceneSnapshot(triageConversationState.patientId);
    const applied = applySceneSnapshot(snapshot);
    const selfPatient = applied?.selfPatient || null;
    const visit = applied?.visit || null;
    const visitIdForProgress = visit?.id || selfPatient?.encounter_id || selfPatient?.visit_id || triageConversationState.visitId;
    const canProgressVisit = Boolean(snapshot?.ui_flags?.can_progress_visit);
    const queueWaitSecondsRemaining = Number(snapshot?.timers?.queue_wait_seconds_remaining ?? 0);

    if (visitIdForProgress && canProgressVisit && queueWaitSecondsRemaining <= 0) {
      try {
        await backendClient.progressVisit(visitIdForProgress);
        snapshot = await backendClient.getSceneSnapshot(triageConversationState.patientId);
        applySceneSnapshot(snapshot);
      } catch (_progressError) {
        // keep polling resilient when progress endpoint is temporarily unavailable
      }
    }

    await Promise.all([
      refreshMedicalRecordTimeline(force, snapshot),
      refreshIntegrationRuntime(force),
    ]);
    taskBoardPresenter.syncIntegratedView({
      snapshot,
      medicalRecordTimeline: integrationState.medicalRecordTimeline,
      hospitalRuntime: integrationState.hospitalRuntime,
      departmentRuntime: integrationState.departmentRuntime,
      departments: integrationState.departments,
      openEmrHealth: integrationState.openEmrHealth,
      icuPatients: integrationState.icuPatients,
    });

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
    const selfPatient = getCurrentSelfPatient();
    const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";
    const consultationAgentType = getCurrentConsultationAgentType();
    const data = visitState === "in_icu_rescue"
      ? await backendClient.sendIcuMessage(doctorConversationState.sessionId, {
        patient_id: doctorConversationState.patientId,
        name: "You (Player)",
        message,
      })
      : consultationAgentType === "surgery"
        ? await backendClient.sendSurgeryMessage(doctorConversationState.sessionId, {
          patient_id: doctorConversationState.patientId,
          name: "You (Player)",
          visit_id: doctorConversationState.visitId || getCurrentVisit()?.id || null,
          message,
        })
        : await backendClient.sendInternalMedicineMessage(doctorConversationState.sessionId, {
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
    syncDoctorDialogue(
      visitState === "in_icu_rescue"
        ? buildIcuDialoguePayloadFromPatient(data.patient, data.session_id || doctorConversationState.sessionId)
        : data
    );
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
      const isClosed = !(visitState === "in_icu_rescue" || isInitialConsultationState(visitState) || isSecondConsultationState(visitState));
      doctorDialogueUi.sendBtn.disabled = isClosed;
    }
  }
}

function submitTriageRequest() {
  submitEActionRequest();
}

async function submitRegistrationFromModal() {
  if (backendState.submitting) return;
  const payload = buildRegistrationPayloadFromForm();
  await submitRegistrationRequest(payload);
  const selfPatient = getCurrentSelfPatient();
  const visitState = getCurrentVisit()?.state || selfPatient?.visit_state || "";
  if (visitState === "registered" || visitState === "waiting_consultation" || visitState === "in_consultation") {
    closeRegistrationModal();
  }
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
  doors,
  canMoveTo,
  canPathfindTo: canMoveTo,
  project,
  gatePoint: mainGatePoint,
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
  if (overlayState.queueOpen) {
    queueRuntime.draw(ctx, canvas);
  }
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

  if (restartConfirmUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeRestartConfirmModal();
      event.preventDefault();
    }
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

  if (testReportUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeTestReportModal();
      event.preventDefault();
    }
    return;
  }

  if (pharmacyPickupUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closePharmacyPickupModal();
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

  if (registrationUi.open) {
    if (event.code === "Escape" && !event.repeat) {
      closeRegistrationModal();
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
  if (event.code === "KeyR" && !event.repeat) {
    openLatestSimulatedReportModal();
    event.preventDefault();
    return;
  }
  if (event.code === "KeyE" && !event.repeat) {
    submitTriageRequest();
    event.preventDefault();
    return;
  }
  if (event.code === "KeyQ" && !event.repeat && microScene.mode === "indoor_room") {
    leaveRegistrationRoom();
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
window.addEventListener("beforeunload", () => {
  eventSubscriber.close();
  stateDebugPanel.dispose();
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

if (registrationUi.form) {
  registrationUi.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitRegistrationFromModal();
  });
}

if (registrationUi.cancelBtn) {
  registrationUi.cancelBtn.addEventListener("click", () => {
    closeRegistrationModal();
  });
}

if (registrationUi.modal) {
  registrationUi.modal.addEventListener("click", (event) => {
    if (event.target === registrationUi.modal) closeRegistrationModal();
  });
}

if (restartConfirmUi.okBtn) {
  restartConfirmUi.okBtn.addEventListener("click", () => {
    closeRestartConfirmModal();
    performFullRestart();
  });
}

if (restartConfirmUi.cancelBtn) {
  restartConfirmUi.cancelBtn.addEventListener("click", () => {
    closeRestartConfirmModal();
  });
}

if (restartConfirmUi.modal) {
  restartConfirmUi.modal.addEventListener("click", (event) => {
    if (event.target === restartConfirmUi.modal) closeRestartConfirmModal();
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

if (testReportUi.closeBtn) {
  testReportUi.closeBtn.addEventListener("click", () => {
    closeTestReportModal();
  });
}

if (testReportUi.modal) {
  testReportUi.modal.addEventListener("click", (event) => {
    if (event.target === testReportUi.modal) closeTestReportModal();
  });
}

if (pharmacyPickupUi.closeBtn) {
  pharmacyPickupUi.closeBtn.addEventListener("click", () => {
    closePharmacyPickupModal();
  });
}

if (pharmacyPickupUi.confirmBtn) {
  pharmacyPickupUi.confirmBtn.addEventListener("click", () => {
    submitPharmacyPickupRequest();
  });
}

if (pharmacyPickupUi.modal) {
  pharmacyPickupUi.modal.addEventListener("click", (event) => {
    if (event.target === pharmacyPickupUi.modal) closePharmacyPickupModal();
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
bindRuntimePanelDrag();
bindRuntimeStatsPanelDrag();
updateFloorHud();
eventSubscriber.connect();
pollBackendStatuses(true);
if (window.location.search.includes("fresh=1") || window.location.search.includes("resume=1") || window.location.search.includes("newSession=1")) {
  window.history.replaceState({}, document.title, window.location.pathname);
}
window.dispatchEvent(new Event("resize"));
requestAnimationFrame(loop);
