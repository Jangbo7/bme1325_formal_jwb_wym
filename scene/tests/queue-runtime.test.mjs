import test from "node:test";
import assert from "node:assert/strict";

import { createQueueRuntime } from "../queue/runtime.js";

test("queue runtime syncs player ticket from api data", () => {
  const runtime = createQueueRuntime();
  runtime.syncFromApi(
    [
      {
        department_id: "internal",
        department_name: "General Medicine",
        waiting: [
          { id: "t-1", patient_id: "P-self", department_id: "internal", department_name: "General Medicine", number: 3, status: "waiting" },
        ],
        called: null,
      },
    ],
    "P-self"
  );
  assert.equal(runtime.state.playerTicket.id, "t-1");
});
