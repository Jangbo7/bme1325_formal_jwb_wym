import { fixedNpcDefinitions, fixedNpcDialogueBooks, roomKindLabels } from "./fixed-data.js";

function createFallbackDialogueBook(name = "Resident") {
  return {
    startNodeId: "intro",
    nodes: {
      intro: {
        type: "line",
        text: `${name} gives you a quick nod.`,
        next: "choice",
      },
      choice: {
        type: "choice",
        text: "What would you like to ask?",
        options: [
          { label: "Ask about work", next: "work" },
          { label: "Just chat", next: "chat" },
          { label: "Say goodbye", next: "end" },
        ],
      },
      work: {
        type: "action",
        text: `${name} points at the nearest workstation.`,
        next: "end",
      },
      chat: {
        type: "line",
        text: `${name} keeps the tone light and brief.`,
        next: "end",
      },
      end: {
        type: "end",
        text: `${name} turns back to work.`,
      },
    },
  };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function pointInRect(x, y, rect) {
  return x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h;
}

function getNpcRoom(rooms, definition) {
  const sameKind = rooms.filter((room) => room.kind === definition.roomKind);
  const sameFloor = sameKind.filter((room) => room.floor === definition.floor);
  const pool = sameFloor.length > 0 ? sameFloor : sameKind;
  if (pool.length === 0) return null;
  const index = clamp(definition.roomIndex ?? 0, 0, pool.length - 1);
  return pool[index];
}

function findNearestWalkablePoint(startX, startY, floor, canMoveTo, roomRect) {
  if (!canMoveTo || canMoveTo(startX, startY, floor)) {
    return { x: startX, y: startY };
  }

  for (let radius = 10; radius <= 110; radius += 10) {
    for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 10) {
      const x = startX + Math.cos(angle) * radius;
      const y = startY + Math.sin(angle) * radius;
      if (roomRect && !pointInRect(x, y, roomRect)) continue;
      if (canMoveTo(x, y, floor)) {
        return { x, y };
      }
    }
  }

  if (roomRect) {
    const centerX = roomRect.x + roomRect.w * 0.5;
    const centerY = roomRect.y + roomRect.h * 0.5;
    if (canMoveTo(centerX, centerY, floor)) {
      return { x: centerX, y: centerY };
    }
  }

  return { x: startX, y: startY };
}

function resolveNpcInstance(definition, rooms, roomBounds, canMoveTo) {
  const room = getNpcRoom(rooms, definition);
  if (!room) return null;

  const bounds = roomBounds(room);
  const placement = definition.placement || { x: 0.5, y: 0.5 };
  const targetX = bounds.x + bounds.w * placement.x;
  const targetY = bounds.y + bounds.h * placement.y;
  const safe = findNearestWalkablePoint(targetX, targetY, room.floor, canMoveTo, bounds);

  return {
    kind: "fixed",
    interactable: true,
    id: definition.id,
    name: definition.name,
    roleLabel: definition.roleLabel,
    floor: room.floor,
    roomKind: room.kind,
    roomLabel: roomKindLabels[room.kind] || room.kind,
    roomIndex: definition.roomIndex ?? 0,
    x: safe.x,
    y: safe.y,
    interactionRadius: definition.interactionRadius ?? 68,
    bodyColor: definition.bodyColor || "#7aa2ff",
    headColor: definition.headColor || "#f2d0bf",
    accentColor: definition.accentColor || "#a8c9ff",
    dialogueSetId: definition.dialogueSetId,
  };
}

function normalizePoint(point) {
  if (!point) return null;
  const x = Number(point.x);
  const y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  const floor = Number.isFinite(Number(point.floor)) ? Number(point.floor) : null;
  return { x, y, floor };
}

export function createFixedNpcRuntime({ rooms, roomBounds, canMoveTo }) {
  const npcs = fixedNpcDefinitions
    .map((definition) => resolveNpcInstance(definition, rooms, roomBounds, canMoveTo))
    .filter(Boolean);

  const dialogueState = {
    open: false,
    npcId: null,
    nodeId: null,
    selectedOptionIndex: 0,
  };

  function getNpcById(npcId) {
    return npcs.find((npc) => npc.id === npcId) || null;
  }

  function getDialogueBook(npc = getCurrentNpc()) {
    if (!npc) return createFallbackDialogueBook();
    return fixedNpcDialogueBooks[npc.dialogueSetId] || createFallbackDialogueBook(npc.name);
  }

  function getCurrentNpc() {
    return getNpcById(dialogueState.npcId);
  }

  function getCurrentNode(book = getDialogueBook()) {
    const nodeId = dialogueState.nodeId || book.startNodeId || "intro";
    return book.nodes[nodeId] || book.nodes.end || null;
  }

  function getNearestNpc(point) {
    const location = normalizePoint(point);
    if (!location) return null;

    let best = null;
    let bestDistance = Infinity;
    for (const npc of npcs) {
      if (location.floor !== null && npc.floor !== location.floor) continue;
      const distance = Math.hypot(location.x - npc.x, location.y - npc.y);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { ...npc, distance };
      }
    }
    return best;
  }

  function getNearestInteractableNpc(point) {
    const location = normalizePoint(point);
    if (!location) return null;

    let best = null;
    let bestDistance = Infinity;
    for (const npc of npcs) {
      if (location.floor !== null && npc.floor !== location.floor) continue;
      const distance = Math.hypot(location.x - npc.x, location.y - npc.y);
      if (distance > npc.interactionRadius) continue;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { ...npc, distance };
      }
    }
    return best;
  }

  function getSnapshot() {
    const npc = getCurrentNpc();
    const book = getDialogueBook(npc);
    const node = getCurrentNode(book);
    const options = node?.type === "choice" && Array.isArray(node.options)
      ? node.options.map((option, index) => ({
        label: option.label || `Option ${index + 1}`,
        next: option.next || "end",
      }))
      : [];
    const selectedOptionIndex = options.length > 0 ? clamp(dialogueState.selectedOptionIndex, 0, options.length - 1) : 0;
    const selectedOptionLabel = options[selectedOptionIndex]?.label || "";

    let statusText = "Conversation closed.";
    let hintText = "Press E to talk.";
    let primaryActionLabel = "Continue";

    if (dialogueState.open) {
      if (node?.type === "choice") {
        statusText = "Choose a reply.";
        hintText = "Use the arrows or click an option, then press E to confirm.";
        primaryActionLabel = "Choose highlighted";
      } else if (node?.type === "end") {
        statusText = "Conversation is ready to close.";
        hintText = "Press E or Close to exit the conversation.";
        primaryActionLabel = "Close";
      } else {
        statusText = "Press E to continue.";
        hintText = "Press E to continue or Esc to close.";
        primaryActionLabel = "Continue";
      }
    }

    return {
      open: dialogueState.open,
      npc,
      node,
      options,
      selectedOptionIndex,
      selectedOptionLabel,
      canAdvance: dialogueState.open && Boolean(node) && (node.type === "line" || node.type === "action" || node.type === "end" || (node.type === "choice" && options.length > 0)),
      canClose: dialogueState.open,
      statusText,
      hintText,
      primaryActionLabel,
    };
  }

  function openDialogue(npc) {
    const targetNpc = typeof npc === "string" ? getNpcById(npc) : npc;
    if (!targetNpc) return false;

    const book = getDialogueBook(targetNpc);
    dialogueState.open = true;
    dialogueState.npcId = targetNpc.id;
    dialogueState.nodeId = book.startNodeId || "intro";
    dialogueState.selectedOptionIndex = 0;
    return true;
  }

  function closeDialogue() {
    dialogueState.open = false;
    dialogueState.npcId = null;
    dialogueState.nodeId = null;
    dialogueState.selectedOptionIndex = 0;
    return true;
  }

  function moveSelection(delta) {
    const snapshot = getSnapshot();
    if (!snapshot.open || snapshot.node?.type !== "choice" || snapshot.options.length === 0) return false;
    const nextIndex = (snapshot.selectedOptionIndex + delta + snapshot.options.length) % snapshot.options.length;
    dialogueState.selectedOptionIndex = nextIndex;
    return true;
  }

  function chooseOption(index) {
    const snapshot = getSnapshot();
    if (!snapshot.open || snapshot.node?.type !== "choice" || snapshot.options.length === 0) return false;

    const safeIndex = clamp(index, 0, snapshot.options.length - 1);
    const nextNodeId = snapshot.options[safeIndex]?.next || "end";
    const book = getDialogueBook();
    if (!book.nodes[nextNodeId]) {
      if (book.nodes.end) {
        dialogueState.nodeId = "end";
        dialogueState.selectedOptionIndex = 0;
        return true;
      }
      return closeDialogue();
    }

    dialogueState.nodeId = nextNodeId;
    dialogueState.selectedOptionIndex = 0;
    return true;
  }

  function advanceDialogue() {
    const snapshot = getSnapshot();
    if (!snapshot.open || !snapshot.node) return false;

    if (snapshot.node.type === "choice") {
      return chooseOption(snapshot.selectedOptionIndex);
    }

    if (snapshot.node.type === "end") {
      closeDialogue();
      return true;
    }

    const book = getDialogueBook();
    const nextNodeId = snapshot.node.next;
    if (!nextNodeId) {
      if (book.nodes.end) {
        dialogueState.nodeId = "end";
        dialogueState.selectedOptionIndex = 0;
        return true;
      }
      return closeDialogue();
    }

    if (!book.nodes[nextNodeId]) {
      if (book.nodes.end) {
        dialogueState.nodeId = "end";
        dialogueState.selectedOptionIndex = 0;
        return true;
      }
      return closeDialogue();
    }

    dialogueState.nodeId = nextNodeId;
    dialogueState.selectedOptionIndex = 0;
    return true;
  }

  function tryInteract(point) {
    if (dialogueState.open) return false;
    const npc = getNearestInteractableNpc(point);
    if (!npc) return false;
    return openDialogue(npc);
  }

  function isDialogueOpen() {
    return dialogueState.open;
  }

  function update() {}

  return {
    getNpcs: () => npcs,
    getNpcById,
    getNearestNpc,
    getNearestInteractableNpc,
    tryInteract,
    isDialogueOpen,
    getDialogueSnapshot: getSnapshot,
    advanceDialogue,
    chooseOption,
    moveSelection,
    closeDialogue,
    update,
  };
}
