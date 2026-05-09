export function createNpcRuntime({ rooms, roomBounds, canMoveTo, project, constants }) {
  const { CHARACTER_FOOT_RADIUS } = constants;
  const npcs = initRandomNpcs(rooms, roomBounds, canMoveTo);

  function initRandomNpcs(allRooms, boundsFn, canMove) {
    const areas = allRooms
      .filter((room) => room.kind === "hall" || room.kind === "triage")
      .map((room) => ({ room, bounds: boundsFn(room) }));
    const list = [];
    for (let i = 0; i < 10; i += 1) {
      const area = areas[i % areas.length];
      if (!area) break;
      let point = randomPoint(area.bounds);
      let tries = 0;
      while (!canMove(point.x, point.y, area.room.floor) && tries < 20) {
        point = randomPoint(area.bounds);
        tries += 1;
      }
      list.push({
        id: `merged-npc-${i + 1}`,
        floor: area.room.floor,
        x: point.x,
        y: point.y,
        state: "idle",
        speed: 42,
        targetX: null,
        targetY: null,
        walkTimer: 0,
        walkInterval: 2200 + Math.random() * 3500,
        bodyColor: "#7dbf83",
        accentColor: "#c6dd8f",
        headColor: "#f0c9b7",
        hairColor: "#5d4128",
        facing: "down",
      });
    }
    return list;
  }

  function randomPoint(bounds, padding = 22) {
    const minX = bounds.x + padding;
    const minY = bounds.y + padding;
    const maxX = bounds.x + bounds.w - padding;
    const maxY = bounds.y + bounds.h - padding;
    return {
      x: minX + Math.random() * Math.max(1, maxX - minX),
      y: minY + Math.random() * Math.max(1, maxY - minY),
    };
  }

  function pickTarget(npc) {
    const candidates = rooms.filter((room) => room.floor === npc.floor && (room.kind === "hall" || room.kind === "triage"));
    if (candidates.length === 0) return;
    const room = candidates[Math.floor(Math.random() * candidates.length)];
    let point = randomPoint(roomBounds(room));
    let tries = 0;
    while (!canMoveTo(point.x, point.y, npc.floor) && tries < 20) {
      point = randomPoint(roomBounds(room));
      tries += 1;
    }
    npc.targetX = point.x;
    npc.targetY = point.y;
    npc.state = "walking";
  }

  function update(delta) {
    for (const npc of npcs) {
      npc.walkTimer += delta * 1000;
      if (npc.state !== "waiting" && npc.walkTimer >= npc.walkInterval && npc.targetX === null) {
        pickTarget(npc);
        npc.walkTimer = 0;
      }
      if (npc.targetX === null || npc.targetY === null || npc.state !== "walking") continue;
      const dx = npc.targetX - npc.x;
      const dy = npc.targetY - npc.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 3) {
        npc.x = npc.targetX;
        npc.y = npc.targetY;
        npc.targetX = null;
        npc.targetY = null;
        npc.state = "idle";
        npc.walkTimer = 0;
        npc.walkInterval = 2200 + Math.random() * 3500;
        continue;
      }
      const vx = (dx / dist) * npc.speed * delta;
      const vy = (dy / dist) * npc.speed * delta;
      if (Math.abs(dx) > Math.abs(dy)) {
        npc.facing = dx < 0 ? "left" : "right";
      } else if (Math.abs(dy) > 0) {
        npc.facing = dy < 0 ? "up" : "down";
      }
      const nx = npc.x + vx;
      const ny = npc.y + vy;
      if (canMoveTo(nx, ny, npc.floor)) {
        npc.x = nx;
        npc.y = ny;
      } else {
        npc.targetX = null;
        npc.targetY = null;
        npc.state = "idle";
        npc.walkTimer = 0;
      }
    }
  }

  function draw(ctx, floor, alpha = 1) {
    for (const npc of npcs) {
      if (npc.floor !== floor) continue;
      const base = project(npc.x, npc.y, 0, npc.floor);
      const px = Math.round(base.x);
      const py = Math.round(base.y);
      ctx.save();
      ctx.globalAlpha *= alpha;
      ctx.fillStyle = "rgba(44, 30, 18, 0.22)";
      ctx.beginPath();
      ctx.ellipse(px, py + 12, CHARACTER_FOOT_RADIUS + 4, CHARACTER_FOOT_RADIUS - 1, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#4d4d5c";
      ctx.fillRect(px - 8, py + 4, 5, 11);
      ctx.fillRect(px + 3, py + 4, 5, 11);

      ctx.fillStyle = npc.bodyColor;
      ctx.fillRect(px - 11, py - 15, 22, 21);
      ctx.fillStyle = npc.accentColor;
      ctx.fillRect(px - 9, py - 13, 18, 8);

      if (npc.facing === "left") {
        ctx.fillRect(px - 14, py - 12, 4, 11);
      } else if (npc.facing === "right") {
        ctx.fillRect(px + 10, py - 12, 4, 11);
      }

      ctx.fillStyle = npc.headColor;
      ctx.fillRect(px - 8, py - 28, 16, 16);
      ctx.fillStyle = npc.hairColor;
      ctx.fillRect(px - 8, py - 28, 16, 5);

      if (npc.state === "waiting") {
        ctx.fillStyle = "#ffe99c";
        ctx.font = "600 10px 'Trebuchet MS'";
        ctx.textAlign = "center";
        ctx.fillText("Waiting", px, py - 34);
      }
      ctx.restore();
    }
  }

  return {
    update,
    draw,
  };
}
