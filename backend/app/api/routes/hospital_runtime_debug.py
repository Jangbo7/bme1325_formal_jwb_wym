from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.schemas.multi_patient_debug import MultiPatientDebugStartRequest, MultiPatientDebugUpdateRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["multi_patient_debug_controller"]


def _runtime_service(request: Request):
    return request.app.state.container["department_runtime_service"]


def _snapshot(request: Request):
    return _runtime_service(request).build_hospital_runtime_snapshot(_controller(request).get_snapshot())


@router.get("/hospital-runtime-debug", response_class=HTMLResponse, include_in_schema=False)
def hospital_runtime_debug_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Hospital Runtime Debug</title>
  <style>
    body { margin: 0; font-family: "Segoe UI", sans-serif; background: #eef3ea; color: #102118; }
    main { max-width: 1400px; margin: 0 auto; padding: 16px; }
    .panel { background: #fff; border: 1px solid #cbd7c6; border-radius: 10px; padding: 12px; margin-top: 10px; }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: end; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }
    .card { border: 1px solid #d4dfcf; border-radius: 10px; padding: 10px; background: #fff; }
    .small { font-size: 13px; color: #3c5742; }
    button { padding: 6px 10px; border-radius: 8px; border: 1px solid #8fac95; background: #2d6842; color: #fff; }
    input, select { padding: 6px 8px; border-radius: 8px; border: 1px solid #98af9a; }
    .muted { color: #4d6655; font-size: 13px; }
  </style>
</head>
<body>
  <main>
    <h1>Hospital Runtime Debug</h1>
    <div class="muted">Engine-driven multi patient simulation with node + department runtime projection.</div>
    <div class="panel toolbar">
      <div><div class="small">Mode</div><select id="mode"><option value="intelligent_agent">intelligent_agent</option><option value="department_mixed">department_mixed</option><option value="legacy_template">legacy_template</option></select></div>
      <div><div class="small">Spawn(s)</div><input id="spawn" type="number" min="0" step="0.5" value="4"></div>
      <div><div class="small">Step(s)</div><input id="step" type="number" min="0.1" step="0.5" value="2"></div>
      <div><div class="small">Max</div><input id="max" type="number" min="1" step="1" value="20"></div>
      <button id="start">Start</button><button id="stop">Stop</button><button id="reset">Reset</button><button id="refresh">Refresh</button>
    </div>
    <div class="panel"><div id="stats"></div></div>
    <div class="panel"><h3>Node Runtime</h3><div class="grid" id="nodes"></div></div>
    <div class="panel"><h3>Department Runtime</h3><div class="grid" id="departments"></div></div>
  </main>
  <script>
    function idem(){return (crypto?.randomUUID?.() || ("idem-"+Date.now()+"-"+Math.random().toString(16).slice(2)));}
    async function api(path, method="GET", body=null){
      const headers={};
      if(method!=="GET"){headers["Content-Type"]="application/json"; headers["Idempotency-Key"]=idem();}
      const r=await fetch(path,{method,headers,body:body?JSON.stringify(body):null});
      const p=await r.json(); if(!r.ok||p.ok===false){throw new Error(p.error?.message||p.error?.details||r.statusText);} return p.data;
    }
    function render(s){
      document.getElementById("stats").textContent = `running=${s.running} mode=${s.mode} active=${s.active_count} spawned=${s.total_spawned} dispatch=${s.dispatch_count} blocked=${s.blocked_count} fairness=${s.fairness_policy} last_tick=${s.last_tick_at||"-"}`;
      document.getElementById("nodes").innerHTML = (s.nodes||[]).map(n=>`
        <div class="card">
          <div><strong>${n.node.name}</strong> <span class="small">(${n.node.node_id})</span></div>
          <div class="small">active=${n.summary.active_count} waiting=${n.summary.waiting_count} called=${n.summary.called_count} consult=${n.summary.in_consultation_count} test=${n.summary.in_test_count} finished=${n.summary.finished_count}</div>
          <div class="small">patients=${n.patients.length}</div>
        </div>`).join("");
      document.getElementById("departments").innerHTML = (s.departments||[]).map(d=>`
        <div class="card">
          <div><strong>${d.department_name}</strong></div>
          <div class="small">active=${d.summary.active_count} wait1=${d.summary.waiting_round1_count} wait2=${d.summary.waiting_round2_count} consult1=${d.summary.in_consultation_round1_count} consult2=${d.summary.in_consultation_round2_count} test=${d.summary.in_test_count} finished=${d.summary.finished_count}</div>
          <div class="small">patients=${d.patients.length}</div>
        </div>`).join("");
    }
    async function refresh(){ render(await api("/api/v1/hospital-runtime-debug/snapshot")); }
    document.getElementById("start").onclick = async ()=>{render(await api("/api/v1/hospital-runtime-debug/start","POST",{mode:document.getElementById("mode").value,spawn_interval_seconds:Number(document.getElementById("spawn").value),step_interval_seconds:Number(document.getElementById("step").value),max_active_patients:Number(document.getElementById("max").value)}));};
    document.getElementById("stop").onclick = async ()=>{render(await api("/api/v1/hospital-runtime-debug/stop","POST",{}));};
    document.getElementById("reset").onclick = async ()=>{render(await api("/api/v1/hospital-runtime-debug/reset","POST",{}));};
    document.getElementById("refresh").onclick = async ()=>refresh();
    setInterval(refresh, 1200); refresh();
  </script>
</body>
</html>
        """
    )


@router.post("/api/v1/hospital-runtime-debug/start")
def start_hospital_runtime_debug(body: MultiPatientDebugStartRequest, request: Request):
    if body.max_active_patients is not None and body.max_active_patients < 1:
        raise HTTPException(status_code=422, detail="max_active_patients must be >= 1")
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
    data = _runtime_service(request).build_hospital_runtime_snapshot(snapshot)
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/hospital-runtime-debug/stop")
def stop_hospital_runtime_debug(request: Request):
    snapshot = _controller(request).stop()
    data = _runtime_service(request).build_hospital_runtime_snapshot(snapshot)
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/hospital-runtime-debug/update-config")
def update_hospital_runtime_debug_config(body: MultiPatientDebugUpdateRequest, request: Request):
    if body.max_active_patients is not None and body.max_active_patients < 1:
        raise HTTPException(status_code=422, detail="max_active_patients must be >= 1")
    snapshot = _controller(request).update_config(
        mode=body.mode,
        spawn_interval_seconds=body.spawn_interval_seconds,
        step_interval_seconds=body.step_interval_seconds,
        max_active_patients=body.max_active_patients,
    )
    data = _runtime_service(request).build_hospital_runtime_snapshot(snapshot)
    return {"ok": True, "data": data.model_dump()}


@router.post("/api/v1/hospital-runtime-debug/reset")
def reset_hospital_runtime_debug(request: Request):
    snapshot = _controller(request).reset()
    data = _runtime_service(request).build_hospital_runtime_snapshot(snapshot)
    return {"ok": True, "data": data.model_dump()}


@router.get("/api/v1/hospital-runtime-debug/snapshot")
def get_hospital_runtime_debug_snapshot(request: Request):
    data = _snapshot(request)
    return {"ok": True, "data": data.model_dump()}


@router.get("/api/v1/hospital-runtime/snapshot")
def get_hospital_runtime_snapshot(request: Request):
    data = _snapshot(request)
    return {"ok": True, "data": data.model_dump()}
