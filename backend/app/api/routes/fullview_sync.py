from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


router = APIRouter()


class FullviewGateUpdate(BaseModel):
    enabled: bool


@router.get("/fullview-sync-monitor", response_class=HTMLResponse, include_in_schema=False)
def fullview_sync_monitor_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Fullview Sync Monitor</title>
  <style>
    :root { --bg:#eef2ec; --panel:#fff; --line:#cad5c9; --ink:#132117; --muted:#48604e; --accent:#2e6b46; --warn:#a96d00; --error:#8a1f1f; }
    body { margin:0; font-family:"Segoe UI",sans-serif; color:var(--ink); background:linear-gradient(180deg,#f8fbf6,var(--bg)); }
    main { max-width:1500px; margin:auto; padding:18px; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:14px; margin-top:12px; }
    .row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
    .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; margin-top:12px; }
    .stat { border:1px dashed var(--line); border-radius:10px; padding:10px; }
    button, select { font:inherit; border:1px solid #90a792; border-radius:8px; padding:7px 10px; }
    button { background:var(--accent); color:#fff; cursor:pointer; }
    button.secondary { background:#edf4ee; color:var(--ink); }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { padding:8px; border-bottom:1px solid #e2ebe1; text-align:left; vertical-align:top; }
    .table-wrap { overflow:auto; }
    .muted { color:var(--muted); font-size:13px; }
    .bad { color:var(--error); }
    .warn { color:var(--warn); }
    a { color:var(--accent); }
  </style>
</head>
<body>
<main>
  <div class="row">
    <h1 style="margin:0;">Fullview Sync Monitor</h1>
    <a href="/runtime-console">Back to Runtime Console</a>
  </div>
  <div class="muted">Backend-owned monitoring and control. This page does not modify the Fullview frontend.</div>
  <section class="panel">
    <div class="row">
      <label><input id="gate" type="checkbox" /> Wait for Fullview acceptance and visual cooldown</label>
      <button id="apply">Apply</button>
      <button id="refresh" class="secondary">Refresh</button>
      <span id="worker" class="muted"></span>
    </div>
    <div id="stats" class="stats"></div>
    <div id="error" class="bad" style="margin-top:10px;"></div>
  </section>
  <section class="panel">
    <div class="row">
      <strong>Recent commands</strong>
      <select id="statusFilter">
        <option value="">all</option><option>pending</option><option>sending</option>
        <option>retryable</option><option>blocked</option><option>dead_letter</option>
        <option>accepted_unobserved</option><option>observed</option>
        <option>observe_timeout</option><option>cleanup_pending</option>
        <option>cleanup_complete</option><option>skipped</option>
      </select>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>patient / encounter</th><th>sequence</th><th>event</th><th>status</th><th>reason</th><th>updated</th><th>action</th></tr></thead>
      <tbody id="commands"></tbody>
    </table></div>
  </section>
</main>
<script>
  let latest = [];
  async function json(path, options={}){
    const method = String(options.method || "GET").toUpperCase();
    options.headers = {...(options.headers || {})};
    if(method !== "GET" && !options.headers["Idempotency-Key"]){
      options.headers["Idempotency-Key"] = (crypto?.randomUUID?.() || `fullview-sync-${Date.now()}-${Math.random()}`);
    }
    const response = await fetch(path, options);
    const body = await response.json();
    if(!response.ok || body.ok === false){ throw new Error(body.detail || body.error || response.statusText); }
    return body.data || body;
  }
  function renderCommands(){
    const filter = document.getElementById("statusFilter").value;
    const commands = filter ? latest.filter(item => item.status === filter) : latest;
    document.getElementById("commands").innerHTML = commands.map(item => `
      <tr>
        <td>${item.patient_id}<div class="muted">${item.encounter_id}</div></td>
        <td>${item.sequence_no}</td><td>${item.event_id || item.request_type}</td>
        <td class="${["blocked","dead_letter","observe_timeout"].includes(item.status) ? "bad" : (["retryable","accepted_unobserved"].includes(item.status) ? "warn" : "")}">${item.status}</td>
        <td>${item.reason_code || "-"}<div class="muted">${item.last_error || ""}</div></td>
        <td>${item.updated_at || "-"}</td>
        <td>${["blocked","dead_letter","retryable","observe_timeout"].includes(item.status) ? `<button class="secondary" onclick="retryCommand('${item.command_id}')">Retry</button>` : "-"}</td>
      </tr>`).join("");
  }
  async function refresh(){
    try {
      const body = await json("/api/v1/fullview-sync/control");
      document.getElementById("gate").checked = Boolean(body.control.gate.enabled);
      document.getElementById("worker").textContent = `worker=${body.control.worker.running ? "running" : "stopped"} sync=${body.control.worker.enabled ? "enabled" : "disabled"}`;
      document.getElementById("error").textContent = body.control.worker.last_loop_error || "";
      document.getElementById("stats").innerHTML = Object.entries(body.control.counts || {}).map(([key,value]) => `<div class="stat"><strong>${key}</strong><div>${value}</div></div>`).join("") || `<div class="stat muted">No commands</div>`;
      latest = body.commands || [];
      renderCommands();
    } catch(error) { document.getElementById("error").textContent = error.message; }
  }
  async function retryCommand(commandId){
    await json(`/api/v1/fullview-sync/outbox/${commandId}/retry`, {method:"POST"});
    await refresh();
  }
  document.getElementById("apply").onclick = async () => {
    try {
      await json("/api/v1/fullview-sync/control", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({enabled:document.getElementById("gate").checked})
      });
      await refresh();
    } catch(error) { document.getElementById("error").textContent = error.message; }
  };
  document.getElementById("refresh").onclick = refresh;
  document.getElementById("statusFilter").onchange = renderCommands;
  setInterval(refresh, 2000); refresh();
</script>
</body>
</html>
        """
    )


@router.get("/api/v1/fullview-sync/control")
def get_fullview_control(request: Request, limit: int = Query(200, ge=1, le=500)):
    container = request.app.state.container
    repo = container["fullview_sync_repo"]
    return {
        "ok": True,
        "control": {
            "gate": container["hospital_supervisor"].get_fullview_step_gate_status(),
            "worker": container["fullview_sync_worker"].status(),
            "listener": container["fullview_event_listener"].status(),
            "counts": repo.get_status_counts(),
        },
        "commands": repo.list_recent(limit),
    }


@router.post("/api/v1/fullview-sync/control")
def update_fullview_control(body: FullviewGateUpdate, request: Request):
    container = request.app.state.container
    controller = container["hospital_supervisor"]
    service = container["runtime_console_service"]
    config = controller.set_fullview_step_gate_enabled(body.enabled)
    service.fullview_step_gate_enabled = bool(
        service.fullview_sync_enabled and body.enabled
    )
    session = controller.get_runtime_session()
    if session.session_id:
        service.update_global_config(session.session_id, config)
    return {
        "ok": True,
        "control": {
            "gate": controller.get_fullview_step_gate_status(),
            "worker": container["fullview_sync_worker"].status(),
            "listener": container["fullview_event_listener"].status(),
            "counts": container["fullview_sync_repo"].get_status_counts(),
        },
    }


@router.get("/api/v1/fullview-sync/outbox")
def list_fullview_outbox(request: Request, limit: int = Query(100, ge=1, le=500)):
    repo = request.app.state.container["fullview_sync_repo"]
    return {"ok": True, "commands": repo.list_recent(limit)}


@router.get("/api/v1/fullview-sync/projection/{patient_id}/{encounter_id}")
def get_fullview_projection(patient_id: str, encounter_id: str, request: Request):
    repo = request.app.state.container["fullview_sync_repo"]
    projection = repo.get_projection(patient_id, encounter_id)
    if projection is None:
        raise HTTPException(status_code=404, detail="Fullview projection not found")
    return {"ok": True, "projection": projection}


@router.get("/api/v1/fullview-sync/encounters/{encounter_id}")
def get_encounter_fullview_sync(encounter_id: str, request: Request):
    repo = request.app.state.container["fullview_sync_repo"]
    return {"ok": True, "sync": repo.get_encounter_sync_status(encounter_id)}


@router.post("/api/v1/fullview-sync/encounters/{encounter_id}/retry")
def retry_fullview_encounter(encounter_id: str, request: Request):
    repo = request.app.state.container["fullview_sync_repo"]
    retried = repo.retry_encounter(encounter_id)
    request.app.state.container["fullview_sync_worker"].wake()
    return {"ok": True, "encounter_id": encounter_id, "retried": retried}


@router.post("/api/v1/fullview-sync/outbox/{command_id}/retry")
def retry_fullview_command(command_id: str, request: Request):
    repo = request.app.state.container["fullview_sync_repo"]
    command = repo.retry(command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Fullview command not found or not retryable")
    request.app.state.container["fullview_sync_worker"].wake()
    return {"ok": True, "command": command}
