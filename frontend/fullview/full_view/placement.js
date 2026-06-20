import { ROOMS, TILE } from "./map.js";

export function placeInRoom(roomId, relX, relY) {
  const room = ROOMS.find((item) => item.id === roomId);
  if (!room) throw new Error(`Unknown room for placement: ${roomId}`);
  return {
    floor: room.floor,
    roomId,
    relX,
    relY,
    x: (room.x + room.w * clampUnit(relX)) * TILE,
    y: (room.y + room.h * clampUnit(relY)) * TILE,
  };
}

function clampUnit(value) {
  return Math.min(0.94, Math.max(0.06, Number(value) || 0.5));
}
