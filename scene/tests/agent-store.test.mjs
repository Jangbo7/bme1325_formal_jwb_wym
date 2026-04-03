import test from "node:test";
import assert from "node:assert/strict";

import { buildDialogueMessages, createAgentStore } from "../agent/store.js";

test("agent store syncs patient and queue state", () => {
  const store = createAgentStore();
  store.syncPatient({ id: "P-self", name: "Player" });
  store.syncQueues([{ department_id: "internal", waiting: [] }]);
  assert.equal(store.lastPatient.id, "P-self");
  assert.equal(store.lastQueues.length, 1);
});

test("dialogue message builder falls back to assistant message", () => {
  const messages = buildDialogueMessages({
    name: "Player",
    dialogue: { assistant_message: "Need more details." },
  });
  assert.equal(messages[0].role, "user");
  assert.equal(messages[1].body, "Need more details.");
});
