// 星露谷风格医院游戏主逻辑
import { createBackendClient } from './api/client.js';

// ============== 配置 ==============
const CONFIG = {
  TILE_SIZE: 48,
  PLAYER_SPEED: 20,
  CAMERA_LERP: 0.1,
};

const COLORS = {
  SKY_BLUE: '#87CEEB',
  GRASS_GREEN: '#7EC850',
  DIRT_BROWN: '#8B6914',
  DARK_BROWN: '#5C4033',
  WOOD_BROWN: '#A0522D',
  WALL_BROWN: '#DEB887',
  ROOF_RED: '#C04040',
  WINDOW_BLUE: '#ADD8E6',
  TEXT_DARK: '#3d2817',
  TEXT_LIGHT: '#FFF8DC',
  HEALTH_RED: '#E74C3C',
  HEALTH_GREEN: '#27AE60',
  WATER_BLUE: '#5DADE2',
};

// ============== 房间定义 ==============
const ROOMS = [
  { id: 'lobby', name: '医院大厅', x: 12, y: 10, w: 8, h: 6, type: 'main', exits: [{ dir: 'up', targetRoom: 'triage', targetX: 7, targetY: 9 }, { dir: 'left', targetRoom: 'icu', targetX: 9, targetY: 17 }, { dir: 'right', targetRoom: 'internal', targetX: 21, targetY: 17 }] },
  { id: 'triage', name: '门诊', x: 4, y: 4, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'down', targetRoom: 'lobby', targetX: 16, targetY: 13 }] },
  { id: 'pharmacy', name: '药房', x: 22, y: 4, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'down', targetRoom: 'lobby', targetX: 16, targetY: 13 }] },
  { id: 'icu', name: 'ICU', x: 4, y: 12, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'right', targetRoom: 'lobby', targetX: 13, targetY: 16 }] },
  { id: 'internal', name: '内科', x: 22, y: 12, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'left', targetRoom: 'lobby', targetX: 19, targetY: 16 }] },
  { id: 'lab', name: '化验室', x: 12, y: 18, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'up', targetRoom: 'lobby', targetX: 16, targetY: 15 }] },
  { id: 'garden', name: '后花园', x: 12, y: 25, w: 8, h: 6, type: 'outdoor', exits: [{ dir: 'up', targetRoom: 'lobby', targetX: 16, targetY: 15 }] },
];

// ============== NPC定义 ==============
const NPC_TEMPLATES = {
  doctor: { emoji: '👨‍⚕️', color: '#FFFFFF' },
  nurse: { emoji: '👩‍⚕️', color: '#FFB6C1' },
  patient_male: { emoji: '👨', color: '#ADD8E6' },
  patient_female: { emoji: '👩', color: '#FFB6C1' },
  visitor: { emoji: '🧑', color: '#98D8AA' },
};

// NPC多种对话内容
const NPC_DIALOGUES = {
  triage: [
    '你好，有什么不舒服吗？请描述一下您的症状。',
    '欢迎来到门诊。请问您今天是来看什么病的？',
    '请先测量一下体温和血压，我会根据您的情况安排就诊。',
  ],
  icu: [
    '重症监护室需要特殊许可才能进入。请问您有什么事？',
    'ICU是危重病人监护区域，非授权人员不得进入。',
    '如果您是病人家属，请先到前台登记。',
  ],
  internal: [
    '内科主要诊治各种内科疾病，请问您哪里不舒服？',
    '常见内科疾病包括感冒发烧、高血压、糖尿病等。',
    '请详细描述一下您的症状，我会为您做详细诊断。',
  ],
  pharmacy: [
    '请出示处方单取药。',
    '药房开放时间为早上8点到晚上6点。',
    '如有疑问，请咨询值班药师。',
  ],
  lobby_nurse: [
    '欢迎来到医院！请问需要什么帮助？',
    '您好！如果您需要挂号，请到相应科室。',
    '请注意保持安静，这是医疗场所。',
  ],
  lobby_patient: [
    '我在这里等检查结果，已经等了一会儿了...',
    '医生说还要再等等，结果出来会通知我的。',
    '这家医院服务不错，就是人有点多。',
  ],
  garden_visitor: [
    '花园空气真好，病情好多了。',
    '出来透透气，感觉整个人都精神多了。',
    '这里环境优雅，很适合休养。',
  ],
};

function getNPCDialogue(npcId, dialogueIndex) {
  let category = '';
  if (npcId === 'npc_1') category = 'triage';
  else if (npcId === 'npc_2') category = 'lobby_nurse';
  else if (npcId === 'npc_3') category = 'icu';
  else if (npcId === 'npc_4') category = 'internal';
  else if (npcId === 'npc_5') category = 'pharmacy';
  else if (npcId === 'npc_6') category = 'lobby_patient';
  else if (npcId === 'npc_7') category = 'garden_visitor';
  
  const dialogues = NPC_DIALOGUES[category] || ['你好！'];
  return dialogues[dialogueIndex % dialogues.length];
}

const NPCs = [
  { id: 'npc_1', name: '张医生', template: 'doctor', room: 'triage', x: 5, y: 6 },
  { id: 'npc_2', name: '李护士', template: 'nurse', room: 'lobby', x: 14, y: 12 },
  { id: 'npc_3', name: '王主任', template: 'doctor', room: 'icu', x: 5, y: 13 },
  { id: 'npc_4', name: '刘医生', template: 'doctor', room: 'internal', x: 23, y: 13 },
  { id: 'npc_5', name: '赵药师', template: 'doctor', room: 'pharmacy', x: 23, y: 6 },
  { id: 'npc_6', name: '钱先生', template: 'patient_male', room: 'lobby', x: 16, y: 13 },
  { id: 'npc_7', name: '孙女士', template: 'patient_female', room: 'garden', x: 14, y: 28 },
];

// ============== 游戏状态 ==============
class GameState {
  constructor() {
    this.player = { x: 16, y: 13, direction: 'down' };
    this.camera = { x: 0, y: 0 };
    this.currentRoom = 'lobby';
    this.npcs = NPCs.map(npc => ({ ...npc, dialogueIndex: 0 }));
    this.dialogueActive = false;
    this.currentNPC = null;
    this.menuOpen = false;
    this.apiConnected = false;
    this.day = 1;
    this.time = 9 * 60;
    this.weather = 'sunny';
    this.apiKey = '';
    this.currentDialogueCounter = {};
    this.dialogueActionInProgress = false;
  }

  updateTime(deltaMinutes) {
    this.time += deltaMinutes;
    if (this.time >= 24 * 60) {
      this.time -= 24 * 60;
      this.day++;
    }
  }

  getTimeString() {
    const hours = Math.floor(this.time / 60);
    const minutes = this.time % 60;
    const period = hours < 12 ? '上午' : '下午';
    const displayHour = hours > 12 ? hours - 12 : hours;
    return `第 ${this.day} 天 - ${period} ${displayHour}:${minutes.toString().padStart(2, '0')}`;
  }

  getNextDialogue(npcId) {
    if (!this.currentDialogueCounter[npcId]) {
      this.currentDialogueCounter[npcId] = 0;
    }
    const index = this.currentDialogueCounter[npcId];
    this.currentDialogueCounter[npcId] = (index + 1) % 3;
    return getNPCDialogue(npcId, index);
  }
}

// ============== 渲染器 ==============
class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.resize();
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  clear() {
    this.ctx.fillStyle = COLORS.SKY_BLUE;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  drawGround() {
    const { ctx } = this;
    for (let y = 0; y < 35; y++) {
      for (let x = 0; x < 32; x++) {
        const screenX = x * CONFIG.TILE_SIZE - gameState.camera.x;
        const screenY = y * CONFIG.TILE_SIZE - gameState.camera.y;
        
        if (screenX < -CONFIG.TILE_SIZE || screenX > this.canvas.width ||
            screenY < -CONFIG.TILE_SIZE || screenY > this.canvas.height) continue;

        const isGrass = (x + y) % 7 === 0;
        ctx.fillStyle = isGrass ? COLORS.GRASS_GREEN : '#8BC34A';
        ctx.fillRect(screenX, screenY, CONFIG.TILE_SIZE, CONFIG.TILE_SIZE);
        
        if (isGrass) {
          ctx.fillStyle = '#6B8E23';
          ctx.fillRect(screenX + 4, screenY + 8, 2, 6);
          ctx.fillRect(screenX + 20, screenY + 4, 2, 8);
        }
      }
    }
  }

  drawRoom(room) {
    const { ctx } = this;
    const offsetX = room.x * CONFIG.TILE_SIZE - gameState.camera.x;
    const offsetY = room.y * CONFIG.TILE_SIZE - gameState.camera.y;

    ctx.fillStyle = COLORS.WALL_BROWN;
    ctx.fillRect(offsetX, offsetY, room.w * CONFIG.TILE_SIZE, room.h * CONFIG.TILE_SIZE);
    
    for (let y = 0; y < room.h; y++) {
      for (let x = 0; x < room.w; x++) {
        ctx.strokeStyle = 'rgba(139, 69, 19, 0.2)';
        ctx.strokeRect(offsetX + x * CONFIG.TILE_SIZE, offsetY + y * CONFIG.TILE_SIZE, CONFIG.TILE_SIZE, CONFIG.TILE_SIZE);
      }
    }

    ctx.fillStyle = COLORS.DARK_BROWN;
    ctx.fillRect(offsetX, offsetY - 40, room.w * CONFIG.TILE_SIZE, 40);
    ctx.fillRect(offsetX, offsetY + room.h * CONFIG.TILE_SIZE - 20, room.w * CONFIG.TILE_SIZE, 20);
    ctx.fillRect(offsetX - 20, offsetY, 20, room.h * CONFIG.TILE_SIZE);
    ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE, offsetY, 20, room.h * CONFIG.TILE_SIZE);

    // 画门
    const doorWidth = CONFIG.TILE_SIZE * 1.5;
    const doorHeight = CONFIG.TILE_SIZE * 2;
    ctx.fillStyle = COLORS.WOOD_BROWN;
    
    if (room.type === 'main') {
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2, offsetY - doorHeight + 20, doorWidth, doorHeight);
      ctx.fillStyle = COLORS.WINDOW_BLUE;
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2 + 5, offsetY - doorHeight + 25, doorWidth - 10, doorHeight - 30);
    } else {
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2, offsetY + room.h * CONFIG.TILE_SIZE - 10, doorWidth, doorHeight);
      ctx.fillStyle = COLORS.WINDOW_BLUE;
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2 + 5, offsetY + room.h * CONFIG.TILE_SIZE - 5, doorWidth - 10, doorHeight - 30);
    }

    // 画出口标记
    ctx.fillStyle = '#FFD700';
    ctx.font = 'bold 12px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('出口', offsetX + room.w * CONFIG.TILE_SIZE / 2, offsetY + room.h * CONFIG.TILE_SIZE + 15);

    ctx.fillStyle = COLORS.ROOF_RED;
    ctx.beginPath();
    ctx.moveTo(offsetX - 20, offsetY);
    ctx.lineTo(offsetX + room.w * CONFIG.TILE_SIZE / 2, offsetY - 60);
    ctx.lineTo(offsetX + room.w * CONFIG.TILE_SIZE + 20, offsetY);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = 'rgba(139, 90, 43, 0.9)';
    ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - 40, offsetY - 85, 80, 25);
    ctx.fillStyle = COLORS.TEXT_LIGHT;
    ctx.font = 'bold 14px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(room.name, offsetX + room.w * CONFIG.TILE_SIZE / 2, offsetY - 67);
  }

  drawPlayer() {
    const { ctx } = this;
    const screenX = gameState.player.x * CONFIG.TILE_SIZE - gameState.camera.x;
    const screenY = gameState.player.y * CONFIG.TILE_SIZE - gameState.camera.y;

    ctx.fillStyle = '#4169E1';
    ctx.fillRect(screenX + 12, screenY + 20, 24, 28);
    
    ctx.fillStyle = '#FFDAB9';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 15, 14, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.fillStyle = '#8B4513';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 10, 14, Math.PI, 0);
    ctx.fill();
    
    ctx.fillStyle = '#000';
    if (gameState.player.direction === 'up') {
    } else {
      ctx.fillRect(screenX + 18, screenY + 12, 3, 3);
      ctx.fillRect(screenX + 27, screenY + 12, 3, 3);
    }

    ctx.fillStyle = '#2F4F4F';
    ctx.fillRect(screenX + 14, screenY + 48, 8, 12);
    ctx.fillRect(screenX + 26, screenY + 48, 8, 12);
  }

  drawNPC(npc) {
    const { ctx } = this;
    const template = NPC_TEMPLATES[npc.template];
    const screenX = npc.x * CONFIG.TILE_SIZE - gameState.camera.x;
    const screenY = npc.y * CONFIG.TILE_SIZE - gameState.camera.y;

    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.beginPath();
    ctx.ellipse(screenX + 24, screenY + 60, 16, 6, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = template.color;
    ctx.fillRect(screenX + 10, screenY + 22, 28, 26);
    
    ctx.fillStyle = '#FFDAB9';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 15, 13, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#000';
    ctx.fillRect(screenX + 18, screenY + 12, 3, 3);
    ctx.fillRect(screenX + 27, screenY + 12, 3, 3);
    ctx.fillStyle = '#E74C3C';
    ctx.beginPath();
    ctx.arc(screenX + 16, screenY + 18, 3, 0, Math.PI * 2);
    ctx.arc(screenX + 32, screenY + 18, 3, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = 'rgba(0,0,0,0.7)';
    ctx.fillRect(screenX + 4, screenY - 10, 40, 16);
    ctx.fillStyle = '#FFF';
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(npc.name, screenX + 24, screenY + 2);
  }

  drawInteractionPrompt(npc) {
    const { ctx } = this;
    const screenX = npc.x * CONFIG.TILE_SIZE - gameState.camera.x;
    const screenY = npc.y * CONFIG.TILE_SIZE - gameState.camera.y - 80;

    ctx.fillStyle = 'rgba(34, 139, 34, 0.95)';
    ctx.fillRect(screenX - 10, screenY, 70, 28);
    ctx.strokeStyle = '#228B22';
    ctx.lineWidth = 2;
    ctx.strokeRect(screenX - 10, screenY, 70, 28);
    
    ctx.fillStyle = '#FFF';
    ctx.font = 'bold 14px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('按 E 对话', screenX + 25, screenY + 19);
  }

  drawExitPrompt() {
    const { ctx } = this;
    ctx.fillStyle = 'rgba(255, 215, 0, 0.9)';
    ctx.fillRect(this.canvas.width / 2 - 60, 80, 120, 30);
    ctx.strokeStyle = '#DAA520';
    ctx.lineWidth = 2;
    ctx.strokeRect(this.canvas.width / 2 - 60, 80, 120, 30);
    ctx.fillStyle = '#000';
    ctx.font = 'bold 12px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('按 Q 走出房间', this.canvas.width / 2, 100);
  }
}

// ============== 游戏逻辑 ==============
class GameLogic {
  constructor() {
    this.keys = {};
    this.lastTime = 0;
  }

  init() {
    window.addEventListener('keydown', (e) => {
      this.keys[e.key.toLowerCase()] = true;
      if (e.key.toLowerCase() === 'e') this.tryInteract();
      if (e.key.toLowerCase() === 'q') this.tryExitRoom();
      if (e.key === 'Escape' && gameState.dialogueActive) this.closeDialogue();
    });
    window.addEventListener('keyup', (e) => {
      this.keys[e.key.toLowerCase()] = false;
    });
  }

  update(deltaTime) {
    if (gameState.dialogueActive) return;

    let dx = 0, dy = 0;
    if (this.keys['w'] || this.keys['arrowup']) { dy = -1; gameState.player.direction = 'up'; }
    if (this.keys['s'] || this.keys['arrowdown']) { dy = 1; gameState.player.direction = 'down'; }
    if (this.keys['a'] || this.keys['arrowleft']) { dx = -1; gameState.player.direction = 'left'; }
    if (this.keys['d'] || this.keys['arrowright']) { dx = 1; gameState.player.direction = 'right'; }

    if (dx !== 0 || dy !== 0) {
      const newX = gameState.player.x + dx * (CONFIG.PLAYER_SPEED * deltaTime / 1000);
      const newY = gameState.player.y + dy * (CONFIG.PLAYER_SPEED * deltaTime / 1000);
      
      if (this.canMoveTo(newX, newY)) {
        gameState.player.x = newX;
        gameState.player.y = newY;
      }
      
      gameState.updateTime(deltaTime / 60000 * 10);
    }

    const targetX = gameState.player.x * CONFIG.TILE_SIZE - renderer.canvas.width / 2;
    const targetY = gameState.player.y * CONFIG.TILE_SIZE - renderer.canvas.height / 2;
    gameState.camera.x += (targetX - gameState.camera.x) * CONFIG.CAMERA_LERP;
    gameState.camera.y += (targetY - gameState.camera.y) * CONFIG.CAMERA_LERP;

    this.updateCurrentRoom();
  }

  canMoveTo(x, y) {
    if (x < 0 || x > 30 || y < 0 || y > 33) return false;
    
    for (const room of ROOMS) {
      const inRoomX = x >= room.x - 3 && x < room.x + room.w + 3;
      const inRoomY = y >= room.y - 3 && y < room.y + room.h + 3;
      if (inRoomX && inRoomY) {
        return true;
      }
    }
    return false;
  }

  updateCurrentRoom() {
    const px = gameState.player.x;
    const py = gameState.player.y;
    
    for (const room of ROOMS) {
      if (px >= room.x && px < room.x + room.w && py >= room.y && py < room.y + room.h) {
        if (gameState.currentRoom !== room.id) {
          gameState.currentRoom = room.id;
          document.getElementById('current-room').textContent = room.name;
        }
        break;
      }
    }
  }

  tryInteract() {
    if (gameState.dialogueActive || gameState.dialogueActionInProgress) return;

    const px = gameState.player.x;
    const py = gameState.player.y;
    
    for (const npc of gameState.npcs) {
      const dist = Math.sqrt(Math.pow(px - npc.x, 2) + Math.pow(py - npc.y, 2));
      if (dist < 2) {
        this.startDialogue(npc);
        return;
      }
    }
  }

  tryExitRoom() {
    if (gameState.dialogueActive || gameState.dialogueActionInProgress) return;

    const currentRoom = ROOMS.find(r => r.id === gameState.currentRoom);
    if (!currentRoom || !currentRoom.exits || currentRoom.exits.length === 0) return;
    
    const exit = currentRoom.exits[0];
    const targetRoom = ROOMS.find(r => r.id === exit.targetRoom);
    if (targetRoom) {
      gameState.player.x = exit.targetX;
      gameState.player.y = exit.targetY;
      gameState.currentRoom = exit.targetRoom;
      document.getElementById('current-room').textContent = targetRoom.name;
    }
  }

  startDialogue(npc) {
    gameState.dialogueActive = true;
    gameState.currentNPC = npc;
    
    const dialogueBox = document.getElementById('dialogue-box');
    const portrait = document.getElementById('dialogue-portrait');
    const nameEl = document.getElementById('dialogue-name');
    const textEl = document.getElementById('dialogue-text');
    const optionsEl = document.getElementById('dialogue-options');
    
    portrait.textContent = NPC_TEMPLATES[npc.template].emoji;
    nameEl.textContent = npc.name;
    const dialogue = gameState.getNextDialogue(npc.id);
    textEl.textContent = dialogue;
    
    optionsEl.innerHTML = '';
    if (npc.template === 'doctor') {
      if (npc.room === 'triage') {
        this.addDialogueOption('我要挂号', () => this.requestRegistration(npc));
        this.addDialogueOption('我有症状要描述', () => this.describeSymptoms(npc));
      } else if (npc.room === 'internal') {
        this.addDialogueOption('我要内科问诊', () => this.requestInternalMedicine(npc));
        this.addDialogueOption('我有内科问题咨询', () => this.consultInternal(npc));
      } else if (npc.room === 'icu') {
        this.addDialogueOption('我想了解ICU情况', () => this.consultICU(npc));
        this.addDialogueOption('我有危重病人咨询', () => this.requestICUConsultation(npc));
      }
    }
    this.addDialogueOption('谢谢，再见', () => this.closeDialogue());
    
    dialogueBox.classList.remove('hidden');
  }

  addDialogueOption(text, callback) {
    const btn = document.createElement('button');
    btn.className = 'dialogue-option';
    btn.textContent = text;
    btn.onclick = async () => {
      if (gameState.dialogueActionInProgress) return;
      gameState.dialogueActionInProgress = true;
      try {
        const shouldKeepOpen = callback ? await callback() === false : false;
        if (!shouldKeepOpen) {
          this.closeDialogue();
        }
      } finally {
        gameState.dialogueActionInProgress = false;
      }
    };
    document.getElementById('dialogue-options').appendChild(btn);
  }

  async requestRegistration(npc) {
    const symptoms = await showTextInputDialog('请描述您的症状：', '', '例如：发烧、咳嗽两天');
    if (!symptoms) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createTriageSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: symptoms,
        });
        alert(`分诊成功！Session: ${session.session_id}\n请到相应科室就诊。`);
      } catch (e) {
        alert('分诊失败，将使用本地模拟分诊。');
        this.mockTriageResult(symptoms);
      }
    } else {
      this.mockTriageResult(symptoms);
    }
  }

  mockTriageResult(symptoms) {
    const symptomsLower = symptoms.toLowerCase();
    let dept = '内科';
    let level = 3;
    
    if (symptomsLower.includes('发烧') || symptomsLower.includes('感冒') || symptomsLower.includes('咳嗽')) {
      dept = '内科';
      level = 3;
    } else if (symptomsLower.includes('骨折') || symptomsLower.includes('外伤') || symptomsLower.includes('出血')) {
      dept = '急诊';
      level = 2;
    } else if (symptomsLower.includes('心脏') || symptomsLower.includes('胸痛') || symptomsLower.includes('呼吸困难')) {
      dept = 'ICU';
      level = 1;
    }
    
    alert(`模拟分诊结果:\n科室: ${dept}\n优先级: ${level}\n请到相应科室就诊。`);
  }

  async describeSymptoms(npc) {
    const symptoms = await showTextInputDialog('请详细描述您的症状：', '', '尽量描述持续时间、疼痛程度、伴随症状');
    if (!symptoms || !backendClient || !gameState.apiKey) {
      if (!backendClient || !gameState.apiKey) {
        alert('API未连接或未设置API Key，将使用本地模拟诊断。');
      }
      return;
    }
    
    try {
      const session = await backendClient.createTriageSession({
        patient_id: 'player_1',
        name: '玩家',
        chief_complaint: symptoms,
      });
      alert(`症状登记成功！Session: ${session.session_id}`);
    } catch (e) {
      alert('症状登记失败：' + e.message);
    }
  }

  async requestInternalMedicine(npc) {
    const symptoms = await showTextInputDialog('请描述您的内科症状：', '', '例如：头痛、胸闷、乏力');
    if (!symptoms) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createInternalMedicineSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: symptoms,
        });
        alert(`内科问诊创建成功！Session: ${session.session_id}\n医生将为您诊断。`);
      } catch (e) {
        alert('内科问诊失败：' + e.message);
      }
    } else {
      alert('内科问诊：您的症状已记录。\n根据RAG知识库建议：\n1. 详细检查\n2. 血液化验\n3. 后续治疗');
    }
  }

  async consultInternal(npc) {
    const question = await showTextInputDialog('请描述您的内科问题：', '', '请输入你想咨询的问题');
    if (!question) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createInternalMedicineSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: question,
        });
        alert(`内科咨询创建成功！Session: ${session.session_id}`);
      } catch (e) {
        alert('内科咨询失败：' + e.message);
      }
    } else {
      alert('内科咨询：基于RAG知识库，\n建议您预约内科门诊进行详细检查。');
    }
  }

  async consultICU(npc) {
    alert('ICU（重症监护室）介绍：\n\nICU是医院危重病人的监护区域，\n配备专业设备和医护人员。\n\n如需咨询ICU相关问题，\n请通过API连接到后台系统。');
  }

  async requestICUConsultation(npc) {
    const info = await showTextInputDialog('请描述危重病人的情况：', '', '例如：意识状态、呼吸、血压等');
    if (!info) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createICUSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: info,
        });
        alert(`ICU会诊创建成功！Session: ${session.session_id}\nICU医生将进行评估。`);
      } catch (e) {
        alert('ICU会诊创建失败：' + e.message);
      }
    } else {
      alert('ICU会诊请求已记录。\n基于RAG知识库：\n1. 立即评估生命体征\n2. 准备ICU监护设备\n3. 联系ICU专科医生');
    }
  }

  closeDialogue() {
    gameState.dialogueActive = false;
    gameState.currentNPC = null;
    document.getElementById('dialogue-box').classList.add('hidden');
  }

  teleportToNpc(npc) {
    gameState.player.x = npc.x;
    gameState.player.y = npc.y - 1;
    gameState.currentRoom = npc.room;
    document.getElementById('current-room').textContent = ROOMS.find(r => r.id === npc.room)?.name || '未知';
  }
}

function showTextInputDialog(title, defaultValue = '', placeholder = '') {
  const modal = document.getElementById('input-modal');
  const titleEl = document.getElementById('input-modal-title');
  const inputEl = document.getElementById('input-modal-field');
  const cancelBtn = document.getElementById('input-modal-cancel');
  const confirmBtn = document.getElementById('input-modal-confirm');

  if (!modal || !titleEl || !inputEl || !cancelBtn || !confirmBtn) {
    return Promise.resolve(null);
  }

  titleEl.textContent = title;
  inputEl.value = defaultValue;
  inputEl.placeholder = placeholder;
  modal.classList.remove('hidden');
  inputEl.focus();
  inputEl.select();

  return new Promise((resolve) => {
    const cleanup = () => {
      modal.classList.add('hidden');
      confirmBtn.removeEventListener('click', onConfirm);
      cancelBtn.removeEventListener('click', onCancel);
      inputEl.removeEventListener('keydown', onKeyDown);
    };

    const onConfirm = () => {
      const value = inputEl.value.trim();
      cleanup();
      resolve(value || null);
    };

    const onCancel = () => {
      cleanup();
      resolve(null);
    };

    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        onConfirm();
      }
    };

    confirmBtn.addEventListener('click', onConfirm);
    cancelBtn.addEventListener('click', onCancel);
    inputEl.addEventListener('keydown', onKeyDown);
  });
}

// ============== UI更新 ==============
function updateUI() {
  document.getElementById('player-name').textContent = '村民';
  document.getElementById('current-room').textContent = ROOMS.find(r => r.id === gameState.currentRoom)?.name || '未知';
  document.getElementById('time-display').textContent = gameState.getTimeString();
  document.getElementById('weather-display').textContent = gameState.weather === 'sunny' ? '☀️ 晴天' : '⛅ 多云';
  
  const npcList = document.getElementById('npc-list');
  npcList.innerHTML = '';
  for (const npc of gameState.npcs) {
    const div = document.createElement('div');
    div.className = 'npc-item';
    div.innerHTML = `
      <div class="npc-avatar">${NPC_TEMPLATES[npc.template].emoji}</div>
      <div class="npc-info">
        <div class="npc-name">${npc.name}</div>
        <div class="npc-location">${ROOMS.find(r => r.id === npc.room)?.name || ''}</div>
      </div>
      <div class="npc-teleport-hint">点击传送</div>
    `;
    div.onclick = () => {
      gameLogic.teleportToNpc(npc);
    };
    npcList.appendChild(div);
  }
}

// ============== API Key设置 ==============
async function showApiKeyDialog() {
  const apiKey = await showTextInputDialog(
    '请输入 API Key（留空使用本地模拟）',
    gameState.apiKey || '',
    '例如：sk-xxxx'
  );
  if (apiKey === null) return;

  gameState.apiKey = apiKey.trim();
  if (backendClient) {
    backendClient.updateApiKey(gameState.apiKey || 'mock-key-001');
  }
  if (gameState.apiKey) {
    alert('API Key 已设置');
  } else {
    alert('已切换为本地模拟模式');
  }
}

// ============== 主循环 ==============
let gameState, renderer, gameLogic, backendClient;

function gameLoop(timestamp) {
  const deltaTime = timestamp - gameLogic.lastTime;
  gameLogic.lastTime = timestamp;
  
  gameLogic.update(deltaTime);
  
  renderer.clear();
  renderer.drawGround();
  
  for (const room of ROOMS) {
    renderer.drawRoom(room);
  }
  
  for (const npc of gameState.npcs) {
    renderer.drawNPC(npc);
    const dist = Math.sqrt(
      Math.pow(gameState.player.x - npc.x, 2) + 
      Math.pow(gameState.player.y - npc.y, 2)
    );
    if (dist < 2) {
      renderer.drawInteractionPrompt(npc);
    }
  }
  
  renderer.drawPlayer();
  
  const currentRoom = ROOMS.find(r => r.id === gameState.currentRoom);
  if (currentRoom && currentRoom.type !== 'main' && currentRoom.exits && currentRoom.exits.length > 0) {
    renderer.drawExitPrompt();
  }
  
  updateUI();
  
  requestAnimationFrame(gameLoop);
}

// ============== 初始化 ==============
async function init() {
  const canvas = document.getElementById('game-canvas');
  renderer = new Renderer(canvas);
  gameState = new GameState();
  gameLogic = new GameLogic();
  
  gameLogic.init();
  
  backendClient = createBackendClient({
    baseUrl: 'http://127.0.0.1:8799/api/v1',
    apiKey: 'mock-key-001',
  });
  
  try {
    await backendClient.health();
    gameState.apiConnected = true;
    console.log('API连接成功');
  } catch (e) {
    console.log('API未连接，游戏将以离线模式运行');
  }
  
  window.addEventListener('resize', () => renderer.resize());
  const apiSettingsBtn = document.getElementById('api-settings-btn');
  if (apiSettingsBtn) {
    apiSettingsBtn.addEventListener('click', () => {
      showApiKeyDialog();
    });
  }
  
  requestAnimationFrame(gameLoop);
  
  setTimeout(() => {
    showApiKeyDialog();
  }, 1000);
}

window.addEventListener('DOMContentLoaded', init);
