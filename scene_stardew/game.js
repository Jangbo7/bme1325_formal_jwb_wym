// 鏄熼湶璋烽鏍煎尰闄㈡父鎴忎富閫昏緫
import { createBackendClient } from './api/client.js';

// ============== 閰嶇疆 ==============
const CONFIG = {
  TILE_SIZE: 48,
  PLAYER_SPEED: 20,
  CAMERA_LERP: 0.1,
};

const API_RUNTIME_CONFIG = (typeof window !== 'undefined' && (window.HOS_STARDEW_API || window.HOS_PRIVATE_API)) || {};

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

// ============== 鎴块棿瀹氫箟 ==============
const ROOMS = [
  { id: 'lobby', name: '鍖婚櫌澶у巺', x: 12, y: 10, w: 8, h: 6, type: 'main', exits: [{ dir: 'up', targetRoom: 'triage', targetX: 7, targetY: 9 }, { dir: 'left', targetRoom: 'icu', targetX: 9, targetY: 17 }, { dir: 'right', targetRoom: 'internal', targetX: 21, targetY: 17 }] },
  { id: 'triage', name: '闂ㄨ瘖', x: 4, y: 4, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'down', targetRoom: 'lobby', targetX: 16, targetY: 13 }] },
  { id: 'pharmacy', name: '鑽埧', x: 22, y: 4, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'down', targetRoom: 'lobby', targetX: 16, targetY: 13 }] },
  { id: 'icu', name: 'ICU', x: 4, y: 12, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'right', targetRoom: 'lobby', targetX: 13, targetY: 16 }] },
  { id: 'internal', name: '鍐呯', x: 22, y: 12, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'left', targetRoom: 'lobby', targetX: 19, targetY: 16 }] },
  { id: 'lab', name: '鍖栭獙瀹?, x: 12, y: 18, w: 6, h: 5, type: 'clinic', exits: [{ dir: 'up', targetRoom: 'lobby', targetX: 16, targetY: 15 }] },
  { id: 'garden', name: '鍚庤姳鍥?, x: 12, y: 25, w: 8, h: 6, type: 'outdoor', exits: [{ dir: 'up', targetRoom: 'lobby', targetX: 16, targetY: 15 }] },
];

// ============== NPC瀹氫箟 ==============
const NPC_TEMPLATES = {
  doctor: { emoji: '馃懆鈥嶁殨锔?, color: '#FFFFFF' },
  nurse: { emoji: '馃懇鈥嶁殨锔?, color: '#FFB6C1' },
  patient_male: { emoji: '馃懆', color: '#ADD8E6' },
  patient_female: { emoji: '馃懇', color: '#FFB6C1' },
  visitor: { emoji: '馃', color: '#98D8AA' },
};

// NPC澶氱瀵硅瘽鍐呭
const NPC_DIALOGUES = {
  triage: [
    '浣犲ソ锛屾湁浠€涔堜笉鑸掓湇鍚楋紵璇锋弿杩颁竴涓嬫偍鐨勭棁鐘躲€?,
    '娆㈣繋鏉ュ埌闂ㄨ瘖銆傝闂偍浠婂ぉ鏄潵鐪嬩粈涔堢梾鐨勶紵',
    '璇峰厛娴嬮噺涓€涓嬩綋娓╁拰琛€鍘嬶紝鎴戜細鏍规嵁鎮ㄧ殑鎯呭喌瀹夋帓灏辫瘖銆?,
  ],
  icu: [
    '閲嶇棁鐩戞姢瀹ら渶瑕佺壒娈婅鍙墠鑳借繘鍏ャ€傝闂偍鏈変粈涔堜簨锛?,
    'ICU鏄嵄閲嶇梾浜虹洃鎶ゅ尯鍩燂紝闈炴巿鏉冧汉鍛樹笉寰楄繘鍏ャ€?,
    '濡傛灉鎮ㄦ槸鐥呬汉瀹跺睘锛岃鍏堝埌鍓嶅彴鐧昏銆?,
  ],
  internal: [
    '鍐呯涓昏璇婃不鍚勭鍐呯鐤剧梾锛岃闂偍鍝噷涓嶈垝鏈嶏紵',
    '甯歌鍐呯鐤剧梾鍖呮嫭鎰熷啋鍙戠儳銆侀珮琛€鍘嬨€佺硸灏跨梾绛夈€?,
    '璇疯缁嗘弿杩颁竴涓嬫偍鐨勭棁鐘讹紝鎴戜細涓烘偍鍋氳缁嗚瘖鏂€?,
  ],
  pharmacy: [
    '璇峰嚭绀哄鏂瑰崟鍙栬嵂銆?,
    '鑽埧寮€鏀炬椂闂翠负鏃╀笂8鐐瑰埌鏅氫笂6鐐广€?,
    '濡傛湁鐤戦棶锛岃鍜ㄨ鍊肩彮鑽笀銆?,
  ],
  lobby_nurse: [
    '娆㈣繋鏉ュ埌鍖婚櫌锛佽闂渶瑕佷粈涔堝府鍔╋紵',
    '鎮ㄥソ锛佸鏋滄偍闇€瑕佹寕鍙凤紝璇峰埌鐩稿簲绉戝銆?,
    '璇锋敞鎰忎繚鎸佸畨闈欙紝杩欐槸鍖荤枟鍦烘墍銆?,
  ],
  lobby_patient: [
    '鎴戝湪杩欓噷绛夋鏌ョ粨鏋滐紝宸茬粡绛変簡涓€浼氬効浜?..',
    '鍖荤敓璇磋繕瑕佸啀绛夌瓑锛岀粨鏋滃嚭鏉ヤ細閫氱煡鎴戠殑銆?,
    '杩欏鍖婚櫌鏈嶅姟涓嶉敊锛屽氨鏄汉鏈夌偣澶氥€?,
  ],
  garden_visitor: [
    '鑺卞洯绌烘皵鐪熷ソ锛岀梾鎯呭ソ澶氫簡銆?,
    '鍑烘潵閫忛€忔皵锛屾劅瑙夋暣涓汉閮界簿绁炲浜嗐€?,
    '杩欓噷鐜浼橀泤锛屽緢閫傚悎浼戝吇銆?,
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
  
  const dialogues = NPC_DIALOGUES[category] || ['浣犲ソ锛?];
  return dialogues[dialogueIndex % dialogues.length];
}

const NPCs = [
  { id: 'npc_1', name: '寮犲尰鐢?, template: 'doctor', room: 'triage', x: 5, y: 6 },
  { id: 'npc_2', name: '鏉庢姢澹?, template: 'nurse', room: 'lobby', x: 14, y: 12 },
  { id: 'npc_3', name: '鐜嬩富浠?, template: 'doctor', room: 'icu', x: 5, y: 13 },
  { id: 'npc_4', name: '鍒樺尰鐢?, template: 'doctor', room: 'internal', x: 23, y: 13 },
  { id: 'npc_5', name: '璧佃嵂甯?, template: 'doctor', room: 'pharmacy', x: 23, y: 6 },
  { id: 'npc_6', name: '閽卞厛鐢?, template: 'patient_male', room: 'lobby', x: 16, y: 13 },
  { id: 'npc_7', name: '瀛欏コ澹?, template: 'patient_female', room: 'garden', x: 14, y: 28 },
];

// ============== 娓告垙鐘舵€?==============
function getClientId() {
  let clientId = localStorage.getItem('client_id');
  if (!clientId) {
    clientId = crypto.randomUUID();
    localStorage.setItem('client_id', clientId);
  }
  return clientId;
}

const clientId = getClientId();
const patientId = `P-${clientId}`;

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
    this.isNpcPanelOpen = false;
    this.isStatusPanelOpen = false;
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
    const period = hours < 12 ? '涓婂崍' : '涓嬪崍';
    const displayHour = hours > 12 ? hours - 12 : hours;
    return `绗?${this.day} 澶?- ${period} ${displayHour}:${minutes.toString().padStart(2, '0')}`;
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

// ============== 娓叉煋鍣?==============
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

    // 鐢婚棬
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

    // 鐢诲嚭鍙ｆ爣璁?
    ctx.fillStyle = '#FFD700';
    ctx.font = 'bold 12px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('鍑哄彛', offsetX + room.w * CONFIG.TILE_SIZE / 2, offsetY + room.h * CONFIG.TILE_SIZE + 15);

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
    ctx.fillText('鎸?E 瀵硅瘽', screenX + 25, screenY + 19);
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
    ctx.fillText('鎸?Q 璧板嚭鎴块棿', this.canvas.width / 2, 100);
  }
}

// ============== 娓告垙閫昏緫 ==============
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
      if (e.key === 'Escape') this.handleEscape();
    });
    window.addEventListener('keyup', (e) => {
      this.keys[e.key.toLowerCase()] = false;
    });
  }

  handleEscape() {
    if (isInputModalOpen()) return;
    if (closeFloatingPanels()) return;
    if (gameState.dialogueActive) this.closeDialogue();
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
        this.addDialogueOption('鎴戣鎸傚彿', () => this.requestRegistration(npc));
        this.addDialogueOption('鎴戞湁鐥囩姸瑕佹弿杩?, () => this.describeSymptoms(npc));
      } else if (npc.room === 'internal') {
        this.addDialogueOption('鎴戣鍐呯闂瘖', () => this.requestInternalMedicine(npc));
        this.addDialogueOption('鎴戞湁鍐呯闂鍜ㄨ', () => this.consultInternal(npc));
      } else if (npc.room === 'icu') {
        this.addDialogueOption('鎴戞兂浜嗚ВICU鎯呭喌', () => this.consultICU(npc));
        this.addDialogueOption('鎴戞湁鍗遍噸鐥呬汉鍜ㄨ', () => this.requestICUConsultation(npc));
      }
    }
    this.addDialogueOption('璋㈣阿锛屽啀瑙?, () => this.closeDialogue());
    
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
    const symptoms = await showTextInputDialog('璇锋弿杩版偍鐨勭棁鐘讹細', '', '渚嬪锛氬彂鐑с€佸挸鍡戒袱澶?);
    if (!symptoms) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createTriageSession({
          patient_id: patientId,
          name: '鐜╁',
          chief_complaint: symptoms,
        });
        alert(`鍒嗚瘖鎴愬姛锛丼ession: ${session.session_id}\n璇峰埌鐩稿簲绉戝灏辫瘖銆俙);
      } catch (e) {
        alert('鍒嗚瘖澶辫触锛屽皢浣跨敤鏈湴妯℃嫙鍒嗚瘖銆?);
        this.mockTriageResult(symptoms);
      }
    } else {
      this.mockTriageResult(symptoms);
    }
  }

  mockTriageResult(symptoms) {
    const symptomsLower = symptoms.toLowerCase();
    let dept = '鍐呯';
    let level = 3;
    
    if (symptomsLower.includes('鍙戠儳') || symptomsLower.includes('鎰熷啋') || symptomsLower.includes('鍜冲椊')) {
      dept = '鍐呯';
      level = 3;
    } else if (symptomsLower.includes('楠ㄦ姌') || symptomsLower.includes('澶栦激') || symptomsLower.includes('鍑鸿')) {
      dept = '鎬ヨ瘖';
      level = 2;
    } else if (symptomsLower.includes('蹇冭剰') || symptomsLower.includes('鑳哥棝') || symptomsLower.includes('鍛煎惛鍥伴毦')) {
      dept = 'ICU';
      level = 1;
    }
    
    alert(`妯℃嫙鍒嗚瘖缁撴灉:\n绉戝: ${dept}\n浼樺厛绾? ${level}\n璇峰埌鐩稿簲绉戝灏辫瘖銆俙);
  }

  async describeSymptoms(npc) {
    const symptoms = await showTextInputDialog('璇疯缁嗘弿杩版偍鐨勭棁鐘讹細', '', '灏介噺鎻忚堪鎸佺画鏃堕棿銆佺柤鐥涚▼搴︺€佷即闅忕棁鐘?);
    if (!symptoms || !backendClient || !gameState.apiKey) {
      if (!backendClient || !gameState.apiKey) {
        alert('API鏈繛鎺ユ垨鏈缃瓵PI Key锛屽皢浣跨敤鏈湴妯℃嫙璇婃柇銆?);
      }
      return;
    }
    
    try {
      const session = await backendClient.createTriageSession({
        patient_id: patientId,
        name: '鐜╁',
        chief_complaint: symptoms,
      });
      alert(`鐥囩姸鐧昏鎴愬姛锛丼ession: ${session.session_id}`);
    } catch (e) {
      alert('鐥囩姸鐧昏澶辫触锛? + e.message);
    }
  }

  async requestInternalMedicine(npc) {
    const symptoms = await showTextInputDialog('璇锋弿杩版偍鐨勫唴绉戠棁鐘讹細', '', '渚嬪锛氬ご鐥涖€佽兏闂枫€佷箯鍔?);
    if (!symptoms) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createInternalMedicineSession({
          patient_id: patientId,
          name: '鐜╁',
          chief_complaint: symptoms,
        });
        alert(`鍐呯闂瘖鍒涘缓鎴愬姛锛丼ession: ${session.session_id}\n鍖荤敓灏嗕负鎮ㄨ瘖鏂€俙);
      } catch (e) {
        alert('鍐呯闂瘖澶辫触锛? + e.message);
      }
    } else {
      alert('鍐呯闂瘖锛氭偍鐨勭棁鐘跺凡璁板綍銆俓n鏍规嵁RAG鐭ヨ瘑搴撳缓璁細\n1. 璇︾粏妫€鏌n2. 琛€娑插寲楠孿n3. 鍚庣画娌荤枟');
    }
  }

  async consultInternal(npc) {
    const question = await showTextInputDialog('璇锋弿杩版偍鐨勫唴绉戦棶棰橈細', '', '璇疯緭鍏ヤ綘鎯冲挩璇㈢殑闂');
    if (!question) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createInternalMedicineSession({
          patient_id: patientId,
          name: '鐜╁',
          chief_complaint: question,
        });
        alert(`鍐呯鍜ㄨ鍒涘缓鎴愬姛锛丼ession: ${session.session_id}`);
      } catch (e) {
        alert('鍐呯鍜ㄨ澶辫触锛? + e.message);
      }
    } else {
      alert('鍐呯鍜ㄨ锛氬熀浜嶳AG鐭ヨ瘑搴擄紝\n寤鸿鎮ㄩ绾﹀唴绉戦棬璇婅繘琛岃缁嗘鏌ャ€?);
    }
  }

  async consultICU(npc) {
    alert('ICU锛堥噸鐥囩洃鎶ゅ锛変粙缁嶏細\n\nICU鏄尰闄㈠嵄閲嶇梾浜虹殑鐩戞姢鍖哄煙锛孿n閰嶅涓撲笟璁惧鍜屽尰鎶や汉鍛樸€俓n\n濡傞渶鍜ㄨICU鐩稿叧闂锛孿n璇烽€氳繃API杩炴帴鍒板悗鍙扮郴缁熴€?);
  }

  async requestICUConsultation(npc) {
    const info = await showTextInputDialog('璇锋弿杩板嵄閲嶇梾浜虹殑鎯呭喌锛?, '', '渚嬪锛氭剰璇嗙姸鎬併€佸懠鍚搞€佽鍘嬬瓑');
    if (!info) return;
    
    if (backendClient && gameState.apiKey) {
      try {
        const session = await backendClient.createICUSession({
          patient_id: patientId,
          name: '鐜╁',
          chief_complaint: info,
        });
        alert(`ICU浼氳瘖鍒涘缓鎴愬姛锛丼ession: ${session.session_id}\nICU鍖荤敓灏嗚繘琛岃瘎浼般€俙);
      } catch (e) {
        alert('ICU浼氳瘖鍒涘缓澶辫触锛? + e.message);
      }
    } else {
      alert('ICU浼氳瘖璇锋眰宸茶褰曘€俓n鍩轰簬RAG鐭ヨ瘑搴擄細\n1. 绔嬪嵆璇勪及鐢熷懡浣撳緛\n2. 鍑嗗ICU鐩戞姢璁惧\n3. 鑱旂郴ICU涓撶鍖荤敓');
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
    document.getElementById('current-room').textContent = ROOMS.find(r => r.id === npc.room)?.name || 'æœªçŸ¥';
    setNpcPanelOpen(false);
  }
}

function setNpcPanelOpen(open) {
  gameState.isNpcPanelOpen = open;
  const shell = document.getElementById('npc-panel-shell');
  const toggle = document.getElementById('npc-panel-toggle');
  const panel = document.getElementById('npc-panel');
  if (!shell || !toggle || !panel) return;

  shell.classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', String(open));
  panel.setAttribute('aria-hidden', String(!open));
}

function setStatusPanelOpen(open) {
  gameState.isStatusPanelOpen = open;
  const shell = document.getElementById('status-panel-shell');
  const toggle = document.getElementById('status-toggle');
  const popover = document.getElementById('status-popover');
  if (!shell || !toggle || !popover) return;

  shell.classList.toggle('open', open);
  toggle.setAttribute('aria-expanded', String(open));
  popover.setAttribute('aria-hidden', String(!open));
}

function toggleNpcPanel() {
  setNpcPanelOpen(!gameState.isNpcPanelOpen);
}

function toggleStatusPanel() {
  setStatusPanelOpen(!gameState.isStatusPanelOpen);
}

function closeFloatingPanels() {
  let closed = false;
  if (gameState.isNpcPanelOpen) {
    setNpcPanelOpen(false);
    closed = true;
  }
  if (gameState.isStatusPanelOpen) {
    setStatusPanelOpen(false);
    closed = true;
  }
  return closed;
}

function isInputModalOpen() {
  const modal = document.getElementById('input-modal');
  return Boolean(modal && !modal.classList.contains('hidden'));
}

function bindPanelInteractions() {
  const npcToggle = document.getElementById('npc-panel-toggle');
  const statusToggle = document.getElementById('status-toggle');
  const npcShell = document.getElementById('npc-panel-shell');
  const statusShell = document.getElementById('status-panel-shell');

  if (npcToggle) {
    npcToggle.addEventListener('click', (event) => {
      event.stopPropagation();
      toggleNpcPanel();
    });
  }

  if (statusToggle) {
    statusToggle.addEventListener('click', (event) => {
      event.stopPropagation();
      toggleStatusPanel();
    });
  }

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (gameState.isNpcPanelOpen && npcShell && !npcShell.contains(target)) {
      setNpcPanelOpen(false);
    }
    if (gameState.isStatusPanelOpen && statusShell && !statusShell.contains(target)) {
      setStatusPanelOpen(false);
    }
  });
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

// ============== UI鏇存柊 ==============
function updateUI() {
  const currentRoomName = ROOMS.find(r => r.id === gameState.currentRoom)?.name || '未知';
  const weatherText = gameState.weather === 'sunny' ? '☀ 晴天' : '☁ 多云';
  const weatherIcon = gameState.weather === 'sunny' ? '☀' : '☁';

  const currentRoomEl = document.getElementById('current-room');
  const timeDisplayEl = document.getElementById('time-display');
  const weatherDisplayEl = document.getElementById('weather-display');
  const statusIconEl = document.getElementById('status-toggle-icon');

  if (currentRoomEl) currentRoomEl.textContent = currentRoomName;
  if (timeDisplayEl) timeDisplayEl.textContent = gameState.getTimeString();
  if (weatherDisplayEl) weatherDisplayEl.textContent = weatherText;
  if (statusIconEl) statusIconEl.textContent = weatherIcon;

  const npcList = document.getElementById('npc-list');
  if (!npcList) return;

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

// ============== API Key璁剧疆 ==============
async function showApiKeyDialog() {
  const apiKey = await showTextInputDialog(
    '璇疯緭鍏?API Key锛堢暀绌轰娇鐢ㄦ湰鍦版ā鎷燂級',
    gameState.apiKey || '',
    '渚嬪锛歴k-xxxx'
  );
  if (apiKey === null) return;

  gameState.apiKey = apiKey.trim();
  if (backendClient) {
    backendClient.updateApiKey(gameState.apiKey || 'mock-key-001');
  }
  if (gameState.apiKey) {
    alert('API Key 宸茶缃?);
  } else {
    alert('宸插垏鎹负鏈湴妯℃嫙妯″紡');
  }
}

// ============== 涓诲惊鐜?==============
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

// ============== 鍒濆鍖?==============
async function init() {
  const canvas = document.getElementById('game-canvas');
  renderer = new Renderer(canvas);
  gameState = new GameState();
  gameLogic = new GameLogic();
  
  gameLogic.init();
  
  backendClient = createBackendClient({
    baseUrl: API_RUNTIME_CONFIG.baseUrl || 'http://127.0.0.1:8787/api/v1',
    apiKey: API_RUNTIME_CONFIG.apiKey || 'mock-key-001',
  });
  
  try {
    await backendClient.health();
    gameState.apiConnected = true;
    console.log('API杩炴帴鎴愬姛');
  } catch (e) {
    console.log('API鏈繛鎺ワ紝娓告垙灏嗕互绂荤嚎妯″紡杩愯');
  }
  
  window.addEventListener('resize', () => renderer.resize());
  bindPanelInteractions();
  setNpcPanelOpen(false);
  setStatusPanelOpen(false);
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

