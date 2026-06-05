from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.agents.npc_patient.profile import list_profiles
from app.schemas.npc_debug import NpcDebugSpawnRequest


router = APIRouter()


def _controller(request: Request):
    return request.app.state.container["npc_patient_debug_controller"]


@router.get("/npc-debug", response_class=HTMLResponse, include_in_schema=False)
def npc_debug_page():
    profiles = [
        {
            "id": profile.profile_id,
            "label": f"{profile.name} ({profile.profile_id})",
        }
        for profile in list_profiles()
    ]
    profile_options = "\n".join(
        f'<option value="{item["id"]}">{item["label"]}</option>'
        for item in profiles
    )
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>NPC Debug</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1e8;
      --card: #fffaf0;
      --ink: #1d1b16;
      --accent: #7a3b1f;
      --line: #d6c9b5;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background: radial-gradient(circle at top, #fff5df 0%, var(--bg) 45%, #ece5d7 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 980px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1 {{
      margin: 0 0 16px;
      font-size: 32px;
      letter-spacing: 0.02em;
    }}
    .toolbar, .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 10px 24px rgba(56, 37, 20, 0.08);
      padding: 16px;
      margin-bottom: 16px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }}
    select, button {{
      font: inherit;
      border-radius: 10px;
      border: 1px solid #b9a488;
      padding: 10px 12px;
      background: #fff;
      color: var(--ink);
    }}
    button {{
      cursor: pointer;
      background: linear-gradient(180deg, #8d4a26 0%, var(--accent) 100%);
      color: #fffaf2;
      border-color: #70331a;
    }}
    button.secondary {{
      background: #f5ecde;
      color: var(--ink);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .meta {{
      font-size: 14px;
      line-height: 1.55;
    }}
    .label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #6b6155;
    }}
    .value {{
      margin-top: 4px;
      font-size: 16px;
      word-break: break-word;
    }}
    #status {{
      min-height: 18px;
      font-size: 14px;
      color: #6b3321;
    }}
    #dialogueBox {{
      display: none;
      border-top: 1px dashed var(--line);
      margin-top: 12px;
      padding-top: 12px;
    }}
    #transcript {{
      display: grid;
      gap: 10px;
    }}
    .turn {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }}
    .turn small {{
      display: block;
      color: #75685a;
      margin-bottom: 6px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>NPC Patient Debug</h1>
    <div class="toolbar">
      <label>
        <span class="label">Profile</span><br />
        <select id="profileSelect">{profile_options}</select>
      </label>
      <button id="spawnBtn">Spawn</button>
      <button id="stepBtn">Step</button>
      <button id="refreshBtn" class="secondary">Refresh</button>
      <button id="resetBtn" class="secondary">Reset</button>
      <a href="/patient-agent-debug" style="font: inherit; border-radius: 10px; border: 1px solid #b9a488; padding: 10px 12px; background: #f5ecde; color: var(--ink); text-decoration: none;">Open Intelligent Agent Debug</a>
    </div>
    <div id="status"></div>
    <section class="panel">
      <div class="grid meta">
        <div><div class="label">NPC</div><div class="value" id="npcId">-</div></div>
        <div><div class="label">Profile</div><div class="value" id="profileId">-</div></div>
        <div><div class="label">Patient</div><div class="value" id="patientId">-</div></div>
        <div><div class="label">Encounter</div><div class="value" id="encounterId">-</div></div>
        <div><div class="label">Visit State</div><div class="value" id="visitState">-</div></div>
        <div><div class="label">Patient State</div><div class="value" id="patientState">-</div></div>
        <div><div class="label">Phase</div><div class="value" id="phase">-</div></div>
        <div><div class="label">Status</div><div class="value" id="npcStatus">-</div></div>
        <div><div class="label">Counterparty</div><div class="value" id="counterparty">-</div></div>
        <div><div class="label">Last Action</div><div class="value" id="lastAction">-</div></div>
        <div><div class="label">Last Error</div><div class="value" id="lastError">-</div></div>
        <div><div class="label">Steps</div><div class="value" id="stepCount">0</div></div>
      </div>
      <div id="dialogueBox">
        <div class="label">Current Dialogue</div>
        <div class="value" id="dialogueSpeaker">-</div>
        <div class="value" id="dialogueMessage">-</div>
      </div>
    </section>
    <section class="panel">
      <div class="label">Transcript</div>
      <div id="transcript"></div>
    </section>
    <section class="panel">
      <div class="label">Medical Record</div>
      <div class="grid meta">
        <div><div class="label">Record ID</div><div class="value" id="mrRecordId">-</div></div>
        <div><div class="label">Entry Count</div><div class="value" id="mrEntryCount">0</div></div>
        <div><div class="label">Latest Type</div><div class="value" id="mrLatestType">-</div></div>
        <div><div class="label">Latest Phase</div><div class="value" id="mrLatestPhase">-</div></div>
        <div><div class="label">Updated At</div><div class="value" id="mrUpdatedAt">-</div></div>
      </div>
      <div id="medicalRecordEntries"></div>
    </section>
  </main>
  <script>
    const statusEl = document.getElementById("status");
    const fields = {{
      npcId: document.getElementById("npcId"),
      profileId: document.getElementById("profileId"),
      patientId: document.getElementById("patientId"),
      encounterId: document.getElementById("encounterId"),
      visitState: document.getElementById("visitState"),
      patientState: document.getElementById("patientState"),
      phase: document.getElementById("phase"),
      npcStatus: document.getElementById("npcStatus"),
      counterparty: document.getElementById("counterparty"),
      lastAction: document.getElementById("lastAction"),
      lastError: document.getElementById("lastError"),
      stepCount: document.getElementById("stepCount"),
      dialogueBox: document.getElementById("dialogueBox"),
      dialogueSpeaker: document.getElementById("dialogueSpeaker"),
      dialogueMessage: document.getElementById("dialogueMessage"),
      transcript: document.getElementById("transcript"),
      mrRecordId: document.getElementById("mrRecordId"),
      mrEntryCount: document.getElementById("mrEntryCount"),
      mrLatestType: document.getElementById("mrLatestType"),
      mrLatestPhase: document.getElementById("mrLatestPhase"),
      mrUpdatedAt: document.getElementById("mrUpdatedAt"),
      medicalRecordEntries: document.getElementById("medicalRecordEntries"),
      profileSelect: document.getElementById("profileSelect"),
    }};

    function nextIdempotencyKey() {{
      if (window.crypto && typeof window.crypto.randomUUID === "function") {{
        return window.crypto.randomUUID();
      }}
      return "npc-debug-" + Date.now() + "-" + Math.random().toString(16).slice(2);
    }}

    async function api(path, method = "GET", body = null) {{
      const headers = {{}};
      if (method !== "GET") {{
        headers["Content-Type"] = "application/json";
        headers["Idempotency-Key"] = nextIdempotencyKey();
      }}
      const response = await fetch(path, {{
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
      }});
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {{
        const message = payload.error?.message || payload.error?.details || response.statusText;
        throw new Error(typeof message === "string" ? message : JSON.stringify(message));
      }}
      return payload.data;
    }}

    function renderSnapshot(snapshot) {{
      if (!snapshot) {{
        Object.values(fields).forEach((node) => {{
          if (node && node.classList && node.id !== "profileSelect") {{
            node.textContent = "";
          }}
        }});
        fields.dialogueBox.style.display = "none";
        fields.transcript.innerHTML = "<div class='value'>No active NPC.</div>";
        fields.mrRecordId.textContent = "-";
        fields.mrEntryCount.textContent = "0";
        fields.mrLatestType.textContent = "-";
        fields.mrLatestPhase.textContent = "-";
        fields.mrUpdatedAt.textContent = "-";
        fields.medicalRecordEntries.innerHTML = "<div class='value'>No record yet.</div>";
        return;
      }}

      fields.npcId.textContent = snapshot.npc_id || "-";
      fields.profileId.textContent = snapshot.profile_id || "-";
      fields.patientId.textContent = snapshot.patient_id || "-";
      fields.encounterId.textContent = snapshot.encounter_id || "-";
      fields.visitState.textContent = snapshot.visit_state || "-";
      fields.patientState.textContent = snapshot.patient_lifecycle_state || "-";
      fields.phase.textContent = snapshot.phase || "-";
      fields.npcStatus.textContent = snapshot.status || "-";
      fields.counterparty.textContent = snapshot.current_counterparty || "-";
      fields.lastAction.textContent = snapshot.last_action || "-";
      fields.lastError.textContent = snapshot.last_error || "-";
      fields.stepCount.textContent = String(snapshot.step_count || 0);
      fields.mrRecordId.textContent = snapshot.medical_record_summary?.record_id || "-";
      fields.mrEntryCount.textContent = String(snapshot.medical_record_summary?.entry_count || 0);
      fields.mrLatestType.textContent = snapshot.medical_record_summary?.latest_entry_type || "-";
      fields.mrLatestPhase.textContent = snapshot.medical_record_summary?.latest_phase || "-";
      fields.mrUpdatedAt.textContent = snapshot.medical_record_summary?.updated_at || "-";

      if (snapshot.current_dialogue) {{
        fields.dialogueBox.style.display = "block";
        fields.dialogueSpeaker.textContent = snapshot.current_dialogue.speaker + " (" + snapshot.current_dialogue.direction + ")";
        fields.dialogueMessage.textContent = snapshot.current_dialogue.message || "-";
      }} else {{
        fields.dialogueBox.style.display = "none";
      }}

      if (!snapshot.transcript || snapshot.transcript.length === 0) {{
        fields.transcript.innerHTML = "<div class='value'>No dialogue yet.</div>";
        return;
      }}

      fields.transcript.innerHTML = snapshot.transcript
        .map((turn) => `
          <div class="turn">
            <small>${{turn.turn_id}} | ${{turn.phase}} | ${{turn.counterparty}} | ${{turn.timestamp}}</small>
            <div><strong>${{turn.speaker}}</strong></div>
            <div>${{turn.message}}</div>
          </div>
        `)
        .join("");
    }}

    function renderMedicalRecordTimeline(data) {{
      if (!data || !data.entries || data.entries.length === 0) {{
        fields.medicalRecordEntries.innerHTML = "<div class='value'>No record entries yet.</div>";
        return;
      }}
      fields.medicalRecordEntries.innerHTML = data.entries
        .map((entry) => `
          <div class="turn">
            <small>#${{entry.entry_id}} | ${{entry.phase}} | ${{entry.entry_type}} | ${{entry.created_at}}</small>
            <div><strong>${{entry.title}}</strong></div>
            <div>${{entry.content_text}}</div>
          </div>
        `)
        .join("");
    }}

    async function refreshSnapshot(showStatus = false) {{
      try {{
        const snapshot = await api("/api/v1/npc-debug/snapshot");
        renderSnapshot(snapshot);
        const timeline = await api("/api/v1/npc-debug/medical-record");
        renderMedicalRecordTimeline(timeline);
        if (showStatus) {{
          statusEl.textContent = "Snapshot refreshed.";
        }}
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }}

    document.getElementById("spawnBtn").addEventListener("click", async () => {{
      try {{
        const snapshot = await api("/api/v1/npc-debug/spawn", "POST", {{
          profile_id: fields.profileSelect.value,
        }});
        statusEl.textContent = "NPC spawned.";
        renderSnapshot(snapshot);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});

    document.getElementById("stepBtn").addEventListener("click", async () => {{
      try {{
        const snapshot = await api("/api/v1/npc-debug/step", "POST", {{}});
        statusEl.textContent = "Step executed.";
        renderSnapshot(snapshot);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});

    document.getElementById("refreshBtn").addEventListener("click", () => refreshSnapshot(true));

    document.getElementById("resetBtn").addEventListener("click", async () => {{
      try {{
        await api("/api/v1/npc-debug/reset", "POST", {{}});
        statusEl.textContent = "Controller reset.";
        renderSnapshot(null);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});

    setInterval(() => refreshSnapshot(false), 2000);
    refreshSnapshot(false);
  </script>
</body>
</html>
        """
    )


@router.post("/api/v1/npc-debug/spawn")
def spawn_npc_debug(body: NpcDebugSpawnRequest, request: Request):
    controller = _controller(request)
    try:
        snapshot = controller.spawn(body.profile_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.post("/api/v1/npc-debug/step")
def step_npc_debug(request: Request):
    controller = _controller(request)
    try:
        snapshot = controller.step()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "data": snapshot.model_dump()}


@router.get("/api/v1/npc-debug/snapshot")
def get_npc_debug_snapshot(request: Request):
    snapshot = _controller(request).get_snapshot()
    return {"ok": True, "data": snapshot.model_dump() if snapshot else None}


@router.post("/api/v1/npc-debug/reset")
def reset_npc_debug(request: Request):
    _controller(request).reset()
    return {"ok": True, "data": None}


@router.get("/api/v1/npc-debug/medical-record")
def get_npc_debug_medical_record(request: Request):
    timeline = _controller(request).get_medical_record()
    return {"ok": True, "data": timeline}
