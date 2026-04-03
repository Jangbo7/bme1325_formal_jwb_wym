export function createNpcRuntime({ rooms, roomBounds, canMoveTo, project, constants }) {
  const { CHARACTER_BODY_HEIGHT, CHARACTER_FOOT_RADIUS, CHARACTER_HEAD_RADIUS } = constants;
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
        bodyColor: "#6ed3b1",
        headColor: "#f0c9b7",
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
      const top = project(npc.x, npc.y, CHARACTER_BODY_HEIGHT - 2, npc.floor);
      ctx.save();
      ctx.globalAlpha *= alpha;
      ctx.fillStyle = "rgba(0,0,0,0.25)";
      ctx.beginPath();
      ctx.ellipse(base.x, base.y + 8, CHARACTER_FOOT_RADIUS + 3, CHARACTER_FOOT_RADIUS - 1, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = npc.bodyColor;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(base.x, base.y - 1);
      ctx.lineTo(top.x, top.y + 6);
      ctx.stroke();
      ctx.fillStyle = npc.headColor;
      ctx.beginPath();
      ctx.arc(top.x, top.y - 4, CHARACTER_HEAD_RADIUS - 1, 0, Math.PI * 2);
      ctx.fill();
      if (npc.state === "waiting") {
        ctx.fillStyle = "#ffe99c";
        ctx.font = "10px 'Segoe UI'";
        ctx.textAlign = "center";
        ctx.fillText("Waiting", top.x, top.y - 16);
      }
      ctx.restore();
    }
  }

  return {
    update,
    draw,
  };
}
