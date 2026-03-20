import { TILE, WALL_THICKNESS, DOOR_THICKNESS, ISO_X, ISO_Y } from "./constants.js";
import { rooms } from "./gameObjects.js";

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function roomBounds(room) {
  return {
    x: room.x * TILE,
    y: room.y * TILE,
    w: room.w * TILE,
    h: room.h * TILE,
  };
}

export function playerRect(player, nextX = player.x, nextY = player.y) {
  return {
    x: nextX - player.width / 2,
    y: nextY - player.height / 2,
    w: player.width,
    h: player.height,
  };
}

export function buildDoor(spec, index) {
  const room = rooms[spec.roomIndex];
  const rect = roomBounds(room);
  const length = spec.length * TILE;
  const offset = spec.offset * TILE;

  if (spec.side === "top" || spec.side === "bottom") {
    const openingX = rect.x + offset;
    const openingY = spec.side === "top" ? rect.y : rect.y + rect.h - WALL_THICKNESS;
    return {
      id: `door-${index}`,
      ...spec,
      open: false,
      opening: { x: openingX, y: openingY, w: length, h: WALL_THICKNESS },
      collider: {
        x: openingX,
        y: openingY + (WALL_THICKNESS - DOOR_THICKNESS) / 2,
        w: length,
        h: DOOR_THICKNESS,
      },
      pivot: {
        x: openingX + length / 2,
        y: openingY + WALL_THICKNESS / 2,
      },
    };
  }

  const openingX = spec.side === "left" ? rect.x : rect.x + rect.w - WALL_THICKNESS;
  const openingY = rect.y + offset;
  return {
    id: `door-${index}`,
    ...spec,
    open: false,
    opening: { x: openingX, y: openingY, w: WALL_THICKNESS, h: length },
    collider: {
      x: openingX + (WALL_THICKNESS - DOOR_THICKNESS) / 2,
      y: openingY,
      w: DOOR_THICKNESS,
      h: length,
    },
    pivot: {
      x: openingX + WALL_THICKNESS / 2,
      y: openingY + length / 2,
    },
  };
}

export function buildRoomWallSegments(roomIndex, doors) {
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
        if (horizontal) {
          segments.push({ x: rect.x + cursor, y: fixed, w: opening.start - cursor, h: WALL_THICKNESS });
        } else {
          segments.push({ x: fixed, y: rect.y + cursor, w: WALL_THICKNESS, h: opening.start - cursor });
        }
      }
      cursor = opening.start + opening.size;
    }

    if (cursor < total) {
      if (horizontal) {
        segments.push({ x: rect.x + cursor, y: fixed, w: total - cursor, h: WALL_THICKNESS });
      } else {
        segments.push({ x: fixed, y: rect.y + cursor, w: WALL_THICKNESS, h: total - cursor });
      }
    }
  }

  carve(rect.w, rect.y, true, roomDoors.filter((door) => door.side === "top"));
  carve(rect.w, rect.y + rect.h - WALL_THICKNESS, true, roomDoors.filter((door) => door.side === "bottom"));
  carve(rect.h, rect.x, false, roomDoors.filter((door) => door.side === "left"));
  carve(rect.h, rect.x + rect.w - WALL_THICKNESS, false, roomDoors.filter((door) => door.side === "right"));

  return segments;
}

export function project(x, y, z = 0, camera, canvas) {
  const dx = x - camera.x;
  const dy = y - camera.y;
  return {
    x: canvas.width / 2 + (dx - dy) * ISO_X,
    y: canvas.height / 2 + (dx + dy) * ISO_Y - z,
  };
}

export function buildCollisionRects(roomWallSegments, props) {
  const colliders = [];

  for (const segments of roomWallSegments) {
    colliders.push(...segments);
  }

  for (const prop of props) {
    colliders.push({
      x: prop.x * TILE,
      y: prop.y * TILE,
      w: prop.w * TILE,
      h: prop.h * TILE,
    });
  }

  return colliders;
}
