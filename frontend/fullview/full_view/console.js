import {
  deletePatient,
  fetchEventRuleCategory,
  fetchEventRuleIndex,
  fetchHospitalEvents,
  fetchHospitalSnapshot,
  requestPatientAdmission,
  requestPatientMove,
} from "./hospital-api.js?v=queue-delete-20260612";

const summary = document.getElementById("consoleSummary");
const roomCount = document.getElementById("roomCount");
const floorsContainer = document.getElementById("consoleFloors");
const roomsContainer = document.getElementById("consoleRooms");
const roomDetail = document.getElementById("consoleRoomDetail");
const selectedRoomMeta = document.getElementById("selectedRoomMeta");
const refreshButton = document.getElementById("consoleRefresh");
const moveForm = document.getElementById("moveEventForm");
const movePatient = document.getElementById("movePatient");
const moveEvent = document.getElementById("moveEvent");
const moveFloor = document.getElementById("moveFloor");
const moveTarget = document.getElementById("moveTarget");
const moveReason = document.getElementById("moveReason");
const moveSubmit = moveForm.querySelector("[type='submit']");
const selectedPersonSummary = document.getElementById("selectedPersonSummary");
const intakeStatus = document.getElementById("intakeStatus");
const admitEmergencyButton = document.getElementById("admitEmergencyPatient");
const admitOutpatientButton = document.getElementById("admitOutpatientPatient");
const eventStatus = document.getElementById("eventStatus");
const eventCount = document.getElementById("eventCount");
const eventsContainer = document.getElementById("consoleEvents");

const CATEGORY_FLOORS = {
  emergency: 1,
  outpatient: 2,
  icu: 3,
  ward: 5,
};

const state = {
  snapshot: null,
  rules: [],
  selectedFloorId: null,
  selectedRoomId: null,
  selectedPersonId: null,
  selectedPersonType: null,
  lastEventSeq: 0,
  events: [],
};

refreshButton.addEventListener("click", () => loadConsole());
floorsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("[data-floor-id]");
  if (!button) return;
  state.selectedFloorId = Number(button.dataset.floorId);
  state.selectedRoomId = roomsForSelectedFloor()[0]?.id || null;
  renderSummary();
  renderRooms();
  renderRoomDetail();
});
roomsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("[data-room-id]");
  if (!button) return;
  state.selectedRoomId = button.dataset.roomId;
  renderRooms();
  renderRoomDetail();
});
roomDetail.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("[data-delete-patient-id]");
  if (deleteButton) {
    event.stopPropagation();
    deletePatientFromConsole(deleteButton.dataset.deletePatientId);
    return;
  }
  const button = event.target.closest("[data-person-id]");
  if (!button) return;
  selectPersonForOperation(button.dataset.personType, button.dataset.personId);
});
movePatient.addEventListener("change", () => {
  state.selectedPersonId = movePatient.value;
  state.selectedPersonType = "patient";
  renderSelectedPersonSummary();
  renderRoomDetail();
  renderMoveRules();
  applySelectedRuleDestination({ syncRoomDetail: false });
});
moveEvent.addEventListener("change", () => applySelectedRuleDestination({ syncRoomDetail: true }));
moveFloor.addEventListener("change", () => renderTargetOptions());
moveForm.addEventListener("submit", submitMoveEvent);
admitEmergencyButton.addEventListener("click", () => admitEntryPatient("emergency"));
admitOutpatientButton.addEventListener("click", () => admitEntryPatient("outpatient"));

await loadConsole();
window.setInterval(refreshEvents, 1200);

async function loadConsole() {
  eventStatus.textContent = "Loading...";
  const [snapshot, rules] = await Promise.all([fetchHospitalSnapshot(), loadMovementRules()]);
  state.snapshot = snapshot;
  state.rules = rules;
  state.lastEventSeq = Math.max(state.lastEventSeq, snapshot.eventSeq || 0);
  syncSelectedFloorAndRoom();
  renderAll();
  eventStatus.textContent = "Ready";
}

async function loadMovementRules() {
  const index = await fetchEventRuleIndex();
  const categories = await Promise.all(index.categories.map((category) => fetchEventRuleCategory(category.file)));
  return categories.flatMap((category) => category.rules.map((rule) => ({
    id: rule.id,
    eventId: rule.eventId,
    name: rule.name,
    categoryId: category.id,
    classification: rule.classification,
    rooms: rule.rooms || [],
    movement: rule.movement,
  })));
}

function renderAll() {
  renderSummary();
  renderRooms();
  renderRoomDetail();
  renderMoveForm();
  renderSelectedPersonSummary();
  renderEvents();
}

function renderSummary() {
  const patients = state.snapshot.patients.length;
  const staff = state.snapshot.staff.length;
  const rooms = state.snapshot.rooms.length;
  const beds = state.snapshot.rooms.reduce((sum, room) => sum + Number(room.capacityBeds || 0), 0);
  const occupied = state.snapshot.rooms.reduce((sum, room) => sum + Number(room.occupiedBeds || 0), 0);
  const floorRooms = roomsForSelectedFloor();
  summary.innerHTML = `
    <span>${patients} patients</span>
    <span>${staff} staff</span>
    <span>${rooms} rooms</span>
    <span>${occupied}/${beds} beds</span>
  `;
  roomCount.textContent = `${floorRooms.length}/${rooms} rooms`;
}

function renderRooms() {
  const floors = state.snapshot.floors;
  floorsContainer.innerHTML = floors.map((floor) => {
    const rooms = state.snapshot.rooms.filter((room) => room.floor === floor.id);
    const patientCount = rooms.reduce((sum, room) => sum + Number(room.patientCount || 0), 0);
    return `
      <button class="console-floor-tab${floor.id === state.selectedFloorId ? " is-active" : ""}" type="button" data-floor-id="${floor.id}">
        <strong>${escapeHtml(floor.shortLabel || `${floor.id}F`)}</strong>
        <span>${escapeHtml(floor.label.replace(/^\dF\s*/, ""))}</span>
        <em>${rooms.length} rooms · ${patientCount} pts</em>
      </button>
    `;
  }).join("");

  const rooms = roomsForSelectedFloor();
  roomsContainer.innerHTML = rooms.map((room) => `
    <button class="console-room${room.id === state.selectedRoomId ? " is-active" : ""}" type="button" data-room-id="${escapeHtml(room.id)}">
      <strong>${escapeHtml(room.label)}</strong>
      <span>${escapeHtml(room.roomCode)} · ${room.patientCount} pts · ${room.staffCount} staff</span>
    </button>
  `).join("");
}

function renderRoomDetail() {
  const room = selectedRoom();
  if (!room) {
    selectedRoomMeta.textContent = "Select a room";
    roomDetail.className = "console-detail-empty";
    roomDetail.textContent = "Select a room to inspect patients, staff, and resources.";
    return;
  }

  selectedRoomMeta.textContent = `${room.roomCode} · ${room.id}`;
  roomDetail.className = "console-room-detail";
  roomDetail.innerHTML = `
    <div class="console-detail-grid">
      ${detailMetric("Kind", room.kind)}
      ${detailMetric("Protected", room.protected ? "Yes" : "No")}
      ${detailMetric("Beds", `${room.occupiedBeds}/${room.capacityBeds || 0}`)}
      ${detailMetric("Queue", String(room.queue?.length || 0))}
    </div>
    <h3>Beds</h3>
    ${bedList(room)}
    <h3>Patients</h3>
    ${peopleList(room.patients, "patient")}
    <h3>Staff</h3>
    ${peopleList(room.staff, "staff")}
  `;
}

function renderMoveForm() {
  const previousPatientId = state.selectedPersonType === "patient" ? state.selectedPersonId : movePatient.value;
  movePatient.innerHTML = state.snapshot.patients
    .filter((patient) => patient.form !== "hidden")
    .map((patient) => `<option value="${escapeAttr(patient.patientId)}">${escapeHtml(patient.patientId)} · ${escapeHtml(patient.name)} · ${escapeHtml(patient.roomId)}</option>`)
    .join("");
  if (previousPatientId && state.snapshot.patients.some((patient) => patient.patientId === previousPatientId)) {
    movePatient.value = previousPatientId;
  }
  renderMoveRules();
  moveFloor.innerHTML = state.snapshot.floors
    .map((floor) => `<option value="${floor.id}">${escapeHtml(floor.label)}</option>`)
    .join("");
  applySelectedRuleDestination({ syncRoomDetail: false });
}

function renderMoveRules() {
  const previousEventId = moveEvent.value;
  const rules = legalMoveRulesForSelectedPatient();
  moveEvent.innerHTML = state.rules
    .filter((rule) => rules.includes(rule))
    .map((rule) => `<option value="${escapeAttr(rule.eventId)}">${escapeHtml(rule.eventId)} · ${escapeHtml(rule.name)}</option>`)
    .join("");
  if (!rules.length) {
    moveEvent.innerHTML = `<option value="" disabled selected>No legal move rule for this patient's current room</option>`;
  } else if (previousEventId && rules.some((rule) => rule.eventId === previousEventId)) {
    moveEvent.value = previousEventId;
  }
  moveSubmit.disabled = !rules.length;
}

function renderTargetOptions(preferredRoomId = null) {
  if (!state.snapshot) return;
  const floorId = Number(moveFloor.value || state.snapshot.floors[0]?.id || 1);
  const rooms = state.snapshot.rooms.filter((room) => room.floor === floorId);
  const currentRoomIsVisible = rooms.some((room) => room.id === moveTarget.value);
  const selectedRoomId = preferredRoomId || (currentRoomIsVisible ? moveTarget.value : rooms[0]?.id);
  moveTarget.innerHTML = rooms.map((room) => (
    `<option value="${escapeAttr(room.id)}"${room.id === selectedRoomId ? " selected" : ""}>${escapeHtml(room.roomCode)} · ${escapeHtml(room.label)} · ${room.availableBeds ?? 0} beds</option>`
  )).join("");
}

function applySelectedRuleDestination({ syncRoomDetail = true } = {}) {
  if (!state.snapshot) return;
  const room = destinationRoomForRule(selectedMoveRule());
  if (!room) {
    renderTargetOptions();
    return;
  }

  moveFloor.value = String(room.floor);
  renderTargetOptions(room.id);
  if (!syncRoomDetail) return;
  state.selectedFloorId = room.floor;
  state.selectedRoomId = room.id;
  renderSummary();
  renderRooms();
  renderRoomDetail();
}

function selectedMoveRule() {
  return state.rules.find((rule) => rule.eventId === moveEvent.value) || null;
}

function selectPersonForOperation(type, personId) {
  state.selectedPersonId = personId;
  state.selectedPersonType = type;
  if (type === "patient") {
    movePatient.value = personId;
    renderMoveRules();
    applySelectedRuleDestination({ syncRoomDetail: false });
  } else {
    moveSubmit.disabled = true;
    eventStatus.textContent = "Staff selected";
  }
  renderSelectedPersonSummary();
  renderRoomDetail();
}

function renderSelectedPersonSummary() {
  const person = selectedPerson();
  if (!person) {
    selectedPersonSummary.textContent = "Select a patient from room detail or the list below.";
    return;
  }
  const id = person.patientId || person.employeeId || person.id;
  const role = person.type === "patient" ? "Patient" : `${person.role || person.type}`;
  const extra = person.type === "patient" ? person.status : person.department;
  selectedPersonSummary.innerHTML = `
    <strong>${escapeHtml(person.name)}</strong>
    <span>${escapeHtml(role)} · ${escapeHtml(id)} · ${escapeHtml(person.roomId)}${extra ? ` · ${escapeHtml(extra)}` : ""}</span>
  `;
}

function selectedPerson() {
  if (!state.selectedPersonId || !state.selectedPersonType) return selectedPatient();
  if (state.selectedPersonType === "patient") {
    return state.snapshot.patients.find((person) => person.patientId === state.selectedPersonId) || null;
  }
  return state.snapshot.staff.find((person) => person.employeeId === state.selectedPersonId) || null;
}

function selectedPatient() {
  return state.snapshot.patients.find((item) => item.patientId === movePatient.value) || null;
}

function legalMoveRulesForSelectedPatient() {
  const room = selectedPatientRoom();
  if (!room) return [];
  return state.rules.filter((rule) => (
    !rule.movement?.blocked &&
    rule.categoryId !== "resource-blocking" &&
    rule.categoryId !== "transfer" &&
    sourceAllowedForRoom(rule, room)
  ));
}

function sourceAllowedForRoom(rule, room) {
  const source = rule.movement?.from;
  if (source === undefined || source === null) return true;
  const sources = Array.isArray(source) ? source : [source];
  return sources.some((sourceId) => sourceValueMatchesRoom(sourceId, room, rule));
}

function sourceValueMatchesRoom(sourceId, room, rule) {
  if (sourceId === room.id) return true;
  if (sourceId === "outside") return false;
  if (sourceId === "current_room") return roomMatchesRuleScope(room, rule);
  if (sourceId === "current_consult_room") return isConsultRoom(room) && roomMatchesRuleScope(room, rule);
  if (sourceId === "current_op_room") return room.floor === 2;
  if (sourceId === "current_ed_room") return room.floor === 1;
  if (sourceId === "current_ed_bed_room") return room.floor === 1 && ["emergency", "rescue", "emergency_consult"].includes(room.kind);
  if (sourceId === "current_icu_bed_room") return room.kind === "icu";
  if (sourceId === "current_icu_exam_room") return room.floor === 3 && ["icu", "monitor"].includes(room.kind);
  if (sourceId === "current_ward_room") return room.kind === "ward";
  if (sourceId === "source_ward_room") return room.kind === "ward";
  if (sourceId === "source_icu_bed_room") return room.kind === "icu";
  if (sourceId === "source_ed_room") return room.floor === 1;
  return false;
}

function roomMatchesRuleScope(room, rule) {
  if (rule.rooms?.includes(room.id)) return true;
  const categoryFloor = CATEGORY_FLOORS[rule.categoryId];
  if (categoryFloor) return room.floor === categoryFloor;
  return false;
}

function isConsultRoom(room) {
  return [
    "consultation",
    "internal_medicine",
    "surgery",
    "pediatrics",
    "fever",
    "obgyn",
  ].includes(room.kind);
}

function destinationRoomForRule(rule) {
  const target = rule?.movement?.to;
  const targets = Array.isArray(target) ? target : [target].filter(Boolean);

  for (const targetId of targets) {
    const room = roomById(targetId);
    if (room) return room;
  }

  for (const targetId of targets) {
    const room = symbolicDestinationRoom(targetId);
    if (room) return room;
  }

  return null;
}

function symbolicDestinationRoom(targetId) {
  if (!targetId || targetId === "exit") return null;
  if (targetId === "target_ward_room") return firstAvailableRoomByKind("ward");
  if (targetId === "source_ward_room") return selectedPatientRoomOfKind("ward");
  if (targetId === "source_icu_bed_room") return selectedPatientRoomOfKind("icu");
  if (targetId === "source_ed_room") return selectedPatientRoomOnFloor(1);
  if (targetId === "current_consult_room" || targetId === "current_room") return selectedPatientRoom();
  return null;
}

function selectedPatientRoomOfKind(kind) {
  const patient = selectedPatient();
  const assignedRoom = patient?.bedRoomId ? roomById(patient.bedRoomId) : null;
  if (assignedRoom?.kind === kind) return assignedRoom;
  const room = selectedPatientRoom();
  if (room?.kind === kind) return room;
  return firstAvailableRoomByKind(kind);
}

function selectedPatientRoomOnFloor(floor) {
  const room = selectedPatientRoom();
  if (room?.floor === floor) return room;
  return state.snapshot.rooms.find((item) => item.floor === floor) || null;
}

function selectedPatientRoom() {
  const patient = selectedPatient();
  return patient ? roomById(patient.roomId) : null;
}

function firstAvailableRoomByKind(kind) {
  return state.snapshot.rooms.find((room) => room.kind === kind && Number(room.availableBeds || 0) > 0)
    || state.snapshot.rooms.find((room) => room.kind === kind)
    || null;
}

function roomById(roomId) {
  return state.snapshot.rooms.find((room) => room.id === roomId) || null;
}

async function submitMoveEvent(event) {
  event.preventDefault();
  if (state.selectedPersonType && state.selectedPersonType !== "patient") {
    eventStatus.textContent = "Only patient move events are supported here.";
    return;
  }
  if (!moveEvent.value) {
    eventStatus.textContent = "No legal move rule for this patient.";
    return;
  }
  const patient = state.snapshot.patients.find((item) => item.patientId === movePatient.value);
  if (!patient) return;
  eventStatus.textContent = "Sending...";
  try {
    const response = await requestPatientMove({
      requestId: `console-${Date.now()}`,
      source: "console",
      operatorId: "manual-admin",
      eventId: moveEvent.value,
      patientId: patient.patientId,
      fromRoomId: patient.roomId,
      toRoomId: moveTarget.value,
      context: { reason: moveReason.value.trim() },
    });
    eventStatus.textContent = response.accepted ? `Accepted #${response.eventSeq}` : `${response.reasonCode}`;
    await loadConsole();
    await refreshEvents();
  } catch (error) {
    eventStatus.textContent = error.message;
  }
}

async function deletePatientFromConsole(patientId) {
  const patient = state.snapshot?.patients?.find((item) => item.patientId === patientId);
  if (!patient) return;
  if (!window.confirm(`Delete patient ${patient.name} (${patientId})?`)) return;

  eventStatus.textContent = "Deleting...";
  try {
    const response = await deletePatient(patientId);
    if (response.accepted) {
      if (state.selectedPersonId === patientId) {
        state.selectedPersonId = null;
        state.selectedPersonType = null;
      }
      eventStatus.textContent = "Deleted";
    } else {
      eventStatus.textContent = response.reasonCode || "Rejected";
      window.alert(response.message || "Delete rejected by backend.");
    }
    await loadConsole();
    await refreshEvents();
  } catch (error) {
    eventStatus.textContent = "Delete failed";
    window.alert(error.message);
  }
}

async function admitEntryPatient(department) {
  intakeStatus.textContent = "Creating...";
  setIntakeButtonsDisabled(true);
  try {
    const response = await requestPatientAdmission({
      requestId: `console-intake-${department}-${Date.now()}`,
      source: "console-intake",
      operatorId: "manual-admin",
      department,
      context: { reason: `${department} patient intake` },
    });
    const patient = response.patient;
    intakeStatus.textContent = response.accepted
      ? `${patient?.patientId || "Patient"} triaged`
      : response.reasonCode || "Rejected";
    await loadConsole();
    if (patient?.patientId) {
      focusPatient(patient.patientId);
    }
    await refreshEvents();
  } catch (error) {
    intakeStatus.textContent = error.message;
  } finally {
    setIntakeButtonsDisabled(false);
  }
}

function setIntakeButtonsDisabled(disabled) {
  admitEmergencyButton.disabled = disabled;
  admitOutpatientButton.disabled = disabled;
}

function focusPatient(patientId) {
  const patient = state.snapshot.patients.find((item) => item.patientId === patientId);
  const room = patient ? roomById(patient.roomId) : null;
  state.selectedPersonId = patientId;
  state.selectedPersonType = "patient";
  if (room) {
    state.selectedFloorId = room.floor;
    state.selectedRoomId = room.id;
  }
  if (patient) movePatient.value = patient.patientId;
  renderAll();
}

async function refreshEvents() {
  try {
    const result = await fetchHospitalEvents(0);
    state.events = result.events || [];
    renderEvents();
  } catch (error) {
    eventStatus.textContent = `Events unavailable: ${error.message}`;
  }
}

function renderEvents() {
  const events = [...state.events].sort((a, b) => b.eventSeq - a.eventSeq).slice(0, 18);
  eventCount.textContent = `${state.events.length} events`;
  eventsContainer.innerHTML = events.length ? events.map((event) => `
    <article class="console-event ${event.accepted ? "is-accepted" : "is-rejected"}">
      <strong>#${event.eventSeq} ${escapeHtml(event.eventId || "EVENT")}</strong>
      <span>${escapeHtml(event.patientId || "")}</span>
      <p class="console-event-route">${event.accepted ? formatAnimation(event.animationPlan) : `${escapeHtml(event.reasonCode)}: ${escapeHtml(event.message)}`}</p>
    </article>
  `).join("") : `<div class="console-detail-empty">No events yet.</div>`;
}

function selectedRoom() {
  return state.snapshot?.rooms.find((room) => room.id === state.selectedRoomId) || null;
}

function syncSelectedFloorAndRoom() {
  const floors = state.snapshot.floors;
  const selectedRoom = state.snapshot.rooms.find((room) => room.id === state.selectedRoomId);
  if (selectedRoom) {
    state.selectedFloorId = selectedRoom.floor;
    return;
  }

  const floorExists = floors.some((floor) => floor.id === state.selectedFloorId);
  if (!floorExists) state.selectedFloorId = floors[0]?.id || null;
  state.selectedRoomId = roomsForSelectedFloor()[0]?.id || null;
}

function roomsForSelectedFloor() {
  if (!state.snapshot) return [];
  return state.snapshot.rooms.filter((room) => room.floor === state.selectedFloorId);
}

function detailMetric(label, value) {
  return `
    <div class="console-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function peopleList(people, type) {
  if (!people?.length) return `<div class="console-detail-empty">No ${type} in this room.</div>`;
  return `
    <div class="console-people-list">
      ${people.map((person) => {
        const personId = person.patientId || person.employeeId;
        const selected = state.selectedPersonType === type && state.selectedPersonId === personId;
        const row = `
          <button class="console-person-row${selected ? " is-active" : ""}" type="button" data-person-type="${escapeAttr(type)}" data-person-id="${escapeAttr(personId)}">
            <strong>${escapeHtml(person.name)}</strong>
            <span>${escapeHtml(person.patientId || person.employeeId)} · ${escapeHtml(person.status || person.role || person.type)}</span>
          </button>
        `;
        if (type !== "patient") return row;
        return `
          <div class="console-person-entry">
            ${row}
            <button class="console-patient-delete" type="button" data-delete-patient-id="${escapeAttr(personId)}" aria-label="Delete ${escapeAttr(person.name)}">Delete</button>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function bedList(room) {
  const beds = normalizedRoomBeds(room);
  if (!beds?.length) return `<div class="console-detail-empty">No beds in this room.</div>`;
  return `
    <div class="console-bed-list">
      ${beds.map((bed) => `
        <div class="console-bed-row${bed.occupied ? " is-occupied" : " is-free"}">
          <strong>${escapeHtml(bed.bedId)}</strong>
          <span>
            ${bed.occupied
              ? `${escapeHtml(bed.patientName || "Assigned patient")} · ${escapeHtml(bed.patientId)}${bed.patientAway ? " · away" : ""}`
              : "Available"}
          </span>
        </div>
      `).join("")}
    </div>
  `;
}

function normalizedRoomBeds(room) {
  const capacity = Math.max(Number(room.capacityBeds || 0), room.beds?.length || 0);
  if (!capacity) return [];

  const baseBeds = (room.beds?.length
    ? room.beds
    : Array.from({ length: capacity }, (_, index) => ({ bedId: `${room.id}-bed-${String(index + 1).padStart(2, "0")}` })))
    .map((bed, index) => ({ ...bed, bedId: bed.bedId || `${room.id}-bed-${String(index + 1).padStart(2, "0")}` }));
  const assignments = normalizeBedAssignments(room.bedAssignments || [], room.id, capacity);
  const patientsById = new Map(state.snapshot.patients.map((patient) => [patient.patientId, patient]));
  const assignedByBed = new Map();

  baseBeds.forEach((bed) => {
    if (bed.patientId) assignedByBed.set(bed.bedId, bed.patientId);
  });
  assignments.forEach((assignment) => {
    if (assignment.bedId && assignment.patientId) assignedByBed.set(assignment.bedId, assignment.patientId);
  });
  patientsAssignedToRoom(room).forEach((patient) => {
    const bedId = patient.bedId || firstUnassignedBedId(baseBeds, assignedByBed);
    if (bedId) assignedByBed.set(bedId, patient.patientId);
  });

  return baseBeds.map((baseBed, index) => {
    const bedId = baseBed.bedId || `${room.id}-bed-${String(index + 1).padStart(2, "0")}`;
    const patientId = assignedByBed.get(bedId) || null;
    const patient = patientId ? patientsById.get(patientId) : null;
    return {
      bedId,
      occupied: Boolean(patientId),
      patientId,
      patientName: patient?.name || baseBed.patientName || null,
      patientStatus: patient?.status || baseBed.patientStatus || null,
      patientCurrentRoomId: patient?.roomId || baseBed.patientCurrentRoomId || null,
      patientAway: Boolean((patient && patient.roomId !== room.id) || baseBed.patientAway),
    };
  });
}

function patientsAssignedToRoom(room) {
  const roomPatients = room.patients || [];
  const snapshotPatients = state.snapshot.patients || [];
  const candidates = [
    ...roomPatients,
    ...snapshotPatients.filter((patient) => patient.bedRoomId === room.id),
    ...roomPatients.filter((patient) => patient.form === "bed"),
  ];
  const byId = new Map();
  candidates.forEach((patient) => {
    if (patient.patientId) byId.set(patient.patientId, patient);
  });
  return Array.from(byId.values());
}

function firstUnassignedBedId(beds, assignedByBed) {
  const bed = beds.find((item) => !assignedByBed.has(item.bedId));
  return bed?.bedId || null;
}

function normalizeBedAssignments(assignments, roomId, capacity) {
  return assignments.map((assignment, index) => {
    if (assignment && typeof assignment === "object") {
      return {
        bedId: assignment.bedId || `${roomId}-bed-${String(index + 1).padStart(2, "0")}`,
        patientId: assignment.patientId,
      };
    }
    return {
      bedId: `${roomId}-bed-${String(index + 1).padStart(2, "0")}`,
      patientId: assignment,
    };
  }).filter((assignment, index) => assignment.patientId && index < capacity);
}

function formatAnimation(plan) {
  if (!plan) return "No animation plan";
  const via = plan.viaRoomIds?.length ? ` via ${plan.viaRoomIds.join(" -> ")}` : "";
  return escapeHtml(`${plan.transport} ${plan.fromRoomId} -> ${plan.toRoomId}${via}`);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
