export const TILE = 32;

export const WORLD = {
  width: 84 * TILE,
  height: 48 * TILE,
};

export const FLOOR_PLATE = {
  x: 4,
  y: 4,
  w: 74,
  h: 40,
};

export const ELEVATOR = {
  x: 62,
  y: 32,
  w: 10,
  h: 10,
};

export const ELEVATOR_SPAWN = {
  x: (ELEVATOR.x + ELEVATOR.w / 2) * TILE,
  y: (ELEVATOR.y + ELEVATOR.h / 2) * TILE,
};

export function room(floor, id, kind, label, x, y, w, h, accent) {
  return { floor, id, kind, label, x, y, w, h, accent };
}

export function elevatorRoom(floor) {
  return room(floor, `elevator_${floor}`, "elevator", `${floor}F Elevator`, ELEVATOR.x, ELEVATOR.y, ELEVATOR.w, ELEVATOR.h, "#d7b07b");
}

export function door(roomId, side, offset, length) {
  return { roomId, side, offset, length };
}

export function prop(floor, x, y, w, h, type) {
  return { floor, x, y, w, h, type };
}

export function elevatorProp(floor) {
  return prop(floor, ELEVATOR.x + 3.2, ELEVATOR.y + 3.7, 3.6, 1.6, "elevator");
}
