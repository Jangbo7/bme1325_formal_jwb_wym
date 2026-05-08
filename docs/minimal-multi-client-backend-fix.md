# 多人联调最小改动方案

## 目标
让两个人同时使用同一套后端时，不会互相覆盖病人、会话和流程状态。

## 当前问题
当前默认实现里有几个固定值，会把不同人的操作落到同一份数据上：

- 前端默认 `baseUrl` 指向同一个后端地址。
- 病人 ID 默认是 `P-self`。
- triage 会话在缺少 `session_id` 时回退到 `session-main`。
- 后端启动时默认会清空运行态数据，NPC 模拟器也默认开启。

## 最小改动

### 1. 前端改成“每个浏览器实例一个独立病人”
把所有 `patient_id = "P-self"` 的默认值改成浏览器本地生成的唯一 ID。

建议规则：

- 第一次打开页面时，在 `localStorage` 里生成并保存一个 `client_id`
- `patient_id = "P-" + client_id`
- 之后所有创建 visit / triage session / internal medicine session 的请求都使用这个 `patient_id`

这样两个人即使连的是同一个后端，也会落到不同的病人记录上。

需要改的地方：

- `scene/core/bootstrap.js`
- `scene_stardew/game.js`
- 任何 schema 或默认值里写死 `P-self` 的地方

### 2. 去掉 `session-main` 兜底
triage 里如果前端没传 `session_id`，不要再回退到 `session-main`。

规则改成：

- 前端不传 `session_id` 时，由后端生成 UUID
- 后端只负责保证 session 唯一，不再使用固定默认值

需要改的地方：

- `backend/app/agents/triage/graph.py`
- `scene/core/bootstrap.js`

### 3. 共享后端时关闭重置和模拟器
为了避免两个人一刷新就把数据清掉，建议把共享联调用的后端配置改成：

- `RESET_ON_SERVER_START=false`
- `SIMULATOR_ENABLED=false`

需要改的地方：

- `backend/.env` 或启动脚本
- 不建议改代码逻辑，直接改环境变量即可

## 可选项
如果两个人不是同一台机器，而是都访问一台共享后端，再额外做这一步：

- 后端监听 `0.0.0.0`
- 前端 `baseUrl` 改成后端机器的局域网 IP

## 不做的事
为了保持改动最小，这次不做以下事情：

- 不改数据库结构
- 不加登录系统
- 不加权限系统
- 不改事件总线或业务流程
- 不做前后端重构

## 验收标准

- 两个浏览器窗口同时打开时，生成的是两个不同的 `patient_id`
- 两边创建的 visit/session 不会互相覆盖
- 不再出现 `session-main` 作为默认会话
- 重启后端不会自动清空联调数据
- 关闭模拟器后，不会有后台 NPC 持续改动共享数据

## 交付建议
按这个顺序改最稳：

1. 先改前端 `patient_id`
2. 再去掉 `session-main`
3. 最后把 `RESET_ON_SERVER_START` 和 `SIMULATOR_ENABLED` 关掉

