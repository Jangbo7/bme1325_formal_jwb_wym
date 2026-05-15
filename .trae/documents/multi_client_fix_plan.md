# 多人联调问题修复实施计划

## 问题分析

当前实现存在以下问题，导致多人同时使用同一后端时出现冲突：

1. **固定的 patient_id**：前端默认使用 `P-self` 作为患者 ID，导致不同用户的操作落到同一份患者数据上
2. **固定的 session_id**：triage 会话在缺少 session_id 时回退到 `session-main`，导致会话冲突
3. **自动重置和模拟器**：后端启动时默认清空数据，NPC 模拟器持续修改共享数据

## 实施步骤

### 1. 前端实现独立 patient_id

**修改文件：** `scene/core/bootstrap.js`

**修改内容：**
- 在 localStorage 中生成并存储唯一的 client_id
- 将 `triageConversationState.patientId` 和 `doctorConversationState.patientId` 改为使用 `P-${client_id}`
- 移除 `session-main` 的硬编码

**修改文件：** `scene_stardew/game.js`

**修改内容：**
- 在 localStorage 中生成并存储唯一的 client_id
- 将所有 `patient_id: 'player_1'` 改为使用 `P-${client_id}`

### 2. 后端移除 session-main 兜底

**修改文件：** `backend/app/agents/triage/graph.py`

**修改内容：**
- 将第 50 行的 `session_id = work.get("session_id") or payload.get("session_id") or "session-main"` 改为生成 UUID
- 确保后端在前端未传 session_id 时生成唯一的会话 ID

### 3. 配置修改

**修改文件：** `backend/.env`

**修改内容：**
- 设置 `RESET_ON_SERVER_START=false`
- 设置 `SIMULATOR_ENABLED=false`

### 4. 网络配置（可选）

如果多用户在不同机器上访问同一后端：
- 确保后端监听 `0.0.0.0`
- 前端 `baseUrl` 改为后端机器的局域网 IP

## 技术实现细节

### 前端 client_id 生成

```javascript
// 在应用启动时生成 client_id
function getClientId() {
  let clientId = localStorage.getItem('client_id');
  if (!clientId) {
    clientId = crypto.randomUUID();
    localStorage.setItem('client_id', clientId);
  }
  return clientId;
}

// 使用 client_id 生成 patient_id
const clientId = getClientId();
const patientId = `P-${clientId}`;
```

### 后端 session_id 生成

```python
import uuid

# 生成唯一的 session_id
session_id = work.get("session_id") or payload.get("session_id") or str(uuid.uuid4())
```

## 验收标准

1. **独立患者 ID**：两个浏览器窗口同时打开时，生成不同的 `patient_id`
2. **会话隔离**：两边创建的 visit/session 不会互相覆盖
3. **无固定会话**：不再出现 `session-main` 作为默认会话
4. **数据持久**：重启后端不会自动清空联调数据
5. **无干扰**：关闭模拟器后，不会有后台 NPC 持续改动共享数据

## 实施顺序

1. 先修改前端 `patient_id` 逻辑
2. 再修改后端移除 `session-main` 兜底
3. 最后修改环境变量配置

## 风险评估

- **低风险**：修改仅涉及前端患者 ID 生成和后端会话 ID 生成，不涉及核心业务逻辑
- **向后兼容**：修改后的代码仍然支持现有 API 调用方式
- **可回滚**：如果出现问题，可通过恢复环境变量和代码文件快速回滚

## 预期效果

修改完成后，多个用户可以同时使用同一后端进行联调，不会互相干扰，解决 404 错误和数据覆盖问题。