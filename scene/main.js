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
