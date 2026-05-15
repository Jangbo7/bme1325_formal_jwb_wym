from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.schemas.multi_patient_debug import MultiPatientDebugStartRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["multi_patient_debug_controller"]


@router.get("/multi-patient-debug", response_class=HTMLResponse, include_in_schema=False)
def multi_patient_debug_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Multi Patient Debug</title>
  <style>
    :root {
      --bg: #f2f7ef;
      --ink: #142215;
      --panel: #ffffff;
      --line: #c9d8c8;
      --accent: #2f6d44;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top, #f9fff5 0%, var(--bg) 50%, #e3ebdf 100%);
    }
    main { max-width: 1200px; margin: 0 auto; padding: 20px 16px 40px; }
    h1 { margin: 0 0 8px; }
    .toolbar, .panel, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 8px 20px rgba(15, 35, 16, 0.08);
    }
    .toolbar { padding: 14px; display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
    .panel { padding: 14px; margin-top: 12px; }
    label { font-size: 12px; text-transform: uppercase; color: #4f6253; }
    input, select, button {
      font: inherit;
      border: 1px solid #8ea88f;
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
    }
    button {
      background: linear-gradient(180deg, #3f8259 0%, var(--accent) 100%);
      color: #fff;
      cursor: pointer;
    }
    button.secondary { background: #edf5ee; color: var(--ink); }
    .muted { color: #4e6153; font-size: 13px; }
    #status { margin-top: 10px; font-size: 14px; color: #28553a; min-height: 18px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
    .stat { border: 1px dashed var(--line); border-radius: 10px; padding: 8px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; margin-top: 12px; }
    .card { padding: 12px; }
    .badge { font-size: 12px; border-radius: 999px; padding: 2px 8px; border: 1px solid #9db39e; display: inline-block; }
    .row { margin-top: 6px; font-size: 14px; }
    .dialogue { margin-top: 10px; padding: 10px; border: 1px dashed var(--line); border-radius: 10px; background: #f7fbf6; }
    pre { white-space: pre-wrap; word-break: break-word; margin: 0; font-size: 12px; }
  </style>
</head>
<body>
  <main>
    <h1>Multi Patient Debug</h1>
    <div class="muted">Auto-generate up to 10 patients and auto-step each patient to the next legal state at fixed intervals (random step order).</div>
    <div class="toolbar">
      <div>
        <label>Mode</label><br />
        <select id="mode">
          <option value="intelligent_agent">intelligent_agent</option>
          <option value="legacy_template">legacy_template</option>
        </select>
      </div>
      <div>
        <label>Spawn Interval(s)</label><br />
        <input id="spawnInterval" type="number" min="0" step="0.5" value="4" />
      </div>
      <div>
        <label>Step Interval(s)</label><br />
        <input id="stepInterval" type="number" min="0.1" step="0.5" value="2" />
      </div>
      <div>
        <label>Max Patients (<=10)</label><br />
        <input id="maxPatients" type="number" min="1" max="10" step="1" value="10" />
      </div>
      <button id="startBtn">Start</button>
      <button id="stopBtn" class="secondary">Stop</button>
      <button id="resetBtn" class="secondary">Reset</button>
      <button id="refreshBtn" class="secondary">Refresh</button>
    </div>
    <div id="status"></div>
    <section class="panel">
      <div class="stats" id="stats"></div>
    </section>
    <section class="cards" id="cards"></section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const statsEl = document.getElementById("stats");
    const cardsEl = document.getElementById("cards");

    function nextIdempotencyKey() {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
      return "multi-patient-debug-" + Date.now() + "-" + Math.random().toString(16).slice(2);
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

    function render(snapshot) {
      if (!snapshot) {
        statsEl.innerHTML = "<div class='muted'>No data.</div>";
        cardsEl.innerHTML = "";
        return;
      }

      statsEl.innerHTML = `
        <div class="stat"><strong>running</strong><div>${snapshot.running}</div></div>
        <div class="stat"><strong>mode</strong><div>${snapshot.mode}</div></div>
        <div class="stat"><strong>active</strong><div>${snapshot.active_count}</div></div>
        <div class="stat"><strong>spawned</strong><div>${snapshot.total_spawned}</div></div>
        <div class="stat"><strong>spawn interval</strong><div>${snapshot.spawn_interval_seconds}</div></div>
        <div class="stat"><strong>step interval</strong><div>${snapshot.step_interval_seconds}</div></div>
        <div class="stat"><strong>last spawn</strong><div>${snapshot.last_spawn_at || "-"}</div></div>
        <div class="stat"><strong>last tick</strong><div>${snapshot.last_tick_at || "-"}</div></div>
      `;

      if (!snapshot.patients || snapshot.patients.length === 0) {
        cardsEl.innerHTML = "<div class='muted'>No patients yet.</div>";
        return;
      }

      cardsEl.innerHTML = snapshot.patients.map((p) => {
        const dialogueHtml = p.current_dialogue
          ? `
            <div class="dialogue">
              <div><strong>${p.current_counterparty}</strong> | ${p.current_dialogue.direction}</div>
              <div class="row">${p.current_dialogue.speaker}</div>
              <div class="row">${p.current_dialogue.message || "-"}</div>
            </div>
          `
          : `<div class="row muted">No dialogue in this step (for example queueing or testing phase).</div>`;

        const caseSummary = p.case_summary ? `<pre>${JSON.stringify(p.case_summary, null, 2)}</pre>` : "";
        return `
          <article class="card">
            <div><strong>${p.npc_id}</strong> <span class="badge">${p.mode}</span></div>
            <div class="row">patient: ${p.patient_id}</div>
            <div class="row">encounter: ${p.encounter_id || "-"}</div>
            <div class="row">visit: ${p.visit_state || "-"}</div>
            <div class="row">lifecycle: ${p.patient_lifecycle_state || "-"}</div>
            <div class="row">phase/status: ${p.phase} / ${p.status}</div>
            <div class="row">last action: ${p.last_action || "-"}</div>
            <div class="row">step: ${p.step_count} | finished: ${p.finished}</div>
            ${dialogueHtml}
            ${caseSummary}
          </article>
        `;
      }).join("");
    }

    async function refresh(showStatus = false) {
      try {
        const snapshot = await api("/api/v1/multi-patient-debug/snapshot");
        render(snapshot);
        if (showStatus) statusEl.textContent = "Snapshot refreshed.";
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    document.getElementById("startBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/v1/multi-patient-debug/start", "POST", {
          mode: document.getElementById("mode").value,
          spawn_interval_seconds: Number(document.getElementById("spawnInterval").value),
          step_interval_seconds: Number(document.getElementById("stepInterval").value),
          max_active_patients: Number(document.getElementById("maxPatients").value),
        });
        statusEl.textContent = "Started.";
        render(data);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("stopBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/v1/multi-patient-debug/stop", "POST", {});
        statusEl.textContent = "Stopped.";
        render(data);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("resetBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/v1/multi-patient-debug/reset", "POST", {});
        statusEl.textContent = "Reset.";
        render(data);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("refreshBtn").addEventListener("click", () => refresh(true));
    setInterval(() => refresh(false), 1000);
    refresh(false);
  </script>
</body>
</html>
        """
    )


@router.post("/api/v1/multi-patient-debug/start")
def start_multi_patient_debug(body: MultiPatientDebugStartRequest, request: Request):
    try:
        snapshot = _controller(request).start(
            mode=body.mode,
            spawn_interval_seconds=body.spawn_interval_seconds,
            step_interval_seconds=body.step_interval_seconds,
            max_active_patients=body.max_active_patients,
        )
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 503 if "llm" in detail.lower() else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/multi-patient-debug/stop")
def stop_multi_patient_debug(request: Request):
    snapshot = _controller(request).stop()
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/multi-patient-debug/reset")
def reset_multi_patient_debug(request: Request):
    snapshot = _controller(request).reset()
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/multi-patient-debug/snapshot")
def get_multi_patient_debug_snapshot(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump()}
