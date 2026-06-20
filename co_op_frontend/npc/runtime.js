function randomBetween(min, max) {
  return min + Math.random() * Math.max(0, max - min);
}

function shuffle(array) {
  const list = [...array];
  for (let i = list.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list;
}

const WORKFLOW_PATTERNS = [
  ["registration", "hall", "triage", "hall", "consultation", "hall"],
  ["hall", "triage", "hall", "lab", "hall", "consultation"],
  ["hall", "registration", "hall", "office", "hall", "ward"],
  ["hall", "lab", "hall", "icu", "hall", "office"],
  ["hall", "consultation", "hall", "ward", "hall", "empty_room"],
  ["hall", "registration", "hall", "triage", "hall", "lab"],
];

const GUIDE_NPC_COUNT = 3;
const GUIDE_SPAWN_POINTS = [
  { x: 14.9 * 32, y: 18.0 * 32, floor: 1 },
  { x: 15.8 * 32, y: 18.6 * 32, floor: 1 },
  { x: 13.7 * 32, y: 18.8 * 32, floor: 1 },
];
const DEFAULT_SPAWN_AVOID = { x: 14 * 32, y: 18 * 32, minDistance: 160 };
const PATH_GRID = 24;
const PATH_NEAR_DISTANCE = 10;
const PATH_MAX_ITERATIONS = 9000;
const PATH_NODE_SEARCH_RADIUS = 8;
const GUIDE_BODY_COLORS = ["#c94b4b", "#d85e5e", "#b94242"];
const GUIDE_ACCENT_COLORS = ["#f3c3c3", "#ffd6d6", "#f0b5b5"];
const BODY_COLORS = ["#7dbf83", "#e3a96d", "#8db1e8", "#b490d9", "#d98f9f", "#88c7bb"];
const ACCENT_COLORS = ["#c6dd8f", "#f2d7a0", "#cddcff", "#dcccff", "#f4c8d2", "#caefe5"];
const HAIR_COLORS = ["#5d4128", "#3f2d20", "#6b4e34", "#2f2522"];

function roomId(room) {
  return `${room.floor}:${room.kind}:${room.x}:${room.y}`;
}

function createRoomGraph(rooms, roomBounds, doors) {
  const roomById = new Map();
  const roomsByKind = new Map();
  const boundsById = new Map();
  const edges = new Map();

  for (const room of rooms) {
    const id = roomId(room);
    roomById.set(id, room);
    boundsById.set(id, roomBounds(room));
    if (!roomsByKind.has(room.kind)) roomsByKind.set(room.kind, []);
    roomsByKind.get(room.kind).push(room);
    edges.set(id, []);
  }

  const hallRooms = rooms.filter((room) => room.kind === "hall");
  for (const door of doors) {
    const room = rooms[door.roomIndex];
    if (!room) continue;
    const sourceId = roomId(room);
    const sourceBounds = boundsById.get(sourceId);
    const roomWaypoint = buildDoorWaypoint(door, sourceBounds);
    if (!roomWaypoint) continue;

    for (const hallRoom of hallRooms) {
      if (hallRoom.floor !== room.floor) continue;
      const hallId = roomId(hallRoom);
      if (hallId === sourceId) continue;
      const hallWaypoint = buildHallConnector(boundsById.get(hallId), door);
      edges.get(sourceId).push({
        to: hallId,
        doorId: door.id,
        fromPoint: { x: roomWaypoint.x, y: roomWaypoint.y },
        toPoint: { x: hallWaypoint.x, y: hallWaypoint.y },
      });
      edges.get(hallId).push({
        to: sourceId,
        doorId: door.id,
        fromPoint: { x: hallWaypoint.x, y: hallWaypoint.y },
        toPoint: { x: roomWaypoint.x, y: roomWaypoint.y },
      });
    }
  }

  return { roomById, roomsByKind, boundsById, edges };
}

function buildDoorWaypoint(door, bounds) {
  if (!door || !bounds) return null;
  if (door.side === "bottom") {
    return { x: door.pivot.x, y: bounds.y + bounds.h - 28 };
  }
  if (door.side === "top") {
    return { x: door.pivot.x, y: bounds.y + 28 };
  }
  if (door.side === "left") {
    return { x: bounds.x + 28, y: door.pivot.y };
  }
  return { x: bounds.x + bounds.w - 28, y: door.pivot.y };
}

function buildHallConnector(bounds, door) {
  const x = Math.max(bounds.x + 36, Math.min(bounds.x + bounds.w - 36, door.pivot.x));
  const y = Math.max(bounds.y + 36, Math.min(bounds.y + bounds.h - 36, door.pivot.y));
  return { x, y };
}

function randomPointInBounds(bounds, padding = 28) {
  const minX = bounds.x + padding;
  const minY = bounds.y + padding;
  const maxX = bounds.x + bounds.w - padding;
  const maxY = bounds.y + bounds.h - padding;
  return {
    x: randomBetween(minX, Math.max(minX + 1, maxX)),
    y: randomBetween(minY, Math.max(minY + 1, maxY)),
  };
}

function findWalkablePoint(candidate, floor, canMoveTo, bounds, maxTries = 36) {
  let point = { ...candidate };
  let tries = 0;
  while (!canMoveTo(point.x, point.y, floor) && tries < maxTries) {
    point = randomPointInBounds(bounds, 24);
    tries += 1;
  }
  return point;
}

function createRoomStop(room, bounds, canMoveTo) {
  const anchor = randomPointInBounds(bounds, room.kind === "hall" ? 34 : 26);
  const safe = findWalkablePoint(anchor, room.floor, canMoveTo, bounds);
  return {
    roomId: roomId(room),
    roomKind: room.kind,
    room,
    bounds,
    floor: room.floor,
    x: safe.x,
    y: safe.y,
  };
}

function resolveRoomByKind(kind, graph) {
  const candidates = graph.roomsByKind.get(kind) || graph.roomsByKind.get("hall") || [];
  if (!candidates.length) return null;
  return candidates[Math.floor(Math.random() * candidates.length)];
}

function findRoomPath(graph, startRoomId, targetRoomId) {
  if (!startRoomId || !targetRoomId) return [];
  if (startRoomId === targetRoomId) return [startRoomId];
  const queue = [[startRoomId]];
  const visited = new Set([startRoomId]);

  while (queue.length) {
    const path = queue.shift();
    const current = path[path.length - 1];
    const nextEdges = graph.edges.get(current) || [];
    for (const edge of nextEdges) {
      if (visited.has(edge.to)) continue;
      const nextPath = [...path, edge.to];
      if (edge.to === targetRoomId) return nextPath;
      visited.add(edge.to);
      queue.push(nextPath);
    }
  }

  return [startRoomId, targetRoomId];
}

function buildTransitWaypoints(graph, pathRoomIds, targetStop) {
  if (!pathRoomIds.length) return [targetStop];
  if (pathRoomIds.length === 1) return [targetStop];

  const waypoints = [];
  const pushWaypoint = (waypoint) => {
    const previous = waypoints[waypoints.length - 1];
    if (
      previous
      && Math.abs(previous.x - waypoint.x) < 1
      && Math.abs(previous.y - waypoint.y) < 1
      && previous.roomId === waypoint.roomId
    ) {
      return;
    }
    waypoints.push(waypoint);
  };

  for (let i = 0; i < pathRoomIds.length - 1; i += 1) {
    const fromId = pathRoomIds[i];
    const toId = pathRoomIds[i + 1];
    const edge = (graph.edges.get(fromId) || []).find((item) => item.to === toId);
    if (!edge) continue;
    const currentRoom = graph.roomById.get(fromId);
    const nextRoom = graph.roomById.get(toId);
    pushWaypoint({
      x: edge.fromPoint.x,
      y: edge.fromPoint.y,
      floor: currentRoom?.floor || targetStop.floor,
      roomId: fromId,
      roomKind: currentRoom?.kind || targetStop.roomKind,
      mode: "door_approach",
      doorId: edge.doorId,
    });
    pushWaypoint({
      x: edge.toPoint.x,
      y: edge.toPoint.y,
      floor: nextRoom?.floor || targetStop.floor,
      roomId: toId,
      roomKind: nextRoom?.kind || targetStop.roomKind,
      mode: "door_exit",
      doorId: edge.doorId,
    });
  }

  pushWaypoint({
    x: targetStop.x,
    y: targetStop.y,
    floor: targetStop.floor,
    roomId: targetStop.roomId,
    roomKind: targetStop.roomKind,
    mode: "room",
    doorId: null,
  });
  return waypoints;
}

function facingFromDelta(dx, dy, fallback = "down") {
  if (Math.abs(dx) > Math.abs(dy)) return dx < 0 ? "left" : "right";
  if (Math.abs(dy) > 0.5) return dy < 0 ? "up" : "down";
  return fallback;
}

function ensureNpcSpawnAwayFromPlayer(startStop, room, bounds, canMoveTo) {
  let safeStop = startStop;
  let tries = 0;
  while (Math.hypot(safeStop.x - DEFAULT_SPAWN_AVOID.x, safeStop.y - DEFAULT_SPAWN_AVOID.y) < DEFAULT_SPAWN_AVOID.minDistance && tries < 24) {
    safeStop = createRoomStop(room, bounds, canMoveTo);
    tries += 1;
  }
  return safeStop;
}

function detectRoomState(x, y, floor, rooms, roomBounds) {
  const room = rooms.find((candidate) => {
    if (candidate.floor !== floor) return false;
    const bounds = roomBounds(candidate);
    return x >= bounds.x + 6 && x <= bounds.x + bounds.w - 6 && y >= bounds.y + 6 && y <= bounds.y + bounds.h - 6;
  });

  if (!room) {
    return {
      roomId: `${floor}:grounds`,
      roomKind: "grounds",
      room: null,
    };
  }

  return {
    roomId: roomId(room),
    roomKind: room.kind,
    room,
  };
}

function groundRoomId(floor) {
  return `${floor}:grounds`;
}

function snapToGrid(value) {
  return Math.round(value / PATH_GRID) * PATH_GRID;
}

function pathNodeKey(node) {
  return `${node.floor}:${node.x}:${node.y}`;
}

function heuristicDistance(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function findNearestPathNode(point, floor, canPathfindTo) {
  const baseX = snapToGrid(point.x);
  const baseY = snapToGrid(point.y);
  let bestNode = null;
  let bestDistance = Infinity;

  for (let radius = 0; radius <= PATH_NODE_SEARCH_RADIUS; radius += 1) {
    for (let offsetX = -radius; offsetX <= radius; offsetX += 1) {
      for (let offsetY = -radius; offsetY <= radius; offsetY += 1) {
        const candidate = {
          x: baseX + offsetX * PATH_GRID,
          y: baseY + offsetY * PATH_GRID,
          floor,
        };
        if (!canPathfindTo(candidate.x, candidate.y, floor)) continue;
        const distance = Math.hypot(candidate.x - point.x, candidate.y - point.y);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestNode = candidate;
        }
      }
    }
    if (bestNode) return bestNode;
  }

  return null;
}

function rebuildPathFromNodes(nodeMap, finalKey) {
  const nodes = [];
  let cursor = nodeMap.get(finalKey) || null;
  while (cursor) {
    nodes.push({ x: cursor.x, y: cursor.y, floor: cursor.floor });
    cursor = cursor.parentKey ? nodeMap.get(cursor.parentKey) || null : null;
  }
  return nodes.reverse();
}

function compactPathNodes(nodes) {
  if (nodes.length <= 2) return nodes;
  const compact = [nodes[0]];
  for (let index = 1; index < nodes.length - 1; index += 1) {
    const previous = nodes[index - 1];
    const current = nodes[index];
    const next = nodes[index + 1];
    const deltaAX = current.x - previous.x;
    const deltaAY = current.y - previous.y;
    const deltaBX = next.x - current.x;
    const deltaBY = next.y - current.y;
    if (deltaAX !== deltaBX || deltaAY !== deltaBY) {
      compact.push(current);
    }
  }
  compact.push(nodes[nodes.length - 1]);
  return compact;
}

function buildPathWaypoints(startPoint, targetStop, canPathfindTo) {
  if (startPoint.floor !== targetStop.floor) return [];

  const startNode = findNearestPathNode(startPoint, startPoint.floor, canPathfindTo);
  const goalNode = findNearestPathNode(targetStop, targetStop.floor, canPathfindTo);
  if (!startNode || !goalNode) return [];

  const openList = [];
  const visited = new Map();
  const closed = new Set();
  const startKey = pathNodeKey(startNode);
  const startRecord = {
    ...startNode,
    g: 0,
    f: heuristicDistance(startNode, goalNode),
    parentKey: null,
  };
  openList.push(startRecord);
  visited.set(startKey, startRecord);

  const directions = [
    { x: PATH_GRID, y: 0 },
    { x: -PATH_GRID, y: 0 },
    { x: 0, y: PATH_GRID },
    { x: 0, y: -PATH_GRID },
  ];

  let bestKey = startKey;
  let bestDistance = heuristicDistance(startNode, goalNode);
  let iterations = 0;

  while (openList.length && iterations < PATH_MAX_ITERATIONS) {
    iterations += 1;
    let bestIndex = 0;
    for (let index = 1; index < openList.length; index += 1) {
      if (openList[index].f < openList[bestIndex].f) bestIndex = index;
    }

    const current = openList.splice(bestIndex, 1)[0];
    const currentKey = pathNodeKey(current);
    if (closed.has(currentKey)) continue;
    closed.add(currentKey);

    const currentDistance = heuristicDistance(current, goalNode);
    if (currentDistance < bestDistance) {
      bestDistance = currentDistance;
      bestKey = currentKey;
    }

    if (current.x === goalNode.x && current.y === goalNode.y) {
      bestKey = currentKey;
      break;
    }

    for (const direction of directions) {
      const nextNode = {
        x: current.x + direction.x,
        y: current.y + direction.y,
        floor: current.floor,
      };
      const nextKey = pathNodeKey(nextNode);
      if (closed.has(nextKey)) continue;
      if (!canPathfindTo(nextNode.x, nextNode.y, nextNode.floor)) continue;

      const nextG = current.g + PATH_GRID;
      const previousRecord = visited.get(nextKey);
      if (previousRecord && nextG >= previousRecord.g) continue;

      const nextRecord = {
        ...nextNode,
        g: nextG,
        f: nextG + heuristicDistance(nextNode, goalNode),
        parentKey: currentKey,
      };
      visited.set(nextKey, nextRecord);
      openList.push(nextRecord);
    }
  }

  if (bestDistance > PATH_GRID * 3) return [];

  const pathNodes = compactPathNodes(rebuildPathFromNodes(visited, bestKey)).slice(1);
  const waypoints = pathNodes.map((node) => ({
    x: node.x,
    y: node.y,
    floor: node.floor,
    roomId: null,
    roomKind: null,
    mode: "path",
    doorId: null,
  }));

  waypoints.push({
    x: targetStop.x,
    y: targetStop.y,
    floor: targetStop.floor,
    roomId: targetStop.roomId,
    roomKind: targetStop.roomKind,
    mode: "room",
    doorId: null,
  });
  return waypoints;
}

export function createNpcRuntime({ rooms, roomBounds, doors, canMoveTo, canPathfindTo, project, constants, gatePoint }) {
  const { CHARACTER_FOOT_RADIUS } = constants;
  const graph = createRoomGraph(rooms, roomBounds, doors);
  const runtimeGatePoint = gatePoint || { x: 14 * 32, y: 18 * 32, floor: 1 };
  const roomDoorsById = new Map();
  for (const door of doors) {
    const room = rooms[door.roomIndex];
    if (!room) continue;
    const id = roomId(room);
    if (!roomDoorsById.has(id)) roomDoorsById.set(id, []);
    roomDoorsById.get(id).push(door);
  }

  function findNearbyWalkablePoint(candidate, floor) {
    if (canMoveTo(candidate.x, candidate.y, floor)) return { x: candidate.x, y: candidate.y };
    for (let radius = 8; radius <= 96; radius += 8) {
      for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 8) {
        const nx = candidate.x + Math.cos(angle) * radius;
        const ny = candidate.y + Math.sin(angle) * radius;
        if (canMoveTo(nx, ny, floor)) return { x: nx, y: ny };
      }
    }
    return { x: candidate.x, y: candidate.y };
  }

  function buildDoorTransitPoints(door, room) {
    const bounds = roomBounds(room);
    const inside = buildDoorWaypoint(door, bounds);
    if (!inside) return null;

    let outside = { x: inside.x, y: inside.y };
    if (door.side === "bottom") outside = { x: door.pivot.x, y: bounds.y + bounds.h + 28 };
    else if (door.side === "top") outside = { x: door.pivot.x, y: bounds.y - 28 };
    else if (door.side === "left") outside = { x: bounds.x - 28, y: door.pivot.y };
    else if (door.side === "right") outside = { x: bounds.x + bounds.w + 28, y: door.pivot.y };

    return {
      inside: { ...findNearbyWalkablePoint(inside, room.floor), floor: room.floor },
      outside: { ...findNearbyWalkablePoint(outside, room.floor), floor: room.floor },
    };
  }

  function appendWaypoint(list, waypoint) {
    const previous = list[list.length - 1];
    if (
      previous
      && Math.abs(previous.x - waypoint.x) < 1
      && Math.abs(previous.y - waypoint.y) < 1
      && previous.floor === waypoint.floor
    ) {
      return;
    }
    list.push(waypoint);
  }

  function appendWaypoints(list, waypoints) {
    for (const waypoint of waypoints) appendWaypoint(list, waypoint);
  }

  function chooseDoorForRoom(room, referencePoint) {
    const doorList = roomDoorsById.get(roomId(room)) || [];
    if (!doorList.length) return null;

    let bestDoor = null;
    let bestDistance = Infinity;
    for (const door of doorList) {
      const transit = buildDoorTransitPoints(door, room);
      if (!transit) continue;
      const distance = Math.hypot(transit.outside.x - referencePoint.x, transit.outside.y - referencePoint.y);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestDoor = door;
      }
    }
    return bestDoor;
  }

  function buildDoorAwareRoute(npc, targetRoom, targetStop) {
    const pathfinder = canPathfindTo || canMoveTo;
    const currentState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
    const startPoint = {
      x: npc.x,
      y: npc.y,
      floor: npc.floor,
      roomId: currentState.roomId,
      roomKind: currentState.roomKind,
    };

    if (!targetRoom) {
      if (currentState.room) {
        const exitDoor = chooseDoorForRoom(currentState.room, targetStop);
        const exitTransit = exitDoor ? buildDoorTransitPoints(exitDoor, currentState.room) : null;
        if (exitTransit) {
          const route = [];
          appendWaypoints(route, buildPathWaypoints(startPoint, {
            x: exitTransit.inside.x,
            y: exitTransit.inside.y,
            floor: currentState.room.floor,
            roomId: currentState.roomId,
            roomKind: currentState.roomKind,
            mode: "door_approach",
            doorId: exitDoor.id,
          }, pathfinder));
          appendWaypoint(route, {
            x: exitTransit.outside.x,
            y: exitTransit.outside.y,
            floor: currentState.room.floor,
            roomId: groundRoomId(currentState.room.floor),
            roomKind: "grounds",
            mode: "door_exit",
            doorId: exitDoor.id,
          });
          appendWaypoints(route, buildPathWaypoints({
            x: exitTransit.outside.x,
            y: exitTransit.outside.y,
            floor: currentState.room.floor,
            roomId: groundRoomId(currentState.room.floor),
            roomKind: "grounds",
          }, targetStop, pathfinder));
          return route;
        }
      }
      return buildPathWaypoints(startPoint, targetStop, pathfinder);
    }

    if (currentState.roomId === targetStop.roomId) {
      return buildPathWaypoints(startPoint, targetStop, pathfinder);
    }

    const route = [];
    let cursor = startPoint;

    if (currentState.room) {
      const exitDoor = chooseDoorForRoom(currentState.room, targetStop);
      const exitTransit = exitDoor ? buildDoorTransitPoints(exitDoor, currentState.room) : null;
      if (exitTransit) {
        appendWaypoints(route, buildPathWaypoints(cursor, {
          x: exitTransit.inside.x,
          y: exitTransit.inside.y,
          floor: currentState.room.floor,
          roomId: currentState.roomId,
          roomKind: currentState.roomKind,
          mode: "door_approach",
          doorId: exitDoor.id,
        }, pathfinder));
        appendWaypoint(route, {
          x: exitTransit.outside.x,
          y: exitTransit.outside.y,
          floor: currentState.room.floor,
          roomId: groundRoomId(currentState.room.floor),
          roomKind: "grounds",
          mode: "door_exit",
          doorId: exitDoor.id,
        });
        cursor = {
          x: exitTransit.outside.x,
          y: exitTransit.outside.y,
          floor: currentState.room.floor,
          roomId: groundRoomId(currentState.room.floor),
          roomKind: "grounds",
        };
      }
    }

    const entryDoor = chooseDoorForRoom(targetRoom, cursor);
    const entryTransit = entryDoor ? buildDoorTransitPoints(entryDoor, targetRoom) : null;
    if (!entryTransit) {
      return buildPathWaypoints(cursor, targetStop, pathfinder);
    }

    appendWaypoints(route, buildPathWaypoints(cursor, {
      x: entryTransit.outside.x,
      y: entryTransit.outside.y,
      floor: targetRoom.floor,
      roomId: groundRoomId(targetRoom.floor),
      roomKind: "grounds",
      mode: "approach",
      doorId: entryDoor.id,
    }, pathfinder));
    appendWaypoint(route, {
      x: entryTransit.inside.x,
      y: entryTransit.inside.y,
      floor: targetRoom.floor,
      roomId: targetStop.roomId,
      roomKind: targetStop.roomKind,
      mode: "door_enter",
      doorId: entryDoor.id,
    });
    appendWaypoints(route, buildPathWaypoints({
      x: entryTransit.inside.x,
      y: entryTransit.inside.y,
      floor: targetRoom.floor,
      roomId: targetStop.roomId,
      roomKind: targetStop.roomKind,
    }, targetStop, pathfinder));
    return route;
  }

  function rebuildPathToCurrentTarget(npc) {
    const targetId = npc.targetRoomId;
    if (!targetId) return false;
    const targetRoom = graph.roomById.get(targetId);
    if (!targetRoom) return false;
    const targetBounds = graph.boundsById.get(targetId) || roomBounds(targetRoom);
    const targetStop = createRoomStop(targetRoom, targetBounds, canMoveTo);
    const roomState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
    npc.currentRoomId = roomState.roomId;
    npc.roomKind = roomState.roomKind;
    const pathWaypoints = buildDoorAwareRoute(npc, targetRoom, targetStop);
    npc.path = pathWaypoints.length
      ? pathWaypoints
      : buildTransitWaypoints(graph, findRoomPath(graph, npc.currentRoomId, targetId), targetStop);
    npc.state = "walking";
    npc.blockedMs = 0;
    return npc.path.length > 0;
  }

  function createNpc(index) {
    const startRoom = resolveRoomByKind("hall", graph) || rooms[0];
    const startBounds = graph.boundsById.get(roomId(startRoom)) || roomBounds(startRoom);
    const isGuideNpc = index < GUIDE_NPC_COUNT;
    const preferredGuideSpawn = isGuideNpc ? GUIDE_SPAWN_POINTS[index % GUIDE_SPAWN_POINTS.length] : null;
    const baseStartStop = preferredGuideSpawn
      ? {
          roomId: roomId(startRoom),
          roomKind: startRoom.kind,
          room: startRoom,
          bounds: startBounds,
          floor: preferredGuideSpawn.floor,
          ...findWalkablePoint(preferredGuideSpawn, preferredGuideSpawn.floor, canMoveTo, startBounds),
        }
      : createRoomStop(startRoom, startBounds, canMoveTo);
    const startStop = isGuideNpc ? baseStartStop : ensureNpcSpawnAwayFromPlayer(baseStartStop, startRoom, startBounds, canMoveTo);
    const startRoomState = detectRoomState(startStop.x, startStop.y, startStop.floor, rooms, roomBounds);
    return {
      id: `flow-npc-${index + 1}`,
      floor: startStop.floor,
      x: startStop.x,
      y: startStop.y,
      currentRoomId: startRoomState.roomId,
      routePattern: shuffle(WORKFLOW_PATTERNS[index % WORKFLOW_PATTERNS.length]),
      routeStep: 0,
      path: [],
      state: "pausing",
      stateTimerMs: 900 + Math.random() * 1200,
      speed: (isGuideNpc ? 50 : 42) + Math.random() * 14,
      roomKind: startRoomState.roomKind,
      bodyColor: isGuideNpc ? GUIDE_BODY_COLORS[index % GUIDE_BODY_COLORS.length] : BODY_COLORS[index % BODY_COLORS.length],
      accentColor: isGuideNpc ? GUIDE_ACCENT_COLORS[index % GUIDE_ACCENT_COLORS.length] : ACCENT_COLORS[index % ACCENT_COLORS.length],
      headColor: "#f0c9b7",
      hairColor: HAIR_COLORS[index % HAIR_COLORS.length],
      facing: "down",
      waitLabel: isGuideNpc ? "Route NPC" : "Waiting",
      isGuideNpc,
      targetRoomId: null,
      targetRoomKind: null,
      blockedMs: 0,
    };
  }

  const npcs = Array.from({ length: 9 }, (_, index) => createNpc(index));
  const hospitalNpcs = new Map();
  let hospitalSpawnSequence = 0;

  function allNpcs() {
    return [...npcs, ...hospitalNpcs.values()];
  }

  function createHospitalNpc(patient) {
    const spawnOffsets = [
      { x: 0, y: 0 },
      { x: 26, y: 18 },
      { x: -26, y: 20 },
      { x: 34, y: -14 },
      { x: -34, y: -12 },
      { x: 12, y: 30 },
      { x: -12, y: 28 },
    ];
    const offset = spawnOffsets[hospitalSpawnSequence % spawnOffsets.length];
    hospitalSpawnSequence += 1;
    const candidate = {
      x: runtimeGatePoint.x + offset.x,
      y: runtimeGatePoint.y + offset.y,
    };
    const safe = findNearbyWalkablePoint(candidate, runtimeGatePoint.floor);
    const roomState = detectRoomState(safe.x, safe.y, runtimeGatePoint.floor, rooms, roomBounds);
    return {
      id: `hospital-${patient.patientId}`,
      patientId: patient.patientId,
      floor: runtimeGatePoint.floor,
      x: safe.x,
      y: safe.y,
      currentRoomId: roomState.roomId,
      routePattern: [],
      routeStep: 0,
      path: [],
      state: "idle",
      stateTimerMs: 0,
      speed: 48,
      roomKind: roomState.roomKind,
      bodyColor: patient.priority === "H" ? "#d85e5e" : patient.priority === "L" ? "#76c59d" : "#8db1e8",
      accentColor: patient.priority === "H" ? "#ffd6d6" : patient.priority === "L" ? "#bdeccf" : "#cddcff",
      headColor: "#f0c9b7",
      hairColor: "#5d4128",
      facing: "right",
      waitLabel: patient.displayLabel || "Patient",
      isGuideNpc: false,
      isHospitalNpc: true,
      targetRoomId: null,
      targetRoomKind: null,
      blockedMs: 0,
      removeOnArrival: false,
      statusSummary: "",
      backendTargetKey: "",
      stepSeconds: 2,
      nextStepAt: "",
      backendPhase: "",
      backendRuntimeStatus: "",
      arrivedAtTargetAt: 0,
    };
  }

  function assignDestinationToPoint(npc, point, { roomKind = "grounds", removeOnArrival = false } = {}) {
    const targetRoom = roomKind && roomKind !== "grounds" ? resolveRoomByKind(roomKind, graph) : null;
    const targetStop = {
      x: point.x,
      y: point.y,
      floor: point.floor,
      roomId: targetRoom ? roomId(targetRoom) : groundRoomId(point.floor),
      roomKind,
      room: targetRoom,
      bounds: targetRoom ? (graph.boundsById.get(roomId(targetRoom)) || roomBounds(targetRoom)) : null,
    };
    npc.path = buildDoorAwareRoute(npc, targetRoom, targetStop);
    npc.state = npc.path.length ? "walking" : "idle";
    npc.targetRoomId = targetStop.roomId;
    npc.targetRoomKind = roomKind;
    npc.removeOnArrival = removeOnArrival;
    npc.blockedMs = 0;
  }

  function assignHospitalNpcDestination(npc, patient) {
    npc.waitLabel = patient.displayLabel || npc.waitLabel;
    npc.stepSeconds = Number.isFinite(Number(patient.stepSeconds)) ? Math.max(0.1, Number(patient.stepSeconds)) : 2;
    npc.speed = patient.finished ? 72 : Math.max(48, Math.min(160, 220 / npc.stepSeconds));
    npc.statusSummary = patient.statusSummary || "";
    npc.nextStepAt = patient.nextStepAt || "";
    npc.backendPhase = patient.phase || "";
    npc.backendRuntimeStatus = patient.runtimeStatus || "";
    const nextTargetKey = `${patient.roomKind}|${patient.finished ? "finished" : "active"}|${patient.visitState}|${patient.currentNodeId || ""}|${patient.targetNodeId || ""}|${patient.nextStepAt || ""}`;
    if (npc.backendTargetKey === nextTargetKey) return;
    if (
      npc.targetRoomKind === patient.roomKind
      && npc.targetRoomId
      && !patient.finished
      && npc.path.length
    ) {
      npc.backendTargetKey = nextTargetKey;
      return;
    }
    npc.backendTargetKey = nextTargetKey;
    if (patient.finished) {
      assignDestinationToPoint(
        npc,
        { x: runtimeGatePoint.x, y: runtimeGatePoint.y, floor: runtimeGatePoint.floor },
        { roomKind: "grounds", removeOnArrival: true }
      );
      return;
    }
    const targetRoom = resolveRoomByKind(patient.roomKind, graph);
    if (!targetRoom) return;
    const targetBounds = graph.boundsById.get(roomId(targetRoom)) || roomBounds(targetRoom);
    const targetStop = createRoomStop(targetRoom, targetBounds, canMoveTo);
    npc.path = buildDoorAwareRoute(npc, targetRoom, targetStop);
    npc.state = npc.path.length ? "walking" : "idle";
    npc.targetRoomId = roomId(targetRoom);
    npc.targetRoomKind = patient.roomKind;
    npc.removeOnArrival = false;
    npc.blockedMs = 0;
    npc.arrivedAtTargetAt = 0;
  }

  function syncHospitalPatients(scenePatients = []) {
    const seen = new Set();
    for (const patient of scenePatients) {
      const patientId = String(patient.patientId || "");
      if (!patientId) continue;
      seen.add(patientId);
      let npc = hospitalNpcs.get(patientId);
      if (!npc) {
        npc = createHospitalNpc(patient);
        hospitalNpcs.set(patientId, npc);
      }
      assignHospitalNpcDestination(npc, patient);
    }

    for (const [patientId, npc] of hospitalNpcs.entries()) {
      if (seen.has(patientId)) continue;
      if (!npc.removeOnArrival) {
        assignDestinationToPoint(
          npc,
          { x: runtimeGatePoint.x, y: runtimeGatePoint.y, floor: runtimeGatePoint.floor },
          { roomKind: "grounds", removeOnArrival: true }
        );
      }
    }
  }

  function assignNextDestination(npc) {
    if (!npc.routePattern.length) return;
    const nextKind = npc.routePattern[npc.routeStep % npc.routePattern.length];
    npc.routeStep += 1;
    assignDestinationByKind(npc, nextKind);
  }

  function assignDestinationByKind(npc, roomKind) {
    const targetRoom = resolveRoomByKind(roomKind, graph);
    if (!targetRoom) return false;
    const targetId = roomId(targetRoom);
    const targetBounds = graph.boundsById.get(targetId) || roomBounds(targetRoom);
    const targetStop = createRoomStop(targetRoom, targetBounds, canMoveTo);
    const roomState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
    npc.currentRoomId = roomState.roomId;
    npc.roomKind = roomState.roomKind;
    const pathWaypoints = buildDoorAwareRoute(npc, targetRoom, targetStop);
    npc.path = pathWaypoints.length
      ? pathWaypoints
      : buildTransitWaypoints(graph, findRoomPath(graph, npc.currentRoomId, targetId), targetStop);
    npc.state = "walking";
    npc.targetRoomId = targetId;
    npc.targetRoomKind = roomKind;
    npc.blockedMs = 0;
    npc.waitLabel = npc.isGuideNpc ? `Route: ${roomKind}` : roomKind === "hall" ? "Waiting" : "Transit";
    return true;
  }

  function arriveAtWaypoint(npc) {
    if (!npc.path.length) {
      if (npc.isHospitalNpc && npc.removeOnArrival) {
        hospitalNpcs.delete(npc.patientId);
        return;
      }
      npc.state = "pausing";
      npc.stateTimerMs = npc.isHospitalNpc ? 100 : 1200 + Math.random() * 2200;
      npc.waitLabel = npc.isGuideNpc ? `At ${npc.roomKind}` : npc.roomKind === "hall" ? "Waiting" : "Check-in";
      npc.arrivedAtTargetAt = performance.now();
      return;
    }
    const waypoint = npc.path.shift();
    npc.x = waypoint.x;
    npc.y = waypoint.y;
    npc.floor = waypoint.floor;
    const roomState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
    npc.currentRoomId = waypoint.roomId || roomState.roomId || npc.currentRoomId;
    npc.roomKind = waypoint.roomKind || roomState.roomKind || npc.roomKind;
    if (!npc.path.length) {
      if (npc.isHospitalNpc && npc.removeOnArrival) {
        hospitalNpcs.delete(npc.patientId);
        return;
      }
      npc.state = "pausing";
      npc.stateTimerMs = npc.isHospitalNpc ? 100 : 1200 + Math.random() * 2200;
      npc.waitLabel = npc.isGuideNpc ? `At ${npc.roomKind}` : npc.roomKind === "hall" ? "Waiting" : "Check-in";
      npc.targetRoomId = null;
      npc.targetRoomKind = null;
      npc.blockedMs = 0;
      npc.arrivedAtTargetAt = performance.now();
    }
  }

  function update(delta) {
    for (const npc of allNpcs()) {
      if (npc.isHospitalNpc && npc.state === "idle") {
        continue;
      }
      if (npc.state === "pausing") {
        npc.stateTimerMs -= delta * 1000;
        if (npc.stateTimerMs <= 0) {
          if (npc.isHospitalNpc) {
            npc.state = "idle";
            continue;
          }
          assignNextDestination(npc);
        }
        continue;
      }

      const waypoint = npc.path[0];
      if (!waypoint) {
        npc.state = npc.isHospitalNpc ? "idle" : "pausing";
        npc.stateTimerMs = npc.isHospitalNpc ? 0 : 1000 + Math.random() * 1800;
        continue;
      }

      const dx = waypoint.x - npc.x;
      const dy = waypoint.y - npc.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 3) {
        arriveAtWaypoint(npc);
        continue;
      }

      npc.facing = facingFromDelta(dx, dy, npc.facing);
      const step = npc.speed * delta;
      const ratio = step >= dist ? 1 : step / dist;
      const nextX = npc.x + dx * ratio;
      const nextY = npc.y + dy * ratio;
      if (canMoveTo(nextX, nextY, waypoint.floor)) {
        npc.x = nextX;
        npc.y = nextY;
        npc.floor = waypoint.floor;
        const roomState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
        npc.currentRoomId = roomState.roomId;
        npc.roomKind = roomState.roomKind;
        npc.blockedMs = 0;
        continue;
      }

      const slideOptions = [
        { x: npc.x + dx * ratio, y: npc.y, floor: waypoint.floor },
        { x: npc.x, y: npc.y + dy * ratio, floor: waypoint.floor },
        { x: npc.x + dx * ratio * 0.75 - dy * ratio * 0.3, y: npc.y + dy * ratio * 0.75 + dx * ratio * 0.3, floor: waypoint.floor },
        { x: npc.x + dx * ratio * 0.75 + dy * ratio * 0.3, y: npc.y + dy * ratio * 0.75 - dx * ratio * 0.3, floor: waypoint.floor },
      ];
      const slideMove = slideOptions.find((candidate) => canMoveTo(candidate.x, candidate.y, candidate.floor));
      if (slideMove) {
        npc.x = slideMove.x;
        npc.y = slideMove.y;
        npc.floor = slideMove.floor;
        const roomState = detectRoomState(npc.x, npc.y, npc.floor, rooms, roomBounds);
        npc.currentRoomId = roomState.roomId;
        npc.roomKind = roomState.roomKind;
        npc.blockedMs = 0;
        continue;
      }

      npc.blockedMs += delta * 1000;
      if (npc.blockedMs >= 500) {
        if (!rebuildPathToCurrentTarget(npc)) {
          npc.state = "pausing";
          npc.stateTimerMs = 600;
        }
      }
    }
  }

  function draw(ctx, floor, alpha = 1) {
    for (const npc of allNpcs()) {
      if (npc.floor !== floor) continue;
      const base = project(npc.x, npc.y, 0, npc.floor);
      const px = Math.round(base.x);
      const py = Math.round(base.y);
      ctx.save();
      ctx.globalAlpha *= alpha;
      ctx.fillStyle = "rgba(44, 30, 18, 0.22)";
      ctx.beginPath();
      ctx.ellipse(px, py + 14, CHARACTER_FOOT_RADIUS + 3, CHARACTER_FOOT_RADIUS - 2, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#4d4d5c";
      ctx.fillRect(px - 6, py + 9, 4, 10);
      ctx.fillRect(px + 2, py + 9, 4, 10);
      ctx.fillRect(px - 8, py + 18, 6, 3);
      ctx.fillRect(px + 2, py + 18, 6, 3);

      ctx.fillStyle = npc.bodyColor;
      ctx.fillRect(px - 9, py - 6, 18, 18);
      ctx.fillStyle = npc.headColor;
      ctx.fillRect(px - 3, py - 10, 6, 6);
      ctx.fillStyle = npc.accentColor;
      ctx.fillRect(px - 7, py - 2, 14, 4);
      ctx.fillRect(px - 2, py + 2, 4, 10);
      ctx.fillStyle = "#f7f2e6";
      ctx.fillRect(px - 2, py - 2, 4, 5);
      ctx.fillStyle = npc.accentColor;
      ctx.fillRect(px - 10, py + 2, 3, 8);
      ctx.fillRect(px + 7, py + 2, 3, 8);

      if (npc.facing === "left") {
        ctx.fillRect(px - 12, py, 3, 8);
      } else if (npc.facing === "right") {
        ctx.fillRect(px + 9, py, 3, 8);
      }

      ctx.fillStyle = npc.headColor;
      ctx.fillRect(px - 9, py - 24, 18, 16);
      ctx.fillStyle = npc.hairColor;
      ctx.fillRect(px - 10, py - 25, 20, 6);
      ctx.fillRect(px - 10, py - 19, 4, 7);
      ctx.fillRect(px + 6, py - 19, 4, 7);
      ctx.fillStyle = npc.accentColor;
      ctx.fillRect(px - 11, py - 27, 22, 3);
      ctx.fillRect(px - 8, py - 30, 16, 4);

      if (npc.facing !== "up") {
        const eyeY = py - 18;
        ctx.fillStyle = "#2b2018";
        if (npc.facing === "left") {
          ctx.fillRect(px - 6, eyeY, 2, 2);
        } else if (npc.facing === "right") {
          ctx.fillRect(px + 4, eyeY, 2, 2);
        } else {
          ctx.fillRect(px - 6, eyeY, 2, 2);
          ctx.fillRect(px + 4, eyeY, 2, 2);
        }
      }

      if (npc.state === "pausing" || npc.state === "idle") {
        ctx.fillStyle = npc.isGuideNpc ? "#fff1a8" : "#ffe99c";
        ctx.font = "600 10px 'Trebuchet MS'";
        ctx.textAlign = "center";
        ctx.fillText(npc.waitLabel, px, py - 34);
      }

      if (npc.isHospitalNpc && npc.statusSummary) {
        const width = 92;
        const height = 14;
        ctx.fillStyle = "rgba(47, 31, 20, 0.88)";
        ctx.fillRect(px - width / 2, py - 52, width, height);
        ctx.strokeStyle = "rgba(255, 241, 184, 0.6)";
        ctx.lineWidth = 1;
        ctx.strokeRect(px - width / 2, py - 52, width, height);
        ctx.fillStyle = "#fff6de";
        ctx.font = "600 8px 'Trebuchet MS'";
        ctx.fillText(npc.statusSummary, px, py - 42);
      }

      if (npc.isGuideNpc) {
        const label = "ROUTE NPC";
        const width = 62;
        const height = 16;
        ctx.fillStyle = "rgba(135, 28, 28, 0.92)";
        ctx.fillRect(px - width / 2, py - 52, width, height);
        ctx.strokeStyle = "rgba(255, 213, 213, 0.95)";
        ctx.lineWidth = 2;
        ctx.strokeRect(px - width / 2, py - 52, width, height);
        ctx.fillStyle = "#fff3f3";
        ctx.font = "700 9px 'Trebuchet MS'";
        ctx.textAlign = "center";
        ctx.fillText(label, px, py - 41);
      }
      ctx.restore();
    }
  }

  return {
    update,
    draw,
    routeGuideNpcsTo: (roomKind) => {
      let routed = 0;
      for (const npc of npcs) {
        if (!npc.isGuideNpc) continue;
        if (assignDestinationByKind(npc, roomKind)) routed += 1;
      }
      return routed;
    },
    syncHospitalPatients,
    getNpcs: () => allNpcs(),
  };
}
