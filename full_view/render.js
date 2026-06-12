import { DEPARTMENT_STATUS, FLOOR_PLATE, TILE, WORLD } from "./map.js";
import { WALL_THICKNESS } from "./runtime.js";

const MINIMAP = {
  x: 18,
  bottom: 18,
  width: 196,
  height: 124,
  titleHeight: 26,
  verticalRatio: 0.76,
};

const FLOOR_COLORS = {
  1: { base: "#76a85c", grid: "rgba(255, 242, 207, 0.09)", shadow: "rgba(84, 54, 34, 0.24)" },
  2: { base: "#7eb36b", grid: "rgba(233, 255, 221, 0.09)", shadow: "rgba(45, 74, 48, 0.23)" },
  3: { base: "#6da6a2", grid: "rgba(229, 255, 255, 0.1)", shadow: "rgba(26, 62, 67, 0.24)" },
  4: { base: "#7b82ad", grid: "rgba(244, 238, 255, 0.1)", shadow: "rgba(40, 36, 70, 0.25)" },
  5: { base: "#78a881", grid: "rgba(244, 255, 235, 0.09)", shadow: "rgba(35, 65, 44, 0.24)" },
};

const PROP_STYLES = {
  bed: { fill: "#f8e8d0", trim: "#b45e6d" },
  cabinet: { fill: "#b7c58b", trim: "#637f45" },
  desk: { fill: "#c58a58", trim: "#7a4d32" },
  elevator: { fill: "#b9a27d", trim: "#5e5144" },
  reception: { fill: "#d1a15f", trim: "#8a5e35" },
  screen: { fill: "#394c5d", trim: "#76d4e4" },
  sofa: { fill: "#76a0c8", trim: "#406b8e" },
  table: { fill: "#b18468", trim: "#684737" },
};

export function clearCanvas(ctx, canvas, floorId) {
  const palette = FLOOR_COLORS[floorId] || FLOOR_COLORS[1];
  ctx.save();
  ctx.fillStyle = palette.base;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

export function drawFloorScene(ctx, canvas, scene) {
  const { floorId, rooms, props, walls, doors, patients = [], staff = [], selectedEntityId, player, camera, now = 0, alpha = 1, drawPlayer = true } = scene;
  const palette = FLOOR_COLORS[floorId] || FLOOR_COLORS[1];

  ctx.save();
  camera.viewportWidth = canvas.width;
  camera.viewportHeight = canvas.height;
  ctx.globalAlpha = alpha;
  drawGround(ctx, canvas, camera, palette);
  drawFloorPlate(ctx, camera);
  rooms.forEach((room) => drawRoom(ctx, camera, room));
  doors.filter((door) => door.floor === floorId).forEach((door) => drawDoor(ctx, camera, door));
  props.filter((prop) => prop.floor === floorId).forEach((prop) => drawProp(ctx, camera, prop));
  patients.forEach((patient) => drawPatient(ctx, camera, patient, now, selectedEntityId));
  staff.forEach((member) => drawStaff(ctx, camera, member, now, member.id === selectedEntityId));
  walls.filter((wall) => wall.floor === floorId).forEach((wall) => drawWall(ctx, camera, wall));
  rooms.forEach((room) => drawRoomLabel(ctx, camera, room));
  if (drawPlayer && player.floor === floorId) drawPlayerSprite(ctx, camera, player);
  ctx.restore();
}

export function drawMinimap(ctx, canvas, { floorId, rooms, player, selectedRoomId }) {
  const layout = getMinimapLayout(canvas);
  const { x, y, width, height, scaleX, scaleY } = layout;

  ctx.save();
  ctx.globalAlpha = 0.94;
  ctx.fillStyle = "rgba(46, 35, 25, 0.82)";
  roundedRect(ctx, x, y, width, height, 10);
  ctx.fill();
  ctx.strokeStyle = "rgba(255, 232, 184, 0.45)";
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.font = "700 11px Trebuchet MS, sans-serif";
  ctx.fillStyle = "#ffe7b4";
  ctx.fillText(`${floorId}F Mini Map`, x + 12, y + 19);

  rooms.forEach((room) => {
    const rx = x + room.x * TILE * scaleX;
    const ry = layout.mapY + room.y * TILE * scaleY;
    const rw = room.w * TILE * scaleX;
    const rh = room.h * TILE * scaleY;
    ctx.fillStyle = room.accent;
    ctx.globalAlpha = 0.78;
    ctx.fillRect(rx, ry, rw, rh);
    if (room.id === selectedRoomId) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#fff6cf";
      ctx.lineWidth = 2;
      ctx.strokeRect(rx - 2, ry - 2, rw + 4, rh + 4);
    }
  });

  if (player.floor === floorId) {
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#fff8da";
    ctx.beginPath();
    ctx.arc(x + player.x * scaleX, layout.mapY + player.y * scaleY, 4, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function getMinimapLayout(canvas) {
  const x = MINIMAP.x;
  const y = canvas.height - MINIMAP.height - MINIMAP.bottom;
  const mapY = y + MINIMAP.titleHeight;
  const mapHeight = MINIMAP.height * MINIMAP.verticalRatio;
  return {
    x,
    y,
    width: MINIMAP.width,
    height: MINIMAP.height,
    mapY,
    mapHeight,
    scaleX: MINIMAP.width / WORLD.width,
    scaleY: mapHeight / WORLD.height,
  };
}

export function minimapPointToWorld(canvas, point) {
  const layout = getMinimapLayout(canvas);
  const insidePanel =
    point.x >= layout.x &&
    point.x <= layout.x + layout.width &&
    point.y >= layout.y &&
    point.y <= layout.y + layout.height;
  if (!insidePanel) return null;

  const insideMap =
    point.x >= layout.x &&
    point.x <= layout.x + layout.width &&
    point.y >= layout.mapY &&
    point.y <= layout.mapY + layout.mapHeight;
  if (!insideMap) return { insidePanel: true, world: null };

  return {
    insidePanel: true,
    world: {
      x: (point.x - layout.x) / layout.scaleX,
      y: (point.y - layout.mapY) / layout.scaleY,
    },
  };
}

export function drawTransitionWash(ctx, canvas, progress) {
  const pulse = Math.sin(progress * Math.PI);
  ctx.save();
  ctx.fillStyle = `rgba(255, 242, 209, ${0.18 * pulse})`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = `rgba(31, 24, 18, ${0.18 * pulse})`;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

export function renderStatusRows(container, floor, labels) {
  container.innerHTML = floor.departmentKinds
    .map((kind) => {
      const status = DEPARTMENT_STATUS[kind];
      const name = labels[kind] || kind;
      return `
        <div class="status-row" style="--accent: ${status.accent}">
          <span class="status-row__name">${name}</span>
          <span class="status-row__meta">${status.status} · ${status.patients} pts</span>
        </div>
      `;
    })
    .join("");
}

export function departmentLabels() {
  return {
    emergency: "Emergency",
    outpatient: "Outpatient",
    pharmacy: "Pharmacy",
    lab: "Laboratory",
    icu: "ICU",
    mdt: "MDT",
    ward: "Ward",
  };
}

function drawGround(ctx, canvas, camera, palette) {
  ctx.fillStyle = palette.base;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  const zoom = camera.zoom || 1;
  const gridSize = TILE * zoom;
  const startX = positiveModulo(canvas.width / 2 - camera.x * zoom, gridSize);
  const startY = positiveModulo(canvas.height / 2 - camera.y * zoom, gridSize);
  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  for (let x = startX; x < canvas.width; x += gridSize) {
    ctx.beginPath();
    ctx.moveTo(Math.round(x) + 0.5, 0);
    ctx.lineTo(Math.round(x) + 0.5, canvas.height);
    ctx.stroke();
  }
  for (let y = startY; y < canvas.height; y += gridSize) {
    ctx.beginPath();
    ctx.moveTo(0, Math.round(y) + 0.5);
    ctx.lineTo(canvas.width, Math.round(y) + 0.5);
    ctx.stroke();
  }
}

function drawFloorPlate(ctx, camera) {
  const x = FLOOR_PLATE.x * TILE;
  const y = FLOOR_PLATE.y * TILE;
  const w = FLOOR_PLATE.w * TILE;
  const h = FLOOR_PLATE.h * TILE;
  const p = project(camera, x, y);
  const z = camera.zoom || 1;
  const sw = w * z;
  const sh = h * z;

  ctx.fillStyle = "rgba(238, 221, 180, 0.22)";
  ctx.fillRect(p.x + 10 * z, p.y + 12 * z, sw, sh);
  ctx.fillStyle = "rgba(242, 226, 184, 0.24)";
  ctx.fillRect(p.x, p.y, sw, sh);
  ctx.strokeStyle = "rgba(97, 67, 38, 0.55)";
  ctx.lineWidth = Math.max(2, 4 * z);
  ctx.strokeRect(p.x, p.y, sw, sh);
}

function drawRoom(ctx, camera, room) {
  const x = room.x * TILE;
  const y = room.y * TILE;
  const w = room.w * TILE;
  const h = room.h * TILE;
  const p = project(camera, x, y);
  const z = camera.zoom || 1;
  const sw = w * z;
  const sh = h * z;
  const wall = WALL_THICKNESS * z;

  ctx.fillStyle = "rgba(64, 43, 29, 0.22)";
  ctx.fillRect(p.x + 8 * z, p.y + 9 * z, sw, sh);
  ctx.fillStyle = shade(room.accent, 0.88);
  ctx.fillRect(p.x, p.y, sw, sh);
  ctx.fillStyle = "rgba(255, 255, 255, 0.16)";
  ctx.fillRect(p.x + wall, p.y + wall, sw - wall * 2, sh - wall * 2);
  ctx.fillStyle = "rgba(255, 250, 226, 0.16)";
  for (let yy = p.y + wall + 18 * z; yy < p.y + sh - wall; yy += 34 * z) {
    ctx.fillRect(p.x + wall + 14 * z, yy, sw - wall * 2 - 28 * z, Math.max(1, 3 * z));
  }
}

function drawWall(ctx, camera, wall) {
  const p = project(camera, wall.x, wall.y);
  const z = camera.zoom || 1;
  const w = wall.w * z;
  const h = wall.h * z;
  ctx.fillStyle = "#5b3d2b";
  ctx.fillRect(p.x, p.y, w, h);
  ctx.fillStyle = "rgba(255, 226, 166, 0.22)";
  if (wall.w > wall.h) ctx.fillRect(p.x, p.y, w, Math.max(1, 3 * z));
  else ctx.fillRect(p.x, p.y, Math.max(1, 3 * z), h);
}

function drawDoor(ctx, camera, door) {
  const p = project(camera, door.x, door.y);
  const z = camera.zoom || 1;
  ctx.fillStyle = "rgba(255, 230, 160, 0.74)";
  ctx.fillRect(p.x, p.y, door.w * z, door.h * z);
}

function drawProp(ctx, camera, prop) {
  const style = PROP_STYLES[prop.type] || PROP_STYLES.desk;
  const x = prop.x * TILE;
  const y = prop.y * TILE;
  const w = prop.w * TILE;
  const h = prop.h * TILE;
  const p = project(camera, x, y);
  const z = camera.zoom || 1;
  const sw = w * z;
  const sh = h * z;

  ctx.fillStyle = "rgba(45, 29, 18, 0.2)";
  ctx.fillRect(p.x + 4 * z, p.y + 5 * z, sw, sh);
  ctx.fillStyle = style.fill;
  ctx.fillRect(p.x, p.y, sw, sh);
  ctx.strokeStyle = style.trim;
  ctx.lineWidth = Math.max(1, 3 * z);
  ctx.strokeRect(p.x + 1.5 * z, p.y + 1.5 * z, sw - 3 * z, sh - 3 * z);

  if (prop.type === "bed") {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(p.x + 8 * z, p.y + 7 * z, 18 * z, sh - 14 * z);
  }
  if (prop.type === "screen") {
    ctx.fillStyle = style.trim;
    ctx.fillRect(p.x + 8 * z, p.y + 7 * z, sw - 16 * z, sh - 14 * z);
  }
  if (prop.type === "elevator") {
    ctx.strokeStyle = "#4e443b";
    ctx.beginPath();
    ctx.moveTo(p.x + sw / 2, p.y + 6 * z);
    ctx.lineTo(p.x + sw / 2, p.y + sh - 6 * z);
    ctx.stroke();
  }
}

function drawPatient(ctx, camera, patient, now, selectedEntityId) {
  if (patient.form === "consultation") {
    if (selectedEntityId === patient.id) drawEntitySelection(ctx, camera, patient.x - 24, patient.y + 8, now, 18, 24);
    if (patient.showConsultationDoctor !== false && selectedEntityId === consultationDoctorEntityId(patient)) {
      drawEntitySelection(ctx, camera, patient.x + 26, patient.y + 8, now, 18, 24);
    }
  } else if (selectedEntityId === patient.id) {
    drawEntitySelection(ctx, camera, patient.x, patient.y, now, patient.form === "bed" ? 34 : 22, patient.form === "bed" ? 16 : 24);
  }
  if (patient.form === "bed") drawBedPatient(ctx, camera, patient, now);
  else if (patient.form === "stretcher") drawStretcherPatient(ctx, camera, patient, now);
  else if (patient.form === "consultation") drawConsultationPatient(ctx, camera, patient, now);
  else if (patient.form === "waiting") drawWaitingPatient(ctx, camera, patient, now);
  else drawWalkingPatient(ctx, camera, patient, now);
}

function consultationDoctorEntityId(patient) {
  return `${patient.id}::doctor`;
}

function drawBedPatient(ctx, camera, patient, now) {
  const p = project(camera, patient.x, patient.y);
  const s = patientScale(camera);
  const breathing = Math.sin(now / 520 + patient.id.length) * 0.8;

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y));
  ctx.scale(s, s);
  ctx.fillStyle = "rgba(33, 22, 14, 0.18)";
  ctx.fillRect(-19, 13, 44, 6);
  ctx.fillStyle = "#fff7e1";
  ctx.fillRect(-20, -7, 45, 18);
  ctx.strokeStyle = "#8f6d55";
  ctx.lineWidth = 2;
  ctx.strokeRect(-20, -7, 45, 18);
  ctx.fillStyle = patient.blanket || "#7fbfa2";
  ctx.fillRect(-4, -5 + breathing, 26, 14);
  ctx.fillStyle = patient.skin || "#f0c49a";
  ctx.fillRect(-17, -4, 10, 10);
  ctx.fillStyle = "#3c3340";
  ctx.fillRect(-18, -6, 11, 3);
  ctx.fillStyle = "#335a78";
  ctx.fillRect(29, -8, 7, 13);
  ctx.fillStyle = "#8ef0c5";
  ctx.fillRect(31, -5, 3, 5);
  ctx.restore();
}

function drawConsultationPatient(ctx, camera, patient, now) {
  const p = project(camera, patient.x, patient.y);
  const s = patientScale(camera);
  const talk = Math.sin(now / 360 + patient.id.length) > 0 ? 1 : 0;
  const showDoctor = patient.showConsultationDoctor !== false;

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y));
  ctx.scale(s, s);
  drawSeatedPerson(ctx, -16, 5, patient.color || "#5f8ec9", "#f2c799");
  if (showDoctor) drawSeatedStaff(ctx, 18, 5, "doctor", patient.doctorGender || "female");
  ctx.fillStyle = "#b98154";
  ctx.fillRect(-4, 0, 10, 18);
  ctx.fillStyle = talk ? "#fff5d0" : "#e7f3ff";
  roundedRect(ctx, -16, -28, 34, 14, 5);
  ctx.fill();
  ctx.fillStyle = "#6a5039";
  ctx.fillRect(-9, -22, 5, 3);
  ctx.fillRect(0, -22, 5, 3);
  ctx.restore();
}

function drawWaitingPatient(ctx, camera, patient, now) {
  const p = project(camera, patient.x, patient.y);
  const s = patientScale(camera);
  const idle = Math.sin(now / 700 + patient.id.length) * 0.7;

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y + idle));
  ctx.scale(s, s);
  ctx.fillStyle = "#5f7897";
  ctx.fillRect(-15, 1, 30, 7);
  ctx.fillStyle = "#6f86a5";
  ctx.fillRect(-16, 10, 32, 7);
  ctx.fillStyle = "rgba(33, 22, 14, 0.2)";
  ctx.fillRect(-11, 17, 24, 4);
  drawSeatedPerson(ctx, 0, 2, patient.color || "#7899c6", "#f2c799");
  ctx.fillStyle = "#334b62";
  ctx.fillRect(-10, 15, 5, 7);
  ctx.fillRect(5, 15, 5, 7);
  ctx.restore();
}

function drawWalkingPatient(ctx, camera, patient, now) {
  const phase = now / 180 + (patient.phase || 0);
  const step = Math.sin(phase);
  const p = project(camera, patient.x + step * 8, patient.y);
  const s = patientScale(camera);

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y + Math.abs(step) * -1.5));
  ctx.scale(s, s);
  ctx.fillStyle = "rgba(33, 22, 14, 0.2)";
  ctx.beginPath();
  ctx.ellipse(1, 15, 12, 4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = patient.color || "#5f8ec9";
  ctx.fillRect(-7, -1, 14, 17);
  ctx.fillStyle = "#f2c799";
  ctx.fillRect(-6, -14, 12, 12);
  ctx.fillStyle = "#3c3340";
  ctx.fillRect(-7, -16, 14, 4);
  ctx.fillStyle = "#244259";
  ctx.fillRect(-8, 14, 5, 9 + step * 2);
  ctx.fillRect(3, 14, 5, 9 - step * 2);
  ctx.restore();
}

function drawStretcherPatient(ctx, camera, patient, now) {
  const p = project(camera, patient.x, patient.y);
  const s = patientScale(camera);
  const isTransporting = patient.transportMode === "stretcher";
  const bob = isTransporting ? Math.sin((patient.movePhase || now / 120) * 2) * 0.8 : 0;
  const facing = patient.facing || "right";
  const porter = porterOffset(facing);

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y + bob));
  ctx.scale(s, s);

  ctx.fillStyle = "rgba(33, 22, 14, 0.2)";
  ctx.beginPath();
  ctx.ellipse(2, 17, 31, 6, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#dfe8ee";
  ctx.fillRect(-24, -7, 48, 16);
  ctx.strokeStyle = "#6f8795";
  ctx.lineWidth = 2;
  ctx.strokeRect(-24, -7, 48, 16);
  ctx.fillStyle = "#b7c9d5";
  ctx.fillRect(-27, 8, 54, 4);
  ctx.fillStyle = "#46545d";
  ctx.fillRect(-19, 13, 5, 5);
  ctx.fillRect(14, 13, 5, 5);

  ctx.fillStyle = patient.blanket || "#d46d8e";
  ctx.fillRect(-5, -5, 24, 12);
  ctx.fillStyle = patient.skin || "#f2c799";
  ctx.fillRect(-20, -4, 10, 10);
  ctx.fillStyle = "#3c3340";
  ctx.fillRect(-21, -6, 11, 3);

  if (isTransporting) drawPorter(ctx, porter.x, porter.y, facing);
  ctx.restore();
}

function drawPorter(ctx, x, y, facing) {
  ctx.fillStyle = "#80b78a";
  ctx.fillRect(x - 7, y - 1, 14, 18);
  ctx.fillStyle = "#f2c799";
  ctx.fillRect(x - 6, y - 14, 12, 12);
  ctx.fillStyle = "#2f3440";
  ctx.fillRect(x - 7, y - 16, 14, 4);
  ctx.fillStyle = "#4e6a52";
  ctx.fillRect(x - 9, y + 15, 5, 8);
  ctx.fillRect(x + 4, y + 15, 5, 8);
  ctx.fillStyle = "#5f8a68";
  if (facing === "left") ctx.fillRect(x - 14, y + 2, 7, 5);
  else if (facing === "right") ctx.fillRect(x + 7, y + 2, 7, 5);
  else {
    ctx.fillRect(x - 13, y + 2, 6, 5);
    ctx.fillRect(x + 7, y + 2, 6, 5);
  }
}

function porterOffset(facing) {
  if (facing === "left") return { x: 33, y: 0 };
  if (facing === "right") return { x: -33, y: 0 };
  if (facing === "up") return { x: 0, y: 28 };
  return { x: 0, y: -26 };
}

function drawStaff(ctx, camera, member, now, selected = false) {
  if (selected) drawEntitySelection(ctx, camera, member.x, member.y, now, 22, 26);
  if (member.pose === "seated") {
    drawSeatedStaffAt(ctx, camera, member, now);
    return;
  }
  drawStandingStaff(ctx, camera, member, now);
}

function drawStandingStaff(ctx, camera, member, now) {
  const phase = now / 220 + (member.phase || 0);
  const walk = member.pose === "walking" ? Math.sin(phase) : 0;
  const monitorLean = member.pose === "monitoring" ? Math.sin(now / 640 + member.id.length) * 0.8 : 0;
  const p = project(camera, member.x + walk * 7, member.y + monitorLean);
  const s = patientScale(camera);

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y + Math.abs(walk) * -1.2));
  ctx.scale(s, s);
  drawStaffShadow(ctx);
  drawStandingStaffShape(ctx, member.role, member.gender, walk);
  ctx.restore();
}

function drawSeatedStaffAt(ctx, camera, member, now) {
  const p = project(camera, member.x, member.y);
  const s = patientScale(camera);
  const idle = Math.sin(now / 690 + member.id.length) * 0.5;

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y + idle));
  ctx.scale(s, s);
  drawSeatedStaff(ctx, 0, 2, member.role, member.gender);
  ctx.restore();
}

function drawStandingStaffShape(ctx, role, gender, walk = 0) {
  const uniform = role === "porter" ? "#80b78a" : role === "nurse" ? "#f0a1c1" : "#fff9ef";
  const trim = role === "porter" ? "#4f7f59" : role === "nurse" ? "#c95d8e" : "#8eb7cc";
  const pants = role === "porter" ? "#4e6a52" : role === "nurse" ? "#8d5f82" : "#5f7893";

  ctx.fillStyle = uniform;
  ctx.fillRect(-8, -1, 16, 20);
  ctx.fillStyle = trim;
  ctx.fillRect(-8, 5, 16, 3);
  if (role === "doctor") {
    ctx.strokeStyle = "#6d8fa2";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-3, 1);
    ctx.lineTo(1, 8);
    ctx.lineTo(5, 1);
    ctx.stroke();
  } else if (role === "nurse") {
    ctx.fillStyle = "#fff6fb";
    ctx.fillRect(-6, -18, 12, 4);
    ctx.fillStyle = trim;
    ctx.fillRect(-2, -18, 4, 4);
  } else if (role === "porter") {
    ctx.fillStyle = "#eaf5df";
    ctx.fillRect(-5, 2, 10, 3);
  }

  ctx.fillStyle = "#f2c799";
  ctx.fillRect(-6, -15, 12, 12);
  drawHair(ctx, gender);

  ctx.fillStyle = trim;
  ctx.fillRect(-13, 2, 5, 12);
  ctx.fillRect(8, 2, 5, 12);
  ctx.fillStyle = pants;
  ctx.fillRect(-8, 17, 6, 10 + walk * 2);
  ctx.fillRect(2, 17, 6, 10 - walk * 2);
}

function drawSeatedStaff(ctx, x, y, role, gender) {
  const uniform = role === "porter" ? "#80b78a" : role === "nurse" ? "#f0a1c1" : "#fff9ef";
  const trim = role === "porter" ? "#4f7f59" : role === "nurse" ? "#c95d8e" : "#8eb7cc";
  const pants = role === "porter" ? "#4e6a52" : role === "nurse" ? "#8d5f82" : "#5f7893";

  ctx.fillStyle = uniform;
  ctx.fillRect(x - 7, y - 4, 14, 15);
  ctx.fillStyle = trim;
  ctx.fillRect(x - 7, y + 4, 14, 3);
  ctx.fillStyle = "#f2c799";
  ctx.fillRect(x - 6, y - 15, 12, 11);
  drawHair(ctx, gender, x, y);
  if (role === "nurse") {
    ctx.fillStyle = "#fff6fb";
    ctx.fillRect(x - 6, y - 18, 12, 4);
    ctx.fillStyle = trim;
    ctx.fillRect(x - 2, y - 18, 4, 4);
  }
  ctx.fillStyle = pants;
  ctx.fillRect(x - 9, y + 9, 6, 6);
  ctx.fillRect(x + 3, y + 9, 6, 6);
}

function drawStaffShadow(ctx) {
  ctx.fillStyle = "rgba(33, 22, 14, 0.2)";
  ctx.beginPath();
  ctx.ellipse(1, 16, 12, 4, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawEntitySelection(ctx, camera, x, y, now, rx, ry) {
  const p = project(camera, x, y);
  const pulse = 0.85 + Math.sin(now / 180) * 0.12;
  const z = patientScale(camera);

  ctx.save();
  ctx.translate(Math.round(p.x), Math.round(p.y));
  ctx.scale(z, z);
  ctx.strokeStyle = "#fff0a8";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.ellipse(0, 4, rx * pulse, ry * pulse, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

function drawHair(ctx, gender, x = 0, y = 0) {
  ctx.fillStyle = "#3a3037";
  if (gender === "female") {
    ctx.fillRect(x - 8, y - 17, 16, 5);
    ctx.fillRect(x - 8, y - 12, 4, 8);
    ctx.fillRect(x + 4, y - 12, 4, 8);
    return;
  }
  ctx.fillRect(x - 7, y - 17, 14, 4);
  ctx.fillRect(x - 5, y - 19, 10, 3);
}

function drawSeatedPerson(ctx, x, y, body, skin) {
  ctx.fillStyle = body;
  ctx.fillRect(x - 7, y - 4, 14, 15);
  ctx.fillStyle = skin;
  ctx.fillRect(x - 6, y - 15, 12, 11);
  ctx.fillStyle = "#3c3340";
  ctx.fillRect(x - 7, y - 17, 14, 4);
  ctx.fillStyle = "#263d55";
  ctx.fillRect(x - 9, y + 9, 6, 6);
  ctx.fillRect(x + 3, y + 9, 6, 6);
}

function patientScale(camera) {
  return Math.max(0.72, Math.min(1.1, camera.zoom || 1));
}

function drawRoomLabel(ctx, camera, room) {
  const label = room.label;
  const x = room.x * TILE + room.w * TILE / 2;
  const y = room.y * TILE + 26;
  const p = project(camera, x, y);
  const fontSize = 12;

  ctx.save();
  ctx.font = `800 ${fontSize}px Trebuchet MS, PingFang SC, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const metrics = ctx.measureText(label);
  const width = Math.ceil(metrics.width) + 18;
  roundedRect(ctx, Math.round(p.x - width / 2), Math.round(p.y - 12), width, 24, 6);
  ctx.fillStyle = "rgba(49, 34, 24, 0.75)";
  ctx.fill();
  ctx.fillStyle = "#fff3cf";
  ctx.fillText(label, Math.round(p.x), Math.round(p.y));
  ctx.restore();
}

function drawPlayerSprite(ctx, camera, player) {
  const p = project(camera, player.x, player.y);
  const z = camera.zoom || 1;
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.scale(z, z);
  ctx.fillStyle = "rgba(31, 20, 13, 0.24)";
  ctx.beginPath();
  ctx.ellipse(2, 15, 13, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#335a78";
  ctx.fillRect(-8, -1, 16, 20);
  ctx.fillStyle = "#f6c487";
  ctx.fillRect(-7, -15, 14, 14);
  ctx.fillStyle = "#2d2b33";
  ctx.fillRect(-8, -17, 16, 5);
  ctx.fillStyle = "#f7f1d5";
  ctx.fillRect(-5, 3, 10, 5);

  ctx.fillStyle = "#244259";
  if (player.facing === "left") ctx.fillRect(-13, 2, 5, 12);
  else if (player.facing === "right") ctx.fillRect(8, 2, 5, 12);
  else {
    ctx.fillRect(-12, 2, 5, 12);
    ctx.fillRect(7, 2, 5, 12);
  }
  ctx.restore();
}

function project(camera, x, y) {
  const zoom = camera.zoom || 1;
  return {
    x: Math.round((x - camera.x) * zoom + (camera.viewportWidth || 1280) / 2),
    y: Math.round((y - camera.y) * zoom + (camera.viewportHeight || 720) / 2),
  };
}

function positiveModulo(value, modulus) {
  return ((value % modulus) + modulus) % modulus;
}

function roundedRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function shade(hex, amount) {
  const value = Number.parseInt(hex.slice(1), 16);
  const r = Math.min(255, Math.round(((value >> 16) & 255) * amount + 255 * (1 - amount)));
  const g = Math.min(255, Math.round(((value >> 8) & 255) * amount + 255 * (1 - amount)));
  const b = Math.min(255, Math.round((value & 255) * amount + 255 * (1 - amount)));
  return `rgb(${r}, ${g}, ${b})`;
}
