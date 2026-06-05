from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.schemas.patient_agent_debug import PatientAgentDebugSpawnRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["patient_agent_debug_controller"]


@router.get("/patient-agent-debug", response_class=HTMLResponse, include_in_schema=False)
def patient_agent_debug_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Patient Agent Debug</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2e8;
      --card: #fbfff7;
      --ink: #142217;
      --accent: #2f6b45;
      --line: #bfd1c2;
    }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background: radial-gradient(circle at top, #f5fff2 0%, var(--bg) 45%, #e1eadc 100%);
      color: var(--ink);
    }
    main {
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: 34px;
    }
    .subtle {
      font-size: 14px;
      color: #516255;
      margin-bottom: 16px;
    }
    .toolbar, .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 10px 24px rgba(31, 62, 37, 0.08);
      padding: 16px;
      margin-bottom: 16px;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }
    input, button, a.button {
      font: inherit;
      border-radius: 10px;
      border: 1px solid #8bab93;
      padding: 10px 12px;
      background: #fff;
      color: var(--ink);
      text-decoration: none;
    }
    button, a.button.primary {
      cursor: pointer;
      background: linear-gradient(180deg, #45805a 0%, var(--accent) 100%);
      color: #f7fff8;
      border-color: #27573a;
    }
    button.secondary, a.button.secondary {
      background: #edf5ee;
      color: var(--ink);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #617267;
    }
    .value {
      margin-top: 4px;
      font-size: 16px;
      word-break: break-word;
    }
    #status {
      min-height: 18px;
      font-size: 14px;
      color: #2a5d3e;
      margin-bottom: 12px;
    }
    #dialogueBox {
      display: none;
      border-top: 1px dashed var(--line);
      margin-top: 12px;
      padding-top: 12px;
    }
    #transcript, #medicalRecordEntries {
      display: grid;
      gap: 10px;
    }
    .turn {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }
    .turn small {
      display: block;
      color: #66756b;
      margin-bottom: 6px;
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, monospace;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <main>
    <h1>Patient Agent Debug</h1>
    <div class="subtle">LLM-generated case card + LLM-generated patient replies. Legacy template mode remains at <a href="/npc-debug">/npc-debug</a>.</div>
    <div class="toolbar">
      <label>
        <span class="label">Seed (Optional)</span><br />
        <input id="seedInput" placeholder="replay hint" />
      </label>
      <button id="spawnBtn">Spawn</button>
      <button id="stepBtn">Step</button>
      <button id="refreshBtn" class="secondary">Refresh</button>
      <button id="resetBtn" class="secondary">Reset</button>
      <a href="/npc-debug" class="button secondary">Open Legacy Debug</a>
    </div>
    <div id="status"></div>
    <section class="panel">
      <div class="grid">
        <div><div class="label">NPC</div><div class="value" id="npcId">-</div></div>
        <div><div class="label">Mode</div><div class="value" id="mode">-</div></div>
        <div><div class="label">Patient</div><div class="value" id="patientId">-</div></div>
        <div><div class="label">Encounter</div><div class="value" id="encounterId">-</div></div>
        <div><div class="label">Visit State</div><div class="value" id="visitState">-</div></div>
        <div><div class="label">Patient State</div><div class="value" id="patientState">-</div></div>
        <div><div class="label">Phase</div><div class="value" id="phase">-</div></div>
        <div><div class="label">Status</div><div class="value" id="npcStatus">-</div></div>
        <div><div class="label">Case Status</div><div class="value" id="caseStatus">-</div></div>
        <div><div class="label">Counterparty</div><div class="value" id="counterparty">-</div></div>
        <div><div class="label">Last Action</div><div class="value" id="lastAction">-</div></div>
        <div><div class="label">Steps</div><div class="value" id="stepCount">0</div></div>
      </div>
      <div id="dialogueBox">
        <div class="label">Current Dialogue</div>
        <div class="value" id="dialogueSpeaker">-</div>
        <div class="value" id="dialogueMessage">-</div>
      </div>
    </section>
    <section class="panel">
      <div class="label">Case Summary</div>
      <pre id="caseSummary">No case yet.</pre>
    </section>
    <section class="panel">
      <div class="label">Policy State</div>
      <pre id="policyState">No policy decision yet.</pre>
    </section>
    <section class="panel">
      <div class="label">Transcript</div>
      <div id="transcript"></div>
    </section>
    <section class="panel">
      <div class="label">Medical Record</div>
      <div class="grid">
        <div><div class="label">Record ID</div><div class="value" id="mrRecordId">-</div></div>
        <div><div class="label">Entry Count</div><div class="value" id="mrEntryCount">0</div></div>
        <div><div class="label">Latest Type</div><div class="value" id="mrLatestType">-</div></div>
        <div><div class="label">Latest Phase</div><div class="value" id="mrLatestPhase">-</div></div>
      </div>
      <div id="medicalRecordEntries"></div>
    </section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const fields = {
      npcId: document.getElementById("npcId"),
      mode: document.getElementById("mode"),
      patientId: document.getElementById("patientId"),
      encounterId: document.getElementById("encounterId"),
      visitState: document.getElementById("visitState"),
      patientState: document.getElementById("patientState"),
      phase: document.getElementById("phase"),
      npcStatus: document.getElementById("npcStatus"),
      caseStatus: document.getElementById("caseStatus"),
      counterparty: document.getElementById("counterparty"),
      lastAction: document.getElementById("lastAction"),
      stepCount: document.getElementById("stepCount"),
      dialogueBox: document.getElementById("dialogueBox"),
      dialogueSpeaker: document.getElementById("dialogueSpeaker"),
      dialogueMessage: document.getElementById("dialogueMessage"),
      caseSummary: document.getElementById("caseSummary"),
      policyState: document.getElementById("policyState"),
      transcript: document.getElementById("transcript"),
      mrRecordId: document.getElementById("mrRecordId"),
      mrEntryCount: document.getElementById("mrEntryCount"),
      mrLatestType: document.getElementById("mrLatestType"),
      mrLatestPhase: document.getElementById("mrLatestPhase"),
      medicalRecordEntries: document.getElementById("medicalRecordEntries"),
      seedInput: document.getElementById("seedInput"),
    };

    function nextIdempotencyKey() {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
      return "patient-agent-debug-" + Date.now() + "-" + Math.random().toString(16).slice(2);
    }

    async function api(path, method = "GET", body = null) {
      const headers = {};
      if (method !== "GET") {
        headers["Content-Type"] = "application/json";
        headers["Idempotency-Key"] = nextIdempotencyKey();
      }
      const response = await fetch(path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        const message = payload.error?.message || payload.error?.details || response.statusText;
        throw new Error(typeof message === "string" ? message : JSON.stringify(message));
      }
      return payload.data;
    }

    function renderSnapshot(snapshot) {
      if (!snapshot) {
        fields.npcId.textContent = "-";
        fields.mode.textContent = "-";
        fields.patientId.textContent = "-";
        fields.encounterId.textContent = "-";
        fields.visitState.textContent = "-";
        fields.patientState.textContent = "-";
        fields.phase.textContent = "-";
        fields.npcStatus.textContent = "-";
        fields.caseStatus.textContent = "-";
        fields.counterparty.textContent = "-";
        fields.lastAction.textContent = "-";
        fields.stepCount.textContent = "0";
        fields.caseSummary.textContent = "No case yet.";
        fields.policyState.textContent = "No policy decision yet.";
        fields.dialogueBox.style.display = "none";
        fields.transcript.innerHTML = "<div class='value'>No active patient agent.</div>";
        fields.mrRecordId.textContent = "-";
        fields.mrEntryCount.textContent = "0";
        fields.mrLatestType.textContent = "-";
        fields.mrLatestPhase.textContent = "-";
        fields.medicalRecordEntries.innerHTML = "<div class='value'>No record yet.</div>";
        return;
      }

      fields.npcId.textContent = snapshot.npc_id || "-";
      fields.mode.textContent = snapshot.mode || "-";
      fields.patientId.textContent = snapshot.patient_id || "-";
      fields.encounterId.textContent = snapshot.encounter_id || "-";
      fields.visitState.textContent = snapshot.visit_state || "-";
      fields.patientState.textContent = snapshot.patient_lifecycle_state || "-";
      fields.phase.textContent = snapshot.phase || "-";
      fields.npcStatus.textContent = snapshot.status || "-";
      fields.caseStatus.textContent = snapshot.case_generation_status || "-";
      fields.counterparty.textContent = snapshot.current_counterparty || "-";
      fields.lastAction.textContent = snapshot.last_action || "-";
      fields.stepCount.textContent = String(snapshot.step_count || 0);
      fields.caseSummary.textContent = JSON.stringify(snapshot.case_summary || {}, null, 2);
      fields.policyState.textContent = JSON.stringify(snapshot.policy_state || {}, null, 2);
      fields.mrRecordId.textContent = snapshot.medical_record_summary?.record_id || "-";
      fields.mrEntryCount.textContent = String(snapshot.medical_record_summary?.entry_count || 0);
      fields.mrLatestType.textContent = snapshot.medical_record_summary?.latest_entry_type || "-";
      fields.mrLatestPhase.textContent = snapshot.medical_record_summary?.latest_phase || "-";

      if (snapshot.current_dialogue) {
        fields.dialogueBox.style.display = "block";
        fields.dialogueSpeaker.textContent = snapshot.current_dialogue.speaker + " (" + snapshot.current_dialogue.direction + ")";
        fields.dialogueMessage.textContent = snapshot.current_dialogue.message || "-";
      } else {
        fields.dialogueBox.style.display = "none";
      }

      if (!snapshot.transcript || snapshot.transcript.length === 0) {
        fields.transcript.innerHTML = "<div class='value'>No dialogue yet.</div>";
      } else {
        fields.transcript.innerHTML = snapshot.transcript.map((turn) => `
          <div class="turn">
            <small>${turn.turn_id} | ${turn.phase} | ${turn.counterparty} | ${turn.timestamp}</small>
            <div><strong>${turn.speaker}</strong></div>
            <div>${turn.message}</div>
          </div>
        `).join("");
      }
    }

    function renderMedicalRecordTimeline(data) {
      if (!data || !data.entries || data.entries.length === 0) {
        fields.medicalRecordEntries.innerHTML = "<div class='value'>No record entries yet.</div>";
        return;
      }
      fields.medicalRecordEntries.innerHTML = data.entries.map((entry) => `
        <div class="turn">
          <small>#${entry.entry_id} | ${entry.phase} | ${entry.entry_type} | ${entry.created_at}</small>
          <div><strong>${entry.title}</strong></div>
          <div>${entry.content_text}</div>
        </div>
      `).join("");
    }

    async function refreshSnapshot(showStatus = false) {
      try {
        const snapshot = await api("/api/v1/patient-agent-debug/snapshot");
        renderSnapshot(snapshot);
        const timeline = await api("/api/v1/patient-agent-debug/medical-record");
        renderMedicalRecordTimeline(timeline);
        if (showStatus) {
          statusEl.textContent = "Snapshot refreshed.";
        }
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    document.getElementById("spawnBtn").addEventListener("click", async () => {
      try {
        const snapshot = await api("/api/v1/patient-agent-debug/spawn", "POST", {
          seed: fields.seedInput.value || null,
        });
        statusEl.textContent = "Patient agent spawned.";
        renderSnapshot(snapshot);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("stepBtn").addEventListener("click", async () => {
      try {
        const snapshot = await api("/api/v1/patient-agent-debug/step", "POST", {});
        statusEl.textContent = "Step executed.";
        renderSnapshot(snapshot);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("refreshBtn").addEventListener("click", () => refreshSnapshot(true));

    document.getElementById("resetBtn").addEventListener("click", async () => {
      try {
        await api("/api/v1/patient-agent-debug/reset", "POST", {});
        statusEl.textContent = "Controller reset.";
        renderSnapshot(null);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    setInterval(() => refreshSnapshot(false), 2000);
    refreshSnapshot(false);
  </script>
</body>
</html>
        """
    )


@router.post("/api/v1/patient-agent-debug/spawn")
def spawn_patient_agent_debug(body: PatientAgentDebugSpawnRequest, request: Request):
    controller = _controller(request)
    try:
        snapshot = controller.spawn(seed=body.seed)
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 503 if "llm" in detail.lower() else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/patient-agent-debug/step")
def step_patient_agent_debug(request: Request):
    controller = _controller(request)
    try:
        snapshot = controller.step()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 503 if "llm" in detail.lower() else 500
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/patient-agent-debug/snapshot")
def get_patient_agent_debug_snapshot(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/patient-agent-debug/reset")
def reset_patient_agent_debug(request: Request):
    _controller(request).reset()
    return {"ok": True, "data": None}


@router.get("/api/v1/patient-agent-debug/medical-record")
def get_patient_agent_debug_medical_record(request: Request):
    timeline = _controller(request).get_medical_record()
    return {"ok": True, "data": timeline}
