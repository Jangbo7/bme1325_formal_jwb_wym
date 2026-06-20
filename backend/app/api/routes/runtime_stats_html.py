from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse


router = APIRouter()

PHASE_ORDER = ["triage", "queue", "consult1", "testing", "consult2", "payment", "pharmacy", "completed", "unknown"]


def _container(request: Request) -> dict:
    return request.app.state.container


def _runtime_snapshot(request: Request):
    runtime_service = _container(request)["department_runtime_service"]
    controller = _container(request)["multi_patient_debug_controller"]
    return runtime_service.build_hospital_runtime_snapshot(controller.get_snapshot())


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _map_phase(patient: dict) -> str:
    visit_state = (patient.get("visit_state") or "").lower()
    department_status = (patient.get("department_status") or patient.get("department_flow_status") or "").lower()
    if patient.get("finished") or visit_state == "completed":
        return "completed"
    if visit_state in {"arrived", "triaged"}:
        return "triage"
    if "queue" in department_status or visit_state in {"registered", "waiting_consultation"}:
        return "queue"
    if visit_state in {"in_consultation"} or "round1" in department_status and "consultation" in department_status:
        return "consult1"
    if visit_state in {"waiting_test", "waiting_test_payment", "test_payment_completed", "in_test", "waiting_outpatient_procedure", "in_outpatient_procedure", "waiting_return_consultation", "results_ready"}:
        return "testing"
    if visit_state in {"in_second_consultation"} or "round2" in department_status and "consultation" in department_status:
        return "consult2"
    if visit_state in {"diagnosis_finalized", "waiting_payment", "medical_payment_completed", "disposition_pending"}:
        return "payment"
    if visit_state in {"waiting_pharmacy"}:
        return "pharmacy"
    return "unknown"


def _room_label(patient: dict) -> str:
    return patient.get("current_room_name") or patient.get("room_type") or patient.get("assigned_department_name") or "unknown"


def _serialize_patient_detail(request: Request, patient: dict) -> dict:
    container = _container(request)
    patient_repo = container["patient_repo"]
    visit_repo = container["visit_repo"]
    medical_record_repo = container["medical_record_repo"]
    session_repo = container["session_repo"]

    patient_row = patient_repo.get(patient["patient_id"])
    visit_id = patient.get("visit_id") or patient.get("encounter_id")
    visit_row = visit_repo.get(visit_id) if visit_id else None
    timeline = medical_record_repo.get_visit_timeline(visit_id) if visit_id else None

    active_agent_type = (
        patient.get("active_agent_type")
        or (visit_row or {}).get("active_agent_type")
        or "triage"
    )
    session_row = session_repo.get_latest_by_visit_and_agent(visit_id, active_agent_type) if visit_id else None
    turns = session_repo.list_turns(session_row["id"], limit=40) if session_row else []

    profile = {}
    if visit_row:
        try:
            profile = visit_repo.get_visit_data(visit_id).get("registration_profile") or {}
        except Exception:
            profile = {}

    latest_entry = (timeline or {}).get("entries", [])[-1] if timeline and timeline.get("entries") else None
    diagnosis_summary = None
    if latest_entry:
        content = latest_entry.get("content") or {}
        diagnosis_summary = {
            "title": latest_entry.get("title"),
            "phase": latest_entry.get("phase"),
            "entry_type": latest_entry.get("entry_type"),
            "final_diagnosis": content.get("final_diagnosis"),
            "diagnosis_level": content.get("diagnosis_level"),
            "prescriptions": content.get("prescriptions") or content.get("prescription_plan") or [],
            "patient_plan": content.get("patient_plan"),
        }

    return {
        "npc_id": patient.get("npc_id"),
        "patient_id": patient.get("patient_id"),
        "visit_id": visit_id,
        "name": (patient_row or {}).get("name") or patient.get("patient_id"),
        "phase": _map_phase(patient),
        "room": _room_label(patient),
        "visit_state": patient.get("visit_state"),
        "lifecycle_state": (patient_row or {}).get("lifecycle_state"),
        "assigned_department_name": patient.get("assigned_department_name"),
        "current_node_id": patient.get("current_node_id"),
        "target_node_id": patient.get("target_node_id"),
        "last_action": patient.get("last_action") or patient.get("last_transition_action"),
        "profile": {
            "sex": profile.get("sex"),
            "age": profile.get("age"),
            "id_number": profile.get("id_number"),
            "priority": (patient_row or {}).get("priority"),
            "location": (patient_row or {}).get("location"),
        },
        "dialogue_history": turns,
        "medical_record_summary": (timeline or {}).get("summary"),
        "medical_record_entries": (timeline or {}).get("entries", [])[-12:],
        "diagnosis_summary": diagnosis_summary,
    }


def _build_runtime_stats_payload(request: Request) -> dict:
    snapshot = _runtime_snapshot(request)
    runtime_repo = _container(request)["runtime_stage_sample_repo"]

    phase_counts = Counter()
    room_counts = Counter()
    active_patients = []
    for department in snapshot.departments:
        for patient in department.patients:
            payload = patient.model_dump()
            phase = _map_phase(payload)
            payload["department_status"] = payload.get("department_status") or payload.get("department_flow_status")
            payload["phase"] = phase
            if phase != "completed":
                active_patients.append(payload)
            phase_counts[phase] += 1
            room_counts[_room_label(payload)] += 1
    for patient in snapshot.unassigned_patients:
        payload = patient.model_dump()
        phase = _map_phase(payload)
        payload["phase"] = phase
        if phase != "completed":
            active_patients.append(payload)
        phase_counts[phase] += 1
        room_counts[_room_label(payload)] += 1

    phase_payload = {phase: int(phase_counts.get(phase, 0)) for phase in PHASE_ORDER}
    room_payload = dict(sorted(room_counts.items(), key=lambda item: (-item[1], item[0])))
    runtime_repo.append_sample(
        window_label="live",
        phase_counts=phase_payload,
        room_counts=room_payload,
        active_total=snapshot.active_count,
        historical_total=snapshot.total_spawned,
    )

    samples = runtime_repo.list_recent_samples(limit=240)
    series = defaultdict(list)
    for sample in samples:
        label = sample["sampled_at"][11:19] if len(sample["sampled_at"]) >= 19 else sample["sampled_at"]
        for phase in PHASE_ORDER:
            series[phase].append({"t": label, "value": int(sample["phase_counts"].get(phase, 0))})

    detailed_patients = [_serialize_patient_detail(request, patient) for patient in active_patients]
    detailed_patients.sort(key=lambda item: (PHASE_ORDER.index(item["phase"]) if item["phase"] in PHASE_ORDER else 99, item["name"]))

    windows = {
        "current": phase_payload,
        "history_latest": samples[-1]["phase_counts"] if samples else phase_payload,
        "history_5m_avg": {},
    }
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    recent_samples = [sample for sample in samples if (_parse_iso(sample["sampled_at"]) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
    for phase in PHASE_ORDER:
        values = [int(sample["phase_counts"].get(phase, 0)) for sample in recent_samples]
        windows["history_5m_avg"][phase] = round(sum(values) / len(values), 2) if values else 0

    return {
        "runtime": {
            "running": snapshot.running,
            "mode": snapshot.mode,
            "llm_probability": getattr(snapshot, "llm_probability", None),
            "active_count": snapshot.active_count,
            "historical_total_spawned": snapshot.total_spawned,
            "dispatch_count": snapshot.dispatch_count,
            "blocked_count": snapshot.blocked_count,
            "step_interval_seconds": snapshot.step_interval_seconds,
            "spawn_interval_seconds": snapshot.spawn_interval_seconds,
            "max_active_patients": snapshot.max_active_patients,
            "last_spawn_at": snapshot.last_spawn_at,
            "last_tick_at": snapshot.last_tick_at,
        },
        "phase_counts": phase_payload,
        "room_counts": room_payload,
        "series": {phase: series.get(phase, []) for phase in PHASE_ORDER},
        "windows": windows,
        "patients": detailed_patients,
    }


@router.get("/runtime-stats-html", response_class=HTMLResponse, include_in_schema=False)
def runtime_stats_html_page():
    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hospital Runtime Analytics</title>
  <style>
    :root { color-scheme: light; --bg:#f6f3eb; --card:#fffdf8; --line:#d8d1c2; --ink:#2f3d35; --muted:#6b766f; --accent:#4f7f62; --soft:#eef3e8; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Segoe UI",sans-serif; background:linear-gradient(180deg,#f5f0e4 0%,#eef4e7 100%); color:var(--ink); }
    .page { max-width:1440px; margin:0 auto; padding:20px; }
    .hero { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:16px; }
    .hero h1 { margin:0; font-size:30px; }
    .hero p { margin:6px 0 0; color:var(--muted); }
    .toolbar,.stats-grid,.content-grid { display:grid; gap:14px; }
    .toolbar { grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); margin-bottom:14px; }
    .stats-grid { grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); margin-bottom:14px; }
    .content-grid { grid-template-columns:minmax(0,1.4fr) minmax(360px,0.95fr); align-items:start; }
    .card { background:rgba(255,253,248,0.92); border:1px solid var(--line); border-radius:18px; padding:16px; box-shadow:0 12px 34px rgba(68,77,55,0.08); backdrop-filter: blur(12px); }
    .toolbar .card { padding:12px 14px; }
    .label { font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }
    .big { font-size:30px; font-weight:700; margin-top:6px; }
    .sub { font-size:13px; color:var(--muted); margin-top:4px; }
    .toolbar-row { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
    button,select { border:1px solid #b5c5b6; background:#fff; color:var(--ink); border-radius:999px; padding:8px 14px; font:inherit; cursor:pointer; }
    button.is-active { background:var(--accent); color:#fff; border-color:var(--accent); }
    .chart-wrap { min-height:420px; display:grid; gap:12px; }
    .canvas-box { width:100%; aspect-ratio: 16 / 9; min-height:320px; }
    canvas { width:100%; height:100%; display:block; }
    .legend { display:flex; flex-wrap:wrap; gap:8px 12px; font-size:13px; color:var(--muted); }
    .legend-item { display:flex; align-items:center; gap:8px; }
    .dot { width:12px; height:12px; border-radius:999px; display:inline-block; }
    .patients-list { display:grid; gap:10px; max-height:860px; overflow:auto; padding-right:4px; }
    .patient-row { border:1px solid #ded7c9; border-radius:14px; padding:12px; background:#fff; cursor:pointer; transition:transform .15s ease, box-shadow .15s ease, border-color .15s ease; }
    .patient-row:hover, .patient-row.is-active { transform:translateY(-1px); box-shadow:0 8px 22px rgba(58,74,58,0.1); border-color:#9cb39f; }
    .patient-head { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .patient-name { font-weight:700; }
    .badge { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:5px 10px; font-size:12px; font-weight:700; color:#fff; }
    .meta { margin-top:8px; font-size:13px; color:var(--muted); display:grid; gap:4px; }
    .details { display:grid; gap:12px; }
    .detail-section { border:1px solid #e1dacd; border-radius:14px; padding:12px; background:#fff; }
    .detail-section h3 { margin:0 0 8px; font-size:15px; }
    .kv { display:grid; grid-template-columns:120px 1fr; gap:6px 10px; font-size:13px; }
    .kv strong { color:#657267; }
    .history { display:grid; gap:8px; max-height:240px; overflow:auto; }
    .history-item { border-left:3px solid #d5decb; padding-left:10px; font-size:13px; }
    .history-item .role { font-weight:700; }
    .pill-grid { display:flex; flex-wrap:wrap; gap:8px; }
    .pill { background:var(--soft); border-radius:999px; padding:6px 10px; font-size:12px; color:#345042; }
    .empty { color:var(--muted); font-size:13px; }
    @media (max-width: 1080px) { .content-grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <div>
        <h1>Hospital Runtime Analytics</h1>
        <p>查看当前与近期阶段分布、房间占用和病人详情，支持柱状图、饼图、折线图切换。</p>
      </div>
      <div class="toolbar-row">
        <button id="refreshBtn">Refresh</button>
        <select id="windowSelect">
          <option value="current">Current Snapshot</option>
          <option value="history_5m_avg">Last 5 Minutes Avg</option>
          <option value="history_latest">Latest Saved Sample</option>
        </select>
      </div>
    </div>

    <div class="stats-grid">
      <div class="card"><div class="label">Running</div><div class="big" id="runtimeRunning">-</div><div class="sub" id="runtimeMode">mode -</div></div>
      <div class="card"><div class="label">Active Patients</div><div class="big" id="runtimeActive">0</div><div class="sub" id="runtimeHistorical">historical 0</div></div>
      <div class="card"><div class="label">Runtime Ticks</div><div class="big" id="runtimeDispatch">0</div><div class="sub" id="runtimeBlocked">blocked 0</div></div>
      <div class="card"><div class="label">Intervals</div><div class="big" id="runtimeIntervals">-</div><div class="sub" id="runtimeLastTimes">-</div></div>
    </div>

    <div class="content-grid">
      <div class="card chart-wrap">
        <div class="toolbar-row">
          <button class="view-btn is-active" data-view="bar">Bar</button>
          <button class="view-btn" data-view="pie">Pie</button>
          <button class="view-btn" data-view="line">Line</button>
        </div>
        <div class="canvas-box"><canvas id="chartCanvas" width="920" height="520"></canvas></div>
        <div class="legend" id="chartLegend"></div>
        <div class="detail-section">
          <h3>Room Occupancy</h3>
          <div class="pill-grid" id="roomOccupancy"></div>
        </div>
      </div>

      <div class="details">
        <div class="card">
          <h2 style="margin:0 0 10px;font-size:18px;">Patient List</h2>
          <div class="patients-list" id="patientsList"></div>
        </div>
        <div class="card">
          <h2 style="margin:0 0 10px;font-size:18px;">Patient Detail</h2>
          <div id="patientDetail" class="empty">点击左侧病人查看 id、个人信息、对话历史和诊断结果。</div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const PHASES = ["triage","queue","consult1","testing","consult2","payment","pharmacy","completed","unknown"];
    const COLORS = {
      triage:"#3b82f6", queue:"#f3c84b", consult1:"#8b5cf6", testing:"#13b6c8", consult2:"#a855f7",
      payment:"#f28b32", pharmacy:"#42a868", completed:"#6b7f77", unknown:"#98a39a"
    };
    let state = { view: "bar", window: "current", payload: null, selectedPatientId: null };

    async function loadData() {
      const response = await fetch("/api/v1/runtime-stats-html/data");
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload?.error?.message || payload?.detail || "failed to load runtime stats");
      }
      state.payload = payload.data;
      if (!state.selectedPatientId && state.payload.patients.length) {
        state.selectedPatientId = state.payload.patients[0].patient_id;
      }
      render();
    }

    function phaseValueMap() {
      if (!state.payload) return {};
      if (state.window === "current") return state.payload.phase_counts || {};
      return (state.payload.windows || {})[state.window] || {};
    }

    function renderOverview() {
      const runtime = state.payload.runtime;
      document.getElementById("runtimeRunning").textContent = runtime.running ? "Running" : "Stopped";
      document.getElementById("runtimeMode").textContent = `mode ${runtime.mode} | llm ${runtime.llm_probability ?? "-"}`;
      document.getElementById("runtimeActive").textContent = String(runtime.active_count ?? 0);
      document.getElementById("runtimeHistorical").textContent = `historical ${runtime.historical_total_spawned ?? 0}`;
      document.getElementById("runtimeDispatch").textContent = String(runtime.dispatch_count ?? 0);
      document.getElementById("runtimeBlocked").textContent = `blocked ${runtime.blocked_count ?? 0}`;
      document.getElementById("runtimeIntervals").textContent = `spawn ${runtime.spawn_interval_seconds}s / step ${runtime.step_interval_seconds}s`;
      document.getElementById("runtimeLastTimes").textContent = `last spawn ${runtime.last_spawn_at || "-"} | tick ${runtime.last_tick_at || "-"}`;
    }

    function drawBar(ctx, values, width, height) {
      const entries = PHASES.map((phase) => [phase, Number(values[phase] || 0)]);
      const maxValue = Math.max(1, ...entries.map(([, v]) => v));
      const chartHeight = height - 56;
      const stepX = width / entries.length;
      ctx.font = "12px Segoe UI";
      entries.forEach(([phase, value], index) => {
        const barW = Math.min(54, stepX * 0.58);
        const x = index * stepX + (stepX - barW) / 2;
        const barH = (value / maxValue) * (chartHeight - 28);
        const y = chartHeight - barH + 8;
        ctx.fillStyle = COLORS[phase];
        ctx.fillRect(x, y, barW, barH);
        ctx.fillStyle = "#47534a";
        ctx.fillText(String(value), x + 10, y - 8);
        ctx.save();
        ctx.translate(x + barW / 2, height - 12);
        ctx.rotate(-0.35);
        ctx.fillText(phase, -18, 0);
        ctx.restore();
      });
    }

    function drawPie(ctx, values, width, height) {
      const entries = PHASES.map((phase) => [phase, Number(values[phase] || 0)]).filter(([, value]) => value > 0);
      const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
      let start = -Math.PI / 2;
      const radius = Math.min(width, height) * 0.28;
      const centerX = width * 0.36;
      const centerY = height * 0.5;
      ctx.font = "13px Segoe UI";
      entries.forEach(([phase, value]) => {
        const angle = (value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, start, start + angle);
        ctx.closePath();
        ctx.fillStyle = COLORS[phase];
        ctx.fill();
        const labelAngle = start + angle / 2;
        const lx = centerX + Math.cos(labelAngle) * (radius + 24);
        const ly = centerY + Math.sin(labelAngle) * (radius + 24);
        ctx.fillStyle = "#47534a";
        ctx.fillText(`${phase} ${value}`, lx - 12, ly);
        start += angle;
      });
      ctx.fillStyle = "#2f3d35";
      ctx.font = "700 22px Segoe UI";
      ctx.fillText(String(total), centerX - 10, centerY + 8);
    }

    function drawLine(ctx, payload, width, height) {
      const phasesToShow = ["triage","queue","consult1","testing","consult2","payment","pharmacy"];
      const allPoints = phasesToShow.flatMap((phase) => payload.series[phase] || []);
      const maxValue = Math.max(1, ...allPoints.map((item) => Number(item.value || 0)));
      const sampleCount = Math.max(2, ...phasesToShow.map((phase) => (payload.series[phase] || []).length));
      const pad = { left: 36, right: 16, top: 16, bottom: 32 };
      const chartW = width - pad.left - pad.right;
      const chartH = height - pad.top - pad.bottom;
      ctx.strokeStyle = "#cfd7cb";
      ctx.beginPath();
      ctx.moveTo(pad.left, pad.top + chartH);
      ctx.lineTo(pad.left + chartW, pad.top + chartH);
      ctx.stroke();
      phasesToShow.forEach((phase) => {
        const points = payload.series[phase] || [];
        if (!points.length) return;
        ctx.strokeStyle = COLORS[phase];
        ctx.lineWidth = 2;
        ctx.beginPath();
        points.forEach((point, index) => {
          const x = pad.left + (index / Math.max(1, sampleCount - 1)) * chartW;
          const y = pad.top + chartH - (Number(point.value || 0) / maxValue) * chartH;
          if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
      });
      ctx.fillStyle = "#667268";
      ctx.font = "12px Segoe UI";
      const sampleLine = payload.series.triage || [];
      sampleLine.forEach((point, index) => {
        const x = pad.left + (index / Math.max(1, sampleCount - 1)) * chartW;
        ctx.fillText(point.t, x - 12, height - 10);
      });
    }

    function renderLegend(values) {
      const legend = document.getElementById("chartLegend");
      legend.innerHTML = PHASES.map((phase) => `
        <div class="legend-item">
          <span class="dot" style="background:${COLORS[phase]}"></span>
          <span>${phase}: ${Number(values[phase] || 0)}</span>
        </div>
      `).join("");
    }

    function syncCanvasSize() {
      const canvas = document.getElementById("chartCanvas");
      const box = canvas.parentElement;
      const width = Math.max(720, Math.floor(box.clientWidth));
      const height = Math.max(360, Math.floor(box.clientHeight || width * 0.56));
      canvas.width = width;
      canvas.height = height;
      return { canvas, width, height };
    }

    function renderChart() {
      const { canvas, width, height } = syncCanvasSize();
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, width, height);
      const values = phaseValueMap();
      if (state.view === "pie") drawPie(ctx, values, width, height);
      else if (state.view === "line") drawLine(ctx, state.payload, width, height);
      else drawBar(ctx, values, width, height);
      renderLegend(values);
    }

    function renderRooms() {
      const host = document.getElementById("roomOccupancy");
      const items = Object.entries(state.payload.room_counts || {});
      host.innerHTML = items.length
        ? items.map(([room, count]) => `<span class="pill">${room}: ${count}</span>`).join("")
        : `<span class="empty">No room occupancy data.</span>`;
    }

    function phaseBadge(phase) {
      return `<span class="badge" style="background:${COLORS[phase] || COLORS.unknown}">${phase}</span>`;
    }

    function renderPatients() {
      const host = document.getElementById("patientsList");
      const patients = state.payload.patients || [];
      host.innerHTML = patients.length
        ? patients.map((patient) => `
          <div class="patient-row ${state.selectedPatientId === patient.patient_id ? "is-active" : ""}" data-patient-id="${patient.patient_id}">
            <div class="patient-head">
              <div>
                <div class="patient-name">${patient.name}</div>
                <div class="meta">${patient.assigned_department_name || "-"} · ${patient.room || "-"}</div>
              </div>
              ${phaseBadge(patient.phase)}
            </div>
            <div class="meta">
              <div>id: ${patient.patient_id}</div>
              <div>visit: ${patient.visit_id || "-"}</div>
              <div>node: ${patient.current_node_id || "-"} → ${patient.target_node_id || "-"}</div>
            </div>
          </div>
        `).join("")
        : `<div class="empty">No active patients in runtime.</div>`;
      host.querySelectorAll(".patient-row").forEach((row) => {
        row.addEventListener("click", () => {
          state.selectedPatientId = row.dataset.patientId;
          renderPatients();
          renderPatientDetail();
        });
      });
    }

    function renderPatientDetail() {
      const host = document.getElementById("patientDetail");
      const patient = (state.payload.patients || []).find((item) => item.patient_id === state.selectedPatientId);
      if (!patient) {
        host.className = "empty";
        host.textContent = "No patient selected.";
        return;
      }
      const diagnosis = patient.diagnosis_summary || {};
      const prescriptions = diagnosis.prescriptions || [];
      host.className = "details";
      host.innerHTML = `
        <div class="detail-section">
          <h3>${patient.name} ${phaseBadge(patient.phase)}</h3>
          <div class="kv">
            <strong>Patient ID</strong><span>${patient.patient_id}</span>
            <strong>Visit ID</strong><span>${patient.visit_id || "-"}</span>
            <strong>Department</strong><span>${patient.assigned_department_name || "-"}</span>
            <strong>Visit State</strong><span>${patient.visit_state || "-"}</span>
            <strong>Current Node</strong><span>${patient.current_node_id || "-"}</span>
            <strong>Target Node</strong><span>${patient.target_node_id || "-"}</span>
            <strong>Last Action</strong><span>${patient.last_action || "-"}</span>
          </div>
        </div>
        <div class="detail-section">
          <h3>Personal Info</h3>
          <div class="kv">
            <strong>Sex</strong><span>${patient.profile.sex || "-"}</span>
            <strong>Age</strong><span>${patient.profile.age ?? "-"}</span>
            <strong>ID Number</strong><span>${patient.profile.id_number || "-"}</span>
            <strong>Priority</strong><span>${patient.profile.priority || "-"}</span>
            <strong>Location</strong><span>${patient.profile.location || "-"}</span>
          </div>
        </div>
        <div class="detail-section">
          <h3>Diagnosis Result</h3>
          <div class="kv">
            <strong>Title</strong><span>${diagnosis.title || "-"}</span>
            <strong>Phase</strong><span>${diagnosis.phase || "-"}</span>
            <strong>Final Diagnosis</strong><span>${diagnosis.final_diagnosis || "-"}</span>
            <strong>Diagnosis Level</strong><span>${diagnosis.diagnosis_level ?? "-"}</span>
            <strong>Plan</strong><span>${diagnosis.patient_plan || "-"}</span>
          </div>
          <div class="pill-grid" style="margin-top:10px;">
            ${prescriptions.length ? prescriptions.map((item) => `<span class="pill">${item.name || item.medication || JSON.stringify(item)}</span>`).join("") : `<span class="empty">No prescriptions.</span>`}
          </div>
        </div>
        <div class="detail-section">
          <h3>Dialogue History</h3>
          <div class="history">
            ${patient.dialogue_history.length ? patient.dialogue_history.map((turn) => `
              <div class="history-item">
                <div class="role">${turn.role} · ${turn.timestamp || "-"}</div>
                <div>${turn.content || ""}</div>
              </div>
            `).join("") : `<div class="empty">No dialogue turns recorded yet.</div>`}
          </div>
        </div>
        <div class="detail-section">
          <h3>Medical Record Timeline</h3>
          <div class="history">
            ${(patient.medical_record_entries || []).length ? patient.medical_record_entries.map((entry) => `
              <div class="history-item">
                <div class="role">${entry.title} · ${entry.phase} · ${entry.created_at}</div>
                <div>${entry.content_text || ""}</div>
              </div>
            `).join("") : `<div class="empty">No medical record entries yet.</div>`}
          </div>
        </div>
      `;
    }

    function render() {
      if (!state.payload) return;
      renderOverview();
      renderChart();
      renderRooms();
      renderPatients();
      renderPatientDetail();
    }

    document.querySelectorAll(".view-btn").forEach((button) => {
      button.addEventListener("click", () => {
        state.view = button.dataset.view;
        document.querySelectorAll(".view-btn").forEach((item) => item.classList.toggle("is-active", item === button));
        renderChart();
      });
    });
    document.getElementById("windowSelect").addEventListener("change", (event) => {
      state.window = event.target.value;
      renderChart();
    });
    document.getElementById("refreshBtn").addEventListener("click", () => loadData().catch(showError));
    window.addEventListener("resize", () => {
      if (state.payload) renderChart();
    });

    function showError(error) {
      const message = error?.message || "unknown error";
      document.getElementById("patientsList").innerHTML = `<div class="empty">Failed to load runtime stats: ${message}</div>`;
      document.getElementById("patientDetail").textContent = message;
    }

    loadData().catch(showError);
    setInterval(() => loadData().catch(() => {}), 4000);
  </script>
</body>
</html>
        """
    )


@router.get("/api/v1/runtime-stats-html/data")
def runtime_stats_html_data(request: Request):
    return {"ok": True, "data": _build_runtime_stats_payload(request)}


@router.get("/api/v1/runtime-stats-html/patient/{patient_id}")
def runtime_stats_patient_detail(patient_id: str, request: Request):
    payload = _build_runtime_stats_payload(request)
    patient = next((item for item in payload["patients"] if item["patient_id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="patient not found in active runtime")
    return {"ok": True, "data": patient}
