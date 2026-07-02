from __future__ import annotations

import json

from fastapi.responses import HTMLResponse


def render_agent_debug_page(
    *,
    title: str,
    heading: str,
    description: str,
    page_slug: str,
    api_base: str,
    presets: list[dict],
    agent_options: list[dict] | None = None,
    selected_agent_type: str | None = None,
    presets_by_agent: dict[str, list[dict]] | None = None,
) -> HTMLResponse:
    grouped_presets = presets_by_agent or {
        selected_agent_type or "__default__": [
            {"preset_id": item["preset_id"], "label": item["label"], "payload": item["payload"]}
            for item in presets
        ]
    }
    preset_json = json.dumps(grouped_presets, ensure_ascii=False)
    agent_options_json = json.dumps(agent_options or [], ensure_ascii=False)
    initial_agent_json = json.dumps(selected_agent_type or "", ensure_ascii=False)
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
      overflow-anchor: none;
    }}
    main {{
      max-width: 1220px;
      margin: 0 auto;
      padding: 24px 16px 48px;
      overflow-anchor: none;
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
      overflow-anchor: none;
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
    #transcript {{
      display: grid;
      gap: 10px;
      max-height: 520px;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-right: 4px;
    }}
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
      <label id="agentTypeField" style="display:none;">
        <span class="label">Agent</span><br />
        <select id="agentTypeSelect"></select>
      </label>
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
        <div><div class="label">Department</div><div class="value" id="departmentId">-</div></div>
        <div><div class="label">Agent Label</div><div class="value" id="agentLabel">-</div></div>
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
    const PRESETS_BY_AGENT = {preset_json};
    const AGENT_OPTIONS = {agent_options_json};
    const INITIAL_AGENT_TYPE = {initial_agent_json};
    const apiBase = "{api_base}";
    const statusEl = document.getElementById("status");
    const agentTypeField = document.getElementById("agentTypeField");
    const agentTypeSelect = document.getElementById("agentTypeSelect");
    const presetSelect = document.getElementById("presetSelect");
    const preloadJsonEl = document.getElementById("preloadJson");
    const traceBlock = document.getElementById("traceBlock");
    const transcriptEl = document.getElementById("transcript");
    const transcriptState = {{
      visible: [],
      target: [],
      timers: [],
      animating: false,
    }};
    let autoAdvanceTimer = null;
    let autoAdvanceInFlight = false;
    let latestTraceText = "";
    const fields = {{
      debugSessionId: document.getElementById("debugSessionId"),
      agentType: document.getElementById("agentType"),
      departmentId: document.getElementById("departmentId"),
      agentLabel: document.getElementById("agentLabel"),
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

    function currentAgentType() {{
      if (!AGENT_OPTIONS.length) {{
        return INITIAL_AGENT_TYPE || Object.keys(PRESETS_BY_AGENT)[0] || "";
      }}
      return agentTypeSelect.value || INITIAL_AGENT_TYPE || AGENT_OPTIONS[0]?.agent_type || "";
    }}

    function currentPresets() {{
      return PRESETS_BY_AGENT[currentAgentType()] || [];
    }}

    function fillAgentSelect() {{
      if (!AGENT_OPTIONS.length) {{
        return;
      }}
      agentTypeField.style.display = "";
      agentTypeSelect.innerHTML = AGENT_OPTIONS.map((agent) => `<option value="${{agent.agent_type}}">${{agent.label}}</option>`).join("");
      const preferred = INITIAL_AGENT_TYPE || AGENT_OPTIONS[0]?.agent_type || "";
      if (preferred) {{
        agentTypeSelect.value = preferred;
      }}
      agentTypeSelect.addEventListener("change", () => {{
        fillPresetSelect();
        refresh(false);
      }});
    }}

    function fillPresetSelect() {{
      const presets = currentPresets();
      presetSelect.innerHTML = presets.map((preset) => `<option value="${{preset.preset_id}}">${{preset.label}}</option>`).join("");
      if (presets.length > 0) {{
        preloadJsonEl.value = JSON.stringify(presets[0].payload, null, 2);
      }} else {{
        preloadJsonEl.value = "{{}}";
      }}
    }}

    function loadSelectedPreset() {{
      const preset = currentPresets().find((item) => item.preset_id === presetSelect.value);
      if (!preset) return;
      preloadJsonEl.value = JSON.stringify(preset.payload, null, 2);
    }}

    function clearAutoAdvanceTimer() {{
      if (autoAdvanceTimer !== null) {{
        window.clearTimeout(autoAdvanceTimer);
        autoAdvanceTimer = null;
      }}
    }}

    function clearTranscriptTimers() {{
      transcriptState.timers.forEach((timerId) => window.clearTimeout(timerId));
      transcriptState.timers = [];
      transcriptState.animating = false;
    }}

    function transcriptKey(turn) {{
      return [
        turn.role || "",
        turn.timestamp || "",
        turn.content || "",
        turn.metadata?.message_type || "",
      ].join("|");
    }}

    function isTranscriptPrefix(prefix, full) {{
      if (prefix.length > full.length) return false;
      return prefix.every((turn, index) => transcriptKey(turn) === transcriptKey(full[index]));
    }}

    function isSameTranscript(left, right) {{
      return left.length === right.length && isTranscriptPrefix(left, right);
    }}

    function paintTranscript(turns, scrollToBottom = false) {{
      if (!turns || turns.length === 0) {{
        transcriptEl.innerHTML = "<div class='value'>No transcript yet.</div>";
        return;
      }}
      transcriptEl.innerHTML = turns.map((turn) => `
        <div class="turn">
          <small>${{turn.role}} | ${{turn.timestamp || "-"}}</small>
          <div>${{turn.content}}</div>
        </div>
      `).join("");
      if (scrollToBottom) {{
        transcriptEl.scrollTop = transcriptEl.scrollHeight;
      }}
    }}

    function renderTranscript(snapshot, animateNew = false) {{
      const fullTranscript = snapshot?.transcript || [];
      if (!snapshot || !snapshot.transcript || snapshot.transcript.length === 0) {{
        clearTranscriptTimers();
        transcriptState.visible = [];
        transcriptState.target = [];
        transcriptEl.innerHTML = "<div class='value'>No transcript yet.</div>";
        return;
      }}
      if (transcriptState.animating && isTranscriptPrefix(transcriptState.visible, fullTranscript)) {{
        return;
      }}
      if (!animateNew && isSameTranscript(transcriptState.visible, fullTranscript)) {{
        return;
      }}
      if (!animateNew || transcriptState.visible.length === 0 || !isTranscriptPrefix(transcriptState.visible, fullTranscript)) {{
        clearTranscriptTimers();
        transcriptState.visible = fullTranscript.slice();
        transcriptState.target = fullTranscript.slice();
        paintTranscript(transcriptState.visible, false);
        return;
      }}
      const newTurns = fullTranscript.slice(transcriptState.visible.length);
      if (newTurns.length <= 1) {{
        clearTranscriptTimers();
        transcriptState.visible = fullTranscript.slice();
        transcriptState.target = fullTranscript.slice();
        paintTranscript(transcriptState.visible, true);
        return;
      }}
      clearTranscriptTimers();
      transcriptState.animating = true;
      transcriptState.target = fullTranscript.slice();
      const baseTurns = transcriptState.visible.slice();
      newTurns.forEach((turn, index) => {{
        const timerId = window.setTimeout(() => {{
          transcriptState.visible = baseTurns.concat(newTurns.slice(0, index + 1));
          paintTranscript(transcriptState.visible, true);
          if (index === newTurns.length - 1) {{
            transcriptState.animating = false;
            transcriptState.timers = [];
          }}
        }}, index * 900);
        transcriptState.timers.push(timerId);
      }});
    }}

    function latestTranscriptTurn(snapshot) {{
      const turns = snapshot?.transcript || [];
      return turns.length ? turns[turns.length - 1] : null;
    }}

    function shouldAutoAdvance(snapshot) {{
      const latest = latestTranscriptTurn(snapshot);
      return Boolean(latest && latest.role === "assistant" && latest.metadata?.pending_auto_continue);
    }}

    function scheduleAutoAdvance(snapshot) {{
      clearAutoAdvanceTimer();
      if (!shouldAutoAdvance(snapshot)) return;
      if (autoAdvanceInFlight) return;
      autoAdvanceTimer = window.setTimeout(async () => {{
        autoAdvanceTimer = null;
        autoAdvanceInFlight = true;
        try {{
          const agent = currentAgentType() || "";
          const query = agent ? `?agent_type=${{encodeURIComponent(agent)}}` : "";
          const data = await api(`${{apiBase}}/advance${{query}}`, "POST", {{ agent_type: agent || null }});
          renderSnapshot(data, {{ animateTranscript: true }});
        }} catch (error) {{
          statusEl.textContent = error.message;
        }} finally {{
          autoAdvanceInFlight = false;
        }}
      }}, 1000);
    }}

    function renderSnapshot(snapshot, options = {{}}) {{
      if (!snapshot) {{
        clearAutoAdvanceTimer();
        clearTranscriptTimers();
        transcriptState.visible = [];
        transcriptState.target = [];
        Object.values(fields).forEach((node) => node.textContent = "-");
        renderTranscript(null);
        traceBlock.textContent = "No trace yet.";
        return;
      }}
      fields.debugSessionId.textContent = snapshot.debug_session_id || "-";
      fields.agentType.textContent = snapshot.agent_type || "-";
      fields.departmentId.textContent = snapshot.department_id || "-";
      fields.agentLabel.textContent = snapshot.agent_label || "-";
      fields.patientId.textContent = snapshot.patient_id || "-";
      fields.visitId.textContent = snapshot.visit_id || "-";
      fields.sessionId.textContent = snapshot.session_id || "-";
      fields.visitState.textContent = snapshot.visit_state || "-";
      fields.patientState.textContent = snapshot.patient_lifecycle_state || "-";
      fields.lastError.textContent = snapshot.last_error || "-";
      renderTranscript(snapshot, Boolean(options.animateTranscript));
      const traceText = JSON.stringify({{
        preload_summary: snapshot.preload_summary,
        latest_reply: snapshot.latest_reply,
        trace: snapshot.trace,
        medical_record_summary: snapshot.medical_record_summary,
      }}, null, 2);
      if (traceText !== latestTraceText) {{
        latestTraceText = traceText;
        traceBlock.textContent = traceText;
      }}
      scheduleAutoAdvance(snapshot);
      if (options.preservePageScroll) {{
        window.scrollTo({{ top: options.preservePageScroll.top, left: options.preservePageScroll.left, behavior: "auto" }});
      }}
    }}

    async function refresh(showStatus = false) {{
      try {{
        const query = currentAgentType() ? `?agent_type=${{encodeURIComponent(currentAgentType())}}` : "";
        const snapshot = await api(`${{apiBase}}/snapshot${{query}}`);
        const pageScroll = showStatus ? null : {{ top: window.scrollY, left: window.scrollX }};
        renderSnapshot(snapshot, pageScroll ? {{ preservePageScroll: pageScroll }} : {{}});
        if (showStatus) statusEl.textContent = "Snapshot refreshed.";
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }}

    document.getElementById("loadPresetBtn").addEventListener("click", loadSelectedPreset);
    presetSelect.addEventListener("change", loadSelectedPreset);
    document.getElementById("applyBtn").addEventListener("click", async () => {{
      try {{
        const payload = JSON.parse(preloadJsonEl.value || "{{}}");
        const data = await api(`${{apiBase}}/preload`, "POST", {{
          agent_type: currentAgentType() || null,
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
        const data = await api(`${{apiBase}}/message`, "POST", {{ agent_type: currentAgentType() || null, message }});
        statusEl.textContent = "Message sent.";
        renderSnapshot(data, {{ animateTranscript: true }});
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});
    document.getElementById("refreshBtn").addEventListener("click", () => refresh(true));
    document.getElementById("resetBtn").addEventListener("click", async () => {{
      try {{
        await api(`${{apiBase}}/reset`, "POST", {{ agent_type: currentAgentType() || null }});
        statusEl.textContent = "Debug session reset.";
        clearAutoAdvanceTimer();
        renderSnapshot(null);
      }} catch (error) {{
        statusEl.textContent = error.message;
      }}
    }});

    fillAgentSelect();
    fillPresetSelect();
    setInterval(() => refresh(false), 2000);
    refresh(false);
  </script>
</body>
</html>
        """
    )
