from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.schemas.runtime_console import (
    RuntimeConsoleCommandRequest,
    RuntimeConsoleDepartmentConfigUpdateRequest,
    RuntimeConsoleGlobalConfigUpdateRequest,
    RuntimeConsoleStartRequest,
)


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["hospital_supervisor"]


def _service(request: Request):
    return request.app.state.container["runtime_console_service"]


@router.get("/runtime-console", response_class=HTMLResponse, include_in_schema=False)
def runtime_console_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Runtime Console</title>
  <style>
    :root { --bg:#eef2ec; --panel:#fff; --line:#cad5c9; --ink:#132117; --muted:#48604e; --accent:#2e6b46; --warn:#a96d00; --error:#8a1f1f; --rare-patient-bg:#fff0e2; --rare-patient-line:#d68a36; --rare-report-bg:#e7f4ff; --rare-report-line:#3e8acb; --rare-both-bg:#fff3c7; --rare-both-line:#ae7d00; --rare-unknown-bg:#f4ebff; --rare-unknown-line:#7f5ab6; }
    body { margin:0; font-family:"Segoe UI",sans-serif; color:var(--ink); background:linear-gradient(180deg,#f8fbf6 0%, var(--bg) 100%); }
    main { max-width:1500px; margin:0 auto; padding:18px; }
    h1 { margin:0 0 8px; }
    .toolbar, .panel { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:14px; box-shadow:0 10px 24px rgba(12,25,16,.07); }
    .toolbar { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; }
    .button-row { display:flex; flex-wrap:wrap; gap:8px; align-items:end; }
    .stack { margin-top:12px; display:grid; gap:12px; }
    input, button { font:inherit; border:1px solid #90a792; border-radius:9px; padding:8px 10px; }
    button { background:var(--accent); color:#fff; cursor:pointer; }
    button.secondary { background:#edf4ee; color:var(--ink); }
    .muted { color:var(--muted); font-size:13px; }
    .stats, .cards, .dept-grid { display:grid; gap:10px; }
    .stats { grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); }
    .cards { grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }
    .dept-grid { grid-template-columns:repeat(auto-fit,minmax(360px,1fr)); }
    .stat, .card { border:1px dashed var(--line); border-radius:12px; padding:10px; background:#fafcf9; }
    .table-wrap { overflow:auto; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { padding:8px; border-bottom:1px solid #e2ebe1; text-align:left; vertical-align:top; }
    details.panel summary { cursor:pointer; font-weight:600; }
    .pill { display:inline-block; border-radius:999px; padding:2px 8px; font-size:12px; border:1px solid var(--line); }
    .pill.warning { color:var(--warn); border-color:#e1c27d; background:#fff8e8; }
    .pill.error { color:var(--error); border-color:#d8a2a2; background:#fff0f0; }
    .pill.rare { color:#fff; border-color:transparent; }
    .pill.rare-patient { background:var(--rare-patient-line); }
    .pill.rare-report { background:var(--rare-report-line); }
    .pill.rare-both { background:var(--rare-both-line); }
    .pill.rare-unknown { background:var(--rare-unknown-line); }
    .legend { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }
    .patient-row--rare-event td { border-bottom-width:1px; }
    .patient-row--rare-event-patient td { background:linear-gradient(180deg,var(--rare-patient-bg) 0%, #fff9f2 100%); }
    .patient-row--rare-event-report td { background:linear-gradient(180deg,var(--rare-report-bg) 0%, #f8fcff 100%); }
    .patient-row--rare-event-both td { background:linear-gradient(180deg,var(--rare-both-bg) 0%, #fffbee 100%); }
    .patient-row--rare-event-unknown td { background:linear-gradient(180deg,var(--rare-unknown-bg) 0%, #fcf9ff 100%); }
    .patient-row--rare-event-patient td:first-child { box-shadow: inset 4px 0 0 var(--rare-patient-line); }
    .patient-row--rare-event-report td:first-child { box-shadow: inset 4px 0 0 var(--rare-report-line); }
    .patient-row--rare-event-both td:first-child { box-shadow: inset 4px 0 0 var(--rare-both-line); }
    .patient-row--rare-event-unknown td:first-child { box-shadow: inset 4px 0 0 var(--rare-unknown-line); }
    .issue { border-left:4px solid var(--line); padding-left:10px; margin-top:8px; }
    .issue.warning { border-left-color:#d39b2c; }
    .issue.error { border-left-color:#b33a3a; }
  </style>
</head>
<body>
  <main>
    <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
      <h1>Runtime Console</h1>
      <a href="/fullview-sync-monitor" target="_blank" rel="noopener">Open Fullview Sync Monitor</a>
    </div>
    <div class="muted">Formal runtime control for mixed scripted and intelligent patients. Panels are collapsible and remember browser-native open state.</div>
    <div class="stack">
      <details class="panel" open>
        <summary>Global Control</summary>
        <div class="toolbar" style="margin-top:12px;">
          <div><div class="muted">Max Active</div><input id="maxActive" type="number" min="1" value="20" /></div>
          <div><div class="muted">Agent Ratio</div><input id="agentRatio" type="number" min="0" max="1" step="0.1" value="0.5" /></div>
          <div><div class="muted">Agent Spawn(s)</div><input id="agentSpawn" type="number" min="0" step="0.5" value="4" /></div>
          <div><div class="muted">Agent Step(s)</div><input id="agentStep" type="number" min="0.1" step="0.5" value="2" /></div>
          <div><div class="muted">Script Spawn(s)</div><input id="scriptSpawn" type="number" min="0" step="0.5" value="4" /></div>
          <div><div class="muted">Script Step(s)</div><input id="scriptStep" type="number" min="0.1" step="0.5" value="2" /></div>
          <div>
            <div class="muted">Fullview Step Gate</div>
            <label><input id="fullviewStepGate" type="checkbox" /> Wait for accepted</label>
          </div>
        </div>
        <div class="button-row" style="margin-top:12px;">
          <button id="startBtn">Start</button>
          <button id="pauseSpawnBtn" class="secondary">Pause Spawn</button>
          <button id="pauseStepBtn" class="secondary">Pause Step</button>
          <button id="resumeBtn" class="secondary">Resume</button>
          <button id="drainBtn" class="secondary">Drain</button>
          <button id="stopBtn" class="secondary">Stop</button>
          <button id="resetBtn" class="secondary">Reset</button>
          <button id="applyConfigBtn" class="secondary">Apply Config</button>
          <button id="refreshBtn" class="secondary">Refresh</button>
        </div>
        <div id="session" class="muted" style="margin-top:10px;"></div>
      </details>
      <details class="panel" open>
        <summary>Issues</summary>
        <div class="stats" id="issueStats" style="margin-top:12px;"></div>
        <div class="cards" id="issues" style="margin-top:12px;"></div>
      </details>
      <details class="panel">
        <summary>Patients</summary>
        <div class="legend" id="patientLegend" style="margin-top:12px;">
          <span class="muted">Special event color:</span>
          <span class="pill rare rare-patient">patient</span>
          <span class="pill rare rare-report">report</span>
          <span class="pill rare rare-both">both</span>
          <span class="pill rare rare-unknown">unknown</span>
        </div>
        <div class="table-wrap" style="margin-top:12px;"><table><thead><tr><th>patient</th><th>source</th><th>department</th><th>stage</th><th>status</th><th>issue</th></tr></thead><tbody id="patients"></tbody></table></div>
      </details>
      <details class="panel">
        <summary>Departments</summary>
        <div class="dept-grid" id="departments" style="margin-top:12px;"></div>
      </details>
    </div>
  </main>
  <script>
    function idem(){ return (crypto?.randomUUID?.() || ("runtime-console-"+Date.now()+"-"+Math.random().toString(16).slice(2))); }
    async function api(path, method="GET", body=null){
      const headers={};
      if(method!=="GET"){ headers["Content-Type"]="application/json"; headers["Idempotency-Key"]=idem(); }
      const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
      const payload = await response.json();
      if(!response.ok || payload.ok===false){ throw new Error(payload.error?.message || payload.error?.details || response.statusText); }
      return payload.data;
    }
    function globalConfigFromInputs(){
      return {
        max_active_patients: Number(document.getElementById("maxActive").value),
        active_mix_mode: "strict_ratio",
        active_agent_ratio: Number(document.getElementById("agentRatio").value),
        fullview_step_gate_enabled: document.getElementById("fullviewStepGate").checked,
        agent_spawn_interval_seconds: Number(document.getElementById("agentSpawn").value),
        agent_step_interval_seconds: Number(document.getElementById("agentStep").value),
        script_spawn_interval_seconds: Number(document.getElementById("scriptSpawn").value),
        script_step_interval_seconds: Number(document.getElementById("scriptStep").value),
      };
    }
    let initializedControls = false;
    function rareEventState(patient){
      const profile = patient.rare_event_profile || {};
      const patientEnabled = Boolean(profile.patient_special_event_enabled);
      const reportEnabled = Boolean(profile.report_special_signal_enabled);
      const triggeredBy = String(patient.rare_event_triggered_by || profile.triggered_by || "").trim().toLowerCase();
      const eventType = String(patient.rare_event_type || profile.event_type || "").trim().toLowerCase();
      if(!eventType && triggeredBy !== "patient" && triggeredBy !== "report" && !patientEnabled && !reportEnabled){
        return "none";
      }
      if(patientEnabled && reportEnabled){ return "both"; }
      if(patientEnabled || triggeredBy === "patient"){ return "patient"; }
      if(reportEnabled || triggeredBy === "report"){ return "report"; }
      return "unknown";
    }
    function rareEventBadge(state){
      if(state === "none"){ return ""; }
      return `<span class="pill rare rare-${state}">rare:${state}</span>`;
    }
    function render(snapshot){
      const session = snapshot.session || {};
      if(!initializedControls){
        document.getElementById("fullviewStepGate").checked = Boolean(snapshot.global_config.fullview_step_gate_enabled);
        initializedControls = true;
      }
      document.getElementById("session").textContent =
        `session=${session.session_id || "-"} status=${session.status} active=${snapshot.active_count}/${snapshot.global_config.max_active_patients} agent=${snapshot.active_agent_count}/${snapshot.active_agent_target} script=${snapshot.active_script_count}/${snapshot.active_script_target} fullview_gate=${snapshot.global_config.fullview_step_gate_enabled ? "on" : "off"} last_tick=${snapshot.last_tick_at || "-"}`;
      document.getElementById("issueStats").innerHTML = [
        `<div class="stat"><strong>warning</strong><div>${snapshot.severity_counts.warning || 0}</div></div>`,
        `<div class="stat"><strong>error</strong><div>${snapshot.severity_counts.error || 0}</div></div>`,
        `<div class="stat"><strong>llm</strong><div>${snapshot.category_counts.llm || 0}</div></div>`,
        `<div class="stat"><strong>capacity</strong><div>${snapshot.category_counts.capacity || 0}</div></div>`,
        `<div class="stat"><strong>stuck</strong><div>${snapshot.category_counts.stuck || 0}</div></div>`,
      ].join("");
      document.getElementById("issues").innerHTML = (snapshot.current_issues || []).map((issue) => `
        <div class="card issue ${issue.severity}">
          <div><span class="pill ${issue.severity}">${issue.severity}</span> <strong>${issue.category}</strong></div>
          <div>${issue.latest_message}</div>
          <div class="muted">${issue.subject_type}:${issue.subject_id}</div>
        </div>
      `).join("") || `<div class="card muted">No active issues.</div>`;
      document.getElementById("patients").innerHTML = (snapshot.patients || []).map((patient) => {
        const rareState = rareEventState(patient);
        const rowClass = rareState === "none" ? "" : ` class="patient-row--rare-event patient-row--rare-event-${rareState}"`;
        return `
        <tr${rowClass}>
          <td>${patient.patient_id} ${rareEventBadge(rareState)}</td>
          <td>${patient.patient_source}/${patient.execution_runner_kind}</td>
          <td>${patient.assigned_department_name || "-"}</td>
          <td>${patient.display_stage || "-"}/${patient.dispatch_state || "-"}</td>
          <td>${patient.status || "-"}</td>
          <td>${patient.last_error || patient.latest_consultation_llm_error || (patient.blocking?.message) || "-"}</td>
        </tr>
      `;
      }).join("");
      document.getElementById("departments").innerHTML = (snapshot.departments || []).map((department) => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
            <strong>${department.department_name}</strong>
            <span class="pill">${department.recent_issue_count} issues</span>
          </div>
          <div class="muted" style="margin-top:6px;">active=${department.summary.active_count} wait=${department.summary.waiting_count} consult=${department.summary.in_consultation_count} test=${department.summary.in_test_count} finished=${department.summary.finished_count}</div>
          <div class="muted">config: enabled=${department.config.enabled} weight=${department.config.spawn_weight} agent=${department.config.allow_agent_patients} script=${department.config.allow_script_patients}</div>
          <div class="muted">blocked=${department.blocked_patients} doctorSlots=${department.doctor_slots.length} rooms=${department.rooms.length}</div>
        </div>
      `).join("");
    }
    let refreshInFlight = false;
    async function refresh(){
      if(refreshInFlight){ return; }
      refreshInFlight = true;
      try {
        render(await api("/api/v1/runtime-console/snapshot"));
      } catch (error) {
        document.getElementById("session").textContent = `refresh failed: ${error.message}`;
      } finally {
        refreshInFlight = false;
      }
    }
    async function runCommand(command){
      try {
        const result = await api("/api/v1/runtime-console/session/command", "POST", { command });
        document.getElementById("session").textContent = result.message || `${command} queued`;
      } catch (error) {
        document.getElementById("session").textContent = `${command} failed: ${error.message}`;
      }
    }
    document.getElementById("startBtn").onclick = async () => {
      try {
        render(await api("/api/v1/runtime-console/session/start", "POST", { global_config: globalConfigFromInputs() }));
      } catch (error) {
        document.getElementById("session").textContent = `start failed: ${error.message}`;
      }
    };
    document.getElementById("pauseSpawnBtn").onclick = () => runCommand("pause_spawn");
    document.getElementById("pauseStepBtn").onclick = () => runCommand("pause_step");
    document.getElementById("resumeBtn").onclick = () => runCommand("resume");
    document.getElementById("drainBtn").onclick = () => runCommand("drain");
    document.getElementById("stopBtn").onclick = () => runCommand("stop");
    document.getElementById("resetBtn").onclick = () => runCommand("reset");
    document.getElementById("applyConfigBtn").onclick = async () => {
      try {
        render(await api("/api/v1/runtime-console/config/global", "POST", { global_config: globalConfigFromInputs() }));
      } catch (error) {
        document.getElementById("session").textContent = `apply config failed: ${error.message}`;
      }
    };
    document.getElementById("refreshBtn").onclick = () => refresh();
    setInterval(refresh, 1500); refresh();
  </script>
</body>
</html>
        """
    )


@router.get("/api/v1/runtime-console/snapshot")
def runtime_console_snapshot(request: Request):
    data = _service(request).build_snapshot(supervisor=_controller(request))
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/runtime-console/session/start")
def start_runtime_console(body: RuntimeConsoleStartRequest, request: Request):
    controller = _controller(request)
    service = _service(request)
    session, department_configs = service.create_session(
        global_config=body.global_config,
        department_configs=body.department_configs,
    )
    try:
        controller.start_runtime_console(
            session_id=session.session_id or "",
            global_config=body.global_config,
            department_configs=department_configs,
        )
    except RuntimeError as exc:
        service.repo.update_session(session.session_id or "", status="stopped", running=0)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    data = service.build_snapshot(supervisor=controller)
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/runtime-console/session/command")
def runtime_console_command(body: RuntimeConsoleCommandRequest, request: Request):
    try:
        _controller(request).request_runtime_console_command(body.command)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "data": {
            "queued": True,
            "command": body.command,
            "message": f"{body.command} queued; it will apply after the current patient step.",
        },
    }


@router.post("/api/v1/runtime-console/config/global")
def update_runtime_console_global_config(body: RuntimeConsoleGlobalConfigUpdateRequest, request: Request):
    controller = _controller(request)
    session = controller.get_runtime_session()
    if not session.session_id:
        raise HTTPException(status_code=409, detail="runtime console session is not active")
    _service(request).update_global_config(session.session_id, body.global_config)
    controller.update_runtime_console_global_config(body.global_config)
    data = _service(request).build_snapshot(supervisor=controller)
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/runtime-console/config/departments")
def update_runtime_console_departments(body: RuntimeConsoleDepartmentConfigUpdateRequest, request: Request):
    controller = _controller(request)
    session = controller.get_runtime_session()
    if not session.session_id:
        raise HTTPException(status_code=409, detail="runtime console session is not active")
    persisted = _service(request).update_department_configs(session.session_id, body.department_configs)
    controller.update_runtime_console_department_configs(persisted)
    data = _service(request).build_snapshot(supervisor=controller)
    return {"ok": True, "data": data.model_dump()}


@router.get("/api/v1/runtime-console/events")
def list_runtime_console_events(
    request: Request,
    session_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    subject_type: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    controller = _controller(request)
    resolved_session_id = session_id or controller.get_runtime_session().session_id
    if not resolved_session_id:
        return {"ok": True, "data": []}
    events = _service(request).list_events(
        session_id=resolved_session_id,
        severity=severity,
        category=category,
        subject_type=subject_type,
        subject_id=subject_id,
        limit=limit,
    )
    return {"ok": True, "data": [event.model_dump() for event in events]}


@router.get("/api/v1/runtime-console/patients")
def runtime_console_patients(request: Request):
    data = _service(request).build_snapshot(supervisor=_controller(request))
    return {"ok": True, "data": [patient.model_dump() for patient in data.patients]}


@router.get("/api/v1/runtime-console/departments")
def runtime_console_departments(request: Request):
    data = _service(request).build_snapshot(supervisor=_controller(request))
    return {"ok": True, "data": [department.model_dump() for department in data.departments]}
