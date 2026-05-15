# A组契约落地实现说明（阶段版）

## 本次范围
- 聚焦 `scene + encounters + 事件镜像`，不包含 OpenEMR 联调。
- 新增 `encounter` 契约接口与转诊接口。
- 在后端保留原 `visit` 流程兼容层，`scene` 优先走 `encounter` 入口。
- 新增 SSE 事件流与 Redis Pub/Sub 镜像桥（可开关）。

## 后端改动摘要
- 新增 ID 工具：
  - `patient_id`: `P-{8位小写hex}`
  - `encounter_id`: `E-{YYYYMMDDHHmmss}-{4位小写hex}`（UTC+8 格式）
- 新增 API：
  - `POST /api/v1/encounters`
  - `GET /api/v1/encounters/{encounter_id}`
  - `POST /api/v1/encounters/{encounter_id}/transfer`
  - `GET /api/v1/events/stream`（SSE）
- 事件桥：
  - 在原 `EventBus` 增加 `tap`，不破坏既有订阅者。
  - `HospitalEventBridge` 把内部事件映射为全院契约 envelope。
  - 可选 Redis 镜像发布到 `hospital.<domain>.<event>`。
- 状态补充：
  - 增加 `transferring` 访问状态，支持转诊中间态。

## scene 前端改动摘要
- 玩家 `patient_id` 改为契约格式生成（从 `client_id` 归一化为 8 位 hex）。
- 就诊创建优先调用 `POST /api/v1/encounters`，失败时降级到旧 `visits`。
- 新增事件订阅模块，连接 `GET /api/v1/events/stream`：
  - 已处理关键事件提示：`encounter.opened`、`patient.registered`、`patient.triaged`、`patient.transferred`、`encounter.consultation_started`、`encounter.consultation_completed`
  - 未实现事件走占位日志，不阻断界面
- 继续保留轮询 `pollBackendStatuses` 作为降级路径。

## 配置项（新增）
在 `backend/.env` 可配置：
- `REDIS_MIRROR_ENABLED`
- `EVENT_PRODUCER`
- `HOSPITAL_REDIS_HOST`
- `HOSPITAL_REDIS_PORT`
- `HOSPITAL_REDIS_DB`
- `HOSPITAL_REDIS_PASSWORD`
- `HOSPITAL_REDIS_CHANNEL_PREFIX`
- `HOSPITAL_REDIS_DURABLE_STREAM_ENABLED`
- `HOSPITAL_REDIS_DURABLE_STREAM_KEY`

## 兼容性说明
- 旧 `/api/v1/visits*` 与 triage/internal_medicine 流程未移除。
- 当前仓库仍保留少量历史兼容 ID（如 `P-self`）供旧流程与回归测试使用；新建患者与新建 encounter 已按契约格式生成。
