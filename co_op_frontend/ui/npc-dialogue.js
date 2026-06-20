function setText(el, value) {
  if (el) {
    el.textContent = value;
  }
}

function renderOptionButtons(optionsEl, options, selectedOptionIndex) {
  if (!optionsEl) return;
  optionsEl.innerHTML = "";

  for (let index = 0; index < options.length; index += 1) {
    const option = options[index];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "triage-btn npc-dialogue__option";
    button.dataset.optionIndex = String(index);
    button.textContent = option.label || `Option ${index + 1}`;
    if (index === selectedOptionIndex) {
      button.classList.add("is-selected");
      button.setAttribute("aria-pressed", "true");
    } else {
      button.setAttribute("aria-pressed", "false");
    }
    optionsEl.appendChild(button);
  }
}

export function renderNpcDialogue(dialogueUi, snapshot) {
  if (!dialogueUi || !dialogueUi.modal) return;

  const npc = snapshot?.npc || null;
  const node = snapshot?.node || null;
  const options = Array.isArray(snapshot?.options) ? snapshot.options : [];

  setText(dialogueUi.title, npc?.name || "Resident");
  setText(dialogueUi.status, snapshot?.statusText || "A nearby staff member is ready to talk.");
  setText(dialogueUi.roleBadge, npc?.roleLabel || "Staff");
  setText(dialogueUi.roomBadge, npc ? `${npc.roomLabel || npc.roomKind || "Room"} / F${npc.floor}` : "Location pending");
  setText(dialogueUi.prompt, node?.text || "No dialogue is available.");
  setText(dialogueUi.hint, snapshot?.hintText || "Press E to continue.");

  if (dialogueUi.modal) {
    dialogueUi.modal.dataset.dialogueType = node?.type || "idle";
  }

  renderOptionButtons(dialogueUi.options, options, snapshot?.selectedOptionIndex ?? 0);

  if (dialogueUi.advanceBtn) {
    dialogueUi.advanceBtn.textContent = snapshot?.primaryActionLabel || "Continue";
    dialogueUi.advanceBtn.disabled = snapshot?.open ? false : true;
    if (node?.type === "choice" && options.length === 0) {
      dialogueUi.advanceBtn.disabled = true;
    }
  }
}
