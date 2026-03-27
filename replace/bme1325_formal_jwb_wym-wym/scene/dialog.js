import { NPC_TYPES } from "./npc.js";
import { createUserMessage, createAssistantMessage, callChatAPI } from "./api.js";

export function createDialogSystem() {
  return {
    isOpen: false,
    currentNPC: null,
    messages: [],
    inputText: "",
    isLoading: false,
    conversationContexts: {},
    recommendedDepts: [],
    buttonRects: [],
  };
}

export function openDialog(dialogSystem, npc) {
  dialogSystem.isOpen = true;
  dialogSystem.currentNPC = npc;
  dialogSystem.inputText = "";
  dialogSystem.recommendedDepts = [];
  dialogSystem.buttonRects = [];

  if (!dialogSystem.conversationContexts[npc.id]) {
    dialogSystem.conversationContexts[npc.id] = [];
  }

  npc.state = "in_conversation";
}

export function closeDialog(dialogSystem) {
  if (dialogSystem.currentNPC) {
    dialogSystem.currentNPC.state = "idle";
  }
  dialogSystem.isOpen = false;
  dialogSystem.currentNPC = null;
  dialogSystem.inputText = "";
  dialogSystem.recommendedDepts = [];
  dialogSystem.buttonRects = [];
}

export function addMessage(dialogSystem, role, content) {
  dialogSystem.messages.push({ role, content, timestamp: Date.now() });
}

export function getConversationHistory(dialogSystem, npcId) {
  return dialogSystem.conversationContexts[npcId] || [];
}

export function saveConversation(dialogSystem, npcId, messages) {
  dialogSystem.conversationContexts[npcId] = messages;
}

export function buildContextMessage(dialogSystem, npcId) {
  const history = getConversationHistory(dialogSystem, npcId);
  if (history.length === 0) return "";

  let context = "对话历史：\n";
  for (const msg of history.slice(-6)) {
    const speaker = msg.role === "user" ? "患者" : npcId.includes("nurse") ? "护士" : "医生";
    context += `${speaker}: ${msg.content}\n`;
  }
  return context;
}

export async function sendMessage(dialogSystem, content, npc, apiCaller, options = {}) {
  if (!content.trim() || dialogSystem.isLoading) return;

  addMessage(dialogSystem, "user", content);
  const userMsg = createUserMessage(content);
  dialogSystem.isLoading = true;

  const context = buildContextMessage(dialogSystem, npc.id);
  const fullContent = context + "患者说: " + content;

  let systemPrompt;
  if (npc.type === NPC_TYPES.NURSE) {
    systemPrompt = getNurseSystemPrompt();
  } else if (npc.type === NPC_TYPES.DOCTOR) {
    systemPrompt = getDoctorSystemPrompt();
  } else if (npc.type === NPC_TYPES.PHARMACIST) {
    systemPrompt = getPharmacistSystemPrompt();
  } else {
    systemPrompt = getNurseSystemPrompt();
  }

  try {
    const response = await (apiCaller
      ? apiCaller([createUserMessage(fullContent)], systemPrompt)
      : callChatAPI(fullContent, options.model, options.imageData));
    addMessage(dialogSystem, "assistant", response);

    const assistantMsg = createAssistantMessage(response);
    const history = getConversationHistory(dialogSystem, npc.id);
    history.push(userMsg, assistantMsg);
    saveConversation(dialogSystem, npc.id, history);

    if (npc.type === NPC_TYPES.NURSE) {
      dialogSystem.recommendedDepts = extractDepartments(response);
    }

    return response;
  } catch (error) {
    addMessage(dialogSystem, "assistant", "抱歉，网络出现了问题，请稍后再试。");
    return "error";
  } finally {
    dialogSystem.isLoading = false;
  }
}

function extractDepartments(text) {
  const mapping = [
    { key: "internal", patterns: ["内科"] },
    { key: "surgery", patterns: ["外科"] },
    { key: "pediatrics", patterns: ["儿科"] },
    { key: "emergency", patterns: ["急诊", "急救"] },
    { key: "eye", patterns: ["眼科", "眼睛"] },
    { key: "ortho", patterns: ["骨科", "关节", "骨"] },
  ];

  const found = [];
  for (const item of mapping) {
    if (item.patterns.some((p) => text.includes(p))) {
      found.push(item.key);
    }
  }

  return found;
}

function getNurseSystemPrompt() {
  return `你是一位医院分诊台的智能护士，名字叫“小医”。你需要：
1. 礼貌地问候患者，询问症状
2. 根据症状建议合适的科室（内科、外科、儿科、眼科等）
3. 如遇紧急情况，提醒患者去急诊
4. 保持专业、耐心、友好
5. 回答简明扼要，一般不超过3句话
6. 可以提供一些基本健康建议

当前医院科室：
- 内科：常见疾病、感冒发烧、慢性病
- 外科：需要手术的疾病、创伤
- 儿科：14岁以下儿童
- 眼科：眼睛相关疾病
- 骨科：骨骼、关节疾病
- 急诊：紧急情况、危重病人`;
}

function getDoctorSystemPrompt() {
  return `你是一位专业的医生，名字叫“Dr.林”。你需要：
1. 详细询问患者的症状和病史
2. 提供专业的医疗建议
3. 如需进一步检查，建议患者做相应检查
4. 开具处方或建议住院治疗
5. 保持专业、温和的态度
6. 回答要专业但通俗易懂`;
}

function getPharmacistSystemPrompt() {
  return `你是一位医院的药师，名字叫“老张”。你需要：
1. 审核处方，确保用药安全
2. 向患者说明药物的用法用量
3. 提醒患者注意药物副作用
4. 保持专业、耐心的态度
5. 回答简明扼要`;
}

export function drawDialogBox(ctx, canvas, dialogSystem, deptLabels = {}) {
  if (!dialogSystem.isOpen) return;

  const boxWidth = 500;
  const boxHeight = 350;
  const boxX = (canvas.width - boxWidth) / 2;
  const boxY = canvas.height - boxHeight - 80;

  ctx.fillStyle = "rgba(16, 11, 24, 0.96)";
  ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.8)";
  ctx.lineWidth = 2;
  ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);

  const npcName = dialogSystem.currentNPC?.name || "NPC";
  ctx.fillStyle = "#a8f8ff";
  ctx.font = "bold 16px 'Segoe UI'";
  ctx.textAlign = "center";
  ctx.fillText(`与 ${npcName} 对话`, boxX + boxWidth / 2, boxY + 26);

  ctx.strokeStyle = "rgba(168, 248, 255, 0.3)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(boxX + 10, boxY + 40);
  ctx.lineTo(boxX + boxWidth - 10, boxY + 40);
  ctx.stroke();

  const messagesY = boxY + 55;
  const messagesHeight = boxHeight - 120;
  ctx.save();
  ctx.beginPath();
  ctx.rect(boxX + 10, messagesY, boxWidth - 20, messagesHeight);
  ctx.clip();

  let y = messagesY + 15;
  const maxWidth = boxWidth - 50;

  for (const msg of dialogSystem.messages.slice(-8)) {
    const isUser = msg.role === "user";
    const x = isUser ? boxX + boxWidth - 30 : boxX + 20;
    const bgColor = isUser ? "rgba(78, 168, 222, 0.3)" : "rgba(232, 143, 176, 0.3)";
    const textColor = isUser ? "#e8f4ff" : "#ffe8f0";

    ctx.font = "13px 'Segoe UI'";
    const lines = wrapText(ctx, msg.content, maxWidth);
    const lineHeight = 18;
    const bgHeight = lines.length * lineHeight + 12;
    const bgWidth = Math.min(maxWidth, ctx.measureText(msg.content).width + 20) + 10;

    ctx.fillStyle = bgColor;
    const bgX = isUser ? boxX + boxWidth - 20 - bgWidth : x - 10;
    ctx.fillRect(bgX, y - 10, bgWidth, bgHeight);

    ctx.fillStyle = textColor;
    ctx.textAlign = isUser ? "right" : "left";
    for (const line of lines) {
      ctx.fillText(line, isUser ? boxX + boxWidth - 25 : x + 5, y + 5);
      y += lineHeight;
    }
    y += 8;
  }

  ctx.restore();

  dialogSystem.buttonRects = [];
  if (dialogSystem.recommendedDepts.length > 0) {
    const btnY = boxY + boxHeight - 84;
    const btnW = 96;
    const btnH = 26;
    const gap = 10;
    const totalW = dialogSystem.recommendedDepts.length * btnW + (dialogSystem.recommendedDepts.length - 1) * gap;
    let startX = boxX + (boxWidth - totalW) / 2;

    dialogSystem.recommendedDepts.forEach((deptId, index) => {
      const rect = { x: startX, y: btnY, w: btnW, h: btnH, deptId };
      dialogSystem.buttonRects.push(rect);
      ctx.fillStyle = "rgba(131, 255, 201, 0.18)";
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
      ctx.strokeStyle = "rgba(131, 255, 201, 0.8)";
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      ctx.fillStyle = "#83ffc9";
      ctx.font = "12px 'Segoe UI'";
      ctx.textAlign = "center";
      const label = deptLabels[deptId] || deptId;
      ctx.fillText(`${index + 1}. ${label}`, rect.x + rect.w / 2, rect.y + 17);
      startX += btnW + gap;
    });
  }

  if (dialogSystem.isLoading) {
    ctx.fillStyle = "#83ffc9";
    ctx.font = "12px 'Segoe UI'";
    ctx.textAlign = "center";
    ctx.fillText("AI 正在思考...", boxX + boxWidth / 2, boxY + boxHeight - 50);
  }

  ctx.fillStyle = "rgba(30, 20, 40, 0.9)";
  ctx.fillRect(boxX + 10, boxY + boxHeight - 45, boxWidth - 20, 35);
  ctx.strokeStyle = "rgba(168, 248, 255, 0.5)";
  ctx.strokeRect(boxX + 10, boxY + boxHeight - 45, boxWidth - 20, 35);

  ctx.fillStyle = "#f2ebff";
  ctx.font = "12px 'Segoe UI'";
  ctx.textAlign = "left";
  ctx.fillText("输入:", boxX + 20, boxY + boxHeight - 22);

  ctx.fillStyle = "#fff";
  ctx.font = "13px 'Segoe UI'";
  const inputDisplay = dialogSystem.inputText || "（中文输入请直接打字，Enter发送，Esc退出）";
  ctx.fillText(inputDisplay, boxX + 55, boxY + boxHeight - 22);
}

function wrapText(ctx, text, maxWidth) {
  const words = text.split("");
  const lines = [];
  let currentLine = "";

  for (const char of words) {
    const testLine = currentLine + char;
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && currentLine.length > 0) {
      lines.push(currentLine);
      currentLine = char;
    } else {
      currentLine = testLine;
    }
  }

  if (currentLine.length > 0) {
    lines.push(currentLine);
  }

  return lines.length > 0 ? lines : [""];
}

export function handleDialogInput(dialogSystem, event) {
  if (event.key === "Enter" && !dialogSystem.isLoading) {
    const text = dialogSystem.inputText.trim();
    if (text) {
      return { action: "send", text };
    }
  } else if (event.key === "Backspace") {
    dialogSystem.inputText = dialogSystem.inputText.slice(0, -1);
  } else if (event.key === "Escape") {
    return { action: "close" };
  } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
    dialogSystem.inputText += event.key;
  }

  return null;
}
