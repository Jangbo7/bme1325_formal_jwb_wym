import { FLOOR_PLATE, TILE, WORLD } from "./map.js";
import { PLAYER_RADIUS } from "./runtime.js";

const GRID_W = WORLD.width / TILE;
const GRID_H = WORLD.height / TILE;
const CLEARANCE = PLAYER_RADIUS + 3;
const COMFORT_DISTANCE = TILE * 1.65;
const MAX_NEAREST_RADIUS = 8;

export function createRoomPath({ floorId, start, targetRoom, targetPoint, collisions }) {
  const startCell = nearestPassableCell(worldToCell(start), floorId, collisions);
  const goalCell = nearestPassableCell(worldToCell(targetPoint || roomCenter(targetRoom)), floorId, collisions, targetRoom);
  if (!startCell || !goalCell) return null;

  const cells = findGridPath(startCell, goalCell, floorId, collisions);
  if (!cells.length) return null;

  return compressWaypoints(cells.map(cellCenter));
}

function findGridPath(start, goal, floorId, collisions) {
  const open = [start];
  const openKeys = new Set([cellKey(start)]);
  const cameFrom = new Map();
  const gScore = new Map([[cellKey(start), 0]]);
  const fScore = new Map([[cellKey(start), heuristic(start, goal)]]);

  while (open.length) {
    open.sort((a, b) => (fScore.get(cellKey(a)) ?? Infinity) - (fScore.get(cellKey(b)) ?? Infinity));
    const current = open.shift();
    const currentKey = cellKey(current);
    openKeys.delete(currentKey);

    if (current.x === goal.x && current.y === goal.y) return reconstructPath(cameFrom, current);

    for (const neighbor of neighbors(current)) {
      if (!isPassableCell(neighbor, floorId, collisions)) continue;
      const neighborKey = cellKey(neighbor);
      const tentative = (gScore.get(currentKey) ?? Infinity) + movementCost(neighbor, floorId, collisions);
      if (tentative >= (gScore.get(neighborKey) ?? Infinity)) continue;

      cameFrom.set(neighborKey, current);
      gScore.set(neighborKey, tentative);
      fScore.set(neighborKey, tentative + heuristic(neighbor, goal));
      if (!openKeys.has(neighborKey)) {
        open.push(neighbor);
        openKeys.add(neighborKey);
      }
    }
  }

  return [];
}

function nearestPassableCell(seed, floorId, collisions, targetRoom = null) {
  if (isPassableCell(seed, floorId, collisions) && (!targetRoom || cellInsideRoom(seed, targetRoom))) return seed;

  for (let radius = 1; radius <= MAX_NEAREST_RADIUS; radius += 1) {
    const candidates = [];
    for (let dx = -radius; dx <= radius; dx += 1) {
      for (let dy = -radius; dy <= radius; dy += 1) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== radius) continue;
        const cell = { x: seed.x + dx, y: seed.y + dy };
        if (targetRoom && !cellInsideRoom(cell, targetRoom)) continue;
        if (isPassableCell(cell, floorId, collisions)) candidates.push(cell);
      }
    }
    if (candidates.length) {
      candidates.sort((a, b) => heuristic(a, seed) - heuristic(b, seed));
      return candidates[0];
    }
  }

  return null;
}

function isPassableCell(cell, floorId, collisions) {
  if (cell.x < 0 || cell.x >= GRID_W || cell.y < 0 || cell.y >= GRID_H) return false;
  const point = cellCenter(cell);
  const minX = FLOOR_PLATE.x * TILE + CLEARANCE;
  const minY = FLOOR_PLATE.y * TILE + CLEARANCE;
  const maxX = (FLOOR_PLATE.x + FLOOR_PLATE.w) * TILE - CLEARANCE;
  const maxY = (FLOOR_PLATE.y + FLOOR_PLATE.h) * TILE - CLEARANCE;
  if (point.x < minX || point.x > maxX || point.y < minY || point.y > maxY) return false;

  return !collisions.some((rect) => {
    if (rect.floor !== floorId) return false;
    return point.x >= rect.x - CLEARANCE &&
      point.x <= rect.x + rect.w + CLEARANCE &&
      point.y >= rect.y - CLEARANCE &&
      point.y <= rect.y + rect.h + CLEARANCE;
  });
}

function movementCost(cell, floorId, collisions) {
  const point = cellCenter(cell);
  const nearest = nearestObstacleDistance(point, floorId, collisions);
  if (nearest >= COMFORT_DISTANCE) return 1;

  const tightness = (COMFORT_DISTANCE - nearest) / COMFORT_DISTANCE;
  return 1 + tightness ** 2 * 5;
}

function nearestObstacleDistance(point, floorId, collisions) {
  const plate = {
    x: FLOOR_PLATE.x * TILE,
    y: FLOOR_PLATE.y * TILE,
    w: FLOOR_PLATE.w * TILE,
    h: FLOOR_PLATE.h * TILE,
  };
  let nearest = Math.min(
    point.x - plate.x,
    point.y - plate.y,
    plate.x + plate.w - point.x,
    plate.y + plate.h - point.y,
  );

  collisions.forEach((rect) => {
    if (rect.floor !== floorId) return;
    nearest = Math.min(nearest, distanceToRect(point, rect));
  });

  return Math.max(0, nearest);
}

function distanceToRect(point, rect) {
  const dx = Math.max(rect.x - point.x, 0, point.x - (rect.x + rect.w));
  const dy = Math.max(rect.y - point.y, 0, point.y - (rect.y + rect.h));
  return Math.hypot(dx, dy);
}

function compressWaypoints(points) {
  if (points.length <= 2) return points;
  const compressed = [points[0]];
  let previousDirection = direction(points[0], points[1]);

  for (let index = 1; index < points.length - 1; index += 1) {
    const nextDirection = direction(points[index], points[index + 1]);
    if (nextDirection.x !== previousDirection.x || nextDirection.y !== previousDirection.y) {
      compressed.push(points[index]);
      previousDirection = nextDirection;
    }
  }

  compressed.push(points[points.length - 1]);
  return compressed;
}

function reconstructPath(cameFrom, current) {
  const path = [current];
  let currentKey = cellKey(current);
  while (cameFrom.has(currentKey)) {
    current = cameFrom.get(currentKey);
    currentKey = cellKey(current);
    path.unshift(current);
  }
  return path;
}

function neighbors(cell) {
  return [
    { x: cell.x + 1, y: cell.y },
    { x: cell.x - 1, y: cell.y },
    { x: cell.x, y: cell.y + 1 },
    { x: cell.x, y: cell.y - 1 },
  ];
}

function worldToCell(point) {
  return {
    x: Math.floor(point.x / TILE),
    y: Math.floor(point.y / TILE),
  };
}

function cellCenter(cell) {
  return {
    x: (cell.x + 0.5) * TILE,
    y: (cell.y + 0.5) * TILE,
  };
}

function cellInsideRoom(cell, room) {
  return cell.x >= room.x &&
    cell.x < room.x + room.w &&
    cell.y >= room.y &&
    cell.y < room.y + room.h;
}

function roomCenter(room) {
  return {
    x: (room.x + room.w / 2) * TILE,
    y: (room.y + room.h / 2) * TILE,
  };
}

function direction(a, b) {
  return {
    x: Math.sign(b.x - a.x),
    y: Math.sign(b.y - a.y),
  };
}

function heuristic(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function cellKey(cell) {
  return `${cell.x},${cell.y}`;
}
