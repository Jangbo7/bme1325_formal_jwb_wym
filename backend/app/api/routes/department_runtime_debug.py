from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.schemas.multi_patient_debug import MultiPatientDebugStartRequest


router = APIRouter()


def _multi_controller(request: Request):
    return request.app.state.container["multi_patient_debug_controller"]


def _runtime_service(request: Request):
    return request.app.state.container["department_runtime_service"]


def _snapshot(request: Request):
    return _runtime_service(request).build_debug_snapshot(_multi_controller(request).get_snapshot())


@router.get("/department-runtime-debug", response_class=HTMLResponse, include_in_schema=False)
def department_runtime_debug_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Department Runtime Debug</title>
  <style>
    :root {
      --bg: #f4f7ee;
      --panel: #ffffff;
      --ink: #122017;
      --line: #cad7c8;
      --accent: #2f6d44;
      --muted: #5d6f63;
    }
    body {
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top, #fafff7 0%, var(--bg) 50%, #e3ebdf 100%);
    }
    main { max-width: 1400px; margin: 0 auto; padding: 20px 16px 48px; }
    h1 { margin: 0 0 8px; }
    .muted { color: var(--muted); font-size: 13px; }
    .toolbar, .panel, .department, .patient {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 8px 20px rgba(15, 35, 16, 0.08);
    }
    .toolbar, .panel { padding: 14px; margin-top: 12px; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
    label { font-size: 12px; text-transform: uppercase; color: var(--muted); }
    input, select, button {
      font: inherit;
      border: 1px solid #90a993;
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
    }
    button {
      background: linear-gradient(180deg, #43835a 0%, var(--accent) 100%);
      color: #fff;
      cursor: pointer;
    }
    button.secondary { background: #edf5ee; color: var(--ink); }
    #status { margin-top: 10px; min-height: 18px; color: #2b5a3d; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
    .stat { border: 1px dashed var(--line); border-radius: 10px; padding: 8px; }
    .departments { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 14px; margin-top: 14px; }
    .department { padding: 12px; }
    .summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
    .summary div { border: 1px dashed var(--line); border-radius: 10px; padding: 8px; font-size: 13px; }
    .patients { display: grid; gap: 10px; margin-top: 12px; }
    .patient { padding: 10px; }
    .row { margin-top: 4px; font-size: 13px; }
    .dialogue { margin-top: 8px; padding: 8px; border: 1px dashed var(--line); border-radius: 10px; background: #f8fbf6; }
    .badge { display: inline-block; border: 1px solid #9db39e; border-radius: 999px; padding: 2px 8px; font-size: 12px; margin-left: 8px; }
    details summary { cursor: pointer; color: #2f6d44; font-size: 13px; }
  </style>
</head>
<body>
  <main>
    <h1>Department Runtime Debug</h1>
    <div class="muted">Department-centric runtime view built on top of the existing multi patient auto-runner. No scene integration in this page.</div>
    <div class="toolbar">
      <div>
        <label>Mode</label><br />
        <select id="mode">
          <option value="intelligent_agent">intelligent_agent</option>
          <option value="department_mixed">department_mixed</option>
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
        <label>Max Active Patients</label><br />
        <input id="maxPatients" type="number" min="1" step="1" value="20" />
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
    <section class="departments" id="departments"></section>
    <section class="panel" id="unassignedPanel" style="display:none;">
      <h3>Unassigned Patients</h3>
      <div class="patients" id="unassignedPatients"></div>
    </section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const statsEl = document.getElementById("stats");
    const departmentsEl = document.getElementById("departments");
    const unassignedPanelEl = document.getElementById("unassignedPanel");
    const unassignedPatientsEl = document.getElementById("unassignedPatients");

    function nextIdempotencyKey() {
      if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
      return "department-runtime-debug-" + Date.now() + "-" + Math.random().toString(16).slice(2);
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

    function renderPatient(patient) {
      const dialogue = patient.current_dialogue
        ? `
          <div class="dialogue">
            <div><strong>${patient.current_counterparty || "-"}</strong></div>
            <div class="row">${patient.current_dialogue.speaker || "-"}</div>
            <div class="row">${patient.current_dialogue.message || "-"}</div>
          </div>
        `
        : `<div class="row muted">No dialogue in this step.</div>`;
      return `
        <article class="patient">
          <div><strong>${patient.npc_id || patient.patient_id}</strong><span class="badge">${patient.department_status || patient.department_flow_status}</span></div>
          <div class="row">patient: ${patient.patient_id}</div>
          <div class="row">visit_state: ${patient.visit_state || "-"}</div>
          <div class="row">lifecycle: ${patient.patient_lifecycle_state || "-"}</div>
          <div class="row">queue_kind: ${patient.queue_kind || "-"}</div>
          <div class="row">node: ${patient.current_node_id || "-"}</div>
          <div class="row">last_action: ${patient.last_action || "-"} | finished: ${patient.finished}</div>
          <details>
            <summary>Details</summary>
            <div class="row">visit: ${patient.visit_id}</div>
            <div class="row">target_node: ${patient.target_node_id || "-"}</div>
            <div class="row">counterparty: ${patient.current_counterparty || "-"}</div>
            ${dialogue}
          </details>
        </article>
      `;
    }

    function render(snapshot) {
      const departmentsWithPatients = (snapshot.departments || []).filter((item) => (item.patients || []).length > 0).length;
      const finishedPatients = (snapshot.departments || []).flatMap((item) => item.patients || []).filter((item) => item.finished).length;
      statsEl.innerHTML = `
        <div class="stat"><strong>running</strong><div>${snapshot.running}</div></div>
        <div class="stat"><strong>mode</strong><div>${snapshot.mode}</div></div>
        <div class="stat"><strong>active_count</strong><div>${snapshot.active_count}</div></div>
        <div class="stat"><strong>spawned</strong><div>${snapshot.total_spawned}</div></div>
        <div class="stat"><strong>dept with patients</strong><div>${departmentsWithPatients}</div></div>
        <div class="stat"><strong>finished patients</strong><div>${finishedPatients}</div></div>
        <div class="stat"><strong>dispatch</strong><div>${snapshot.dispatch_count}</div></div>
        <div class="stat"><strong>blocked</strong><div>${snapshot.blocked_count}</div></div>
        <div class="stat"><strong>last_spawn</strong><div>${snapshot.last_spawn_at || "-"}</div></div>
        <div class="stat"><strong>last_tick</strong><div>${snapshot.last_tick_at || "-"}</div></div>
      `;

      departmentsEl.innerHTML = snapshot.departments.map((department) => `
        <section class="department">
          <details>
          <summary><strong>${department.department_name}</strong> (${department.patients.length})</summary>
          <div class="summary">
            <div>active: ${department.summary.active_count}</div>
            <div>pending reg: ${department.summary.pending_registration_count}</div>
            <div>waiting r1/r2: ${department.summary.waiting_round1_count}/${department.summary.waiting_round2_count}</div>
            <div>called r1/r2: ${department.summary.called_round1_count}/${department.summary.called_round2_count}</div>
            <div>consult r1/r2: ${department.summary.in_consultation_round1_count}/${department.summary.in_consultation_round2_count}</div>
            <div>in test: ${department.summary.in_test_count}</div>
            <div>finished: ${department.summary.finished_count}</div>
            <div>updated: ${department.summary.updated_at}</div>
            <div>patients: ${department.patients.length}</div>
          </div>
          <div class="patients">
            ${department.patients.length ? department.patients.map(renderPatient).join("") : "<div class='muted'>No patients.</div>"}
          </div>
          </details>
        </section>
      `).join("");

      if (snapshot.unassigned_patients && snapshot.unassigned_patients.length) {
        unassignedPanelEl.style.display = "block";
        unassignedPatientsEl.innerHTML = snapshot.unassigned_patients.map(renderPatient).join("");
      } else {
        unassignedPanelEl.style.display = "none";
        unassignedPatientsEl.innerHTML = "";
      }
    }

    async function refresh(showStatus = false) {
      try {
        const snapshot = await api("/api/v1/department-runtime-debug/snapshot");
        render(snapshot);
        if (showStatus) statusEl.textContent = "Snapshot refreshed.";
      } catch (error) {
        statusEl.textContent = error.message;
      }
    }

    document.getElementById("startBtn").addEventListener("click", async () => {
      try {
        const maxRaw = document.getElementById("maxPatients").value.trim();
        const snapshot = await api("/api/v1/department-runtime-debug/start", "POST", {
          mode: document.getElementById("mode").value,
          spawn_interval_seconds: Number(document.getElementById("spawnInterval").value),
          step_interval_seconds: Number(document.getElementById("stepInterval").value),
          max_active_patients: maxRaw ? Number(maxRaw) : null,
        });
        statusEl.textContent = "Started.";
        render(snapshot);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("stopBtn").addEventListener("click", async () => {
      try {
        const snapshot = await api("/api/v1/department-runtime-debug/stop", "POST", {});
        statusEl.textContent = "Stopped.";
        render(snapshot);
      } catch (error) {
        statusEl.textContent = error.message;
      }
    });

    document.getElementById("resetBtn").addEventListener("click", async () => {
      try {
        const snapshot = await api("/api/v1/department-runtime-debug/reset", "POST", {});
        statusEl.textContent = "Reset.";
        render(snapshot);
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


@router.post("/api/v1/department-runtime-debug/start")
def start_department_runtime_debug(body: MultiPatientDebugStartRequest, request: Request):
    if body.max_active_patients is not None and body.max_active_patients < 1:
        raise HTTPException(status_code=422, detail="max_active_patients must be >= 1")
    try:
        _multi_controller(request).start(
            mode=body.mode,
            spawn_interval_seconds=body.spawn_interval_seconds,
            step_interval_seconds=body.step_interval_seconds,
            max_active_patients=body.max_active_patients,
        )
    except RuntimeError as exc:
        detail = str(exc)
        status_code = 503 if "llm" in detail.lower() else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return {"ok": True, "data": _snapshot(request).model_dump()}


@router.post("/api/v1/department-runtime-debug/stop")
def stop_department_runtime_debug(request: Request):
    _multi_controller(request).stop()
    return {"ok": True, "data": _snapshot(request).model_dump()}


@router.post("/api/v1/department-runtime-debug/reset")
def reset_department_runtime_debug(request: Request):
    _multi_controller(request).reset()
    return {"ok": True, "data": _snapshot(request).model_dump()}


@router.get("/api/v1/department-runtime-debug/snapshot")
def get_department_runtime_debug_snapshot(request: Request):
    return {"ok": True, "data": _snapshot(request).model_dump()}
