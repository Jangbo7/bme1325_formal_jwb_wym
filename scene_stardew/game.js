// 星露谷风格医院游戏主逻辑
import { createBackendClient } from './api/client.js';

// ============== 配置 ==============
const CONFIG = {
  TILE_SIZE: 48,
  PLAYER_SPEED: 200,
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
  TEXT_DARK: '#3D2817',
  TEXT_LIGHT: '#FFF8DC',
  HEALTH_RED: '#E74C3C',
  HEALTH_GREEN: '#27AE60',
  WATER_BLUE: '#5DADE2',
};

// ============== 房间定义 ==============
const ROOMS = [
  { id: 'lobby', name: '医院大厅', x: 12, y: 10, w: 8, h: 6, type: 'main' },
  { id: 'triage', name: '门诊', x: 4, y: 4, w: 6, h: 5, type: 'clinic' },
  { id: 'pharmacy', name: '药房', x: 22, y: 4, w: 6, h: 5, type: 'clinic' },
  { id: 'icu', name: 'ICU', x: 4, y: 12, w: 6, h: 5, type: 'clinic' },
  { id: 'internal', name: '内科', x: 22, y: 12, w: 6, h: 5, type: 'clinic' },
  { id: 'lab', name: '化验室', x: 12, y: 18, w: 6, h: 5, type: 'clinic' },
  { id: 'garden', name: '后花园', x: 12, y: 25, w: 8, h: 6, type: 'outdoor' },
];

// ============== NPC定义 ==============
const NPC_TEMPLATES = {
  doctor: { emoji: '👨‍⚕️', color: '#FFFFFF' },
  nurse: { emoji: '👩‍⚕️', color: '#FFB6C1' },
  patient_male: { emoji: '👨', color: '#ADD8E6' },
  patient_female: { emoji: '👩', color: '#FFB6C1' },
  visitor: { emoji: '🧑', color: '#98D8AA' },
};

const NPCs = [
  { id: 'npc_1', name: '张医生', template: 'doctor', room: 'triage', x: 5, y: 6, dialogue: '你好，有什么不舒服吗？' },
  { id: 'npc_2', name: '李护士', template: 'nurse', room: 'lobby', x: 14, y: 12, dialogue: '欢迎来到医院！' },
  { id: 'npc_3', name: '王主任', template: 'doctor', room: 'icu', x: 5, y: 13, dialogue: '重症监护室，需要特殊许可才能进入。' },
  { id: 'npc_4', name: '刘医生', template: 'doctor', room: 'internal', x: 23, y: 13, dialogue: '内科常见疾病，我来帮你看看。' },
  { id: 'npc_5', name: '赵药师', template: 'doctor', room: 'pharmacy', x: 23, y: 6, dialogue: '请出示处方单取药。' },
  { id: 'npc_6', name: '钱先生', template: 'patient_male', room: 'lobby', x: 16, y: 13, dialogue: '我在这里等检查结果...' },
  { id: 'npc_7', name: '孙女士', template: 'patient_female', room: 'garden', x: 14, y: 28, dialogue: '花园空气真好，病情好多了。' },
];

// ============== 游戏状态 ==============
class GameState {
  constructor() {
    this.player = { x: 16, y: 13, direction: 'down' };
    this.camera = { x: 0, y: 0 };
    this.currentRoom = 'lobby';
    this.npcs = [...NPCs];
    this.dialogueActive = false;
    this.currentNPC = null;
    this.menuOpen = false;
    this.apiConnected = false;
    this.day = 1;
    this.time = 9 * 60; // 9:00 in minutes
    this.weather = 'sunny';
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

    // 地板
    ctx.fillStyle = COLORS.WALL_BROWN;
    ctx.fillRect(offsetX, offsetY, room.w * CONFIG.TILE_SIZE, room.h * CONFIG.TILE_SIZE);
    
    // 地板纹理
    for (let y = 0; y < room.h; y++) {
      for (let x = 0; x < room.w; x++) {
        ctx.strokeStyle = 'rgba(139, 69, 19, 0.2)';
        ctx.strokeRect(offsetX + x * CONFIG.TILE_SIZE, offsetY + y * CONFIG.TILE_SIZE, CONFIG.TILE_SIZE, CONFIG.TILE_SIZE);
      }
    }

    // 墙壁
    ctx.fillStyle = COLORS.DARK_BROWN;
    // 上墙
    ctx.fillRect(offsetX, offsetY - 40, room.w * CONFIG.TILE_SIZE, 40);
    // 下墙
    ctx.fillRect(offsetX, offsetY + room.h * CONFIG.TILE_SIZE - 20, room.w * CONFIG.TILE_SIZE, 20);
    // 左墙
    ctx.fillRect(offsetX - 20, offsetY, 20, room.h * CONFIG.TILE_SIZE);
    // 右墙
    ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE, offsetY, 20, room.h * CONFIG.TILE_SIZE);

    // 门
    const doorWidth = CONFIG.TILE_SIZE * 1.5;
    const doorHeight = CONFIG.TILE_SIZE * 2;
    ctx.fillStyle = COLORS.WOOD_BROWN;
    
    // 根据房间位置画门
    if (room.type === 'main') {
      // 大厅的门朝上
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2, offsetY - doorHeight + 20, doorWidth, doorHeight);
      ctx.fillStyle = COLORS.WINDOW_BLUE;
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2 + 5, offsetY - doorHeight + 25, doorWidth - 10, doorHeight - 30);
    } else {
      // 其他房间门朝下
      ctx.fillRect(offsetX + room.w * CONFIG.TILE_SIZE / 2 - doorWidth / 2, offsetY + room.h * CONFIG.TILE_SIZE - 10, doorWidth, doorHeight);
    }

    // 屋顶
    ctx.fillStyle = COLORS.ROOF_RED;
    ctx.beginPath();
    ctx.moveTo(offsetX - 20, offsetY);
    ctx.lineTo(offsetX + room.w * CONFIG.TILE_SIZE / 2, offsetY - 60);
    ctx.lineTo(offsetX + room.w * CONFIG.TILE_SIZE + 20, offsetY);
    ctx.closePath();
    ctx.fill();

    // 房间名称标签
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

    // 身体
    ctx.fillStyle = '#4169E1';
    ctx.fillRect(screenX + 12, screenY + 20, 24, 28);
    
    // 头
    ctx.fillStyle = '#FFDAB9';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 15, 14, 0, Math.PI * 2);
    ctx.fill();
    
    // 头发
    ctx.fillStyle = '#8B4513';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 10, 14, Math.PI, 0);
    ctx.fill();
    
    // 眼睛
    ctx.fillStyle = '#000';
    if (gameState.player.direction === 'up') {
      // 背对 - 不画眼睛
    } else {
      ctx.fillRect(screenX + 18, screenY + 12, 3, 3);
      ctx.fillRect(screenX + 27, screenY + 12, 3, 3);
    }

    // 腿
    ctx.fillStyle = '#2F4F4F';
    ctx.fillRect(screenX + 14, screenY + 48, 8, 12);
    ctx.fillRect(screenX + 26, screenY + 48, 8, 12);
  }

  drawNPC(npc) {
    const { ctx } = this;
    const template = NPC_TEMPLATES[npc.template];
    const screenX = npc.x * CONFIG.TILE_SIZE - gameState.camera.x;
    const screenY = npc.y * CONFIG.TILE_SIZE - gameState.camera.y;

    // 阴影
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.beginPath();
    ctx.ellipse(screenX + 24, screenY + 60, 16, 6, 0, 0, Math.PI * 2);
    ctx.fill();

    // 身体
    ctx.fillStyle = template.color;
    ctx.fillRect(screenX + 10, screenY + 22, 28, 26);
    
    // 头
    ctx.fillStyle = '#FFDAB9';
    ctx.beginPath();
    ctx.arc(screenX + 24, screenY + 15, 13, 0, Math.PI * 2);
    ctx.fill();

    // 表情
    ctx.fillStyle = '#000';
    ctx.fillRect(screenX + 18, screenY + 12, 3, 3);
    ctx.fillRect(screenX + 27, screenY + 12, 3, 3);
    ctx.fillStyle = '#E74C3C';
    ctx.beginPath();
    ctx.arc(screenX + 16, screenY + 18, 3, 0, Math.PI * 2);
    ctx.arc(screenX + 32, screenY + 18, 3, 0, Math.PI * 2);
    ctx.fill();

    // 名称标签
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
      if (e.key === 'Escape') this.closeDialogue();
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
      
      // 简单的碰撞检测
      if (this.canMoveTo(newX, newY)) {
        gameState.player.x = newX;
        gameState.player.y = newY;
      }
      
      // 更新时间
      gameState.updateTime(deltaTime / 60000 * 10); // 1秒游戏时间 = 10分钟
    }

    // 更新相机
    const targetX = gameState.player.x * CONFIG.TILE_SIZE - renderer.canvas.width / 2;
    const targetY = gameState.player.y * CONFIG.TILE_SIZE - renderer.canvas.height / 2;
    gameState.camera.x += (targetX - gameState.camera.x) * CONFIG.CAMERA_LERP;
    gameState.camera.y += (targetY - gameState.camera.y) * CONFIG.CAMERA_LERP;

    // 更新当前位置
    this.updateCurrentRoom();
  }

  canMoveTo(x, y) {
    // 边界检测
    if (x < 0 || x > 30 || y < 0 || y > 33) return false;
    
    // 房间内检测
    for (const room of ROOMS) {
      if (x >= room.x && x < room.x + room.w && y >= room.y && y < room.y + room.h) {
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
    const px = gameState.player.x;
    const py = gameState.player.y;
    
    // 检查相邻的NPC
    for (const npc of gameState.npcs) {
      const dist = Math.sqrt(Math.pow(px - npc.x, 2) + Math.pow(py - npc.y, 2));
      if (dist < 2) {
        this.startDialogue(npc);
        return;
      }
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
    textEl.textContent = npc.dialogue;
    
    // 根据NPC类型设置选项
    optionsEl.innerHTML = '';
    if (npc.template === 'doctor') {
      this.addDialogueOption('我要挂号', () => this.requestRegistration(npc));
      this.addDialogueOption('我有症状要描述', () => this.describeSymptoms(npc));
    }
    this.addDialogueOption('谢谢，再见', () => this.closeDialogue());
    
    dialogueBox.classList.remove('hidden');
  }

  addDialogueOption(text, callback) {
    const btn = document.createElement('button');
    btn.className = 'dialogue-option';
    btn.textContent = text;
    btn.onclick = () => {
      callback();
      this.closeDialogue();
    };
    document.getElementById('dialogue-options').appendChild(btn);
  }

  async requestRegistration(npc) {
    alert(`正在连接到 ${npc.name} 的挂号系统...`);
    if (backendClient) {
      try {
        await backendClient.createTriageSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: '需要挂号',
        });
        alert('挂号成功！请前往相应科室就诊。');
      } catch (e) {
        alert('挂号失败：' + e.message);
      }
    }
  }

  async describeSymptoms(npc) {
    const symptoms = prompt('请描述您的症状：');
    if (symptoms && backendClient) {
      try {
        const session = await backendClient.createTriageSession({
          patient_id: 'player_1',
          name: '玩家',
          chief_complaint: symptoms,
        });
        alert(`挂号成功！Session: ${session.session_id}`);
      } catch (e) {
        alert('挂号失败：' + e.message);
      }
    }
  }

  closeDialogue() {
    gameState.dialogueActive = false;
    gameState.currentNPC = null;
    document.getElementById('dialogue-box').classList.add('hidden');
  }
}

// ============== UI更新 ==============
function updateUI() {
  document.getElementById('player-name').textContent = '村民';
  document.getElementById('current-room').textContent = ROOMS.find(r => r.id === gameState.currentRoom)?.name || '未知';
  document.getElementById('time-display').textContent = gameState.getTimeString();
  document.getElementById('weather-display').textContent = gameState.weather === 'sunny' ? '☀️ 晴天' : '⛅ 多云';
  
  // 更新NPC列表
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
    `;
    div.onclick = () => {
      gameState.player.x = npc.x;
      gameState.player.y = npc.y - 1;
    };
    npcList.appendChild(div);
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
  
  // 初始化后端API客户端
  backendClient = createBackendClient({
    baseUrl: 'http://localhost:1897/api/v1',
    apiKey: 'test-key',
  });
  
  // 测试API连接
  try {
    await backendClient.health();
    gameState.apiConnected = true;
    console.log('API连接成功');
  } catch (e) {
    console.log('API未连接，游戏将以离线模式运行');
  }
  
  window.addEventListener('resize', () => renderer.resize());
  
  requestAnimationFrame(gameLoop);
}

window.addEventListener('DOMContentLoaded', init);
