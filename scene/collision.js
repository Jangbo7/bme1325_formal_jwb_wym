import { WORLD } from "./constants.js";

export function rectsIntersect(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export function canMoveTo(player, nextX, nextY, staticCollisions, doorColliders) {
  const rect = {
    x: nextX - player.width / 2,
    y: nextY - player.height / 2,
    w: player.width,
    h: player.height,
  };

  if (rect.x < 0 || rect.y < 0 || rect.x + rect.w > WORLD.width || rect.y + rect.h > WORLD.height) {
    return false;
  }

  const collisions = [...staticCollisions, ...doorColliders];
  return !collisions.some((wall) => rectsIntersect(rect, wall));
}

export function distanceToDoor(player, door) {
  return Math.hypot(player.x - door.pivot.x, player.y - door.pivot.y);
}

export function nearestDoor(player, doors, maxDistance = 64) {
  let bestDoor = null;
  let bestDistance = Infinity;

  for (const door of doors) {
    const distance = distanceToDoor(player, door);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestDoor = door;
    }
  }

  return bestDistance <= maxDistance ? bestDoor : null;
}

export function currentDoorColliders(doors) {
  return doors.filter((door) => !door.open).map((door) => door.collider);
}
