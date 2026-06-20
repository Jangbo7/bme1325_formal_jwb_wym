# 当前整体架构总览

## 1. 文档目的

本文只描述当前仓库里仍有效的运行结构，供协作者快速回答三个问题：

- 现在有哪些正式入口
- 哪些模块负责业务真值，哪些只是调试 / 展示层
- 新改动应该落到哪里，而不是继续往旧文档和一次性脚本里堆

如果你是第一次接触这个项目，或者你的目标是给前端 / 展示界面提供统一解释入口，建议先读：

- [门诊系统总览与前端展示接口说明](./门诊系统总览与前端展示接口说明.md)

## 2. 一句话概述

当前仓库是一个以 `FastAPI + SQLite + EventBus + 显式状态机` 为核心的医院流程模拟系统，外面挂了三类前端/控制面：

- `scene/`：原有场景前端，负责分诊与基础门诊互动
- `frontend/fullview/`：以 subtree 形式接入的全院可视化前端
- 后端自带 HTML 控制页：`runtime-console` 与 `fullview-sync-monitor`

主线后端能力已经覆盖：

- triage
- 门诊医生问诊：`internal_medicine`、`surgery`
- ICU 专项链路：`icu_doctor`
- patient / NPC / mixed runtime 调度
- Fullview 同步与观察
- OpenEMR 适配

## 3. 当前正式入口

### 3.1 后端应用入口

- `backend/app/main.py`
- `backend/server.py`

`app/main.py` 负责容器装配、仓储、状态机、EventBus、agent service、runtime console、Fullview 同步、OpenEMR 适配和全部路由注册。

### 3.2 后端控制面

- `GET /runtime-console`
- `GET /fullview-sync-monitor`

这两个页面是当前正式的运行态控制与观察面。

### 3.3 交互 / 调试页面

- `GET /triage-agent-debug`
- `GET /doctor-agent-debug`
- `GET /patient-agent-debug`
- `GET /patient-agent-chat-debug`
- `GET /npc-debug`
- `GET /multi-patient-debug`
- `GET /hospital-runtime-debug`
- `GET /department-runtime-debug`

其中：

- `doctor-agent-debug` 是门诊医生类 agent 的统一调试入口
- `internal-medicine-agent-debug` 仍保留为兼容别名
- `runtime-console` 才是正式 runtime 控制面，不应再把旧 debug 页当成操作主界面
- 如果要做一个面向评鉴展示的更好看 GUI，当前最合适的基底不是 `scene/` 单患者页，而是 `department-runtime-debug` 这一类 department-centric 运行态视图

## 4. 前端结构

### 4.1 `scene/` 仍然是有效前端

当前 `scene/` 不是纯历史残留，下面这些路径仍在用：

```text
scene/
  main.js
  constants.js
  gameLogic.js
  gameObjects.js
  render.js
  core/
    bootstrap.js
    state-debug-panel.js
  agent/
    client.js
    event-subscriber.js
    store.js
    triage-form.js
    triage-dialogue.js
  queue/
    runtime.js
  npc/
    runtime.js
    fixed-runtime.js
    fixed-data.js
  ui/
    medical-record.js
    npc-dialogue.js
    task-board.js
```

它的定位是：

- 场景渲染
- 分诊与基础门诊对话
- 队列 / 病历卡 / 任务板展示
- 消费后端投影结果

### 4.2 `frontend/fullview/` 是独立边界

`frontend/fullview/` 是上游 subtree，不应把主仓特有逻辑直接写进去。当前重点关注：

```text
frontend/fullview/full_view/
  index.html
  main.js
  runtime.js
  map-config.json
  hospital-api.js
  event-rules/
  backend/
```

它负责：

- 全院地图
- 房间与移动规则
- 后端 movement / transfer / discharge 请求的可视化承接

## 5. 后端核心分层

### 5.1 业务真值层

- `backend/app/schemas/common.py`
- `backend/app/domain/patient/state_machine.py`
- `backend/app/domain/visit/state_machine.py`
- `backend/app/schemas/orchestration.py`
- `backend/app/services/encounter_orchestration.py`
- `backend/app/services/disposition.py`

这些文件定义：

- patient / visit 生命周期
- 标准门诊状态机
- disposition 语义
- encounter 级状态变迁事件

如果这里没改，前端显示再花哨也不算真正改了流程。

### 5.2 持久化与投影层

- `backend/app/repositories/*`
- `backend/app/services/runtime_projection.py`
- `backend/app/services/department_runtime_service.py`
- `backend/app/services/scene_snapshot_service.py`

职责：

- SQLite 持久化
- 面向前端和调试面的 runtime projection
- 部门态汇总
- 场景快照输出

### 5.3 事件层

- `backend/app/events/bus.py`
- `backend/app/events/types.py`
- `backend/app/events/subscribers/*`
- `backend/app/events/bridge.py`

职责：

- 事务后副作用
- 审计
- 病人 / 部门投影更新
- OpenEMR 与 Redis mirror 扩展

EventBus 负责传播结果，不负责决定主流程。

## 6. Agent 与运行时模块

### 6.1 业务 agent

当前 `backend/app/agents/` 下主要模块：

- `triage`
- `internal_medicine`
- `surgery`
- `icu_doctor`
- `patient_agent`
- `npc_patient`
- `test_simulator`
- `clinical_policy`
- `interactive_debug`
- `multi_patient_debug`
- `department_runtime`

其中：

- `internal_medicine` 与 `surgery` 已接入统一 doctor debug registry
- `clinical_policy/cards/*.yaml` 是当前门诊医生规则的重要结构化来源
- `test_simulator` 仍承担检查结果仿真

### 6.2 Runtime 控制与调度

当前有两套相关能力，但定位不同：

- `backend/app/services/npc_simulator.py`
  - 简单后台模拟器
  - 适合基础自动生成 / 推进
- `backend/app/services/hospital_supervisor.py`
  - 当前正式 mixed runtime 调度核心
  - 被 `runtime-console`、`department-runtime-debug`、`hospital-runtime-debug` 等页面使用

`hospital_supervisor` 负责：

- 活跃病人数控制
- agent/scripted 比例控制
- spawn / step 时钟
- Fullview step gate
- runtime event 记录

### 6.3 Fullview 同步

当前 Fullview 联动核心为：

- `backend/app/services/fullview_mapping.py`
- `backend/app/services/fullview_sync.py`
- `backend/app/repositories/fullview_sync.py`
- `backend/app/api/routes/fullview_sync.py`

职责：

- 把 visit / encounter 事件映射成 movement、transfer、discharge 请求
- 管理 outbox、观察状态、视觉冷却和重试
- 为 `runtime-console` 提供 step gate 能力

## 7. 当前主数据流

### 7.1 患者门诊主链路

1. 前端或运行时创建患者 / 就诊
2. triage 收集信息并完成分诊
3. `encounter_orchestration` 推动注册、排队、问诊、检查、缴费、处置
4. `disposition` 决定普通门诊结束、转急诊、转 ICU、转诊、住院等结果
5. `runtime_projection` / `department_runtime_service` 输出给前端和调试页
6. Fullview 同步层按事件驱动生成移动请求

### 7.2 Runtime console 链路

1. `runtime-console` 写入全局配置
2. `hospital_supervisor` 启动 mixed runtime session
3. agent/scripted 患者按时钟生成并推进
4. 若开启 Fullview gate，则推进会等待 Fullview 接收 / 观察状态
5. runtime 事件和病人列表通过 `/api/v1/runtime-console/*` 输出

## 8. 协作约定

做架构相关修改时，优先检查这几处：

1. 状态机与 `disposition`
2. 对应 service
3. repository / projection
4. 调试页和前端消费面

不要把一次性申请单、历史 handoff 文档、旧 `docs/*_card.md` 再当成当前架构说明。

### 4.2 后端主结构
```text
backend/app/
  main.py
  config.py
  database.py
  api/
    routes/
      health.py
      hospital_runtime_debug.py
      department_runtime_debug.py
      patients.py
      queues.py
      triage.py
      internal_medicine.py
      icu.py
      visits.py
      departments.py
      encounters.py
      events.py
      medical_records.py
      scene_snapshot.py
      npc_debug.py
      multi_patient_debug.py
      triage_agent_debug.py
      internal_medicine_agent_debug.py
      patient_agent_debug.py
      patient_agent_chat_debug.py
      openemr.py
  agents/
    triage/
    internal_medicine/
    icu_doctor/
    patient_agent/
    npc_patient/
    test_simulator/
    interactive_debug/
    multi_patient_debug/
    department_runtime/
    clinical_policy/
  integrations/
    openemr/
  domain/
    patient/
      state_machine.py
    visit/
  departments/
    registry.py
    internal.py
    surgery.py
    pediatrics.py
    emergency.py
    fever.py
  events/
    bus.py
    types.py
    subscribers/
      audit.py
      patient_projection.py
      queue.py
  repositories/
    patients.py
    sessions.py
    queues.py
    agent_memory.py
    visits.py
  schemas/
    common.py
    patient.py
    queue.py
    triage.py
    visit.py
```

---

## 5. 前端架构说明

## 5.1 前端总体职责
前端负责四类事情：
1. 渲染医院场景与角色
2. 管理玩家与分诊台的交互
3. 展示分诊对话、多轮追问、分诊建议
4. 展示排队队列、随机 NPC、任务板等模拟信息

## 5.2 前端模块分工

### `scene/main.js`
- 当前只是入口文件
- 主要负责导入 `core/bootstrap.js`
- 不再承载全部业务逻辑

### `scene/core/bootstrap.js`
- 当前前端的总装配入口
- 负责：
  - Canvas 场景初始化
  - 玩家移动与主循环
  - 分诊卡与分诊对话框打开/关闭
  - 内科会话恢复与对话同步
  - 键盘事件（例如 `E` 键）
  - 轮询后端患者状态和队列状态
  - 将 agent、queue、npc、ui 模块串起来
- 这是当前前端最核心的整合文件

### `scene/agent/client.js`
- 前端访问后端 API 的统一入口
- 负责请求：
  - 创建 triage session
  - 发送 follow-up message
  - 读取 patients
  - 读取 queues
- 也预留了内科与辅助检查相关的请求封装
- 目标是让其他前端模块不直接拼接 fetch 逻辑

### `scene/agent/store.js`
- 负责前端 agent 相关的轻状态
- 负责把后端 `dialogue.turns` 转换成前端渲染消息
- 当前支持三类 assistant message：
  - `recommendation`
  - `followup`
  - `final`
- 也负责基础去重，避免相同 recommendation 或相同 followup 重复展示

### `scene/agent/triage-form.js`
- 负责从分诊卡表单字段构建结构化 payload
- 本质上是“前端采集患者初始信息”的适配层

### `scene/agent/triage-dialogue.js`
- 负责渲染分诊对话页
- 包括：
  - 对话消息气泡
  - recommendation / followup / final 的样式差异
  - evidence chip 渲染
  - badge 渲染（Triage Level / Department）

### `scene/queue/runtime.js`
- 负责前端排队系统展示
- 包括：
  - 队列信息同步
  - 右下角队列看板绘制
  - 玩家号票状态展示

### `scene/npc/runtime.js`
- 负责随机 NPC 的生成、移动、渲染
- 当前主要用于模拟“医院大厅 / 候诊流动感”

### `scene/ui/task-board.js`
- 负责顶部任务板/工作流板展示
- 将 patient、visit、session、active agent 状态与任务文本进行映射展示
- 目前更偏向状态同步面板；辅助检查结果由 `simulated_report` 驱动显示，而不是独立的检验操作面板

### `scene/ui/medical-record.js`
- 负责病历卡展示
- 可以把 triage 结果、internal medicine 记录和 simulated_report 渲染到同一张病历卡中

## 5.3 当前前端交互主线
1. 玩家移动到分诊台附近
2. 按 `E`
3. 如果从未开始分诊：打开分诊卡
4. 如果已开始分诊：直接打开分诊对话
5. 提交分诊卡后创建 triage session
6. 前端轮询 patients / queues
7. 分诊对话页随着后端状态变化同步刷新
8. 分诊完成后进入内科会话；内科完成后由 `test_simulator` 生成 `simulated_report`
9. 当 visit.data 里出现 `simulated_report` 时，病历卡可以直接展示检查报告
10. 回诊、支付和后续处置继续由 visit / queue / state machine 驱动

## 5.4 当前前端的一个现实情况
虽然前端已经拆出模块，但 `scene/core/bootstrap.js` 仍然偏大，当前属于“模块化过渡态”。

另外，辅助检查相关的 UI 还处在“数据展示 + 预留接口”阶段：
- `scene/ui/medical-record.js` 已能展示仿真报告
- `scene/agent/client.js` 已有 `getSimulatedReport` 的真实封装；`completeAuxiliaryTest` 仍是历史占位，当前后端没有对应业务路由
- 仍然没有完整的独立检验科操作页，前端更像是在读结果并引导回诊

因此在可视化里建议这样表达：
- `bootstrap.js` 是“前端 orchestration layer”
- 下面连接多个功能模块，而不是把它画成普通业务组件

---

## 6. 后端架构说明

## 6.1 后端总体职责
后端负责五类事情：
1. 提供统一 REST API
2. 维护 triage / internal_medicine / ICU / patient_agent / NPC / supervisor / runtime projection 的运行时与流程状态
3. 维护 patient / session / memory / queue 的持久化状态
4. 用状态机控制流程合法性
5. 用 EventBus 解耦“分诊完成后的副作用”

## 6.2 后端分层

### API 层：`backend/app/api/routes/`
当前对外接口分成几类：
- 核心业务路由：`visits`、`triage`、`internal_medicine`、`icu`、`patients`、`queues`
- 运行时与投影路由：`scene_snapshot`、`department_runtime`、`hospital_runtime`、`medical_records`
- 事件与科室路由：`events`、`departments`、`encounters`
- 调试入口：`npc-debug`、`multi-patient-debug`、`triage-agent-debug`、`doctor-agent-debug`、`internal-medicine-agent-debug`、`patient-agent-debug`、`patient-agent-chat-debug`、`hospital-runtime-debug`、`department-runtime-debug`
- 集成入口：`openemr`
- 健康检查：`health`

职责：
- 请求接收
- schema 校验
- 调 service
- 返回标准化 JSON

### 应用装配层：`backend/app/main.py`
职责：
- 创建 FastAPI app
- 初始化数据库
- 创建 repository / event bus / state machine / triage / internal_medicine / ICU / patient_agent / npc simulator / hospital supervisor / runtime projector
- 注册 EventBus subscriber
- 注入到 app container

这是后端的“composition root”。

### Agent 层：`backend/app/agents/triage/`
这是当前系统里最成熟的 Agent 包之一；除此之外还有内科、ICU、patient_agent、npc_patient、调试控制层和辅助检查仿真模块。

分工如下：
- `graph.py`
  - 负责 triage graph 的执行顺序
  - 当前节点包括：加载上下文、评估、持久化、构建响应
- `state.py`
  - graph runtime state 定义
- `state_machine.py`
  - triage dialogue 状态机
- `prompts.py`
  - 追问 prompt 与 fallback 文案
- `rules.py`
  - 规则检索、字段解析、缺失字段排序、fallback triage
- `service.py`
  - agent 主服务编排
  - 负责融合 memory、LLM、rules、state transition、response build
- `schemas.py`
  - triage agent 相关局部 schema

### `backend/app/agents/internal_medicine/`
- 负责门诊内科问诊、追问护栏、最终诊断与检查建议
- 当前会把检查分区和仿真报告写回 visit.data

### `backend/app/agents/icu_doctor/`
- 负责高危症状下的 ICU 处理与紧急建议
- 采用和 triage / internal_medicine 类似的独立会话与状态机模式

### `backend/app/agents/patient_agent/`
- 负责受控病人 agent 的病例生成、回复、RAG 上下文、prompt 组装与重试
- 这是当前“可对话病人”的主线实现，不是 legacy NPC runner

### `backend/app/agents/npc_patient/`
- 负责 legacy 多患者调试中的病人画像、planner 和 runner
- 主要用于 `legacy_template` 和 `department_mixed` 这类多患者调度模式

### `backend/app/agents/test_simulator/`
- 负责把内科问诊结果映射为一级辅助检查分区
- 生成可展示的仿真报告
- 这个模块是无状态辅助服务，不承担完整对话流程

### `backend/app/agents/interactive_debug/`
- 负责共享的调试控制器、医生类 debug registry 和预设数据
- 当前医生类问诊调试已收口到统一 `doctor-agent-debug`
- `internal-medicine-agent-debug` 仍保留兼容入口，但内部委托到统一 doctor debug controller

### `backend/app/agents/multi_patient_debug/`
- 负责多患者调试页的兼容控制层

### `backend/app/agents/department_runtime/`
- 负责科室 runtime 的图和服务兼容层

### `backend/app/agents/clinical_policy/`
- 负责 specialty 卡片、matcher、loader 和运行时策略

### 领域状态机层：`backend/app/domain/patient/state_machine.py`
这是全局患者生命周期状态机。

它不管 prompt 和 LLM，只负责：
- 患者是否允许进入下一业务状态
- 状态迁移是否合法
- 状态对应的显示标签是什么

### Department Registry：`backend/app/departments/`
当前用于表达“科室配置 / 规则偏好”的扩展位。

目前包含：
- `internal`
- `surgery`
- `pediatrics`
- `emergency`
- `fever`
- `obgyn`
- `ophthalmology`
- `ent`
- `dentistry`
- `dermatology`
- `psychiatry`
- `rehabilitation`
- `pain`

它们现在是轻量模块，不是独立服务。

### EventBus 层：`backend/app/events/`
EventBus 只负责广播已发生的事实，不负责主业务决策。

当前事件：
- `triage.completed`
- `internal_medicine.consultation_completed`
- `icu.consultation_completed`
- `visit.state_changed`
- `patient.state_changed`
- `test.zone_assigned`
- `test.report_generated`
- `queue.ticket_created`
- `queue.ticket_called`

当前 subscriber：
- `queue.py`
  - triage / visit 流程中的排队副作用
- `patient_projection.py`
  - 根据 lifecycle state 更新展示态
- `audit.py`
  - 记录审计日志，包括内科和辅助检查事件
- `department_runtime.py`
  - 科室 runtime 投影
- `openemr_sync.py`
  - OpenEMR 同步副作用

### Repository 层：`backend/app/repositories/`
负责持久化访问。

主要仓库：
- `patients.py`
- `sessions.py`
- `queues.py`
- `agent_memory.py`

职责：
- 隔离数据库细节
- 让 service / graph 不直接写 SQL
- 为未来迁移数据库实现保留接口边界

### 数据契约层：`backend/app/schemas/`
负责：
- API request/response schema
- 枚举状态
- patient / queue / triage / visit / runtime / debug 的公共结构

---

## 7. 当前状态机设计

## 7.1 患者生命周期状态机
定义在 `backend/app/schemas/common.py` 和 `backend/app/domain/patient/state_machine.py`。

状态：
- `untriaged`
- `triaging`
- `waiting_followup`
- `triaged`
- `queued`
- `called`
- `in_consultation`
- `in_test`
- `completed`
- `cancelled`
- `error`

主路径：
`untriaged -> triaging -> waiting_followup -> triaged -> queued -> called -> in_consultation -> completed`

如果无需追问，则：
`untriaged -> triaging -> triaged -> queued`

## 7.2 Visit 生命周期状态机
定义在 `backend/app/domain/visit/state_machine.py`。

状态里已经包含：
- `arrived`
- `registration_pending`
- `registered`
- `waiting_triage`
- `triaging`
- `in_triage`
- `waiting_followup`
- `triaged`
- `waiting_consultation`
- `in_consultation`
- `waiting_test`
- `waiting_payment`
- `waiting_return_consultation`
- `waiting_pharmacy`
- `completed`
- `cancelled`
- `error`

当前主流程里，内科问诊完成后会进入 `waiting_test`，并把仿真报告写回 `visit.data`。

## 7.3 分诊对话状态机
定义在 `backend/app/agents/triage/state_machine.py`。

状态：
- `idle`
- `collecting_initial_info`
- `evaluating`
- `needs_followup`
- `awaiting_patient_reply`
- `re_evaluating`
- `triaged`
- `failed`

主路径：
`idle -> collecting_initial_info -> evaluating -> needs_followup -> awaiting_patient_reply -> re_evaluating -> triaged`

## 7.4 内科对话状态机
定义在 `backend/app/agents/internal_medicine/state_machine.py`。

状态：
- `idle`
- `collecting_info`
- `evaluating`
- `needs_followup`
- `awaiting_patient_reply`
- `re_evaluating`
- `diagnosis_complete`
- `treatment_planning`
- `completed`
- `failed`

内科 Agent 还会使用 `backend/app/agents/internal_medicine/workflow.py` 里的 `ConsultationProgress` 记录：
- `asked_fields_history`
- `last_question_focus`
- `last_question_text`
- `last_extracted_fields`
- `patient_reply_count`

## 7.5 状态机与 EventBus 的分工
- 状态机负责：判断能不能迁移、迁移到哪里
- EventBus 负责：迁移完成后广播事实
- Subscriber 负责：处理排队、审计、投影等副作用

也就是说：
- 状态机是“流程裁判”
- EventBus 是“广播站”
- Subscriber 是“响应执行者”

---

## 8. 当前记忆模型

## 8.1 总原则
当前记忆拆为三层：
- 共享记忆：稳定患者事实
- Agent 私有记忆：某个 Agent 的对话进度和内部状态
- 工作态：单次 graph 运行中的临时状态

## 8.2 Shared Memory
主要存：
- profile
  - 姓名
  - 年龄
  - 性别
- `medical_records.py`
- `patient_agent_cases.py`
- `department_runtime.py`
  - 过敏史
  - 慢病
- clinical_memory
  - chief complaint
  - symptoms
  - onset_time
  - vitals
  - risk_flags
  - last_department
  - last_triage_level

## 8.3 Agent Private Memory
当前 triage / internal_medicine / ICU agent 会维护各自的私有记忆：
- `dialogue_state`
- `assistant_message`
- `missing_fields`
- `expected_field`
- `last_question_focus`
- `last_question_text`
- `last_question_style`
- `asked_fields_history`
- `recommendation_snapshot`
- `recommendation_changed`
- `message_type`
- `latest_extraction`
- `evidence`

作用：
- 控制下一轮该问什么
- 避免 recommendation 每轮重复
- 避免同一句追问连续重复
- 给前端提供更稳定的展示信号

## 8.4 Visit Data Payload
当前内科与辅助检查链路主要把跨步骤数据落在 `visit.data_json` 里，而不是新增独立表。

常见字段包括：
- `triage_session_id`
- `internal_medicine_session_id`
- `diagnostic_session`
- `simulated_report`
- `internal_medicine_round2_summary`
- `test_category`
- `test_items`
- `registration_completed_at`

这样做的好处是：
- 改动面小
- 状态转换时容易回读
- 前端病历卡和任务板可以直接展示结果

## 8.5 为什么这样拆
这是为了让以后新增 Agent 时不会互相污染。

例如：
- triage agent 的“下一步想问 onset_time”
- 不应该自动成为未来门诊医生 agent 的共享上下文

所以：
- 事实进 shared memory
- 过程进 agent private memory
- 推测尽量停留在 working state

---

## 9. 当前 triage agent 的运行逻辑

## 9.1 初次创建 session
1. 前端提交分诊卡
2. 后端创建 triage session
3. 患者状态进入 `triaging`
4. triage agent 加载 shared memory + private memory + 历史 turns
5. 检索规则知识
6. 调用 LLM 生成 triage result
7. 校验 result，并用 fallback rule 兜底
8. 判断是否还缺字段
9. 若缺字段，则生成 follow-up 问题
10. 若不缺，则完成 triage
11. 持久化 patient / session / memory / queue side effects

## 9.2 继续对话
1. 前端发送用户回复
2. 后端读取当前 session 和私有记忆
3. 从用户自由文本中抽取结构化字段
4. 更新 shared memory
5. 重新评估 triage
6. 决定继续追问还是完成分诊
7. 返回新的 dialogue 和 patient view

## 9.3 当前 follow-up 生成逻辑
当前追问不是完全自由聊天，而是：
- `LLM 生成 + 规则约束`
- 主追问字段必须在缺失字段中
- recommendation 如果没变，不在每轮追问里重复
## 12. 适合 GPT 可视化的结构化描述

如果要生成一张“当前系统架构图”，建议画成下面 5 层：

### Layer 1: User / Scene Layer
- Player
- Triage Desk
- Internal Medicine Dialogue
- Medical Record Card
- Queue Board
- Random NPCs
- ICU Area

### Layer 2: Frontend Interaction Layer
- `scene/core/bootstrap.js`
- `scene/agent/client.js`
- `scene/agent/store.js`
- `scene/agent/triage-form.js`
- `scene/agent/triage-dialogue.js`
- `scene/queue/runtime.js`
- `scene/npc/runtime.js`
- `scene/ui/task-board.js`
- `scene/ui/medical-record.js`

### Layer 3: Backend API Layer
- FastAPI App
- Visit Routes
- Triage Routes
- Internal Medicine Routes
- ICU Routes
- Patient Routes
- Queue Routes
- Health Route

### Layer 4: Backend Runtime Layer
- Triage Graph
- Internal Medicine Graph / Workflow
- ICU Doctor Service
- Test Simulator
- Triage Dialogue State Machine
- Internal Medicine Dialogue State Machine
- Visit Lifecycle State Machine
- Patient Lifecycle State Machine
- EventBus
- Queue Subscriber
- Patient Projection Subscriber
- Audit Subscriber

### Layer 5: Persistence / Knowledge Layer
- Patient Repository
- Session Repository
- Agent Memory Repository
- Visit Repository
- Queue Repository
- SQLite Database
- Triage / Internal Medicine / ICU Rule Store
- LLM Endpoint

---

## 13. 推荐可视化关系（节点与边）

### 13.1 核心节点
- Player
- Scene Bootstrap
- Triage Form
- Triage Dialogue
- Internal Medicine Dialogue
- Medical Record Card
- Visit API
- Triage Graph
- Internal Medicine Graph
- ICU Doctor Service
- Test Simulator
- Triage Dialogue State Machine
- Internal Medicine Dialogue State Machine
- Visit Lifecycle State Machine
- Patient Lifecycle State Machine
- EventBus
- Queue Subscriber
- Patient Projection Subscriber
- Audit Subscriber
- Repositories
- SQLite
- LLM API
- Queue Board
- NPC Runtime
    medical_records.py

    patient_agent_cases.py
  services/
    hospital_supervisor.py
    department_runtime_service.py
    patient_flow_engine.py
    encounter_orchestration.py
    scene_snapshot_service.py
    npc_simulator.py
    patient_agent_service.py
### 13.2 核心边
- Player -> Triage Form
- Triage Form -> Visit / Triage API
- Triage API -> Triage Graph
- Triage Graph -> Triage Service
    department_catalog.py
    department_runtime.py
    encounter.py
    hospital_runtime.py
    multi_patient_debug.py
    npc_debug.py
    orchestration.py
    patient_agent_debug.py
    patient_flow.py
    scene_snapshot.py
    visit.py
- Triage Service -> Rules
- Triage Service -> LLM API
- Triage Service -> Repositories
- Triage Service -> Dialogue State Machine
- Triage Service -> EventBus
- EventBus -> Queue Subscriber
- EventBus -> Patient Projection Subscriber
- EventBus -> Audit Subscriber
- Visit API -> Internal Medicine Service
- Internal Medicine Service -> Test Simulator
- Internal Medicine Service -> Visit Repository
- Internal Medicine Service -> EventBus
- Repositories -> SQLite
- Queue Subscriber -> Queue Repository
- Patient Projection Subscriber -> Patient Repository
- Scene Bootstrap -> Queue Board
- Scene Bootstrap -> Medical Record Card
- Scene Bootstrap -> NPC Runtime

---

## 14. 一句话给 GPT 的压缩版

如果你只想给模型一句压缩描述，可以直接使用：

> 当前项目是一个基于 FastAPI + SQLite + EventBus + 显式状态机的医院分诊与门诊流程模拟系统，前端使用原生 Canvas/ESM 实现。系统核心从 triage 扩展到 internal_medicine、ICU、patient_agent、npc_patient、辅助检查仿真、多患者调度和 OpenEMR 集成；前端通过 bootstrap 连接分诊对话、内科会话、病历卡、队列和调试页，后端通过 repository、memory、LLM、事件桥、supervisor 和状态机协作完成 visit、patient、queue、simulated_report 与 runtime 投影的联动。

这是一套可持续扩展的基础架构。
