import { DOORS, FLOOR_PLATE, ROOMS, TILE } from "./map.js";

export const WALL_THICKNESS = 14;
export const PLAYER_RADIUS = 7;
export const PLAYER_FLOOR_MARGIN = 20;
export const FLOOR_SWITCH_MS = 450;

export function buildGeometry() {
  const doors = DOORS.map((spec, index) => buildDoor(spec, index));
  const walls = ROOMS.flatMap((room) => buildRoomWalls(room, doors));
  const propColliders = [];
  return { doors, walls, propColliders };
}

export function buildPropColliders(props) {
  return props
    .filter((prop) => prop.type !== "elevator")
    .map((prop) => ({
      floor: prop.floor,
      x: prop.x * TILE,
      y: prop.y * TILE,
      w: prop.w * TILE,
      h: prop.h * TILE,
      type: "prop",
    }));
}

export function createPlayer(spawn, floor = 1) {
  return {
    x: spawn.x,
    y: spawn.y,
    floor,
    radius: PLAYER_RADIUS,
    speed: 190,
    facing: "down",
  };
}

export function createCamera(spawn) {
  return { x: spawn.x, y: spawn.y, zoom: 1 };
}

export function updatePlayer({ player, keys, delta, collisions, movementLocked }) {
  clampPlayerToFloor(player);
  if (movementLocked) return;

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
  if (moveX === 0 && moveY === 0) return;

  const length = Math.hypot(moveX, moveY);
  const vx = (moveX / length) * player.speed * delta;
  const vy = (moveY / length) * player.speed * delta;
  if (canMoveTo(player, player.x + vx, player.y, collisions)) player.x += vx;
  if (canMoveTo(player, player.x, player.y + vy, collisions)) player.y += vy;
}

export function updateCamera(camera, player) {
  camera.x += (player.x - camera.x) * 0.12;
  camera.y += (player.y - camera.y) * 0.12;
}

export function roomAtPoint(rooms, player) {
  return rooms.find((room) => {
    if (room.floor !== player.floor) return false;
    const rect = roomRect(room);
    return player.x >= rect.x && player.x <= rect.x + rect.w && player.y >= rect.y && player.y <= rect.y + rect.h;
  }) || null;
}

export function beginFloorTransition(state, targetFloor, spawn) {
  if (state.activeFloor === targetFloor || state.transition) return;
  state.transition = {
    fromFloor: state.activeFloor,
    toFloor: targetFloor,
    startedAt: performance.now(),
    duration: FLOOR_SWITCH_MS,
  };
  state.player.x = spawn.x;
  state.player.y = spawn.y;
  state.player.floor = targetFloor;
  state.camera.x = spawn.x;
  state.camera.y = spawn.y;
}

export function updateFloorTransition(state, now) {
  if (!state.transition) return null;
  const progress = Math.min(1, (now - state.transition.startedAt) / state.transition.duration);
  if (progress >= 1) {
    state.activeFloor = state.transition.toFloor;
    state.transition = null;
  }
  return progress;
}

function canMoveTo(player, nextX, nextY, collisions) {
  const bounds = floorBounds();
  if (nextX - PLAYER_FLOOR_MARGIN < bounds.x || nextY - PLAYER_FLOOR_MARGIN < bounds.y) return false;
  if (nextX + PLAYER_FLOOR_MARGIN > bounds.x + bounds.w || nextY + PLAYER_FLOOR_MARGIN > bounds.y + bounds.h) return false;

  return !collisions.some((rect) => {
    if (rect.floor !== player.floor) return false;
    const closestX = Math.max(rect.x, Math.min(nextX, rect.x + rect.w));
    const closestY = Math.max(rect.y, Math.min(nextY, rect.y + rect.h));
    return (nextX - closestX) ** 2 + (nextY - closestY) ** 2 < player.radius ** 2;
  });
}

function clampPlayerToFloor(player) {
  const bounds = floorBounds();
  player.x = Math.min(bounds.x + bounds.w - PLAYER_FLOOR_MARGIN, Math.max(bounds.x + PLAYER_FLOOR_MARGIN, player.x));
  player.y = Math.min(bounds.y + bounds.h - PLAYER_FLOOR_MARGIN, Math.max(bounds.y + PLAYER_FLOOR_MARGIN, player.y));
}

function floorBounds() {
  return {
    x: FLOOR_PLATE.x * TILE,
    y: FLOOR_PLATE.y * TILE,
    w: FLOOR_PLATE.w * TILE,
    h: FLOOR_PLATE.h * TILE,
  };
}

function buildDoor(spec, index) {
  const room = ROOMS.find((item) => item.id === spec.roomId);
  const rect = roomRect(room);
  const length = spec.length * TILE;
  const offset = spec.offset * TILE;
  if (spec.side === "top" || spec.side === "bottom") {
    const x = rect.x + offset;
    const y = spec.side === "top" ? rect.y : rect.y + rect.h - WALL_THICKNESS;
    return { id: `door-${index}`, floor: room.floor, roomId: room.id, side: spec.side, x, y, w: length, h: WALL_THICKNESS };
  }
  const x = spec.side === "left" ? rect.x : rect.x + rect.w - WALL_THICKNESS;
  const y = rect.y + offset;
  return { id: `door-${index}`, floor: room.floor, roomId: room.id, side: spec.side, x, y, w: WALL_THICKNESS, h: length };
}

function buildRoomWalls(room, doors) {
  const rect = roomRect(room);
  const roomDoors = doors.filter((door) => door.roomId === room.id);
  const walls = [];

  carve(rect.w, rect.x, rect.y, true, roomDoors.filter((door) => door.side === "top"), walls, room.floor);
  carve(rect.w, rect.x, rect.y + rect.h - WALL_THICKNESS, true, roomDoors.filter((door) => door.side === "bottom"), walls, room.floor);
  carve(rect.h, rect.y, rect.x, false, roomDoors.filter((door) => door.side === "left"), walls, room.floor);
  carve(rect.h, rect.y, rect.x + rect.w - WALL_THICKNESS, false, roomDoors.filter((door) => door.side === "right"), walls, room.floor);
  return walls;
}

function carve(total, rectStart, fixed, horizontal, openings, walls, floor) {
  const sorted = openings
    .map((door) => ({
      start: horizontal ? door.x - rectStart : door.y - rectStart,
      size: horizontal ? door.w : door.h,
    }))
    .sort((a, b) => a.start - b.start);

  let cursor = 0;
  for (const opening of sorted) {
    if (opening.start > cursor) pushWall(rectStart, fixed, cursor, opening.start - cursor, horizontal, floor, walls);
    cursor = opening.start + opening.size;
  }
  if (cursor < total) pushWall(rectStart, fixed, cursor, total - cursor, horizontal, floor, walls);
}

function pushWall(rectStart, fixed, cursor, size, horizontal, floor, walls) {
  if (size <= 0) return;
  if (horizontal) walls.push({ floor, x: rectStart + cursor, y: fixed, w: size, h: WALL_THICKNESS, type: "wall" });
  else walls.push({ floor, x: fixed, y: rectStart + cursor, w: WALL_THICKNESS, h: size, type: "wall" });
}

function roomRect(room) {
  return { x: room.x * TILE, y: room.y * TILE, w: room.w * TILE, h: room.h * TILE };
}
