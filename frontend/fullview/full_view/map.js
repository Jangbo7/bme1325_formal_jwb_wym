import { ELEVATOR_SPAWN, FLOOR_PLATE, TILE, WORLD } from "./layout.js";
import { DEPARTMENT_STATUS, ROOM_KIND_LABELS } from "./status.js";

const MAP_CONFIG_FILE = "./map-config.json";
const MAP_CONFIG_STORAGE_KEY = "sim-hospital-map-config";

export { DEPARTMENT_STATUS, FLOOR_PLATE, ROOM_KIND_LABELS, TILE, WORLD };

export let FLOORS = [];
export let ROOMS = [];
export let DOORS = [];
export let PROPS = [];
export let MAP_CONFIG_VERSION = null;

await loadMapConfig();

export async function loadMapConfig({ bustCache = false } = {}) {
  const config = await fetchMapConfig({ bustCache });
  applyMapConfig(config);
  return config;
}

export async function fetchMapConfig({ bustCache = false, preferStored = true } = {}) {
  return readMapConfig(bustCache, preferStored);
}

export async function saveMapConfig(config) {
  const normalizedConfig = structuredClone(config);

  if (typeof window === "undefined") {
    const { writeFile } = await import("node:fs/promises");
    const url = new URL(MAP_CONFIG_FILE, import.meta.url);
    await writeFile(url, `${JSON.stringify(normalizedConfig, null, 2)}\n`);
    applyMapConfig(normalizedConfig);
    return { mode: "file" };
  }

  try {
    const response = await fetch("./api/map-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(normalizedConfig, null, 2),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    window.localStorage.removeItem(MAP_CONFIG_STORAGE_KEY);
    applyMapConfig(normalizedConfig);
    return { mode: "file" };
  } catch (error) {
    window.localStorage.setItem(MAP_CONFIG_STORAGE_KEY, JSON.stringify(normalizedConfig));
    applyMapConfig(normalizedConfig);
    return { mode: "browser", error };
  }
}

export function getFloor(id) {
  return FLOORS.find((floor) => floor.id === id) || FLOORS[0];
}

export function getRoomsForFloor(floorId) {
  return ROOMS.filter((room) => room.floor === floorId);
}

export function getPropsForFloor(floorId) {
  return PROPS.filter((item) => item.floor === floorId);
}

function applyMapConfig(config) {
  if (!config?.floors?.length) throw new Error("map-config.json must include a non-empty floors array.");

  const rooms = [];
  const doors = [];
  const props = [];
  const floors = config.floors.map((floor) => {
    const floorId = Number(floor.id);
    const floorRooms = (floor.rooms || []).map((roomSpec) => {
      const room = normalizeRoom(floorId, roomSpec);
      const roomDoors = (roomSpec.doors || []).map((doorSpec) => normalizeDoor(room.id, doorSpec));
      const roomProps = (roomSpec.items || []).map((itemSpec) => normalizeRoomItem(room, itemSpec));

      doors.push(...roomDoors);
      props.push(...roomProps);
      rooms.push(room);
      return room;
    });

    return {
      id: floorId,
      label: floor.label || `${floorId}F`,
      shortLabel: floor.shortLabel || `${floorId}F`,
      subtitle: floor.subtitle || "",
      spawn: normalizeSpawn(floor.spawn),
      departmentKinds: floor.departmentKinds || [],
      rooms: floorRooms.map((room) => room.id),
    };
  });

  FLOORS = floors;
  ROOMS = assignRoomCodes(rooms);
  DOORS = doors;
  PROPS = props;
  MAP_CONFIG_VERSION = config.version || null;
}

async function readMapConfig(bustCache, preferStored) {
  if (typeof window === "undefined") {
    const { readFile } = await import("node:fs/promises");
    const url = new URL(MAP_CONFIG_FILE, import.meta.url);
    return JSON.parse(await readFile(url, "utf8"));
  }

  const stored = preferStored ? window.localStorage.getItem(MAP_CONFIG_STORAGE_KEY) : null;
  if (stored) return JSON.parse(stored);

  const response = await fetch(MAP_CONFIG_FILE, { cache: bustCache ? "no-store" : "default" });
  if (!response.ok) throw new Error(`Unable to load map-config.json: ${response.status} ${response.statusText}`);
  return response.json();
}

function normalizeRoom(floor, roomSpec) {
  if (!roomSpec?.id) throw new Error(`A room on ${floor}F is missing an id.`);
  const items = roomSpec.items || [];
  return {
    floor,
    id: roomSpec.id,
    kind: roomSpec.kind || "room",
    label: roomSpec.label || roomSpec.id,
    x: Number(roomSpec.x),
    y: Number(roomSpec.y),
    w: Number(roomSpec.w),
    h: Number(roomSpec.h),
    accent: roomSpec.accent || "#b99163",
    protected: Boolean(roomSpec.protected),
    maxBeds: Number.isFinite(Number(roomSpec.maxBeds)) ? Number(roomSpec.maxBeds) : null,
    features: summarizeRoomItems(items),
  };
}

function normalizeDoor(roomId, doorSpec) {
  return {
    roomId,
    side: doorSpec.side || "bottom",
    offset: Number(doorSpec.offset ?? 4),
    length: Number(doorSpec.length ?? 3),
  };
}

function normalizeRoomItem(room, itemSpec) {
  return {
    floor: room.floor,
    roomId: room.id,
    type: itemSpec.type || "desk",
    x: room.x + Number(itemSpec.x || 0),
    y: room.y + Number(itemSpec.y || 0),
    w: Number(itemSpec.w || 1),
    h: Number(itemSpec.h || 1),
  };
}

function normalizeSpawn(spawn) {
  if (!spawn) return ELEVATOR_SPAWN;
  if (typeof spawn.x === "number" && typeof spawn.y === "number") return spawn;
  if (typeof spawn.tileX === "number" && typeof spawn.tileY === "number") {
    return { x: spawn.tileX * TILE, y: spawn.tileY * TILE };
  }
  return ELEVATOR_SPAWN;
}

function summarizeRoomItems(items) {
  const counts = {};
  items.forEach((item) => {
    const type = item.type || "item";
    counts[type] = (counts[type] || 0) + 1;
  });
  return counts;
}

function assignRoomCodes(rooms) {
  const floorCounts = new Map();
  return rooms.map((room) => {
    const next = (floorCounts.get(room.floor) || 0) + 1;
    floorCounts.set(room.floor, next);
    return {
      ...room,
      roomCode: room.roomCode || `${room.floor}F-Room${next}`,
    };
  });
}
