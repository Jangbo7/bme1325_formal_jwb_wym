import { fetchRuleCategory, fetchRuleIndex, saveRuleCategory } from "./rule-api.js";

const EMPTY_RULE = {
  id: "",
  name: "New Rule",
  eventId: "NEW_EVENT",
  classification: "",
  trigger: "",
  rooms: [],
  roomsText: "",
  agents: "",
  prechecks: "",
  actions: "",
  successState: "",
  blocking: "",
  visualization: "",
  movement: {
    schema: "patient-move",
    from: "current_room",
    to: "target_room",
    via: [],
    transport: "walking",
    acuity: "routine",
    patientFormDuringMove: "walking",
    finalForm: "walking",
    escortRequired: false,
    escortRoles: [],
    equipment: [],
    pathPolicy: {
      requiresPath: true,
      useElevator: false,
      avoidWalls: true,
      hallwayPreference: "center",
      stopAtDoorBeforeEntering: true,
    },
    resourcePolicy: {
      lockBeforeMove: true,
      releaseSourceOnArrival: true,
      occupyTargetOnArrival: true,
      keepSourceReservedUntilArrival: false,
    },
    failurePolicy: {
      onNoPath: "stay_source",
      onResourceBlocked: "stay_source",
      onEscortUnavailable: "continue_without_escort",
    },
  },
};

const EDITABLE_FIELDS = [
  ["name", "Name", "input"],
  ["eventId", "Event ID", "input"],
  ["classification", "Classification", "input"],
  ["roomsText", "Rooms", "textarea"],
  ["trigger", "Trigger", "textarea"],
  ["agents", "Agents", "textarea"],
  ["prechecks", "Prechecks", "textarea"],
  ["actions", "Actions", "textarea"],
  ["successState", "Success", "textarea"],
  ["blocking", "Blocking", "textarea"],
  ["visualization", "Visualization", "textarea"],
  ["movement", "Movement JSON", "json"],
];

export function createRulesAdmin({
  panel,
  openButton,
  backButton,
  saveButton,
  categoryList,
  ruleList,
  editor,
  status,
}) {
  const state = {
    index: null,
    category: null,
    categoryMeta: null,
    selectedRuleId: null,
    dirty: false,
  };

  openButton.addEventListener("click", () => openRulesAdmin());
  backButton.addEventListener("click", () => closeRulesAdmin());
  saveButton.addEventListener("click", () => saveCurrentCategory());
  categoryList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-rule-category]");
    if (!button) return;
    selectCategory(button.dataset.ruleCategory);
  });
  ruleList.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-rule-add]");
    if (addButton) {
      addRule();
      return;
    }
    const deleteButton = event.target.closest("[data-rule-delete]");
    if (deleteButton) {
      deleteRule(deleteButton.dataset.ruleDelete);
      return;
    }
    const button = event.target.closest("[data-rule-id]");
    if (!button) return;
    state.selectedRuleId = button.dataset.ruleId;
    renderRules();
  });
  editor.addEventListener("input", (event) => {
    const field = event.target?.dataset?.ruleField;
    if (!field) return;
    const rule = selectedRule();
    if (!rule) return;
    if (field === "movement") {
      rule.movementDraft = event.target.value;
      try {
        rule.movement = JSON.parse(event.target.value);
        rule.movementDraftInvalid = false;
        event.target.classList.remove("is-invalid");
      } catch {
        rule.movementDraftInvalid = true;
        event.target.classList.add("is-invalid");
        state.dirty = true;
        setStatus("Movement JSON invalid. Fix it before saving.");
        return;
      }
      state.dirty = true;
      renderStatus();
      return;
    }
    rule[field] = event.target.value;
    if (field === "roomsText") rule.rooms = parseRoomIds(event.target.value);
    state.dirty = true;
    renderStatus();
  });

  return {
    open: openRulesAdmin,
    close: closeRulesAdmin,
  };

  async function openRulesAdmin() {
    panel.hidden = false;
    setStatus("Loading event rules...");
    state.index = await fetchRuleIndex();
    const first = state.index.categories[0];
    await loadCategory(first.id);
    renderAll();
  }

  function closeRulesAdmin() {
    panel.hidden = true;
  }

  async function selectCategory(categoryId) {
    if (state.dirty) {
      const shouldSwitch = window.confirm("Current rule changes are not saved. Switch category anyway?");
      if (!shouldSwitch) return;
    }
    await loadCategory(categoryId);
    renderAll();
  }

  async function loadCategory(categoryId) {
    const meta = state.index.categories.find((item) => item.id === categoryId);
    if (!meta) return;
    state.categoryMeta = meta;
    state.category = await fetchRuleCategory(meta.file);
    state.selectedRuleId = state.category.rules[0]?.id || null;
    state.dirty = false;
  }

  async function saveCurrentCategory() {
    if (!state.category || !state.categoryMeta) return;
    saveButton.disabled = true;
    try {
      normalizeRulesBeforeSave();
      state.category.updatedAt = new Date().toISOString();
      const result = await saveRuleCategory(state.categoryMeta.file, state.category);
      state.dirty = false;
      setStatus(result.mode === "file" ? "Saved to event-rules JSON" : "Saved in browser storage");
      renderAll();
    } catch (error) {
      setStatus(error.message);
    } finally {
      saveButton.disabled = false;
    }
  }

  function addRule() {
    if (!state.category) return;
    const nextId = uniqueRuleId(state.category.id, state.category.rules);
    const rule = {
      ...structuredClone(EMPTY_RULE),
      id: nextId,
      eventId: nextId.toUpperCase().replaceAll("-", "_"),
      sourceFile: state.category.sourceFile,
    };
    state.category.rules.push(rule);
    state.selectedRuleId = rule.id;
    state.dirty = true;
    renderAll();
  }

  function deleteRule(ruleId) {
    if (!state.category) return;
    state.category.rules = state.category.rules.filter((rule) => rule.id !== ruleId);
    state.selectedRuleId = state.category.rules[0]?.id || null;
    state.dirty = true;
    renderAll();
  }

  function renderAll() {
    renderCategories();
    renderRules();
    renderStatus();
  }

  function renderCategories() {
    categoryList.innerHTML = state.index.categories.map((category) => `
      <button class="rules-admin__category${category.id === state.categoryMeta?.id ? " is-active" : ""}" type="button" data-rule-category="${escapeHtml(category.id)}">
        <span>${escapeHtml(category.label)}</span>
        <strong>${category.ruleCount} rules</strong>
      </button>
    `).join("");
  }

  function renderRules() {
    const rules = state.category?.rules || [];
    ruleList.innerHTML = `
      <button class="rules-admin__add-rule" type="button" data-rule-add="true">Add Rule</button>
      ${rules.map((rule) => `
        <article class="rules-admin__rule${rule.id === state.selectedRuleId ? " is-active" : ""}" data-rule-id="${escapeHtml(rule.id)}">
          <button class="rules-admin__rule-main" type="button" data-rule-id="${escapeHtml(rule.id)}">
            <span>${escapeHtml(rule.eventId || rule.id)}</span>
            <strong>${escapeHtml(rule.name || "Untitled Rule")}</strong>
          </button>
          <button class="rules-admin__delete" type="button" data-rule-delete="${escapeHtml(rule.id)}" aria-label="Delete ${escapeHtml(rule.name || rule.id)}">×</button>
        </article>
      `).join("")}
    `;
    renderEditor();
  }

  function renderEditor() {
    const rule = selectedRule();
    if (!rule) {
      editor.innerHTML = `<div class="rules-admin__empty">Select or add a rule.</div>`;
      return;
    }

    editor.innerHTML = EDITABLE_FIELDS.map(([field, label, type]) => {
      const value = editableValue(rule, field);
      if (type === "input") {
        return `
          <label class="rules-admin__field">
            <span>${label}</span>
            <input data-rule-field="${field}" value="${escapeAttr(value)}" />
          </label>
        `;
      }
      if (type === "json") {
        return `
          <label class="rules-admin__field rules-admin__field--json">
            <span>${label}</span>
            <textarea data-rule-field="${field}" spellcheck="false">${escapeHtml(value)}</textarea>
          </label>
        `;
      }
      return `
        <label class="rules-admin__field">
          <span>${label}</span>
          <textarea data-rule-field="${field}">${escapeHtml(value)}</textarea>
        </label>
      `;
    }).join("");
  }

  function renderStatus() {
    if (!state.category) return;
    setStatus(`${state.category.label} · ${state.category.rules.length} rules${state.dirty ? " · unsaved" : ""}`);
  }

  function selectedRule() {
    return state.category?.rules?.find((rule) => rule.id === state.selectedRuleId) || null;
  }

  function normalizeRulesBeforeSave() {
    state.category.rules.forEach((rule) => {
      rule.rooms = parseRoomIds(rule.roomsText || "");
      rule.id = rule.id || uniqueRuleId(state.category.id, state.category.rules);
      rule.eventId = rule.eventId || rule.id.toUpperCase().replaceAll("-", "_");
      if (rule.movementDraftInvalid) {
        throw new Error(`${rule.eventId || rule.id} has invalid Movement JSON.`);
      }
      if (rule.movementDraft) {
        rule.movement = JSON.parse(rule.movementDraft);
      }
      rule.movement = rule.movement || structuredClone(EMPTY_RULE.movement);
      delete rule.movementDraft;
      delete rule.movementDraftInvalid;
    });
  }
}

function editableValue(rule, field) {
  if (field === "movement") {
    return rule.movementDraft ?? JSON.stringify(rule.movement || EMPTY_RULE.movement, null, 2);
  }
  return rule[field] || "";
}

function parseRoomIds(value) {
  return [...new Set((value.match(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g) || []).filter(Boolean))];
}

function uniqueRuleId(categoryId, rules) {
  const used = new Set(rules.map((rule) => rule.id));
  let index = rules.length + 1;
  let id = `${categoryId}-rule-${index}`;
  while (used.has(id)) {
    index += 1;
    id = `${categoryId}-rule-${index}`;
  }
  return id;
}

function setStatus(text) {
  const element = document.getElementById("rulesAdminStatus");
  if (element) element.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}
