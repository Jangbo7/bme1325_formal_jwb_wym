import { FLOOR_PLATE, PROPS, ROOMS, TILE, WORLD, getFloor, getPropsForFloor, getRoomsForFloor, loadMapConfig } from "./map.js";
import { createMapAdmin } from "./map-admin.js";
import { createRulesAdmin } from "./rules-admin.js";
import { fetchHospitalEvents, fetchHospitalSnapshot, fetchPersonProfile } from "./hospital-api.js?v=queue-delete-20260612";
import { createRoomPath } from "./pathfinding.js";
import { PATIENTS } from "./patients.js?v=profile-guard-20260612";
import { STAFF } from "./staff.js";
import {
  beginFloorTransition,
  buildGeometry,
  buildPropColliders,
  createCamera,
  createPlayer,
  roomAtPoint,
  updateFloorTransition,
  updatePlayer,
} from "./runtime.js";
import {
  clearCanvas,
  departmentLabels,
  drawFloorScene,
  drawMinimap,
  drawTransitionWash,
  minimapPointToWorld,
  renderStatusRows,
} from "./render.js?v=stretcher-static-20260612";

const canvas = document.getElementById("hospitalCanvas");
const ctx = canvas.getContext("2d");
const miniMapCanvas = document.getElementById("miniMapCanvas");
const miniMapCtx = miniMapCanvas.getContext("2d");
const floorTitle = document.getElementById("floorTitle");
const floorSubtitle = document.getElementById("floorSubtitle");
const roomReadout = document.getElementById("roomReadout");
const departmentSnapshot = document.getElementById("departmentSnapshot");
const personInfo = document.getElementById("personInfo");
const roomInfo = document.getElementById("roomInfo");
const floorButtons = Array.from(document.querySelectorAll("[data-floor]"));
const zoomInButton = document.getElementById("zoomIn");
const zoomOutButton = document.getElementById("zoomOut");
const zoomFitButton = document.getElementById("zoomFit");
const mapRefreshButton = document.getElementById("mapRefresh");
const mapAdminOpenButton = document.getElementById("mapAdminOpen");
const rulesAdminOpenButton = document.getElementById("rulesAdminOpen");
const mapAdminPanel = document.getElementById("mapAdmin");
const mapAdminCancelButton = document.getElementById("mapAdminCancel");
const mapAdminSaveButton = document.getElementById("mapAdminSave");
const mapAdminFloors = document.getElementById("mapAdminFloors");
const mapAdminFloorTitle = document.getElementById("mapAdminFloorTitle");
const mapAdminStatus = document.getElementById("mapAdminStatus");
const mapAdminRoomList = document.getElementById("mapAdminRoomList");
const mapAdminAddForm = document.getElementById("mapAdminAddForm");
const mapAdminRoomName = document.getElementById("mapAdminRoomName");
const rulesAdminPanel = document.getElementById("rulesAdmin");
const rulesAdminBackButton = document.getElementById("rulesAdminBack");
const rulesAdminSaveButton = document.getElementById("rulesAdminSave");
const rulesAdminCategories = document.getElementById("rulesAdminCategories");
const rulesAdminList = document.getElementById("rulesAdminList");
const rulesAdminEditor = document.getElementById("rulesAdminEditor");
const rulesAdminStatus = document.getElementById("rulesAdminStatus");
const zoomLabel = document.getElementById("zoomLabel");
const labels = departmentLabels();
const PERSON_SPACING = 72;
const SLOT_CLEARANCE = 34;
const STAFF_BED_MARGIN = 8;
const STAFF_BED_SCAN_STEP = TILE * 0.5;

const geometry = buildGeometry();
let propColliders = buildPropColliders(PROPS);
const initialFloor = getFloor(1);
const player = createPlayer(initialFloor.spawn, initialFloor.id);
const state = {
  activeFloor: initialFloor.id,
  camera: createCamera(initialFloor.spawn),
  cameraControl: {
    mode: "fit",
    flight: null,
  },
  geometry,
  keys: new Set(),
  patients: PATIENTS.map((patient) => ({ ...patient, baseForm: patient.form })),
  staff: STAFF.map((member) => ({ ...member })),
  patientMoves: new Map(),
  porterMoves: new Map(),
  player,
  playerTravel: null,
  selectedEntityId: null,
  selectedInfoRoomId: null,
  selectedRoomId: null,
  lastEventSeq: 0,
  pollingEvents: false,
  transition: null,
};

let lastFrame = performance.now();
let hudFloor = null;
let profileRequestId = 0;

applyFitView();
syncHud();
initializeHospitalState();
const mapAdmin = createMapAdmin({
  panel: mapAdminPanel,
  openButton: mapAdminOpenButton,
  cancelButton: mapAdminCancelButton,
  saveButton: mapAdminSaveButton,
  floorTabs: mapAdminFloors,
  floorTitle: mapAdminFloorTitle,
  status: mapAdminStatus,
  roomList: mapAdminRoomList,
  addForm: mapAdminAddForm,
  roomNameInput: mapAdminRoomName,
  onSaved: async (result) => {
    rebuildMapAfterConfigChange(result.mode === "file" ? "Map saved to map-config.json" : "Map saved in browser storage");
  },
});
const rulesAdmin = createRulesAdmin({
  panel: rulesAdminPanel,
  openButton: rulesAdminOpenButton,
  backButton: rulesAdminBackButton,
  saveButton: rulesAdminSaveButton,
  categoryList: rulesAdminCategories,
  ruleList: rulesAdminList,
  editor: rulesAdminEditor,
  status: rulesAdminStatus,
});
if (window.location.hash === "#admin") mapAdmin.open();
if (window.location.hash === "#rules") rulesAdmin.open();
requestAnimationFrame(loop);

window.addEventListener("keydown", (event) => {
  if (isMovementKey(event.code)) {
    event.preventDefault();
    state.playerTravel = null;
    state.selectedRoomId = null;
    state.keys.add(event.code);
  }
});

window.addEventListener("keyup", (event) => {
  if (isMovementKey(event.code)) state.keys.delete(event.code);
});

floorButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const targetFloor = Number(button.dataset.floor);
    const floor = getFloor(targetFloor);
    resetCameraControl();
    beginFloorTransition(state, targetFloor, floor.spawn);
    applyFitView();
    syncHud(targetFloor);
  });
});

zoomInButton.addEventListener("click", () => {
  fitWholeFloor();
});

zoomOutButton.addEventListener("click", () => {
  fitWholeFloor();
});

zoomFitButton.addEventListener("click", () => {
  fitWholeFloor();
});

mapRefreshButton.addEventListener("click", () => {
  refreshMapConfig();
});

canvas.addEventListener("pointerdown", (event) => {
  if (state.transition) return;
  event.preventDefault();
});

canvas.addEventListener("click", (event) => {
  if (state.transition) return;
  handleCanvasClick(canvasPoint(event));
});

miniMapCanvas.addEventListener("click", (event) => {
  if (state.transition) return;
  handleMinimapClick(canvasPoint(event, miniMapCanvas), miniMapCanvas);
});

function loop(now) {
  const delta = Math.min(0.033, (now - lastFrame) / 1000);
  lastFrame = now;

  const transition = state.transition;
  const transitionProgress = transition ? Math.min(1, (now - transition.startedAt) / transition.duration) : 0;
  const collisions = [...state.geometry.walls, ...propColliders];

  updatePlayer({
    player: state.player,
    keys: state.keys,
    delta,
    collisions,
    movementLocked: Boolean(state.transition) || Boolean(state.playerTravel),
  });
  updatePlayerTravel(delta);
  updatePatientMoves(delta);
  updatePorterMoves(delta);
  updateCameraControl(now);

  render(transition, transitionProgress, now);
  const previousFloor = state.activeFloor;
  updateFloorTransition(state, now);
  if (previousFloor !== state.activeFloor || !state.transition) syncHud(state.activeFloor);

  requestAnimationFrame(loop);
}

async function initializeHospitalState() {
  await refreshHospitalSnapshot({ preserveMoves: false });
  window.setInterval(pollHospitalEvents, 900);
}

async function refreshHospitalSnapshot({ preserveMoves = true } = {}) {
  try {
    const snapshot = await fetchHospitalSnapshot();
    applyHospitalSnapshot(snapshot, { preserveMoves });
    state.lastEventSeq = Math.max(state.lastEventSeq, snapshot.eventSeq || 0);
  } catch (error) {
    console.warn("Hospital snapshot unavailable; using local seed data.", error);
  }
}

function applyHospitalSnapshot(snapshot, { preserveMoves = true } = {}) {
  const movingIds = preserveMoves ? new Set(state.patientMoves.keys()) : new Set();
  const currentById = new Map(state.patients.map((patient) => [patient.id, patient]));
  state.patients = (snapshot.patients || []).map((patient) => {
    const current = currentById.get(patient.id);
    if (movingIds.has(patient.id) && current) return current;
    return {
      ...patient,
      baseForm: patient.baseForm || patient.form,
      phase: patient.phase || current?.phase || 0,
    };
  });
  state.staff = (snapshot.staff || []).map((member) => {
    const returning = returningPorterForSnapshotMember(member);
    if (returning) return returning;
    return {
      ...member,
      role: member.role || member.type,
      phase: member.phase || 0,
    };
  });
  reflowPatients();
  reflowStaff();
  if (state.selectedInfoRoomId) {
    const room = roomById(state.selectedInfoRoomId);
    if (room) renderRoomInfo(room);
  }
}

function returningPorterForSnapshotMember(member) {
  const ids = [member.id, member.staffId, member.staff_id, member.employeeId, member.employee_id].filter(Boolean);
  for (const id of ids) {
    const move = state.porterMoves.get(id);
    if (move?.porter) return move.porter;
  }
  return null;
}

async function pollHospitalEvents() {
  if (state.pollingEvents) return;
  state.pollingEvents = true;
  try {
    const result = await fetchHospitalEvents(state.lastEventSeq);
    for (const event of result.events || []) {
      state.lastEventSeq = Math.max(state.lastEventSeq, event.eventSeq || 0);
      if (event.accepted && event.animationPlan) startBackendPatientMove(event);
      if (event.accepted && !event.animationPlan && (event.eventId === "PATIENT_DELETE" || event.snapshotRefresh)) {
        refreshHospitalSnapshot({ preserveMoves: false });
      }
    }
  } catch (error) {
    console.warn("Hospital event polling unavailable.", error);
  } finally {
    state.pollingEvents = false;
  }
}

function startBackendPatientMove(event) {
  const patient = findPatient(event.patientId);
  const plan = event.animationPlan;
  if (!patient || state.patientMoves.has(patient.id)) return;
  const route = createPatientRouteFromPlan(patient, plan, event);
  if (!route) {
    roomReadout.textContent = `No route found for ${event.eventId}`;
    refreshHospitalSnapshot({ preserveMoves: false });
    return;
  }

  patient.form = transferForm(plan);
  patient.transportMode = plan.transport || null;
  patient.movePhase = 0;
  route.porterId = plan.porterId || null;
  route.porterReturn = plan.porterReturn || null;
  state.patientMoves.set(patient.id, route);
  state.selectedEntityId = patient.id;
  state.selectedRoomId = plan.toRoomId;
  updateRoomReadout();
}

function render(transition, progress, now) {
  const visibleFloor = transition ? transition.toFloor : state.activeFloor;
  clearCanvas(ctx, canvas, visibleFloor);

  if (transition) {
    drawFloorScene(ctx, canvas, sceneForFloor(transition.fromFloor, 1 - progress, false, now));
    drawFloorScene(ctx, canvas, sceneForFloor(transition.toFloor, progress, true, now));
    drawTransitionWash(ctx, canvas, progress);
    renderMiniMap(transition.toFloor);
    return;
  }

  drawFloorScene(ctx, canvas, sceneForFloor(state.activeFloor, 1, true, now));
  renderMiniMap(state.activeFloor);
  updateRoomReadout();
}

function renderMiniMap(floorId) {
  miniMapCtx.clearRect(0, 0, miniMapCanvas.width, miniMapCanvas.height);
  drawMinimap(miniMapCtx, miniMapCanvas, {
    floorId,
    rooms: getRoomsForFloor(floorId),
    player: state.player,
    selectedRoomId: state.selectedRoomId,
  });
}

function sceneForFloor(floorId, alpha, drawPlayer, now) {
  return {
    alpha,
    camera: state.camera,
    doors: state.geometry.doors,
    drawPlayer,
    floorId,
    now,
    patients: patientsForFloor(floorId),
    player: state.player,
    props: getPropsForFloor(floorId),
    rooms: getRoomsForFloor(floorId),
    selectedEntityId: state.selectedEntityId,
    staff: staffForFloor(floorId),
    walls: state.geometry.walls,
  };
}

function fitWholeFloor() {
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  state.selectedRoomId = null;
  applyFitView();
  updateZoomControls();
  updateRoomReadout();
}

function syncHud(previewFloor = state.activeFloor) {
  hudFloor = previewFloor;

  const floor = getFloor(previewFloor);
  floorTitle.textContent = floor.label;
  floorSubtitle.textContent = floor.subtitle;
  renderStatusRows(departmentSnapshot, floor, labels);

  floorButtons.forEach((button) => {
    const isActive = Number(button.dataset.floor) === previewFloor;
    button.classList.toggle("is-active", isActive);
    button.disabled = Boolean(state.transition);
  });

  updateRoomReadout();
  updateZoomControls();
}

function updateRoomReadout() {
  const selectedRoom = ROOMS.find((item) => item.id === state.selectedRoomId);
  if (state.cameraControl.mode === "fit") {
    const transitionSuffix = state.transition ? " · switching floors" : "";
    if (selectedRoom) {
      const hasPatientMove = Array.from(state.patientMoves.values()).some((move) => move.targetRoomId === selectedRoom.id);
      const prefix = state.playerTravel ? "Moving player to" : hasPatientMove ? "Moving patient to" : "Target room";
      roomReadout.textContent = `${prefix}: ${selectedRoom.label}${transitionSuffix}`;
      return;
    }
    roomReadout.textContent = `Current view: Full floor${transitionSuffix}`;
    return;
  }

  const room = roomAtPoint(ROOMS, state.player);
  const prefix = selectedRoom ? "Focused area" : "Current area";
  const area = selectedRoom ? selectedRoom.label : room ? room.label : "Hallway";
  const transitionSuffix = state.transition ? " · switching floors" : "";
  roomReadout.textContent = `${prefix}: ${area}${transitionSuffix}`;
}

function isMovementKey(code) {
  return ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "KeyW", "KeyA", "KeyS", "KeyD"].includes(code);
}

function updateCameraControl() {
  if (state.transition) return;

  state.cameraControl.mode = "fit";
  applyFitView();
}

function handleMinimapClick(point, targetCanvas) {
  const hit = minimapPointToWorld(targetCanvas, point);
  if (!hit?.world) return;

  const targetRoom = roomAtWorldPoint(state.activeFloor, hit.world.x, hit.world.y);
  if (!targetRoom) return;

  const path = createRoomPath({
    floorId: state.activeFloor,
    start: { x: state.player.x, y: state.player.y },
    targetRoom,
    collisions: [...state.geometry.walls, ...propColliders],
  });
  if (!path) {
    roomReadout.textContent = `No route to: ${targetRoom.label}`;
    return;
  }

  state.selectedRoomId = targetRoom.id;
  state.keys.clear();
  state.playerTravel = {
    roomId: targetRoom.id,
    waypointIndex: 0,
    waypoints: path,
    speed: 260,
  };
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  updateRoomReadout();
}

function handleCanvasClick(point) {
  const hitEntity = entityAtCanvasPoint(point);
  if (hitEntity) {
    clearRoomSelection();
    state.selectedEntityId = hitEntity.id;
    state.selectedRoomId = null;
    renderPersonLoading(hitEntity);
    const requestId = ++profileRequestId;
    fetchPersonProfile(hitEntity.profileId || hitEntity.id)
      .then((profile) => {
        if (requestId !== profileRequestId) return;
        renderPersonProfile(profile, hitEntity);
      })
      .catch((error) => {
        if (requestId !== profileRequestId) return;
        renderPersonError(error.message);
      });
    return;
  }

  const world = worldPointFromCanvas(point);
  const hitRoom = roomAtWorldPoint(state.activeFloor, world.x, world.y);
  if (hitRoom) {
    clearPersonSelection();
    state.selectedInfoRoomId = hitRoom.id;
    renderRoomInfo(hitRoom);
    return;
  }

  clearPersonSelection();
  clearRoomSelection();
}

function renderRoomInfo(room) {
  state.selectedRoomId = null;
  roomInfo.className = "room-info";
  roomInfo.innerHTML = [
    roomInfoRow("Room", room.label),
    roomInfoRow("Room ID", room.roomCode),
    roomInfoRow("Patients", String(patientCountInRoom(room))),
    roomInfoRow("Beds", String(room.features?.bed || 0)),
    roomInfoRow("Workstations", formatRoomFeatures(room)),
  ].join("");
}

function clearRoomSelection() {
  state.selectedInfoRoomId = null;
  roomInfo.className = "room-info room-info--empty";
  roomInfo.textContent = "Click a room.";
}

function roomInfoRow(label, value) {
  return `
    <div class="room-info__row">
      <span class="room-info__label">${label}</span>
      <span class="room-info__value">${value}</span>
    </div>
  `;
}

function formatRoomFeatures(room) {
  const features = room.features || {};
  const parts = [
    ["desk", "desk"],
    ["reception", "reception"],
    ["screen", "screen"],
    ["sofa", "sofa"],
    ["cabinet", "cabinet"],
    ["table", "table"],
  ]
    .filter(([key]) => features[key])
    .map(([key, label]) => `${features[key]} ${label}`);
  return parts.length ? parts.join(" · ") : "None";
}

function patientCountInRoom(room) {
  return clickablePatientsForFloor(room.floor).filter((patient) => {
    if (patient.entityType !== "patient") return false;
    return pointInsideRoom(patient, room);
  }).length;
}

function patientsForFloor(floorId) {
  return state.patients
    .filter((patient) => patient.floor === floorId)
    .map((patient) => {
      if (patient.form !== "consultation") return patient;
      const doctorId = patient.doctorProfileId || patient.doctor_profile_id;
      return {
        ...patient,
        showConsultationDoctor: !(doctorId && hasStaffProfile(doctorId)),
      };
    });
}

function pointInsideRoom(point, room) {
  const rx = room.x * TILE;
  const ry = room.y * TILE;
  const rw = room.w * TILE;
  const rh = room.h * TILE;
  return point.x >= rx && point.x <= rx + rw && point.y >= ry && point.y <= ry + rh;
}

function entityAtCanvasPoint(point) {
  const world = worldPointFromCanvas(point);
  const entities = [
    ...staffForFloor(state.activeFloor).map((entity) => ({ ...entity, entityType: entity.role || entity.type })),
    ...clickablePatientsForFloor(state.activeFloor),
  ];

  return entities
    .map((entity) => ({ entity, score: entityHitScore(entity, world) }))
    .filter((hit) => hit.score <= 1)
    .sort((a, b) => a.score - b.score)[0]?.entity || null;
}

function entityHitScore(entity, world) {
  const shape = entity.hitShape || (entity.form === "bed"
    ? { rx: 36, ry: 18 }
    : entity.form === "waiting"
      ? { rx: 26, ry: 24 }
      : { rx: 24, ry: 28 });
  const dx = world.x - entity.x;
  const dy = world.y - entity.y;
  return (dx / shape.rx) ** 2 + (dy / shape.ry) ** 2;
}

function clickablePatientsForFloor(floorId) {
  return patientsForFloor(floorId).flatMap((patient) => {
    if (patient.form !== "consultation") return [{ ...patient, entityType: "patient" }];
    const doctorId = patient.doctorProfileId || patient.doctor_profile_id;
    const showConsultationDoctor = patient.showConsultationDoctor !== false;
    const entities = [
      {
        ...patient,
        entityType: "patient",
        x: patient.x - 24,
        y: patient.y + 8,
        hitShape: { rx: 18, ry: 24 },
      },
    ];
    if (doctorId && showConsultationDoctor) {
      entities.push({
        id: consultationDoctorEntityId(patient),
        profileId: doctorId,
        floor: patient.floor,
        entityType: "doctor",
        x: patient.x + 26,
        y: patient.y + 8,
        hitShape: { rx: 18, ry: 24 },
      });
    }
    return entities;
  });
}

function consultationDoctorEntityId(patient) {
  return `${patient.id}::doctor`;
}

function hasStaffProfile(id) {
  return state.staff.some((member) => {
    return member.id === id ||
      member.staffId === id ||
      member.staff_id === id ||
      member.employeeId === id ||
      member.employee_id === id;
  });
}

function transferForm(plan) {
  if (plan.patientFormDuringMove === "stretcher" || plan.transport === "stretcher") return "stretcher";
  if (plan.patientFormDuringMove === "waiting") return "waiting";
  return "walking";
}

async function refreshMapConfig() {
  if (state.transition) return;
  mapRefreshButton.disabled = true;
  const previousLabel = roomReadout.textContent;
  roomReadout.textContent = "Refreshing map-config.json...";

  try {
    await loadMapConfig({ bustCache: true });
    rebuildMapAfterConfigChange("Map refreshed from map-config.json");
  } catch (error) {
    console.error(error);
    roomReadout.textContent = `Map refresh failed: ${error.message}`;
  } finally {
    window.setTimeout(() => {
      mapRefreshButton.disabled = false;
      if (roomReadout.textContent === "Map refreshed from map-config.json") updateRoomReadout();
      if (roomReadout.textContent.startsWith("Map refresh failed")) return;
      if (previousLabel && roomReadout.textContent === "Refreshing map-config.json...") roomReadout.textContent = previousLabel;
    }, 450);
  }
}

function rebuildMapAfterConfigChange(message) {
  state.geometry = buildGeometry();
  propColliders = buildPropColliders(PROPS);
  state.patientMoves.clear();
  state.keys.clear();
  state.playerTravel = null;
  state.transition = null;

  const floor = getFloor(state.activeFloor) || getFloor(1);
  state.activeFloor = floor.id;
  state.player.floor = floor.id;
  state.player.x = floor.spawn.x;
  state.player.y = floor.spawn.y;
  reflowPatients();
  reflowStaff();
  resetCameraControl();
  applyFitView();
  syncHud(floor.id);
  roomReadout.textContent = message;
}

function reflowPatients() {
  const patientsByRoom = new Map();
  state.patients.forEach((patient) => {
    if (!patient.roomId || state.patientMoves.has(patient.id)) return;
    const room = roomById(patient.roomId);
    if (!room) {
      patient.floor = -1;
      return;
    }
    patient.floor = room.floor;
    if (patient.form === "bed" && isBedCareRoom(room)) {
      const bedPoint = bedPatientPointForPatient(room, patient);
      if (bedPoint) {
        patient.x = bedPoint.x;
        patient.y = bedPoint.y;
        const rel = relativePointInRoom(bedPoint, room);
        patient.relX = rel.relX;
        patient.relY = rel.relY;
        patient.rel_x = rel.relX;
        patient.rel_y = rel.relY;
        return;
      }
    }
    patient.x = (room.x + room.w * clamp(patient.relX ?? 0.5, 0.06, 0.94)) * TILE;
    patient.y = (room.y + room.h * clamp(patient.relY ?? 0.5, 0.06, 0.94)) * TILE;
    if (shouldAutoSpreadPatient(patient)) {
      if (!patientsByRoom.has(room.id)) patientsByRoom.set(room.id, []);
      patientsByRoom.get(room.id).push(patient);
    }
  });

  patientsByRoom.forEach((patients, roomId) => {
    if (patients.length < 2) return;
    const room = roomById(roomId);
    if (!room) return;
    spreadPatientsInsideRoom(room, patients);
  });
}

function shouldAutoSpreadPatient(patient) {
  return ["waiting", "walking", "sitting"].includes(patient.form);
}

function spreadPatientsInsideRoom(room, patients) {
  const points = patientCrowdPointsForRoom(room, patients.length);
  patients
    .slice()
    .sort((a, b) => String(a.patientId || a.id).localeCompare(String(b.patientId || b.id)))
    .forEach((patient, index) => {
      const point = points[index] || roomCrowdFallbackPoint(room, index, patients.length);
      patient.x = point.x;
      patient.y = point.y;
      const rel = relativePointInRoom(point, room);
      patient.relX = rel.relX;
      patient.relY = rel.relY;
      patient.rel_x = rel.relX;
      patient.rel_y = rel.relY;
    });
}

function patientCrowdPointsForRoom(room, count) {
  const candidates = [];
  const center = roomCenter(room);
  const relSlots = relativeSlotsForRoom(room, count, {
    minRelX: 0.16,
    maxRelX: 0.84,
    minRelY: Math.max(0.42, 2.8 / room.h),
    maxRelY: 0.86,
    stepRelX: 0.82 / Math.max(6, room.w),
    stepRelY: 0.78 / Math.max(5, room.h),
  });

  for (const slot of relSlots) {
    const point = pointFromRoomRel(room, slot.relX, slot.relY);
    if (!pointInsideRoom(point, room)) continue;
    if (!spotClearOfObstacles(point, room.floor, propColliders, 14)) continue;
    candidates.push({
      point,
      score: Math.abs(point.x - center.x) * 0.2 + Math.abs(point.y - center.y) * 0.08,
    });
  }

  candidates.sort((a, b) => a.score - b.score);
  const selected = [];
  const minDistance = count > 8 ? 30 : 38;
  for (const candidate of candidates) {
    if (selected.every((point) => Math.hypot(point.x - candidate.point.x, point.y - candidate.point.y) >= minDistance)) {
      selected.push(candidate.point);
      if (selected.length >= count) break;
    }
  }

  while (selected.length < count) {
    selected.push(roomCrowdFallbackPoint(room, selected.length, count));
  }
  return selected;
}

function roomCrowdFallbackPoint(room, index, total) {
  const columns = Math.max(2, Math.ceil(Math.sqrt(total)));
  const rows = Math.ceil(total / columns);
  const col = index % columns;
  const row = Math.floor(index / columns);
  const minRelX = 0.18;
  const maxRelX = 0.82;
  const minRelY = 0.50;
  const maxRelY = 0.86;
  const relX = columns === 1 ? 0.5 : minRelX + (maxRelX - minRelX) * (col / (columns - 1));
  const relY = rows === 1 ? 0.64 : minRelY + (maxRelY - minRelY) * (row / (rows - 1));
  return {
    x: (room.x + room.w * relX) * TILE,
    y: (room.y + room.h * relY) * TILE,
  };
}

function relativeSlotsForRoom(room, count, options = {}) {
  const minRelX = clamp(options.minRelX ?? 0.16, 0.06, 0.94);
  const maxRelX = clamp(options.maxRelX ?? 0.84, minRelX, 0.94);
  const minRelY = clamp(options.minRelY ?? 0.42, 0.06, 0.94);
  const maxRelY = clamp(options.maxRelY ?? 0.86, minRelY, 0.94);
  const stepRelX = Math.max(0.05, options.stepRelX ?? 0.09);
  const stepRelY = Math.max(0.05, options.stepRelY ?? 0.09);
  const slots = [];

  for (let relY = minRelY; relY <= maxRelY + 0.0001; relY += stepRelY) {
    for (let relX = minRelX; relX <= maxRelX + 0.0001; relX += stepRelX) {
      slots.push({
        relX: clamp(relX, minRelX, maxRelX),
        relY: clamp(relY, minRelY, maxRelY),
      });
    }
  }

  const centerX = 0.5;
  const centerY = room.kind === "waiting" ? 0.66 : 0.58;
  slots.sort((a, b) => {
    const aScore = Math.abs(a.relX - centerX) * 0.8 + Math.abs(a.relY - centerY) * 0.45;
    const bScore = Math.abs(b.relX - centerX) * 0.8 + Math.abs(b.relY - centerY) * 0.45;
    return aScore - bScore;
  });

  if (slots.length >= count) return slots;
  while (slots.length < count) {
    const point = roomCrowdFallbackPoint(room, slots.length, count);
    slots.push(relativePointInRoom(point, room));
  }
  return slots;
}

function pointFromRoomRel(room, relX, relY) {
  return {
    x: (room.x + room.w * clamp(relX, 0.06, 0.94)) * TILE,
    y: (room.y + room.h * clamp(relY, 0.06, 0.94)) * TILE,
  };
}

function reflowStaff() {
  const placedStaff = [];
  state.staff.forEach((member) => {
    if (member.locationType === "hallway" || member.location_type === "hallway") {
      const floor = Number(member.floor ?? member.floor_id ?? member.current_location?.floor_id ?? 0);
      const x = Number(member.x ?? member.current_location?.x ?? (member.tile_x ?? member.current_location?.tile_x ?? 0) * TILE);
      const y = Number(member.y ?? member.current_location?.y ?? (member.tile_y ?? member.current_location?.tile_y ?? 0) * TILE);
      member.floor = floor;
      member.x = x;
      member.y = y;
      placedStaff.push({ floor: member.floor, x: member.x, y: member.y });
      return;
    }
    if (!member.roomId) {
      member.floor = -1;
      return;
    }
    const room = roomById(member.roomId);
    if (!room) {
      member.floor = -1;
      return;
    }
    member.floor = room.floor;
    const basePoint = {
      x: (room.x + room.w * clamp(member.relX ?? 0.5, 0.06, 0.94)) * TILE,
      y: (room.y + room.h * clamp(member.relY ?? 0.5, 0.06, 0.94)) * TILE,
    };
    const point = staffPointAvoidingPeopleAndProps(member, room, basePoint, placedStaff);
    member.x = point.x;
    member.y = point.y;
    placedStaff.push({ floor: member.floor, x: member.x, y: member.y });
  });
}

function staffForFloor(floorId) {
  return state.staff.filter((member) => member.floor === floorId && (!staffBusyWithTransport(member) || staffReturningFromTransport(member)));
}

function staffBusyWithTransport(member) {
  const memberIds = new Set([member.id, member.staffId, member.staff_id, member.employeeId, member.employee_id].filter(Boolean));
  return Array.from(state.patientMoves.values()).some((move) => move.porterId && memberIds.has(move.porterId));
}

function staffReturningFromTransport(member) {
  const memberIds = [member.id, member.staffId, member.staff_id, member.employeeId, member.employee_id].filter(Boolean);
  return memberIds.some((id) => state.porterMoves.has(id));
}

function createPatientRoute(patient, targetRoom) {
  const collisions = [...state.geometry.walls, ...propColliders];
  const destination = findAvailableRoomSpot(targetRoom, patient.id, collisions);
  if (!destination) return null;

  if (patient.floor === targetRoom.floor) {
    const path = createRoomPath({
      floorId: patient.floor,
      start: { x: patient.x, y: patient.y },
      targetRoom,
      targetPoint: destination,
      collisions,
    });
    if (!path) return null;
    return {
      destination,
      targetRoomId: targetRoom.id,
      speed: 170,
      segmentIndex: 0,
      waypointIndex: 0,
      segments: [{ type: "path", floor: patient.floor, waypoints: path }],
    };
  }

  const currentElevator = roomById(`elevator_${patient.floor}`);
  const targetElevator = roomById(`elevator_${targetRoom.floor}`);
  if (!currentElevator || !targetElevator) return null;

  const pathToElevator = createRoomPath({
    floorId: patient.floor,
    start: { x: patient.x, y: patient.y },
    targetRoom: currentElevator,
    collisions,
  });
  const pathFromElevator = createRoomPath({
    floorId: targetRoom.floor,
    start: roomCenter(targetElevator),
    targetRoom,
    targetPoint: destination,
    collisions,
  });
  if (!pathToElevator || !pathFromElevator) return null;

  return {
    destination,
    targetRoomId: targetRoom.id,
    speed: 170,
    segmentIndex: 0,
    waypointIndex: 0,
    segments: [
      { type: "path", floor: patient.floor, waypoints: pathToElevator },
      { type: "floor-switch", floor: targetRoom.floor, position: roomCenter(targetElevator) },
      { type: "path", floor: targetRoom.floor, waypoints: pathFromElevator },
    ],
  };
}

function createPatientRouteFromPlan(patient, plan, event = {}) {
  const targetRoom = roomById(plan.toRoomId);
  if (!targetRoom) return null;
  const collisions = [...state.geometry.walls, ...propColliders];
  const assignedBedId = plan.bedId || event.statusUpdates?.bedId || event.status_updates?.bed_id || patient.bedId || patient.bed_id;
  const destination = findAvailableRoomSpot(targetRoom, patient.id, collisions, assignedBedId) || roomCenter(targetRoom);
  const roomIds = [...(plan.viaRoomIds || []), plan.toRoomId].filter(Boolean);
  const route = {
    destination,
    finalForm: plan.finalForm,
    assignedBedId,
    targetRoomId: targetRoom.id,
    speed: plan.transport === "stretcher" ? 150 : 170,
    porterId: plan.porterId || null,
    porterReturn: plan.porterReturn || null,
    segmentIndex: 0,
    waypointIndex: 0,
    segments: [],
  };

  let start = { x: patient.x, y: patient.y };
  let currentFloor = patient.floor;
  for (const roomId of roomIds) {
    const room = roomById(roomId);
    if (!room) continue;

    if (room.floor !== currentFloor) {
      const position = roomCenter(room);
      route.segments.push({ type: "floor-switch", floor: room.floor, position });
      start = position;
      currentFloor = room.floor;
      continue;
    }

    const isFinal = room.id === targetRoom.id;
    const path = createRoomPath({
      floorId: currentFloor,
      start,
      targetRoom: room,
      targetPoint: isFinal ? destination : roomCenter(room),
      collisions,
    });
    if (!path) return null;
    route.segments.push({ type: "path", floor: currentFloor, waypoints: path });
    start = isFinal ? destination : roomCenter(room);
  }

  return route.segments.length ? route : null;
}

function updatePatientMoves(delta) {
  state.patientMoves.forEach((move, patientId) => {
    const patient = findPatient(patientId);
    if (!patient) {
      state.patientMoves.delete(patientId);
      return;
    }

    const segment = move.segments[move.segmentIndex];
    if (!segment) {
      finishPatientMove(patient, move);
      return;
    }

    if (segment.type === "floor-switch") {
      patient.floor = segment.floor;
      patient.x = segment.position.x;
      patient.y = segment.position.y;
      move.segmentIndex += 1;
      move.waypointIndex = 0;
      return;
    }

    movePatientAlongSegment(patient, move, segment, delta);
  });
}

function movePatientAlongSegment(patient, move, segment, delta) {
  const target = segment.waypoints[move.waypointIndex];
  if (!target) {
    move.segmentIndex += 1;
    move.waypointIndex = 0;
    return;
  }

  patient.floor = segment.floor;
  const dx = target.x - patient.x;
  const dy = target.y - patient.y;
  const distanceToTarget = Math.hypot(dx, dy);
  if (distanceToTarget < 4) {
    patient.x = target.x;
    patient.y = target.y;
    move.waypointIndex += 1;
    return;
  }

  const step = Math.min(distanceToTarget, move.speed * delta);
  patient.x += (dx / distanceToTarget) * step;
  patient.y += (dy / distanceToTarget) * step;
  if (Math.abs(dx) > Math.abs(dy)) patient.facing = dx < 0 ? "left" : "right";
  else patient.facing = dy < 0 ? "up" : "down";
  patient.movePhase = (patient.movePhase || 0) + delta * 8;
}

function finishPatientMove(patient, move) {
  state.patientMoves.delete(patient.id);
  const targetRoom = roomById(move.targetRoomId);
  if (targetRoom) {
    patient.floor = targetRoom.floor;
    patient.roomId = targetRoom.id;
    if (move.assignedBedId) {
      patient.bedId = move.assignedBedId;
      patient.bed_id = move.assignedBedId;
      patient.home_bed = {
        ...(patient.home_bed || {}),
        room_id: targetRoom.id,
        bed_id: move.assignedBedId,
      };
    }
    const rel = relativePointInRoom(move.destination, targetRoom);
    patient.relX = rel.relX;
    patient.relY = rel.relY;
    patient.x = move.destination.x;
    patient.y = move.destination.y;
    if (move.finalForm === "hidden") {
      patient.floor = -1;
      patient.form = "hidden";
    } else if (move.finalForm === "stretcher") {
      patient.form = "stretcher";
    } else if (move.finalForm === "consultation") {
      patient.form = "consultation";
    } else if (move.finalForm === "waiting") {
      patient.form = "waiting";
    } else if (move.finalForm === "bed" || isBedCareRoom(targetRoom)) {
      patient.form = "bed";
      patient.blanket = careRoomBlanket(targetRoom);
      patient.skin = patient.skin || "#f2c799";
    } else {
      patient.form = targetRoom.kind === "waiting" ? "waiting" : "walking";
    }
  }
  startPorterReturnMove(move, targetRoom || null, patient);
  patient.transportMode = null;
  patient.movePhase = 0;
  if (state.selectedEntityId === patient.id && targetRoom) renderRoomInfo(targetRoom);
  refreshHospitalSnapshot({ preserveMoves: true });
}

function startPorterReturnMove(move, targetRoom, patient) {
  if (!move.porterId || !move.porterReturn) return;
  const porter = state.staff.find((member) => {
    const ids = [member.id, member.staffId, member.staff_id, member.employeeId, member.employee_id].filter(Boolean);
    return ids.includes(move.porterId);
  });
  if (!porter) return;
  const returnFloor = Number(move.porterReturn.floor ?? move.porterReturn.floorId ?? porter.floor);
  const returnPoint = {
    x: Number(move.porterReturn.x ?? porter.x),
    y: Number(move.porterReturn.y ?? porter.y),
  };
  const startFloor = targetRoom?.floor ?? patient.floor ?? returnFloor;
  const startPoint = { x: patient.x, y: patient.y };
  porter.floor = startFloor;
  porter.floor_id = startFloor;
  porter.x = startPoint.x;
  porter.y = startPoint.y;
  porter.locationType = "transport-return";
  porter.location_type = "transport-return";

  const route = createPorterReturnRoute(startFloor, startPoint, returnFloor, returnPoint, targetRoom);
  if (!route) {
    placePorterAfterMove(move);
    return;
  }
  state.porterMoves.set(porter.id, {
    porter,
    porterReturn: move.porterReturn,
    speed: 165,
    movePhase: 0,
    segmentIndex: 0,
    waypointIndex: 0,
    segments: route.segments,
  });
}

function createPorterReturnRoute(startFloor, startPoint, returnFloor, returnPoint, sourceRoom) {
  const collisions = [...state.geometry.walls, ...propColliders];
  if (startFloor === returnFloor) {
    const floorRooms = getRoomsForFloor(returnFloor);
    const targetRoom = sourceRoom && sourceRoom.floor === returnFloor ? sourceRoom : nearestRoomToPoint(floorRooms, returnPoint);
    const waypoints = createRoomPath({
      floorId: returnFloor,
      start: startPoint,
      targetRoom,
      targetPoint: returnPoint,
      collisions,
    }) || [returnPoint];
    return { segments: [{ type: "path", floor: returnFloor, waypoints }] };
  }

  const startElevator = roomById(`elevator_${startFloor}`);
  const returnElevator = roomById(`elevator_${returnFloor}`);
  if (!startElevator || !returnElevator) return null;
  const pathToElevator = createRoomPath({
    floorId: startFloor,
    start: startPoint,
    targetRoom: startElevator,
    targetPoint: roomCenter(startElevator),
    collisions,
  });
  const pathFromElevator = createRoomPath({
    floorId: returnFloor,
    start: roomCenter(returnElevator),
    targetRoom: returnElevator,
    targetPoint: returnPoint,
    collisions,
  }) || [returnPoint];
  if (!pathToElevator) return null;
  return {
    segments: [
      { type: "path", floor: startFloor, waypoints: pathToElevator },
      { type: "floor-switch", floor: returnFloor, position: roomCenter(returnElevator) },
      { type: "path", floor: returnFloor, waypoints: pathFromElevator },
    ],
  };
}

function updatePorterMoves(delta) {
  state.porterMoves.forEach((move, porterId) => {
    const segment = move.segments[move.segmentIndex];
    if (!segment) {
      finishPorterReturnMove(porterId, move);
      return;
    }
    if (segment.type === "floor-switch") {
      move.porter.floor = segment.floor;
      move.porter.floor_id = segment.floor;
      move.porter.x = segment.position.x;
      move.porter.y = segment.position.y;
      move.segmentIndex += 1;
      move.waypointIndex = 0;
      return;
    }
    movePorterAlongSegment(move, segment, delta);
  });
}

function movePorterAlongSegment(move, segment, delta) {
  const porter = move.porter;
  const target = segment.waypoints[move.waypointIndex];
  if (!target) {
    move.segmentIndex += 1;
    move.waypointIndex = 0;
    return;
  }
  porter.floor = segment.floor;
  porter.floor_id = segment.floor;
  const dx = target.x - porter.x;
  const dy = target.y - porter.y;
  const distanceToTarget = Math.hypot(dx, dy);
  if (distanceToTarget < 4) {
    porter.x = target.x;
    porter.y = target.y;
    move.waypointIndex += 1;
    return;
  }
  const step = Math.min(distanceToTarget, move.speed * delta);
  porter.x += (dx / distanceToTarget) * step;
  porter.y += (dy / distanceToTarget) * step;
  porter.movePhase = (porter.movePhase || 0) + delta * 8;
}

function finishPorterReturnMove(porterId, move) {
  state.porterMoves.delete(porterId);
  placePorterAfterMove({
    porterId,
    porterReturn: move.porterReturn,
  });
}

function placePorterAfterMove(move) {
  if (!move.porterId || !move.porterReturn) return;
  const porter = state.staff.find((member) => {
    const ids = [member.id, member.staffId, member.staff_id, member.employeeId, member.employee_id].filter(Boolean);
    return ids.includes(move.porterId);
  });
  if (!porter) return;
  porter.locationType = "hallway";
  porter.location_type = "hallway";
  porter.roomId = null;
  porter.room_id = null;
  porter.floor = Number(move.porterReturn.floor ?? move.porterReturn.floorId ?? porter.floor);
  porter.floor_id = porter.floor;
  porter.x = Number(move.porterReturn.x ?? porter.x);
  porter.y = Number(move.porterReturn.y ?? porter.y);
  porter.tile_x = Number(move.porterReturn.tileX ?? porter.x / TILE);
  porter.tile_y = Number(move.porterReturn.tileY ?? porter.y / TILE);
  porter.current_location = {
    kind: "hallway",
    location_type: "hallway",
    floor_id: porter.floor,
    tile_x: porter.tile_x,
    tile_y: porter.tile_y,
    x: porter.x,
    y: porter.y,
  };
}

function nearestRoomToPoint(rooms, point) {
  if (!rooms.length) return null;
  return rooms
    .slice()
    .sort((a, b) => {
      const ac = roomCenter(a);
      const bc = roomCenter(b);
      return Math.hypot(ac.x - point.x, ac.y - point.y) - Math.hypot(bc.x - point.x, bc.y - point.y);
    })[0];
}

function findPatient(patientId) {
  return state.patients.find((patient) => patient.id === patientId || patient.patientId === patientId) || null;
}

function roomById(roomId) {
  return ROOMS.find((room) => room.id === roomId) || null;
}

function roomCenter(room) {
  return {
    x: (room.x + room.w / 2) * TILE,
    y: (room.y + room.h / 2) * TILE,
  };
}

function findAvailableRoomSpot(room, movingPatientId, collisions, assignedBedId = null) {
  if (isBedCareRoom(room)) return findAvailableBedSpot(room, movingPatientId, assignedBedId);

  const occupied = occupiedPeopleForFloor(room.floor, movingPatientId);
  const center = roomCenter(room);
  const candidates = [];
  const minX = (room.x + 1.6) * TILE;
  const maxX = (room.x + room.w - 1.6) * TILE;
  const minY = (room.y + Math.max(3.1, room.h * 0.46)) * TILE;
  const maxY = (room.y + room.h - 1.6) * TILE;

  for (let y = maxY; y >= minY; y -= TILE * 0.75) {
    for (let x = minX; x <= maxX; x += TILE * 0.75) {
      const point = { x, y };
      if (!pointInsideRoom(point, room)) continue;
      if (!spotClearOfObstacles(point, room.floor, collisions)) continue;
      const nearestPerson = nearestPersonDistance(point, occupied);
      if (nearestPerson < PERSON_SPACING) continue;
      candidates.push({
        point,
        score: Math.abs(point.x - center.x) * 0.35 -
          (point.y - center.y) * 0.5 -
          Math.min(nearestPerson, PERSON_SPACING * 3) * 0.35,
      });
    }
  }

  if (!candidates.length && SLOT_CLEARANCE > 22) return findFallbackRoomSpot(room, movingPatientId, collisions);
  if (!candidates.length) return null;
  candidates.sort((a, b) => a.score - b.score);
  return candidates[0].point;
}

function findAvailableBedSpot(room, movingPatientId, assignedBedId = null) {
  if (assignedBedId) {
    const assignedPoint = bedPatientPointById(room, assignedBedId);
    if (assignedPoint) return assignedPoint;
  }

  const occupied = occupiedPeopleForFloor(room.floor, movingPatientId);
  const beds = bedPropsForRoom(room)
    .map((item) => ({
      point: bedPatientPoint(item),
      score: item.y * 10 + item.x,
    }))
    .filter(({ point }) => pointInsideRoom(point, room))
    .filter(({ point }) => nearestPersonDistance(point, occupied) >= 54);

  if (!beds.length) return null;
  beds.sort((a, b) => a.score - b.score);
  return beds[0].point;
}

function staffPointAvoidingPeopleAndProps(member, room, basePoint, placedStaff = []) {
  const obstacleRects = propRectsForRoom(room, STAFF_BED_MARGIN);
  const occupied = [
    ...placedStaff.filter((point) => point.floor === room.floor),
    ...state.patients
      .filter((patient) => patient.floor === room.floor && patient.roomId === room.id && patient.form !== "bed")
      .flatMap((patient) => patientOccupancyPoints(patient)),
  ];

  if (staffPointClear(basePoint, room, obstacleRects, occupied)) return basePoint;

  const candidates = [];
  const center = roomCenter(room);
  const relSlots = relativeSlotsForRoom(room, 28, {
    minRelX: 0.14,
    maxRelX: 0.86,
    minRelY: Math.max(0.30, 2.1 / room.h),
    maxRelY: 0.84,
    stepRelX: STAFF_BED_SCAN_STEP / (room.w * TILE),
    stepRelY: STAFF_BED_SCAN_STEP / (room.h * TILE),
  });

  for (const slot of relSlots) {
    const point = pointFromRoomRel(room, slot.relX, slot.relY);
    if (!staffPointClear(point, room, obstacleRects, occupied)) continue;
    candidates.push({
      point,
      score: Math.hypot(point.x - basePoint.x, point.y - basePoint.y) +
        Math.abs(point.x - center.x) * 0.12 +
        Math.max(0, center.y - point.y) * 0.08 +
        roleSideBias(member, point, center),
    });
  }

  if (!candidates.length) return basePoint;
  candidates.sort((a, b) => a.score - b.score);
  return candidates[0].point;
}

function roleSideBias(member, point, center) {
  if (member.role === "nurse") return Math.abs(point.x - center.x) * 0.05;
  if (member.role === "doctor") return point.x < center.x ? 10 : 0;
  return 0;
}

function staffPointClear(point, room, bedRects, occupied) {
  if (!staffBBoxInsideRoom(point, room)) return false;
  const box = staffBBox(point);
  if (bedRects.some((rect) => rectsOverlap(box, rect))) return false;
  if (occupied.some((person) => Math.hypot(point.x - person.x, point.y - person.y) < 38)) return false;
  return true;
}

function bedRectsForRoom(room) {
  return propRectsForRoom(room, STAFF_BED_MARGIN, (item) => item.type === "bed");
}

function propRectsForRoom(room, margin = 0, filter = () => true) {
  return PROPS
    .filter((item) => item.floor === room.floor && filter(item) && propInsideRoom(item, room))
    .map((item) => ({
      x: item.x * TILE - margin,
      y: item.y * TILE - margin,
      w: item.w * TILE + margin * 2,
      h: item.h * TILE + margin * 2,
    }));
}

function staffBBox(point) {
  return {
    x: point.x - 16,
    y: point.y - 22,
    w: 32,
    h: 52,
  };
}

function staffBBoxInsideRoom(point, room) {
  const box = staffBBox(point);
  const roomBox = {
    x: (room.x + 0.35) * TILE,
    y: (room.y + 0.75) * TILE,
    w: (room.w - 0.7) * TILE,
    h: (room.h - 1.1) * TILE,
  };
  return box.x >= roomBox.x &&
    box.y >= roomBox.y &&
    box.x + box.w <= roomBox.x + roomBox.w &&
    box.y + box.h <= roomBox.y + roomBox.h;
}

function rectsOverlap(a, b) {
  return a.x < b.x + b.w &&
    a.x + a.w > b.x &&
    a.y < b.y + b.h &&
    a.y + a.h > b.y;
}

function findFallbackRoomSpot(room, movingPatientId, collisions) {
  const occupied = occupiedPeopleForFloor(room.floor, movingPatientId);
  const center = roomCenter(room);
  const candidates = [];
  const minX = (room.x + 1.3) * TILE;
  const maxX = (room.x + room.w - 1.3) * TILE;
  const minY = (room.y + 2.4) * TILE;
  const maxY = (room.y + room.h - 1.3) * TILE;

  for (let y = maxY; y >= minY; y -= TILE * 0.75) {
    for (let x = minX; x <= maxX; x += TILE * 0.75) {
      const point = { x, y };
      if (!pointInsideRoom(point, room)) continue;
      if (!spotClearOfObstacles(point, room.floor, collisions, 22)) continue;
      const nearestPerson = nearestPersonDistance(point, occupied);
      if (nearestPerson < 56) continue;
      candidates.push({
        point,
        score: Math.abs(point.x - center.x) * 0.35 - (point.y - center.y) * 0.45,
      });
    }
  }

  if (!candidates.length) return null;
  candidates.sort((a, b) => a.score - b.score);
  return candidates[0].point;
}

function occupiedPeopleForFloor(floorId, movingPatientId) {
  const patients = state.patients
    .filter((patient) => patient.floor === floorId && patient.id !== movingPatientId)
    .flatMap((patient) => patientOccupancyPoints(patient));
  const staff = staffForFloor(floorId).map((member) => ({ x: member.x, y: member.y }));
  const reserved = Array.from(state.patientMoves.entries())
    .filter(([patientId, move]) => patientId !== movingPatientId && roomById(move.targetRoomId)?.floor === floorId)
    .map(([, move]) => move.destination)
    .filter(Boolean);
  return [...patients, ...staff, ...reserved];
}

function patientOccupancyPoints(patient) {
  if (patient.form === "consultation") {
    const points = [{ x: patient.x - 24, y: patient.y + 8 }];
    const doctorId = patient.doctorProfileId || patient.doctor_profile_id;
    if (!(doctorId && hasStaffProfile(doctorId))) points.push({ x: patient.x + 26, y: patient.y + 8 });
    return points;
  }
  return [{ x: patient.x, y: patient.y }];
}

function nearestPersonDistance(point, occupied) {
  if (!occupied.length) return Infinity;
  return Math.min(...occupied.map((person) => Math.hypot(point.x - person.x, point.y - person.y)));
}

function spotClearOfObstacles(point, floorId, collisions, clearance = SLOT_CLEARANCE) {
  return !collisions.some((rect) => {
    if (rect.floor !== floorId) return false;
    return point.x >= rect.x - clearance &&
      point.x <= rect.x + rect.w + clearance &&
      point.y >= rect.y - clearance &&
      point.y <= rect.y + rect.h + clearance;
  });
}

function isBedCareRoom(room) {
  return room.kind === "icu" || room.kind === "ward";
}

function careRoomBlanket(room) {
  return room.kind === "icu" ? "#d46d8e" : "#76c59d";
}

function propInsideRoom(item, room) {
  return item.x >= room.x &&
    item.x + item.w <= room.x + room.w &&
    item.y >= room.y &&
    item.y + item.h <= room.y + room.h;
}

function bedPatientPointForPatient(room, patient) {
  const bedId = patient.bedId || patient.bed_id || patient.home_bed?.bed_id;
  return bedPatientPointById(room, bedId) || null;
}

function bedPatientPointById(room, bedId) {
  if (!bedId) return null;
  const bed = bedPropsForRoom(room).find((item) => item.bedId === bedId);
  return bed ? bedPatientPoint(bed) : null;
}

function bedPropsForRoom(room) {
  return PROPS
    .filter((item) => item.floor === room.floor && item.type === "bed" && item.roomId === room.id)
    .map((item, index) => ({
      ...item,
      bedId: `${room.id}-bed-${String(index + 1).padStart(2, "0")}`,
    }));
}

function bedPatientPoint(item) {
  return {
    x: item.x * TILE,
    y: (item.y + 0.2) * TILE,
  };
}

function relativePointInRoom(point, room) {
  return {
    relX: clamp((point.x / TILE - room.x) / room.w, 0.06, 0.94),
    relY: clamp((point.y / TILE - room.y) / room.h, 0.06, 0.94),
  };
}

function worldPointFromCanvas(point) {
  const zoom = state.camera.zoom || 1;
  return {
    x: (point.x - canvas.width / 2) / zoom + state.camera.x,
    y: (point.y - canvas.height / 2) / zoom + state.camera.y,
  };
}

function clearPersonSelection() {
  state.selectedEntityId = null;
  profileRequestId += 1;
  personInfo.className = "person-info person-info--empty";
  personInfo.textContent = "Click a doctor, nurse, or patient.";
}

function renderPersonLoading(entity) {
  personInfo.className = "person-info person-info--empty";
  personInfo.textContent = `Loading ${roleLabel(entity.entityType)} info...`;
}

function renderPersonError(message) {
  personInfo.className = "person-info person-info--empty";
  personInfo.textContent = `Unable to load person info: ${message}`;
}

function renderPersonProfile(profile, entity) {
  if (!profile) {
    personInfo.className = "person-info person-info--empty";
    personInfo.textContent = "Invalid person reference. This record is not available in hospital data.";
    return;
  }

  personInfo.className = "person-info";
  const rows = [
    infoRow("Role", roleLabel(profile.type)),
    infoRow("Department", profile.department),
    infoRow("Name", profile.name),
  ];
  if (profile.type === "patient") {
    rows.splice(1, 0, infoRow("Patient ID", profile.patientId));
    rows.push(infoRow("Symptoms", profile.symptoms));
  } else {
    rows.splice(1, 0, infoRow("Employee ID", profile.employeeId));
  }
  personInfo.innerHTML = rows.join("");
}

function infoRow(label, value) {
  return `
    <div class="person-info__row">
      <span class="person-info__label">${label}</span>
      <span class="person-info__value">${value}</span>
    </div>
  `;
}

function roleLabel(type) {
  return {
    doctor: "Doctor",
    nurse: "Nurse",
    porter: "Porter",
    patient: "Patient",
  }[type] || "Person";
}

function updatePlayerTravel(delta) {
  const travel = state.playerTravel;
  if (!travel) return;

  const target = travel.waypoints[travel.waypointIndex];
  if (!target) {
    state.playerTravel = null;
    updateRoomReadout();
    return;
  }

  const dx = target.x - state.player.x;
  const dy = target.y - state.player.y;
  const distanceToTarget = Math.hypot(dx, dy);
  if (distanceToTarget < 4) {
    state.player.x = target.x;
    state.player.y = target.y;
    travel.waypointIndex += 1;
    if (travel.waypointIndex >= travel.waypoints.length) {
      state.playerTravel = null;
      updateRoomReadout();
    }
    return;
  }

  const step = Math.min(distanceToTarget, travel.speed * delta);
  state.player.x += (dx / distanceToTarget) * step;
  state.player.y += (dy / distanceToTarget) * step;
  if (Math.abs(dx) > Math.abs(dy)) state.player.facing = dx < 0 ? "left" : "right";
  else state.player.facing = dy < 0 ? "up" : "down";
}

function roomAtWorldPoint(floorId, x, y) {
  return getRoomsForFloor(floorId).find((room) => {
    const rx = room.x * TILE;
    const ry = room.y * TILE;
    const rw = room.w * TILE;
    const rh = room.h * TILE;
    return x >= rx && x <= rx + rw && y >= ry && y <= ry + rh;
  }) || null;
}

function canvasPoint(event, targetCanvas = canvas) {
  const rect = targetCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * targetCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * targetCanvas.height,
  };
}

function resetCameraControl() {
  state.selectedRoomId = null;
  state.selectedEntityId = null;
  state.selectedInfoRoomId = null;
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  state.playerTravel = null;
  clearPersonSelection();
  clearRoomSelection();
}

function applyFitView() {
  state.camera.zoom = minZoom();
  const center = floorPlateCenter();
  state.camera.x = center.x;
  state.camera.y = center.y;
  clampCamera(state.camera);
}

function clampCamera(camera) {
  camera.x = clampCameraValue(camera.x, "x");
  camera.y = clampCameraValue(camera.y, "y");
}

function clampCameraValue(value, axis) {
  const zoom = state.camera.zoom || 1;
  const viewportSize = axis === "x" ? canvas.width / zoom : canvas.height / zoom;
  const worldSize = axis === "x" ? WORLD.width : WORLD.height;
  if (viewportSize >= worldSize) return worldSize / 2;
  return clamp(value, viewportSize / 2, worldSize - viewportSize / 2);
}

function minZoom() {
  const plateWidth = FLOOR_PLATE.w * TILE;
  const plateHeight = FLOOR_PLATE.h * TILE;
  return Number((Math.min(canvas.width / plateWidth, canvas.height / plateHeight) * 0.96).toFixed(3));
}

function floorPlateCenter() {
  return {
    x: (FLOOR_PLATE.x + FLOOR_PLATE.w / 2) * TILE,
    y: (FLOOR_PLATE.y + FLOOR_PLATE.h / 2) * TILE,
  };
}

function updateZoomControls() {
  const zoom = state.camera.zoom || 1;
  zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  zoomOutButton.disabled = true;
  zoomInButton.disabled = true;
  zoomFitButton.classList.add("is-active");
}

function clamp(value, min, max) {
  if (max < min) return (min + max) / 2;
  return Math.min(max, Math.max(min, value));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}
