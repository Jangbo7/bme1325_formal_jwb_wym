from __future__ import annotations

from html import escape
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.schemas.multi_patient_debug import MultiPatientDebugStartRequest


router = APIRouter()


def _multi_controller(request: Request):
    return request.app.state.container["multi_patient_debug_controller"]


def _runtime_service(request: Request):
    return request.app.state.container["department_runtime_service"]


def _snapshot(request: Request):
    return _runtime_service(request).build_debug_snapshot(_multi_controller(request).get_snapshot())


def _text(value) -> str:
    if value is None:
        return "-"
    text = str(value)
    return text if text else "-"


def _render_patient_dialogue(patient: dict) -> str:
    dialogue = patient.get("current_dialogue") or {}
    if not dialogue:
        return '<div class="muted">No dialogue in this step.</div>'
    return (
        '<div class="dialogue">'
        f'<div><strong>{escape(_text(patient.get("current_counterparty")))}</strong></div>'
        f'<div class="row">{escape(_text(dialogue.get("speaker")))}</div>'
        f'<div class="row">{escape(_text(dialogue.get("message")))}</div>'
        f'<div class="row">direction: {escape(_text(dialogue.get("direction")))}</div>'
        "</div>"
    )


def _render_patient_card(patient: dict) -> str:
    patient_label = patient.get("npc_id") or patient.get("patient_id")
    patient_detail_id = (
        f'patient-{patient.get("visit_id") or patient.get("patient_id") or patient.get("npc_id") or "unknown"}'
    )
    detail_rows = [
        f'<div class="row">patient: {escape(_text(patient.get("patient_id")))}</div>',
        f'<div class="row">visit: {escape(_text(patient.get("visit_id")))}</div>',
        f'<div class="row">encounter node: {escape(_text(patient.get("current_node_id") or patient.get("current_node")))}</div>',
        f'<div class="row">target node: {escape(_text(patient.get("target_node_id")))}</div>',
        f'<div class="row">queue: {escape(_text(patient.get("queue_kind")))}</div>',
        f'<div class="row">doctor slot: {escape(_text(patient.get("assigned_doctor_slot_name")))} ({escape(_text(patient.get("assigned_doctor_slot_id")))})</div>',
        f'<div class="row">room: {escape(_text(patient.get("current_room_name")))} ({escape(_text(patient.get("current_room_node_id")))}) / {escape(_text(patient.get("room_type")))}</div>',
        f'<div class="row">counterparty: {escape(_text(patient.get("current_counterparty")))}</div>',
        f'<div class="row">active agent: {escape(_text(patient.get("active_agent_type")))}</div>',
        f'<div class="row">last action: {escape(_text(patient.get("last_action") or patient.get("last_transition_action")))}</div>',
        f'<div class="row">entered dept: {escape(_text(patient.get("entered_department_at")))}</div>',
        f'<div class="row">updated: {escape(_text(patient.get("updated_at")))}</div>',
        f'<div class="row">finished at: {escape(_text(patient.get("finished_at")))}</div>',
    ]
    return (
        '<article class="patient">'
        f'<div><strong>{escape(_text(patient_label))}</strong>'
        f'<span class="badge">{escape(_text(patient.get("department_status") or patient.get("department_flow_status")))}</span></div>'
        f'<div class="row">visit_state: {escape(_text(patient.get("visit_state")))}</div>'
        f'<div class="row">runner: {escape(_text(patient.get("execution_runner_kind")))} / capability: {escape(_text(patient.get("department_capability_class")))}</div>'
        f'<div class="row">room: {escape(_text(patient.get("current_room_name")))} ({escape(_text(patient.get("current_room_node_id")))})</div>'
        f'<details data-detail-id="{escape(patient_detail_id)}">'
        '<summary>Patient Details</summary>'
        + "".join(detail_rows)
        + _render_patient_dialogue(patient)
        + "</details></article>"
    )


def _render_initial_department_snapshot(snapshot: dict) -> tuple[str, str, str, str]:
    departments = list(snapshot.get("departments") or [])
    departments_with_patients = sum(1 for item in departments if item.get("patients"))
    finished_patients = sum(
        1 for item in departments for patient in (item.get("patients") or []) if patient.get("finished")
    )
    stats_html = "".join(
        [
            f'<div class="stat"><strong>running</strong><div>{escape(_text(snapshot.get("running")))}</div></div>',
            f'<div class="stat"><strong>mode</strong><div>{escape(_text(snapshot.get("mode")))}</div></div>',
            f'<div class="stat"><strong>active_count</strong><div>{escape(_text(snapshot.get("active_count")))}</div></div>',
            f'<div class="stat"><strong>spawned</strong><div>{escape(_text(snapshot.get("total_spawned")))}</div></div>',
            f'<div class="stat"><strong>llm probability</strong><div>{escape(_text(snapshot.get("llm_probability")))}</div></div>',
            f'<div class="stat"><strong>dept with patients</strong><div>{departments_with_patients}</div></div>',
            f'<div class="stat"><strong>finished patients</strong><div>{finished_patients}</div></div>',
            f'<div class="stat"><strong>dispatch</strong><div>{escape(_text(snapshot.get("dispatch_count")))}</div></div>',
            f'<div class="stat"><strong>blocked</strong><div>{escape(_text(snapshot.get("blocked_count")))}</div></div>',
            f'<div class="stat"><strong>last_spawn</strong><div>{escape(_text(snapshot.get("last_spawn_at")))}</div></div>',
            f'<div class="stat"><strong>last_tick</strong><div>{escape(_text(snapshot.get("last_tick_at")))}</div></div>',
        ]
    )
    department_sections: list[str] = []
    for department in departments:
        summary = department.get("summary") or {}
        patients = list(department.get("patients") or [])
        doctor_slots = list(department.get("doctor_slots") or [])
        rooms = list(department.get("rooms") or [])
        resource_parts: list[str] = []
        if doctor_slots:
            resource_parts.append(
                '<div class="resource-grid">'
                + "".join(
                    f'<div class="resource-card"><div><strong>{escape(_text(slot.get("label")))}</strong></div>'
                    f'<div>id: {escape(_text(slot.get("slot_id")))}</div>'
                    f'<div>active/capacity: {escape(_text(slot.get("active_count")))}/{escape(_text(slot.get("capacity")))}</div></div>'
                    for slot in doctor_slots
                )
                + "</div>"
            )
        if rooms:
            resource_parts.append(
                '<div class="resource-grid">'
                + "".join(
                    f'<div class="resource-card"><div><strong>{escape(_text(room.get("name")))}</strong></div>'
                    f'<div>type: {escape(_text(room.get("room_type")))}</div>'
                    f'<div>active/capacity: {escape(_text(room.get("active_count")))}/{escape(_text(room.get("capacity")))}</div></div>'
                    for room in rooms
                )
                + "</div>"
            )
        patient_rows = ("".join(_render_patient_card(patient) for patient in patients) or "<div class='muted'>No patients.</div>")
        department_sections.append(
            f'<section class="department"><details data-detail-id="dept-{escape(_text(department.get("department_id")))}">'
            f'<summary><strong>{escape(_text(department.get("department_name")))}</strong> ({len(patients)})</summary>'
            f'<div class="summary">'
            f'<div>capability: {escape(_text(department.get("department_capability_class")))} / agent={escape(_text(department.get("department_agent_enabled")))}</div>'
            f'<div>active: {escape(_text(summary.get("active_count")))}</div>'
            f'<div>pending reg: {escape(_text(summary.get("pending_registration_count")))}</div>'
            f'<div>waiting r1/r2: {escape(_text(summary.get("waiting_round1_count")))}/{escape(_text(summary.get("waiting_round2_count")))}</div>'
            f'<div>called r1/r2: {escape(_text(summary.get("called_round1_count")))}/{escape(_text(summary.get("called_round2_count")))}</div>'
            f'<div>consult r1/r2: {escape(_text(summary.get("in_consultation_round1_count")))}/{escape(_text(summary.get("in_consultation_round2_count")))}</div>'
            f'<div>in test: {escape(_text(summary.get("in_test_count")))}</div>'
            f'<div>finished: {escape(_text(summary.get("finished_count")))}</div>'
            f'<div>updated: {escape(_text(summary.get("updated_at")))}</div>'
            f'<div>patients: {len(patients)}</div>'
            f'</div>{"".join(resource_parts)}<div class="patients">{patient_rows}</div></details></section>'
        )
    departments_html = "".join(department_sections) or "<section class='department'><div class='muted'>No departments available.</div></section>"
    unassigned_patients = list(snapshot.get("unassigned_patients") or [])
    unassigned_html = (
        "".join(
            _render_patient_card(patient)
            for patient in unassigned_patients
        )
        if unassigned_patients
        else ""
    )
    return stats_html, departments_html, unassigned_html, ("block" if unassigned_patients else "none")


def _selected_option(value: str, current: str | None) -> str:
    return " selected" if value == (current or "") else ""


def _render_department_runtime_page(snapshot: dict, *, status_message: str | None = None, error_message: str | None = None) -> HTMLResponse:
    initial_stats_html, initial_departments_html, initial_unassigned_html, initial_unassigned_display = _render_initial_department_snapshot(snapshot)
    mode = str(snapshot.get("mode") or "intelligent_agent")
    spawn_interval = _text(snapshot.get("spawn_interval_seconds"))
    step_interval = _text(snapshot.get("step_interval_seconds"))
    max_active_patients = _text(snapshot.get("max_active_patients"))
    llm_probability = "" if snapshot.get("llm_probability") is None else str(snapshot.get("llm_probability"))
    status_text = error_message or status_message or ""
    status_color = "#8a1f1f" if error_message else "#2b5a3d"
    auto_refresh = '<meta http-equiv="refresh" content="1" />' if snapshot.get("running") else ""
    auto_refresh_note = '<div class="muted" style="margin-top: 8px;">Auto refresh enabled while runtime is running.</div>' if snapshot.get("running") else ""
    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Department Runtime Debug</title>
  {auto_refresh}
  <style>
    :root {{
      --bg: #f4f7ee;
      --panel: #ffffff;
      --ink: #122017;
      --line: #cad7c8;
      --accent: #2f6d44;
      --muted: #5d6f63;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top, #fafff7 0%, var(--bg) 50%, #e3ebdf 100%);
    }}
    main {{ max-width: 1400px; margin: 0 auto; padding: 20px 16px 48px; }}
    h1 {{ margin: 0 0 8px; }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .toolbar, .panel, .department, .patient {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: 0 8px 20px rgba(15, 35, 16, 0.08);
    }}
    .toolbar, .panel {{ padding: 14px; margin-top: 12px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }}
    label {{ font-size: 12px; text-transform: uppercase; color: var(--muted); }}
    input, select, button {{
      font: inherit;
      border: 1px solid #90a993;
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
    }}
    button {{
      background: linear-gradient(180deg, #43835a 0%, var(--accent) 100%);
      color: #fff;
      cursor: pointer;
    }}
    button.secondary {{ background: #edf5ee; color: var(--ink); }}
    #status {{ margin-top: 10px; min-height: 18px; color: #2b5a3d; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
    .stat {{ border: 1px dashed var(--line); border-radius: 10px; padding: 8px; }}
    .departments {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 14px; margin-top: 14px; }}
    .department {{ padding: 12px; }}
    .summary {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }}
    .summary div {{ border: 1px dashed var(--line); border-radius: 10px; padding: 8px; font-size: 13px; }}
    .resource-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin-top: 10px; }}
    .resource-card {{ border: 1px dashed var(--line); border-radius: 10px; padding: 8px; font-size: 13px; background: #f8fbf6; }}
    .patients {{ display: grid; gap: 10px; margin-top: 12px; }}
    .patient {{ padding: 10px; }}
    .row {{ margin-top: 4px; font-size: 13px; }}
    .dialogue {{ margin-top: 8px; padding: 8px; border: 1px dashed var(--line); border-radius: 10px; background: #f8fbf6; }}
    .badge {{ display: inline-block; border: 1px solid #9db39e; border-radius: 999px; padding: 2px 8px; font-size: 12px; margin-left: 8px; }}
    details summary {{ cursor: pointer; color: #2f6d44; font-size: 13px; }}
    form.toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }}
  </style>
</head>
<body>
  <main>
    <h1>Department Runtime Debug</h1>
    <div class="muted">Department-centric runtime view built on top of the existing multi patient auto-runner, including legacy offline/probabilistic LLM controls. No scene integration in this page.</div>
    <form class="toolbar" method="get" action="/department-runtime-debug">
      <div>
        <label>Mode</label><br />
        <select id="mode" name="mode">
          <option value="intelligent_agent"{_selected_option("intelligent_agent", mode)}>intelligent_agent</option>
          <option value="department_mixed"{_selected_option("department_mixed", mode)}>department_mixed</option>
          <option value="legacy_template"{_selected_option("legacy_template", mode)}>legacy_template</option>
          <option value="legacy_probabilistic_llm"{_selected_option("legacy_probabilistic_llm", mode)}>legacy_probabilistic_llm</option>
        </select>
      </div>
      <div>
        <label>Spawn Interval(s)</label><br />
        <input id="spawnInterval" name="spawn_interval_seconds" type="number" min="0" step="0.5" value="{escape(spawn_interval)}" />
      </div>
      <div>
        <label>Step Interval(s)</label><br />
        <input id="stepInterval" name="step_interval_seconds" type="number" min="0.1" step="0.5" value="{escape(step_interval)}" />
      </div>
      <div>
        <label>Max Active Patients</label><br />
        <input id="maxPatients" name="max_active_patients" type="number" min="1" step="1" value="{escape(max_active_patients)}" />
      </div>
      <div>
        <label>LLM Probability</label><br />
        <input id="llmProbability" name="llm_probability" type="number" min="0" max="1" step="0.1" value="{escape(llm_probability)}" />
      </div>
      <button type="submit" name="action" value="start">Start</button>
      <button type="submit" name="action" value="stop" class="secondary">Stop</button>
      <button type="submit" name="action" value="reset" class="secondary">Reset</button>
      <button type="submit" name="action" value="refresh" class="secondary">Refresh</button>
    </form>
    <div id="status" style="color: {status_color};">{escape(status_text)}</div>
    {auto_refresh_note}
    <section class="panel">
      <div class="stats" id="stats">{initial_stats_html}</div>
    </section>
    <section class="departments" id="departments">{initial_departments_html}</section>
    <section class="panel" id="unassignedPanel" style="display:{initial_unassigned_display};">
      <h3>Unassigned Patients</h3>
      <div class="patients" id="unassignedPatients">{initial_unassigned_html}</div>
    </section>
  </main>
  <script>
    (function () {{
      const storageKey = "department-runtime-debug-open-details";

      function readOpenIds() {{
        try {{
          const raw = window.sessionStorage.getItem(storageKey);
          const parsed = raw ? JSON.parse(raw) : [];
          return Array.isArray(parsed) ? parsed : [];
        }} catch (_error) {{
          return [];
        }}
      }}

      function writeOpenIds() {{
        try {{
          const openIds = Array.from(document.querySelectorAll("details[data-detail-id][open]"))
            .map((el) => el.getAttribute("data-detail-id"))
            .filter(Boolean);
          window.sessionStorage.setItem(storageKey, JSON.stringify(openIds));
        }} catch (_error) {{
        }}
      }}

      const openIds = new Set(readOpenIds());
      document.querySelectorAll("details[data-detail-id]").forEach(function (el) {{
        const detailId = el.getAttribute("data-detail-id");
        if (detailId && openIds.has(detailId)) {{
          el.open = true;
        }}
        el.addEventListener("toggle", writeOpenIds);
      }});
    }})();
  </script>
</body>
</html>
    """
    return HTMLResponse(html)


@router.get("/department-runtime-debug", response_class=HTMLResponse, include_in_schema=False)
def department_runtime_debug_page(
    request: Request,
    action: str | None = None,
    mode: str = "intelligent_agent",
    spawn_interval_seconds: float = 4.0,
    step_interval_seconds: float = 2.0,
    max_active_patients: str = "20",
    llm_probability: str = "0",
    status: str | None = None,
    error: str | None = None,
):
    if action:
        status_message: str | None = None
        error_message: str | None = None
        max_active_value = None if str(max_active_patients).strip() == "" else int(max_active_patients)
        llm_probability_value = None if str(llm_probability).strip() == "" else float(llm_probability)
        try:
            if action == "start":
                if max_active_value is not None and max_active_value < 1:
                    raise HTTPException(status_code=422, detail="max_active_patients must be >= 1")
                _multi_controller(request).start(
                    mode=mode,
                    spawn_interval_seconds=spawn_interval_seconds,
                    step_interval_seconds=step_interval_seconds,
                    max_active_patients=max_active_value,
                    llm_probability=llm_probability_value,
                )
                status_message = "Started."
            elif action == "stop":
                _multi_controller(request).stop()
                status_message = "Stopped."
            elif action == "reset":
                _multi_controller(request).reset()
                status_message = "Reset."
            else:
                status_message = "Snapshot refreshed."
        except RuntimeError as exc:
            error_message = str(exc)
        except HTTPException as exc:
            error_message = str(exc.detail)
        redirect_url = "/department-runtime-debug"
        if error_message:
            redirect_url += f"?error={quote(error_message)}"
        elif status_message:
            redirect_url += f"?status={quote(status_message)}"
        return RedirectResponse(url=redirect_url, status_code=303)
    return _render_department_runtime_page(
        _snapshot(request).model_dump(),
        status_message=status,
        error_message=error,
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
            llm_probability=body.llm_probability,
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
