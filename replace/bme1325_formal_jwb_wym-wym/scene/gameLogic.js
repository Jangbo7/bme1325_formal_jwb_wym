import { DOOR_SENSOR_DISTANCE, DOOR_CLOSE_DISTANCE } from "./constants.js";
import { distanceToDoor, canMoveTo, currentDoorColliders, nearestDoor, rectsIntersect } from "./collision.js";
import { drawRoomFloor, drawWall, drawDoor, drawProp, drawPlayer, drawLabels, drawHudHint, drawMinimap } from "./render.js";

function playerRect(player, nextX = player.x, nextY = player.y) {
  return {
    x: nextX - player.width / 2,
    y: nextY - player.height / 2,
    w: player.width,
    h: player.height,
  };
}

export function updateDoors(player, doors) {
  for (const door of doors) {
    const distance = distanceToDoor(player, door);
    if (distance <= DOOR_SENSOR_DISTANCE) {
      door.open = true;
      continue;
    }

    if (distance >= DOOR_CLOSE_DISTANCE && !rectsIntersect(playerRect(player), door.collider)) {
      door.open = false;
    }
  }
}

export function update(player, doors, keys, camera, delta, staticCollisions) {
  updateDoors(player, doors);

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

    if (canMoveTo(player, player.x + velocityX, player.y, staticCollisions, currentDoorColliders(doors))) {
      player.x += velocityX;
    }

    if (canMoveTo(player, player.x, player.y + velocityY, staticCollisions, currentDoorColliders(doors))) {
      player.y += velocityY;
    }
  }

  camera.x += (player.x - camera.x - 180) * 0.08;
  camera.y += (player.y - camera.y - 140) * 0.08;
}

export function render(ctx, canvas, rooms, doors, props, player, camera, roomWallSegments) {
  const activeDoor = nearestDoor(player, doors);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#130f18";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  for (const room of rooms) {
    drawRoomFloor(ctx, room, camera, canvas);
  }

  const drawables = [];

  for (const segments of roomWallSegments) {
    for (const segment of segments) {
      drawables.push({
        depth: segment.x + segment.y + segment.w + segment.h,
        draw: () => drawWall(ctx, segment, camera, canvas),
      });
    }
  }

  for (const door of doors) {
    drawables.push({
      depth: door.opening.x + door.opening.y + door.opening.w + door.opening.h + 2,
      draw: () => drawDoor(ctx, door, activeDoor, camera, canvas),
    });
  }

  for (const prop of props) {
    drawables.push({
      depth: prop.x * 32 + prop.y * 32 + prop.w * 32 + prop.h * 32 + 8,
      draw: () => drawProp(ctx, prop, camera, canvas),
    });
  }

  drawables.push({
    depth: player.x + player.y + 12,
    draw: () => drawPlayer(ctx, player, camera, canvas),
  });

  drawables.sort((a, b) => a.depth - b.depth);
  drawables.forEach((entry) => entry.draw());

  drawLabels(ctx, rooms, camera, canvas);
  drawHudHint(ctx, activeDoor, camera, canvas);
  drawMinimap(ctx, rooms, doors, player, canvas);
}
