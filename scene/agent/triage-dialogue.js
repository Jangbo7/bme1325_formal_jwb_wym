function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function renderDialogueMessages(messagesEl, messages) {
  if (!messagesEl) return;
  messagesEl.innerHTML = messages
    .map(
      (message) => `
        <article class="triage-message triage-message--${message.role}">
          <span class="triage-message__label">${escapeHtml(message.label)}</span>
          <div class="triage-message__body">${escapeHtml(message.body)}</div>
        </article>
      `
    )
    .join("");
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

export function renderDialogueEvidence(evidenceEl, evidence) {
  if (!evidenceEl) return;
  if (!Array.isArray(evidence) || evidence.length === 0) {
    evidenceEl.innerHTML = "";
    return;
  }
  evidenceEl.innerHTML = evidence
    .map((item) => `<span class="triage-evidence-chip">${escapeHtml(item.title || item.id || "Matched rule")}</span>`)
    .join("");
}

export function setDialogueBadges(levelEl, deptEl, level, department, priority) {
  if (!levelEl || !deptEl) return;
  levelEl.className = "triage-badge";
  if (priority === "H") levelEl.classList.add("triage-badge--high");
  else if (priority === "M") levelEl.classList.add("triage-badge--medium");
  else if (priority === "L") levelEl.classList.add("triage-badge--low");
  else levelEl.classList.add("triage-badge--muted");
  levelEl.textContent = level ? `Triage Level ${level}` : "Triage Pending";
  deptEl.textContent = department ? `Department ${department}` : "Department Pending";
}
