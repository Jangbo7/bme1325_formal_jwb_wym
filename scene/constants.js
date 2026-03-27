export const TILE = 32;
export const WALL_THICKNESS = TILE * 0.5;
export const DOOR_THICKNESS = 12;
export const WALL_HEIGHT = 58;
export const FLOOR_HEIGHT = 170;
export const DOOR_SENSOR_DISTANCE = 64;
export const DOOR_CLOSE_DISTANCE = 96;
export const STAIR_TRIGGER_COOLDOWN_MS = 3000;
export const ISO_X = 0.92;
export const ISO_Y = 0.48;
export const CHARACTER_FOOT_RADIUS = 7;
export const CHARACTER_BODY_HEIGHT = 32;
export const CHARACTER_HEAD_RADIUS = 8;
export const WORLD = { width: 52 * TILE, height: 36 * TILE };
export const FLOOR_BASE_Z = { 1: 0, 2: FLOOR_HEIGHT };

export const palette = {
  roomFloor: "#705970",
  hallFloor: "#8a7188",
  wallFront: "#593b56",
  wallSide: "#4a3047",
  wallTop: "#866783",
  wallEdge: "rgba(255, 225, 255, 0.18)",
  bed: "#7db1c4",
  desk: "#6d4b35",
  sofa: "#816b4b",
  plant: "#6fa26b",
  screen: "#7fe0dc",
  cabinet: "#8b6b89",
  reception: "#865c74",
  doorFrame: "#8aa5b6",
  doorGlass: "rgba(141, 233, 255, 0.32)",
  doorSensor: "#4ce4ff",
  playerBody: "#2f8fb0",
  playerHead: "#f6d4c0",
  playerLeg: "#28465a",
  shadow: "rgba(0, 0, 0, 0.26)",
  label: "rgba(248, 233, 252, 0.82)",
  inactiveMask: "rgba(7, 7, 12, 0.62)",
};
