import { fetchMapConfig, saveMapConfig } from "./map.js";

const ROOM_W = 11;
const ROOM_H = 8;
const ROOM_X = [6, 19, 32, 45, 58];
const ROOM_Y = [6, 17, 28];
const DEFAULT_ACCENT = "#b99163";
const BED_SIZE = { w: 3.4, h: 1.3 };
const BED_SLOTS = [
  { x: 2, y: 3 },
  { x: 7, y: 3 },
  { x: 2, y: 5.2 },
  { x: 7, y: 5.2 },
];
const BED_MAX_BY_KIND = {
  emergency: 2,
  icu: 4,
  rescue: 2,
  ward: 4,
};

export function createMapAdmin({
  panel,
  openButton,
  cancelButton,
  saveButton,
  floorTabs,
  floorTitle,
  status,
  roomList,
  addForm,
  roomNameInput,
  onSaved,
}) {
  const state = {
    activeFloor: 1,
    config: null,
    dirty: false,
  };

  openButton.addEventListener("click", () => openAdmin());
  cancelButton.addEventListener("click", () => closeAdmin());
  saveButton.addEventListener("click", () => saveAdmin());
  addForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addRoom();
  });
  floorTabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-admin-floor]");
    if (!button) return;
    state.activeFloor = Number(button.dataset.adminFloor);
    renderAdmin();
  });
  roomList.addEventListener("click", (event) => {
    const bedButton = event.target.closest("[data-bed-action]");
    if (bedButton) {
      adjustBeds(bedButton.dataset.roomId, bedButton.dataset.bedAction);
      return;
    }

    const button = event.target.closest("[data-delete-room]");
    if (!button) return;
    deleteRoom(button.dataset.deleteRoom);
  });

  return {
    open: openAdmin,
    close: closeAdmin,
  };

  async function openAdmin() {
    panel.hidden = false;
    setStatus("Loading map-config.json...");
    saveButton.disabled = false;
    state.config = await fetchMapConfig({ bustCache: true });
    state.activeFloor = state.config.floors[0]?.id || 1;
    state.dirty = false;
    renderAdmin();
  }

  function closeAdmin() {
    panel.hidden = true;
    roomNameInput.value = "";
  }

  async function saveAdmin() {
    if (!state.config) return;
    saveButton.disabled = true;
    setStatus("Saving...");
    const result = await saveMapConfig({
      ...state.config,
      updatedAt: new Date().toISOString(),
    });
    state.dirty = false;
    setStatus(result.mode === "file" ? "Saved to map-config.json" : "Saved in browser");
    await onSaved(result);
    window.setTimeout(() => {
      saveButton.disabled = false;
      closeAdmin();
    }, 280);
  }

  function addRoom() {
    const floor = activeFloorConfig();
    const name = roomNameInput.value.trim();
    if (!floor || !name) {
      setStatus("Room name is required.");
      return;
    }

    const slot = nextOpenSlot(floor);
    if (!slot) {
      setStatus(`${floor.shortLabel || `${floor.id}F`} has no open room slot.`);
      return;
    }

    const id = uniqueRoomId(name, state.config);
    floor.rooms.push({
      id,
      kind: "room",
      label: name,
      x: slot.x,
      y: slot.y,
      w: ROOM_W,
      h: ROOM_H,
      accent: DEFAULT_ACCENT,
      doors: [{ side: slot.y >= 28 ? "top" : "bottom", offset: 4, length: 3 }],
      items: [{ type: "desk", x: 3, y: 3, w: 3.4, h: 1.2 }],
    });
    state.dirty = true;
    roomNameInput.value = "";
    setStatus(`Added ${name}`);
    renderAdmin();
  }

  function deleteRoom(roomId) {
    const floor = activeFloorConfig();
    if (!floor) return;
    const room = floor.rooms.find((item) => item.id === roomId);
    if (!room) return;
    if (isProtectedRoom(room)) {
      setStatus(`${room.label} is protected.`);
      return;
    }
    floor.rooms = floor.rooms.filter((item) => item.id !== roomId);
    state.dirty = true;
    setStatus(`Deleted ${room.label}`);
    renderAdmin();
  }

  function renderAdmin() {
    if (!state.config) return;
    renderFloorTabs();
    renderRoomList();
  }

  function renderFloorTabs() {
    floorTabs.innerHTML = state.config.floors
      .map((floor) => `
        <button class="map-admin__floor-btn${floor.id === state.activeFloor ? " is-active" : ""}" type="button" data-admin-floor="${floor.id}">
          <span>${floor.shortLabel || `${floor.id}F`}</span>
          <strong>${floorName(floor)}</strong>
        </button>
      `)
      .join("");
  }

  function renderRoomList() {
    const floor = activeFloorConfig();
    if (!floor) return;
    const rooms = floor.rooms || [];
    floorTitle.textContent = `${floor.shortLabel || `${floor.id}F`} Rooms`;
    setStatus(`${rooms.length} rooms${state.dirty ? " · unsaved" : ""}`);

    roomList.innerHTML = rooms
      .map((room, index) => {
        const features = summarizeRoomItems(room.items || []);
        const protectedRoom = isProtectedRoom(room);
        return `
          <article class="map-admin__room-row${protectedRoom ? " is-protected" : ""}">
            <div>
              <div class="map-admin__room-name">${escapeHtml(room.label || room.id)}</div>
              <div class="map-admin__room-meta">${escapeHtml(room.id)} · ${escapeHtml(room.kind || "room")} · ${index + 1}${protectedRoom ? " · protected" : ""}</div>
            </div>
            <div class="map-admin__room-count">${features}</div>
            ${bedControl(room)}
            <button class="map-admin__delete" type="button" data-delete-room="${escapeHtml(room.id)}" ${protectedRoom ? "disabled" : ""} aria-label="Delete ${escapeHtml(room.label || room.id)}">×</button>
          </article>
        `;
      })
      .join("");
  }

  function activeFloorConfig() {
    return state.config?.floors?.find((floor) => floor.id === state.activeFloor) || null;
  }

  function adjustBeds(roomId, action) {
    const floor = activeFloorConfig();
    const room = floor?.rooms?.find((item) => item.id === roomId);
    if (!room || isProtectedRoom(room) || !canEditBeds(room)) return;

    const items = room.items || [];
    const beds = items.filter((item) => item.type === "bed");
    const maxBeds = roomMaxBeds(room);

    if (action === "add") {
      if (beds.length >= maxBeds) {
        setStatus(`${room.label} is already at max ${maxBeds} beds.`);
        return;
      }
      room.items = [...items, nextBedItem(beds.length)];
      state.dirty = true;
      setStatus(`Added bed to ${room.label}`);
      renderAdmin();
      return;
    }

    if (action === "remove") {
      if (!beds.length) {
        setStatus(`${room.label} has no beds to remove.`);
        return;
      }
      let removed = false;
      room.items = items.filter((item) => {
        if (!removed && item.type === "bed") {
          removed = true;
          return false;
        }
        return true;
      });
      state.dirty = true;
      setStatus(`Removed bed from ${room.label}`);
      renderAdmin();
    }
  }
}

function nextOpenSlot(floor) {
  const taken = new Set((floor.rooms || []).map((room) => `${room.x},${room.y}`));
  for (const y of ROOM_Y) {
    for (const x of ROOM_X) {
      if (!taken.has(`${x},${y}`)) return { x, y };
    }
  }
  return null;
}

function uniqueRoomId(name, config) {
  const used = new Set(config.floors.flatMap((floor) => (floor.rooms || []).map((room) => room.id)));
  const base = slugify(name) || "room";
  let next = base;
  let index = 1;
  while (used.has(next)) {
    index += 1;
    next = `${base}_${index}`;
  }
  return next;
}

function slugify(value) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function summarizeRoomItems(items) {
  const counts = items.reduce((acc, item) => {
    acc[item.type] = (acc[item.type] || 0) + 1;
    return acc;
  }, {});
  const beds = counts.bed || 0;
  const desks = (counts.desk || 0) + (counts.reception || 0) + (counts.table || 0);
  return `${beds} beds · ${desks} desks`;
}

function bedControl(room) {
  if (!canEditBeds(room) || isProtectedRoom(room)) {
    return `<div class="map-admin__bed-control map-admin__bed-control--empty">${isProtectedRoom(room) ? "Locked" : "No beds"}</div>`;
  }
  const beds = (room.items || []).filter((item) => item.type === "bed").length;
  const maxBeds = roomMaxBeds(room);
  return `
    <div class="map-admin__bed-control" aria-label="Bed controls">
      <button type="button" data-bed-action="remove" data-room-id="${escapeHtml(room.id)}" ${beds <= 0 ? "disabled" : ""}>-</button>
      <span>${beds}/${maxBeds}</span>
      <button type="button" data-bed-action="add" data-room-id="${escapeHtml(room.id)}" ${beds >= maxBeds ? "disabled" : ""}>+</button>
    </div>
  `;
}

function canEditBeds(room) {
  const beds = (room.items || []).some((item) => item.type === "bed");
  return beds || Object.hasOwn(BED_MAX_BY_KIND, room.kind) || Number.isFinite(room.maxBeds);
}

function roomMaxBeds(room) {
  return Math.max(0, Number(room.maxBeds ?? BED_MAX_BY_KIND[room.kind] ?? 0));
}

function nextBedItem(index) {
  const slot = BED_SLOTS[index] || BED_SLOTS[BED_SLOTS.length - 1];
  return {
    type: "bed",
    x: slot.x,
    y: slot.y,
    w: BED_SIZE.w,
    h: BED_SIZE.h,
  };
}

function isProtectedRoom(room) {
  return Boolean(room.protected) || room.kind === "elevator" || /^elevator_\d+$/.test(room.id);
}

function floorName(floor) {
  return (floor.label || "").replace(/^\dF\s*/, "") || "Floor";
}

function setStatus(text) {
  const element = document.getElementById("mapAdminStatus");
  if (element) element.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}
