import test from "node:test";
import assert from "node:assert/strict";

import { createFixedNpcRuntime } from "../npc/fixed-runtime.js";

const TILE = 32;

const rooms = [
  { floor: 1, x: 3, y: 4, w: 13, h: 8, kind: "registration" },
  { floor: 1, x: 17, y: 4, w: 12, h: 8, kind: "consultation" },
  { floor: 1, x: 30, y: 4, w: 12, h: 8, kind: "consultation" },
  { floor: 1, x: 3, y: 14, w: 17, h: 10, kind: "triage" },
  { floor: 1, x: 21, y: 13, w: 15, h: 11, kind: "hall" },
  { floor: 1, x: 37, y: 14, w: 9, h: 10, kind: "pharmacy" },
  { floor: 2, x: 4, y: 5, w: 12, h: 8, kind: "ward" },
  { floor: 2, x: 17, y: 4, w: 11, h: 9, kind: "ward" },
  { floor: 2, x: 29, y: 4, w: 12, h: 9, kind: "icu" },
  { floor: 2, x: 4, y: 15, w: 13, h: 10, kind: "lab" },
  { floor: 2, x: 18, y: 14, w: 14, h: 10, kind: "hall" },
  { floor: 2, x: 33, y: 15, w: 12, h: 10, kind: "office" },
];

function roomBounds(room) {
  return { x: room.x * TILE, y: room.y * TILE, w: room.w * TILE, h: room.h * TILE };
}

function createRuntime() {
  return createFixedNpcRuntime({
    rooms,
    roomBounds,
    canMoveTo: () => true,
  });
}

test("fixed npc runtime resolves only fixed staff and respects floor filtering", () => {
  const runtime = createRuntime();
  const npcs = runtime.getNpcs();

  assert.equal(npcs.length, 6);
  assert.ok(npcs.every((npc) => npc.kind === "fixed"));
  assert.ok(npcs.every((npc) => !npc.id.startsWith("merged-npc-")));

  const hallNpc = npcs.find((npc) => npc.id === "hall-clerk");
  assert.ok(hallNpc);

  const nearestSameFloor = runtime.getNearestNpc({
    x: hallNpc.x + 8,
    y: hallNpc.y + 8,
    floor: hallNpc.floor,
  });
  assert.ok(nearestSameFloor);
  assert.equal(nearestSameFloor.id, hallNpc.id);

  const nearestOtherFloor = runtime.getNearestNpc({
    x: hallNpc.x + 8,
    y: hallNpc.y + 8,
    floor: 2,
  });
  assert.ok(nearestOtherFloor);
  assert.equal(nearestOtherFloor.floor, 2);
  assert.notEqual(nearestOtherFloor.id, hallNpc.id);
});

test("fixed npc dialogue advances through line, choice, action, and end", () => {
  const runtime = createRuntime();
  const npc = runtime.getNpcs().find((item) => item.id === "hall-clerk");
  assert.ok(npc);

  assert.equal(runtime.tryInteract({
    x: npc.x + 4,
    y: npc.y + 4,
    floor: npc.floor,
  }), true);
  assert.equal(runtime.isDialogueOpen(), true);

  let snapshot = runtime.getDialogueSnapshot();
  assert.ok(snapshot.npc);
  assert.ok(snapshot.node);
  assert.equal(snapshot.npc.id, "hall-clerk");
  assert.equal(snapshot.node.type, "line");

  assert.equal(runtime.advanceDialogue(), true);
  snapshot = runtime.getDialogueSnapshot();
  assert.ok(snapshot.node);
  assert.equal(snapshot.node.type, "choice");
  assert.equal(snapshot.selectedOptionIndex, 0);

  assert.equal(runtime.moveSelection(1), true);
  snapshot = runtime.getDialogueSnapshot();
  assert.equal(snapshot.selectedOptionIndex, 1);

  assert.equal(runtime.advanceDialogue(), true);
  snapshot = runtime.getDialogueSnapshot();
  assert.ok(snapshot.node);
  assert.equal(snapshot.node.type, "line");

  assert.equal(runtime.advanceDialogue(), true);
  snapshot = runtime.getDialogueSnapshot();
  assert.ok(snapshot.node);
  assert.equal(snapshot.node.type, "end");

  assert.equal(runtime.advanceDialogue(), true);
  assert.equal(runtime.isDialogueOpen(), false);
});

test("fixed npc runtime ignores distant interaction attempts", () => {
  const runtime = createRuntime();
  assert.equal(runtime.tryInteract({
    x: 0,
    y: 0,
    floor: 1,
  }), false);
  assert.equal(runtime.isDialogueOpen(), false);
});
