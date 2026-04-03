import { NPC_TYPES } from "./npc.js";
import { createUserMessage, createAssistantMessage, callChatAPI } from "./api.js";

export const INTERNAL_MEDICINE_RAG = `
## 内科医学知识库

### 常见内科疾病及症状

**1. 呼吸道感染**
- 普通感冒：鼻塞、流涕、咽痛、咳嗽、发热
- 流感：高热（39-40℃）、头痛、肌肉酸痛、乏力
- 支气管炎：咳嗽、咳痰（黄痰或白痰）、喘息

**2. 消化系统疾病**
- 急性胃炎：上腹疼痛、恶心、呕吐、食欲不振
- 慢性胃炎：上腹隐痛、反酸、嗳气、腹胀
- 胃溃疡：周期性上腹疼痛、餐后痛、黑便
- 急性肠炎：腹泻（稀水便）、腹痛、恶心、发热

**3. 心血管疾病**
- 高血压：头痛、头晕、耳鸣、视力模糊，常无症状
- 冠心病：胸痛（心绞痛）、胸闷、气短
- 心律失常：心悸、心跳不规则、乏力、头晕

**4. 内分泌疾病**
- 糖尿病：多饮、多尿、多食、体重下降、皮肤瘙痒
- 甲状腺功能亢进：心悸、多汗、消瘦、情绪激动、手抖
- 甲状腺功能减退：乏力、嗜睡、怕冷、体重增加

**5. 神经系统疾病**
- 头痛：偏头痛、紧张性头痛、丛集性头痛
- 眩晕：良性阵发性位置性眩晕、梅尼埃病
- 脑供血不足：头晕、记忆力下降、肢体麻木

**6. 泌尿系统疾病**
- 尿路感染：尿频、尿急、尿痛、下腹疼痛
- 肾炎：血尿、蛋白尿、水肿、高血压
- 前列腺炎：尿频、尿急、会阴部疼痛

**7. 血液系统疾病**
- 贫血：乏力、头晕、心悸、面色苍白
- 白血病：发热、贫血、出血、肝脾肿大

### 诊断流程

1. 询问病史：症状起始时间、持续时间、严重程度、伴随症状
2. 体格检查：体温、血压、心肺听诊、腹部触诊
3. 辅助检查：血常规、尿常规、心电图、X光、超声等

### 治疗原则

1. 对症治疗：缓解症状
2. 病因治疗：根治病因
3. 一般治疗：休息、饮食调理
4. 药物治疗：遵医嘱按时服药
5. 随访复查：定期复查评估疗效
`;

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
    systemPrompt = getDoctorSystemPrompt(npc);
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

export function getDoctorSystemPrompt(npc = null) {
  const isInternalDoctor = npc && npc.department === "internal";
  const ragContext = isInternalDoctor ? INTERNAL_MEDICINE_RAG : "";

  if (isInternalDoctor) {
    return `你是一位内科医生，名字叫"Dr.林"，你在内科诊室工作。你是专业的内科医生，拥有丰富的内科医学知识。

${ragContext}

你需要：
1. 礼貌地问候患者，询问症状
2. 详细询问患者的症状和病史（包括症状起始时间、持续多久、严重程度、伴随症状等）
3. 根据症状进行初步诊断和鉴别诊断
4. 提供专业的医疗建议和治疗方案
5. 如需进一步检查，建议患者做相应检查（如血常规、尿常规、心电图、X光等）
6. 如需开药，说明药物名称、用法用量
7. 保持专业、温和、耐心的态度
8. 回答要专业但通俗易懂，让患者能够理解
9. 如果患者情况紧急或严重，及时提醒患者去急诊

注意：你只负责内科疾病，其他科室疾病请建议患者去相应科室。`;
  }

  return `你是一位专业的医生，名字叫"Dr.林"。你需要：
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
