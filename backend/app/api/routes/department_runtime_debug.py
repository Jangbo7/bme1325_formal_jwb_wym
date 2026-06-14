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


def _projection_text(patient: dict) -> str:
    round_value = patient.get("consultation_round")
    round_suffix = f" / round {round_value}" if round_value is not None else ""
    return f'{_text(patient.get("display_stage"))} / {_text(patient.get("dispatch_state"))}{round_suffix}'


def _blocking_text(patient: dict) -> str:
    blocking = patient.get("blocking") or {}
    if not blocking:
        return "-"
    return " | ".join(
        _text(value)
        for value in [
            blocking.get("kind"),
            blocking.get("resource_kind"),
            blocking.get("resource_id"),
            blocking.get("message"),
        ]
        if value not in {None, ""}
    )


def _patient_special_outcome_bucket(patient: dict) -> str | None:
    visit_state = str(patient.get("visit_state") or "").strip().lower()
    primary_disposition = str(patient.get("primary_disposition") or "").strip().lower()
    disposition = patient.get("disposition") or {}
    disposition_category = str(disposition.get("category") or "").strip().lower()

    if visit_state == "in_icu_rescue" or primary_disposition == "icu_escalation" or disposition_category == "icu_rescue":
        return "icu"
    if visit_state == "in_emergency" or primary_disposition == "emergency_escalation" or disposition_category == "emergency_escalation":
        return "emergency"
    if primary_disposition == "specialty_referral" or disposition_category == "specialty_referral":
        return "referral"
    return None


def _count_special_outcomes(patients: list[dict]) -> dict[str, int]:
    counts = {
        "referral": 0,
        "emergency": 0,
        "icu": 0,
    }
    for patient in patients:
        bucket = _patient_special_outcome_bucket(patient)
        if bucket:
            counts[bucket] += 1
    return counts


def _patient_rare_event_state(patient: dict) -> str:
    profile = patient.get("rare_event_profile") or {}
    patient_enabled = bool(profile.get("patient_special_event_enabled"))
    report_enabled = bool(profile.get("report_special_signal_enabled"))
    triggered_by = str(patient.get("rare_event_triggered_by") or profile.get("triggered_by") or "").strip().lower()
    event_type = str(patient.get("rare_event_type") or profile.get("event_type") or "").strip().lower()
    if not event_type and triggered_by in {"", "none"} and not patient_enabled and not report_enabled:
        return "none"
    if patient_enabled and report_enabled:
        return "both"
    if patient_enabled or triggered_by == "patient":
        return "patient"
    if report_enabled or triggered_by == "report":
        return "report"
    return "unknown"


def _count_rare_events(patients: list[dict]) -> dict[str, int]:
    counts = {
        "any": 0,
        "patient": 0,
        "report": 0,
        "both": 0,
        "unknown": 0,
    }
    for patient in patients:
        state = _patient_rare_event_state(patient)
        if state == "none":
            continue
        counts["any"] += 1
        counts[state] += 1
    return counts


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
    rare_event_state = _patient_rare_event_state(patient)
    rare_event_class = f" patient--rare-event patient--rare-event-{rare_event_state}" if rare_event_state != "none" else ""
    rare_event_badge = (
        f'<span class="badge badge--rare badge--rare-{escape(rare_event_state)}">rare:{escape(rare_event_state)}</span>'
        if rare_event_state != "none"
        else ""
    )
    detail_rows = [
        f'<div class="row">patient: {escape(_text(patient.get("patient_id")))}</div>',
        f'<div class="row">visit: {escape(_text(patient.get("visit_id")))}</div>',
        f'<div class="row">source: {escape(_text(patient.get("patient_source")))}</div>',
        f'<div class="row">generation hint: {escape(_text(patient.get("generation_hint_department_name")))} ({escape(_text(patient.get("generation_hint_department_id")))})</div>',
        f'<div class="row">rare event: {escape(_text(patient.get("rare_event_type")))} / {escape(_text(patient.get("rare_event_triggered_by")))}</div>',
        f'<div class="row">stage/dispatch: {escape(_projection_text(patient))}</div>',
        f'<div class="row">blocking: {escape(_blocking_text(patient))}</div>',
        f'<div class="row">encounter node: {escape(_text(patient.get("current_node_id") or patient.get("current_node")))}</div>',
        f'<div class="row">target node: {escape(_text(patient.get("target_node_id")))}</div>',
        f'<div class="row">queue: {escape(_text(patient.get("queue_kind")))}</div>',
        f'<div class="row">doctor llm source: {escape(_text(patient.get("latest_consultation_response_source")))}</div>',
        f'<div class="row">doctor llm error: {escape(_text(patient.get("latest_consultation_llm_error")))}</div>',
        f'<div class="row">report acuity: {escape(_text(patient.get("report_acuity_level")))}</div>',
        f'<div class="row">referral target: {escape(_text(patient.get("recommended_department")))}</div>',
        f'<div class="row">re-register required: {escape(_text(patient.get("requires_new_registration")))}</div>',
        f'<div class="row">doctor slot: {escape(_text(patient.get("assigned_doctor_slot_name")))} ({escape(_text(patient.get("assigned_doctor_slot_id")))})</div>',
        f'<div class="row">room: {escape(_text(patient.get("current_room_name")))} ({escape(_text(patient.get("current_room_node_id")))}) / {escape(_text(patient.get("room_type")))}</div>',
        f'<div class="row">resource assignment: {escape(_text((patient.get("resource_assignment") or {}).get("target_resource_kind")))} / {escape(_text((patient.get("resource_assignment") or {}).get("target_node_id")))}</div>',
        f'<div class="row">counterparty: {escape(_text(patient.get("current_counterparty")))}</div>',
        f'<div class="row">active agent: {escape(_text(patient.get("active_agent_type")))}</div>',
        f'<div class="row">last action: {escape(_text(patient.get("last_action") or patient.get("last_transition_action")))}</div>',
        f'<div class="row">entered dept: {escape(_text(patient.get("entered_department_at")))}</div>',
        f'<div class="row">updated: {escape(_text(patient.get("updated_at")))}</div>',
        f'<div class="row">finished at: {escape(_text(patient.get("finished_at")))}</div>',
    ]
    return (
        f'<article class="patient{rare_event_class}">'
        f'<div><strong>{escape(_text(patient_label))}</strong>'
        f'<span class="badge">{escape(_text(patient.get("department_status") or patient.get("department_flow_status")))}</span>'
        f"{rare_event_badge}</div>"
        f'<div class="row">visit_state: {escape(_text(patient.get("visit_state")))}</div>'
        f'<div class="row">stage/dispatch: {escape(_projection_text(patient))}</div>'
        f'<div class="row">runner/source: {escape(_text(patient.get("execution_runner_kind")))} / {escape(_text(patient.get("patient_source")))}</div>'
        f'<div class="row">hint: {escape(_text(patient.get("generation_hint_department_name")))} ({escape(_text(patient.get("generation_hint_department_id")))})</div>'
        f'<div class="row">rare event: {escape(_text(patient.get("rare_event_type")))} / {escape(_text(patient.get("rare_event_triggered_by")))}</div>'
        f'<div class="row">capability: {escape(_text(patient.get("department_capability_class")))}</div>'
        f'<div class="row">report/referral: {escape(_text(patient.get("report_acuity_level")))} / {escape(_text(patient.get("recommended_department")))}</div>'
        f'<div class="row">room: {escape(_text(patient.get("current_room_name")))} ({escape(_text(patient.get("current_room_node_id")))})</div>'
        f'<details data-detail-id="{escape(patient_detail_id)}">'
        '<summary>Patient Details</summary>'
        + "".join(detail_rows)
        + _render_patient_dialogue(patient)
        + "</details></article>"
    )


def _render_initial_department_snapshot(snapshot: dict) -> tuple[str, str, str, str]:
    departments = list(snapshot.get("departments") or [])
    unassigned_patients = list(snapshot.get("unassigned_patients") or [])
    departments_with_patients = sum(1 for item in departments if item.get("patients"))
    finished_patients = sum(
        1 for item in departments for patient in (item.get("patients") or []) if patient.get("finished")
    )
    all_patients = [patient for item in departments for patient in (item.get("patients") or [])] + unassigned_patients
    special_outcome_counts = _count_special_outcomes(all_patients)
    rare_event_counts = _count_rare_events(all_patients)
    stats_html = "".join(
        [
            f'<div class="stat"><strong>running</strong><div>{escape(_text(snapshot.get("running")))}</div></div>',
            f'<div class="stat"><strong>mode</strong><div>{escape(_text(snapshot.get("mode")))}</div></div>',
            f'<div class="stat"><strong>active_count</strong><div>{escape(_text(snapshot.get("active_count")))}</div></div>',
            f'<div class="stat"><strong>spawned</strong><div>{escape(_text(snapshot.get("total_spawned")))}</div></div>',
            f'<div class="stat"><strong>probability</strong><div>{escape(_text(snapshot.get("llm_probability")))}</div></div>',
            f'<div class="stat"><strong>dept with patients</strong><div>{departments_with_patients}</div></div>',
            f'<div class="stat"><strong>finished patients</strong><div>{finished_patients}</div></div>',
            f'<div class="stat"><strong>referrals</strong><div>{special_outcome_counts["referral"]}</div></div>',
            f'<div class="stat"><strong>emergency</strong><div>{special_outcome_counts["emergency"]}</div></div>',
            f'<div class="stat"><strong>icu</strong><div>{special_outcome_counts["icu"]}</div></div>',
            f'<div class="stat"><strong>dispatch</strong><div>{escape(_text(snapshot.get("dispatch_count")))}</div></div>',
            f'<div class="stat"><strong>blocked attempts</strong><div>{escape(_text(snapshot.get("blocked_count")))}</div></div>',
            f'<div class="stat"><strong>blocked patients</strong><div>{escape(_text(snapshot.get("currently_blocked_patients")))}</div></div>',
            f'<div class="stat"><strong>rare events</strong><div>{rare_event_counts["any"]}</div></div>',
            f'<div class="stat"><strong>rare source</strong><div>p={rare_event_counts["patient"]} r={rare_event_counts["report"]} b={rare_event_counts["both"]}</div></div>',
            f'<div class="stat"><strong>last_spawn</strong><div>{escape(_text(snapshot.get("last_spawn_at")))}</div></div>',
            f'<div class="stat"><strong>last_tick</strong><div>{escape(_text(snapshot.get("last_tick_at")))}</div></div>',
        ]
    )
    department_sections: list[str] = []
    for department in departments:
        summary = department.get("summary") or {}
        patients = list(department.get("patients") or [])
        special_counts = _count_special_outcomes(patients)
        rare_event_counts = _count_rare_events(patients)
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
            f'<div>gate capacity: {escape(_text(department.get("department_gate_capacity")))}</div>'
            f'<div>active: {escape(_text(summary.get("active_count")))}</div>'
            f'<div>pending reg: {escape(_text(summary.get("pending_registration_count")))}</div>'
            f'<div>waiting r1/r2: {escape(_text(summary.get("waiting_round1_count")))}/{escape(_text(summary.get("waiting_round2_count")))}</div>'
            f'<div>called r1/r2: {escape(_text(summary.get("called_round1_count")))}/{escape(_text(summary.get("called_round2_count")))}</div>'
             f'<div>consult r1/r2: {escape(_text(summary.get("in_consultation_round1_count")))}/{escape(_text(summary.get("in_consultation_round2_count")))}</div>'
             f'<div>in test: {escape(_text(summary.get("in_test_count")))}</div>'
              f'<div>referral/emergency/icu: {special_counts["referral"]}/{special_counts["emergency"]}/{special_counts["icu"]}</div>'
              f'<div>rare events: {rare_event_counts["any"]} (p={rare_event_counts["patient"]} r={rare_event_counts["report"]} b={rare_event_counts["both"]})</div>'
              f'<div>finished: {escape(_text(summary.get("finished_count")))}</div>'
              f'<div>updated: {escape(_text(summary.get("updated_at")))}</div>'
              f'<div>patients: {len(patients)}</div>'
              f'</div>{"".join(resource_parts)}<div class="patients">{patient_rows}</div></details></section>'
        )
    departments_html = "".join(department_sections) or "<section class='department'><div class='muted'>No departments available.</div></section>"
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
      --rare-patient-bg: #fff0e2;
      --rare-patient-line: #d68a36;
      --rare-report-bg: #e7f4ff;
      --rare-report-line: #3e8acb;
      --rare-both-bg: #fff3c7;
      --rare-both-line: #ae7d00;
      --rare-unknown-bg: #f4ebff;
      --rare-unknown-line: #7f5ab6;
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
    .patient--rare-event {{ border-width: 2px; }}
    .patient--rare-event-patient {{
      background: linear-gradient(180deg, var(--rare-patient-bg) 0%, #fff9f2 100%);
      border-color: var(--rare-patient-line);
      box-shadow: 0 12px 24px rgba(214, 138, 54, 0.16);
    }}
    .patient--rare-event-report {{
      background: linear-gradient(180deg, var(--rare-report-bg) 0%, #f8fcff 100%);
      border-color: var(--rare-report-line);
      box-shadow: 0 12px 24px rgba(62, 138, 203, 0.16);
    }}
    .patient--rare-event-both {{
      background: linear-gradient(180deg, var(--rare-both-bg) 0%, #fffbee 100%);
      border-color: var(--rare-both-line);
      box-shadow: 0 12px 24px rgba(174, 125, 0, 0.16);
    }}
    .patient--rare-event-unknown {{
      background: linear-gradient(180deg, var(--rare-unknown-bg) 0%, #fcf9ff 100%);
      border-color: var(--rare-unknown-line);
      box-shadow: 0 12px 24px rgba(127, 90, 182, 0.14);
    }}
    .row {{ margin-top: 4px; font-size: 13px; }}
    .dialogue {{ margin-top: 8px; padding: 8px; border: 1px dashed var(--line); border-radius: 10px; background: #f8fbf6; }}
    .badge {{ display: inline-block; border: 1px solid #9db39e; border-radius: 999px; padding: 2px 8px; font-size: 12px; margin-left: 8px; }}
    .badge--rare {{ color: #fff; border-color: transparent; }}
    .badge--rare-patient {{ background: #d68a36; }}
    .badge--rare-report {{ background: #3e8acb; }}
    .badge--rare-both {{ background: #ae7d00; }}
    .badge--rare-unknown {{ background: #7f5ab6; }}
    details summary {{ cursor: pointer; color: #2f6d44; font-size: 13px; }}
    form.toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }}
  </style>
</head>
<body>
  <main>
    <h1>Department Runtime Debug</h1>
    <div class="muted">Department-centric runtime view built on top of the existing multi patient auto-runner. In <code>legacy_probabilistic_llm</code>, probability means generated-patient probability, and coverage means spawn hint or scripted preassignment rather than guaranteed final triage destination. <code>blocked_count</code> is blocked attempt count, not unique patient count.</div>
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
        <label>Probability</label><br />
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
