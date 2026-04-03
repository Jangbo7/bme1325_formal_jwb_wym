import {
  TILE,
  WALL_THICKNESS,
  DOOR_THICKNESS,
  WALL_HEIGHT,
  FLOOR_HEIGHT,
  DOOR_SENSOR_DISTANCE,
  DOOR_CLOSE_DISTANCE,
  STAIR_TRIGGER_COOLDOWN_MS,
  ISO_X,
  ISO_Y,
  CHARACTER_FOOT_RADIUS,
  CHARACTER_BODY_HEIGHT,
  CHARACTER_HEAD_RADIUS,
  WORLD,
  FLOOR_BASE_Z,
  palette,
} from "./constants.js";
import { initNPCs, updateNPC, drawNPC, getWalkableBounds, NPC_TYPES, NPC_STATES } from "./npc.js";
import { createQueueManager, addToQueue, addPlayerToQueue, drawQueueBoard, drawRegistrationPanel, updateQueueCalls, QUEUE_DEPARTMENTS } from "./queue.js";
import { createDialogSystem, openDialog, closeDialog, drawDialogBox, sendMessage } from "./dialog.js";
import { update, render } from "./gameLogic.js";
import { project } from "./utils.js";

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

function getDeptTarget(deptId) {
  const target = DEPT_TARGETS[deptId];
  if (!target) return null;
  const room = rooms[target.roomIndex];
  if (!room) return null;
  const center = roomCenter(room);
  return { x: center.x, y: center.y, floor: target.floor, label: target.label };
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

  if (npc.type === NPC_TYPES.DOCTOR && npc.department) {
    if (!playerCall.active || playerCall.deptId !== npc.department) {
      const waitingMsg = "请您先到分诊台挂号，然后等待叫号再来就诊。";
      dialogSystem.messages = [
        { role: "assistant", content: waitingMsg, timestamp: Date.now() },
      ];
      dialogSystem.isOpen = true;
      dialogSystem.currentNPC = npc;
      npc.state = "in_conversation";
      if (imeInput) {
        imeInput.value = "";
        imeInput.classList.add("is-active");
        setTimeout(() => imeInput.focus(), 0);
      }
      setTimeout(() => {
        closeDialog(dialogSystem);
      }, 2000);
      return;
    }
  }

  openDialog(dialogSystem, npc);
  const greetTail = "很高兴见到你，nice to meet you。";
  if (npc.type === NPC_TYPES.NURSE) {
    dialogSystem.messages = [
      { role: "assistant", content: `您好！我是护士小李，请问您有什么不舒服的地方？${greetTail}`, timestamp: Date.now() },
    ];
  } else if (npc.type === NPC_TYPES.DOCTOR) {
    if (playerCall.active && playerCall.deptId === npc.department) {
      dialogSystem.messages = [
        { role: "assistant", content: `您好！我是${npc.name}，您的号到了，请坐，有什么可以帮您的？${greetTail}`, timestamp: Date.now() },
      ];
    } else {
      dialogSystem.messages = [
        { role: "assistant", content: `您好！我是${npc.name}，请坐，有什么可以帮您的？${greetTail}`, timestamp: Date.now() },
      ];
    }
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

let lastTime = performance.now();

function gameLoop(now) {
  const delta = (now - lastTime) / 1000;
  lastTime = now;

  const nowMs = performance.now();
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

  requestAnimationFrame(gameLoop);
}

requestAnimationFrame(gameLoop);

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
