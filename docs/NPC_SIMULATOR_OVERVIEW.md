# 模拟病人系统（NPC Simulator）实现说明

## 目标

这个模拟器用于压测与联调：

1. 定时生成 NPC 病人。
2. 定时推进 NPC 病人的就诊流程（不渲染实体）。
3. 在前端排队面板中可见 NPC 名字。
4. 约束：同时活跃的模拟病人最多 2 个。

## 关键约束

- 活跃 NPC 定义：`patient_id` 前缀为 `P-NPC-`，且 `lifecycle_state` 不在 `completed/cancelled/error`。
- 上限策略：最多 2 个活跃 NPC。达到上限时，本轮 tick 不再创建新 NPC。
- 释放策略：当 NPC 完成流程后，会释放活跃名额，后续 tick 可以再生成新 NPC。

## 主要模块

- `backend/app/services/npc_simulator.py`
  - `NpcPatientSimulator`
  - 负责 spawn + tick + 状态推进。
- `backend/app/main.py`
  - 在容器中注入模拟器。
  - 在 FastAPI startup/shutdown 生命周期启动/停止后台线程。
- `backend/app/config.py`
  - 新增模拟器配置项（开关、tick 间隔、spawn 间隔、活跃上限、等待时长）。

## NPC 基础资料（archetype）

每次创建 NPC 时，从 archetype 列表选型，写入：

- 年龄
- 症状标签（symptom_tags）
- 目标科室（target_department）
- 优先级、分诊级别

资料保存策略：

- 写入 `visit.data_json` 中的 `simulator` 区块。
- 同步写入患者 `triage_note`，便于调试与日志排查。

## 流程导演（tick）

每个 tick 做两件事：

1. `spawn_if_needed`
   - 若活跃 NPC < 2 且满足生成间隔，则创建 1 个 NPC。
2. `advance_active_patients`
   - 按当前 patient/visit 状态推进：
     - `TRIAGED -> REGISTERED`（创建队列票）
     - `REGISTERED -> WAITING_CONSULTATION`（等待阈值后叫号）
     - `WAITING_CONSULTATION -> IN_CONSULTATION`
     - `IN_CONSULTATION -> COMPLETED`（达到咨询时长后完成）

所有推进都走既有状态机约束（patient/visit state machine），避免跳转非法状态。

## 与现有系统的交互关系

- 与患者系统：复用 `PatientRepository` 创建/更新患者。
- 与就诊系统：复用 `VisitRepository` 与 `VisitStateMachine`。
- 与排队系统：复用 `QueueRepository` 创建、叫号、完成票据。
- 与会话系统：写入 triage/internal medicine 的 session id 到 visit data，保持与当前 patient view 路由逻辑兼容。
- 与事件系统：发布 `PATIENT_STATE_CHANGED`、`VISIT_STATE_CHANGED`、`QUEUE_TICKET_CALLED`，保持审计与投影一致。

## 前端表现（当前阶段）

- 不渲染 NPC 实体。
- 仅在队列面板显示 NPC 名字。
- 后端在 `/api/v1/queues` 的 ticket 中提供 `patient_name`；前端 `scene/queue/runtime.js` 读取并显示。

## 配置项

- `SIMULATOR_ENABLED`：是否启用模拟器。
- `SIMULATOR_TICK_SECONDS`：tick 间隔。
- `SIMULATOR_SPAWN_INTERVAL_SECONDS`：生成间隔。
- `SIMULATOR_MAX_ACTIVE_PATIENTS`：活跃上限（当前默认 2）。
- `SIMULATOR_QUEUE_WAIT_SECONDS`：注册后等待叫号时长。
- `SIMULATOR_CONSULT_SECONDS`：诊间停留时长。

## 测试覆盖

新增测试建议与已实现方向：

- 活跃上限不超过 2。
- 完成后可再生成，且仍不超过上限。
- 队列视图返回并可消费 `patient_name`。

以上可保证“定时生成 + 定时推进 + 最多2个活跃NPC + 队列可见名字”的闭环。