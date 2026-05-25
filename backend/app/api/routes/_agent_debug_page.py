from __future__ import annotations

import json

from fastapi.responses import HTMLResponse


def render_agent_debug_page(*, title: str, heading: str, description: str, page_slug: str, api_base: str, presets: list[dict]) -> HTMLResponse:
    preset_json = json.dumps(
        [{"preset_id": item["preset_id"], "label": item["label"], "payload": item["payload"]} for item in presets],
        ensure_ascii=False,
    )
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef3ea;
      --card: #fbfff8;
      --ink: #162019;
      --accent: #315f45;
      --line: #c5d3c5;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background: radial-gradient(circle at top, #f7fff5 0%, var(--bg) 45%, #e1eade 100%);
      color: var(--ink);
    }}
    main {{
      max-width: 1220px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .subtle {{ color: #526356; font-size: 14px; margin-bottom: 16px; }}
    .toolbar, .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 10px 24px rgba(28, 54, 33, 0.08);
      padding: 16px;
      margin-bottom: 16px;
    }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #66766a; }}
    .value {{ margin-top: 4px; font-size: 15px; word-break: break-word; }}
    select, textarea, button, input {{
      font: inherit;
      border-radius: 10px;
      border: 1px solid #90a68f;
      padding: 10px 12px;
      background: #fff;
      color: var(--ink);
    }}
    textarea {{ width: 100%; min-height: 260px; font-family: Consolas, monospace; font-size: 13px; }}
    button {{
      cursor: pointer;
      background: linear-gradient(180deg, #467157 0%, var(--accent) 100%);
      color: #f8fff8;
      border-color: #28523a;
    }}
    button.secondary {{ background: #eef5ef; color: var(--ink); }}
    #status {{ min-height: 18px; color: #2d5b3c; font-size: 14px; margin-bottom: 10px; }}
    #transcript {{ display: grid; gap: 10px; }}
    .turn {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fff;
    }}
    .turn small {{ display: block; color: #6a786f; margin-bottom: 6px; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, monospace;
      font-size: 13px;
    }}
    .chat-row {{ display: flex; gap: 10px; align-items: start; }}
    .chat-row textarea {{ min-height: 96px; flex: 1; }}
  </style>
</head>
<body>
  <main>
    <h1>{heading}</h1>
    <div class="subtle">{description}</div>
    <div class="toolbar">
      <label>
        <span class="label">Preset</span><br />
        <select id="presetSelect"></select>
      </label>
      <button id="loadPresetBtn" class="secondary">Load Preset</button>
      <button id="applyBtn">Apply</button>
      <button id="refreshBtn" class="secondary">Refresh</button>
      <button id="resetBtn" class="secondary">Reset</button>
    </div>
    <div id="status"></div>
    <section class="panel">
      <div class="label">Preload JSON</div>
      <textarea id="preloadJson"></textarea>
    </section>
    <section class="panel">
      <div class="grid">
        <div><div class="label">Debug Session</div><div class="value" id="debugSessionId">-</div></div>
        <div><div class="label">Agent</div><div class="value" id="agentType">-</div></div>
        <div><div class="label">Patient</div><div class="value" id="patientId">-</div></div>
        <div><div class="label">Visit</div><div class="value" id="visitId">-</div></div>
        <div><div class="label">Session</div><div class="value" id="sessionId">-</div></div>
        <div><div class="label">Visit State</div><div class="value" id="visitState">-</div></div>
        <div><div class="label">Lifecycle</div><div class="value" id="patientState">-</div></div>
        <div><div class="label">Last Error</div><div class="value" id="lastError">-</div></div>
      </div>
    </section>
    <section class="panel">
      <div class="label">Chat</div>
      <div id="transcript"></div>
      <div class="chat-row" style="margin-top: 12px;">
        <textarea id="messageInput" placeholder="Type a single test message here..."></textarea>
        <button id="sendBtn">Send</button>
      </div>
    </section>
    <section class="panel">
      <div class="label">Trace</div>
      <pre id="traceBlock">No trace yet.</pre>
    </section>
  </main>
  <script>
    const PRESETS = {preset_json};
    const apiBase = "{api_base}";
    const statusEl = document.getElementById("status");
    const presetSelect = document.getElementById("presetSelect");
    const preloadJsonEl = document.getElementById("preloadJson");
    const traceBlock = document.getElementById("traceBlock");
    const transcriptEl = document.getElementById("transcript");
    const fields = {{
      debugSessionId: document.getElementById("debugSessionId"),
      agentType: document.getElementById("agentType"),
      patientId: document.getElementById("patientId"),
      visitId: document.getElementById("visitId"),
      sessionId: document.getElementById("sessionId"),
      visitState: document.getElementById("visitState"),
      patientState: document.getElementById("patientState"),
      lastError: document.getElementById("lastError"),
    }};

    function nextIdempotencyKey() {{
      if (window.crypto && typeof window.crypto.randomUUID === "function") {{
        return window.crypto.randomUUID();
      }}
      return "{page_slug}-" + Date.now() + "-" + Math.random().toString(16).slice(2);
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

    function fillPresetSelect() {{
      presetSelect.innerHTML = PRESETS.map((preset) => `<option value="${{preset.preset_id}}">${{preset.label}}</option>`).join("");
      if (PRESETS.length > 0) {{
        preloadJsonEl.value = JSON.stringify(PRESETS[0].payload, null, 2);
      }}
    }}

    function loadSelectedPreset() {{
      const preset = PRESETS.find((item) => item.preset_id === presetSelect.value);
      if (!preset) return;
      preloadJsonEl.value = JSON.stringify(preset.payload, null, 2);
    }}

    function renderTranscript(snapshot) {{
      if (!snapshot || !snapshot.transcript || snapshot.transcript.length === 0) {{
        transcriptEl.innerHTML = "<div class='value'>No transcript yet.</div>";
        return;
      }}
      transcriptEl.innerHTML = snapshot.transcript.map((turn) => `
        <div class="turn">
          <small>${{turn.role}} | ${{turn.timestamp || "-"}}</small>
          <div>${{turn.content}}</div>
        </div>
      `).join("");
    }}

    function renderSnapshot(snapshot) {{
      if (!snapshot) {{
        Object.values(fields).forEach((node) => node.textContent = "-");
        renderTranscript(null);
        traceBlock.textContent = "No trace yet.";
        return;
      }}
      fields.debugSessionId.textContent = snapshot.debug_session_id || "-";
      fields.agentType.textContent = snapshot.agent_type || "-";
      fields.patientId.textContent = snapshot.patient_id || "-";
      fields.visitId.textContent = snapshot.visit_id || "-";
      fields.sessionId.textContent = snapshot.session_id || "-";
      fields.visitState.textContent = snapshot.visit_state || "-";
      fields.patientState.textContent = snapshot.patient_lifecycle_state || "-";
      fields.lastError.textContent = snapshot.last_error || "-";
      renderTranscript(snapshot);
      traceBlock.textContent = JSON.stringify({{
        preload_summary: snapshot.preload_summary,
        latest_reply: snapshot.latest_reply,
        trace: snapshot.trace,
        medical_record_summary: snapshot.medical_record_summary,
      }}, null, 2);
    }}

    async function refresh(showStatus = false) {{
      try {{
        const snapshot = await api(`${{apiBase}}/snapshot`);
        renderSnapshot(snapshot);
        if (showStatus) statusEl.textContent = "Snapshot refreshed.";
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }}

    document.getElementById("loadPresetBtn").addEventListener("click", loadSelectedPreset);
    document.getElementById("applyBtn").addEventListener("click", async () => {{
      try {{
        const payload = JSON.parse(preloadJsonEl.value || "{{}}");
        const data = await api(`${{apiBase}}/preload`, "POST", {{
          preset_id: presetSelect.value || null,
          payload,
        }});
        statusEl.textContent = "Preload applied.";
        renderSnapshot(data);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});
    document.getElementById("sendBtn").addEventListener("click", async () => {{
      try {{
        const message = document.getElementById("messageInput").value;
        const data = await api(`${{apiBase}}/message`, "POST", {{ message }});
        statusEl.textContent = "Message sent.";
        renderSnapshot(data);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});
    document.getElementById("refreshBtn").addEventListener("click", () => refresh(true));
    document.getElementById("resetBtn").addEventListener("click", async () => {{
      try {{
        await api(`${{apiBase}}/reset`, "POST", {{}});
        statusEl.textContent = "Debug session reset.";
        renderSnapshot(null);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});

    fillPresetSelect();
    setInterval(() => refresh(false), 2000);
    refresh(false);
  </script>
</body>
</html>
        """
    )
