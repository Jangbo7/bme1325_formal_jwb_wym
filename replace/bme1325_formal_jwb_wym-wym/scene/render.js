import { palette, WALL_HEIGHT, WALL_THICKNESS, DOOR_THICKNESS, TILE } from "./constants.js";
import { project } from "./utils.js";

export function drawQuad(ctx, points, fillStyle, strokeStyle = palette.wallEdge) {
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length; index += 1) {
    ctx.lineTo(points[index].x, points[index].y);
  }
  ctx.closePath();
  ctx.fillStyle = fillStyle;
  ctx.fill();
  if (strokeStyle) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

export function makePrismFaces(x, y, w, h, z, camera, canvas) {
  const a = project(x, y, 0, camera, canvas);
  const b = project(x + w, y, 0, camera, canvas);
  const c = project(x + w, y + h, 0, camera, canvas);
  const d = project(x, y + h, 0, camera, canvas);
  const at = project(x, y, z, camera, canvas);
  const bt = project(x + w, y, z, camera, canvas);
  const ct = project(x + w, y + h, z, camera, canvas);
  const dt = project(x, y + h, z, camera, canvas);

  return {
    top: [at, bt, ct, dt],
    south: [d, c, ct, dt],
    east: [b, c, ct, bt],
    north: [a, b, bt, at],
    west: [a, d, dt, at],
    centerDepth: x + y + w + h,
  };
}

export function drawRoomFloor(ctx, room, camera, canvas) {
  const rect = {
    x: room.x * TILE,
    y: room.y * TILE,
    w: room.w * TILE,
    h: room.h * TILE,
  };

  const quad = [
    project(rect.x, rect.y, 0, camera, canvas),
    project(rect.x + rect.w, rect.y, 0, camera, canvas),
    project(rect.x + rect.w, rect.y + rect.h, 0, camera, canvas),
    project(rect.x, rect.y + rect.h, 0, camera, canvas),
  ];

  drawQuad(ctx, quad, room.kind === "hall" ? palette.hallFloor : palette.roomFloor, "rgba(255,255,255,0.08)");

  ctx.strokeStyle = palette.floorLine;
  ctx.lineWidth = 1;
  for (let tx = 1; tx < room.w; tx += 1) {
    const start = project(rect.x + tx * TILE, rect.y, 0, camera, canvas);
    const end = project(rect.x + tx * TILE, rect.y + rect.h, 0, camera, canvas);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }

  for (let ty = 1; ty < room.h; ty += 1) {
    const start = project(rect.x, rect.y + ty * TILE, 0, camera, canvas);
    const end = project(rect.x + rect.w, rect.y + ty * TILE, 0, camera, canvas);
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
}

export function drawWall(ctx, segment, camera, canvas) {
  const prism = makePrismFaces(segment.x, segment.y, segment.w, segment.h, WALL_HEIGHT, camera, canvas);
  drawQuad(ctx, prism.top, palette.wallTop);

  if (segment.h <= WALL_THICKNESS) {
    drawQuad(ctx, prism.south, palette.wallFront);
  }
  if (segment.w <= WALL_THICKNESS) {
    drawQuad(ctx, prism.east, palette.wallSide);
  }
}

export function drawDoor(ctx, door, activeDoor, camera, canvas) {
  const horizontal = door.side === "top" || door.side === "bottom";
  const opening = door.opening;
  const frame = makePrismFaces(opening.x, opening.y, opening.w, opening.h, 22, camera, canvas);
  drawQuad(ctx, frame.top, "#7e97a7", "rgba(255,255,255,0.12)");

  if (opening.h <= WALL_THICKNESS) {
    drawQuad(ctx, frame.south, "#688091");
  } else {
    drawQuad(ctx, frame.east, "#688091");
  }

  const shrink = door.open ? 0.42 : 1;
  if (horizontal) {
    const width = opening.w * shrink;
    const leftX = opening.x;
    const rightX = opening.x + opening.w - width;
    const y = opening.y + (opening.h - DOOR_THICKNESS) / 2;
    const leftLeaf = makePrismFaces(leftX, y, width * 0.5, DOOR_THICKNESS, 20, camera, canvas);
    const rightLeaf = makePrismFaces(rightX + width * 0.5, y, width * 0.5, DOOR_THICKNESS, 20, camera, canvas);
    drawQuad(ctx, leftLeaf.top, palette.doorGlass);
    drawQuad(ctx, rightLeaf.top, palette.doorGlass);
    drawQuad(ctx, leftLeaf.south, palette.doorFrame);
    drawQuad(ctx, rightLeaf.south, palette.doorFrame);
  } else {
    const height = opening.h * shrink;
    const topY = opening.y;
    const bottomY = opening.y + opening.h - height;
    const x = opening.x + (opening.w - DOOR_THICKNESS) / 2;
    const topLeaf = makePrismFaces(x, topY, DOOR_THICKNESS, height * 0.5, 20, camera, canvas);
    const bottomLeaf = makePrismFaces(x, bottomY + height * 0.5, DOOR_THICKNESS, height * 0.5, 20, camera, canvas);
    drawQuad(ctx, topLeaf.top, palette.doorGlass);
    drawQuad(ctx, bottomLeaf.top, palette.doorGlass);
    drawQuad(ctx, topLeaf.east, palette.doorFrame);
    drawQuad(ctx, bottomLeaf.east, palette.doorFrame);
  }

  const sensor = project(door.pivot.x, door.pivot.y, 24, camera, canvas);
  ctx.fillStyle = palette.doorSensor;
  ctx.beginPath();
  ctx.arc(sensor.x, sensor.y, activeDoor?.id === door.id ? 5 : 3, 0, Math.PI * 2);
  ctx.fill();
}

export function drawProp(ctx, prop, camera, canvas) {
  const x = prop.x * TILE;
  const y = prop.y * TILE;
  const w = prop.w * TILE;
  const h = prop.h * TILE;
  const prism = makePrismFaces(x, y, w, h, prop.z, camera, canvas);

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
  drawQuad(ctx, prism.top, color.top);
  drawQuad(ctx, prism.south, color.front);
  drawQuad(ctx, prism.east, color.side);
}

export function drawPlayer(ctx, player, camera, canvas) {
  const base = project(player.x, player.y, 0, camera, canvas);
  const top = project(player.x, player.y, 32, camera, canvas);

  ctx.fillStyle = palette.shadow;
  ctx.beginPath();
  ctx.ellipse(base.x, base.y + 10, 18, 9, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = palette.playerLeg;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(base.x - 5, base.y + 2);
  ctx.lineTo(base.x - 7, base.y + 18);
  ctx.moveTo(base.x + 5, base.y + 2);
  ctx.lineTo(base.x + 7, base.y + 18);
  ctx.stroke();

  ctx.strokeStyle = palette.playerBody;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(base.x, base.y - 2);
  ctx.lineTo(top.x, top.y + 6);
  ctx.stroke();

  ctx.fillStyle = palette.playerHead;
  ctx.beginPath();
  ctx.arc(top.x, top.y - 4, 8, 0, Math.PI * 2);
  ctx.fill();
}

export function drawLabels(ctx, rooms, camera, canvas) {
  const labels = {
    ward: "Ward",
    pharmacy: "Pharmacy",
    office: "Office",
    emergency: "ER",
    hall: "Lobby",
    rest: "Rest",
    lab: "Lab",
    icu: "ICU",
  };

  ctx.fillStyle = palette.label;
  ctx.font = "13px 'Segoe UI'";
  ctx.textAlign = "center";

  for (const room of rooms) {
    const rect = {
      x: room.x * TILE,
      y: room.y * TILE,
      w: room.w * TILE,
      h: room.h * TILE,
    };
    const point = project(rect.x + rect.w * 0.5, rect.y + rect.h * 0.5, 6, camera, canvas);
    ctx.fillText(labels[room.kind], point.x, point.y);
  }
}

export function drawMinimap(ctx, rooms, doors, player, canvas) {
  const size = 180;
  const scale = 0.11;
  const left = canvas.width - size - 18;
  const top = 18;

  ctx.fillStyle = "rgba(20, 15, 27, 0.72)";
  ctx.fillRect(left, top, size, size);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.strokeRect(left, top, size, size);

  for (const room of rooms) {
    const rect = {
      x: room.x * TILE,
      y: room.y * TILE,
      w: room.w * TILE,
      h: room.h * TILE,
    };
    ctx.fillStyle = room.kind === "hall" ? "#8a7188" : "#705970";
    ctx.fillRect(left + rect.x * scale, top + rect.y * scale, rect.w * scale, rect.h * scale);
  }

  for (const door of doors) {
    ctx.fillStyle = door.open ? "#8df1ff" : "#65879a";
    ctx.fillRect(
      left + door.opening.x * scale,
      top + door.opening.y * scale,
      Math.max(2, door.opening.w * scale),
      Math.max(2, door.opening.h * scale),
    );
  }

  ctx.fillStyle = "#4ed7ff";
  ctx.beginPath();
  ctx.arc(left + player.x * scale, top + player.y * scale, 4, 0, Math.PI * 2);
  ctx.fill();
}

export function drawHudHint(ctx, door, camera, canvas) {
  if (!door) {
    return;
  }

  const point = project(door.pivot.x, door.pivot.y, 52, camera, canvas);
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
