# 模拟病人与运行时调度说明

## 1. 先说结论

当前仓库里“自动病人推进”实际上有两套能力：

1. `NpcPatientSimulator`
   - 简单后台模拟器
   - 适合基础自动生成与推进
2. `HospitalSupervisor`
   - 正式 mixed runtime 调度器
   - 由 `runtime-console` 驱动

如果你的目标是“正式控制多个脚本病人和智能病人混跑”，应优先看 `HospitalSupervisor`，不要只盯着老的 `NpcPatientSimulator`。

## 2. 当前模块分工

### 2.1 `NpcPatientSimulator`

主要文件：

- `backend/app/services/npc_simulator.py`
- `backend/app/main.py`
- `backend/app/config.py`

职责：

- 在后台线程里按固定节奏生成和推进病人
- 复用既有 repository 和状态机
- 适合作为简单、低控制度的自动流量来源

### 2.2 `HospitalSupervisor`

主要文件：

- `backend/app/services/hospital_supervisor.py`
- `backend/app/services/runtime_console_service.py`
- `backend/app/api/routes/runtime_console.py`

职责：

- 维护 runtime session
- 控制活跃病人数
- 控制 intelligent / scripted mix ratio
- 分别控制 spawn / step 时钟
- 记录 runtime events
- 在需要时受 Fullview step gate 约束

### 2.3 `npc_patient`

主要文件：

- `backend/app/agents/npc_patient/profile.py`
- `backend/app/agents/npc_patient/planner.py`
- `backend/app/agents/npc_patient/runner.py`

职责：

- 提供 scripted patient 画像、行为规划和执行器
- 作为 runtime 中“脚本病人”来源的一部分

## 3. 当前推荐理解

### 3.1 哪个才是正式运行时

当前正式控制面是：

- `GET /runtime-console`

它背后控制的是 `HospitalSupervisor`，不是老式单线程 NPC 模拟器。

### 3.2 `NpcPatientSimulator` 还在做什么

它仍有价值，但定位更像：

- 轻量自动压测
- 基础联调
- 不需要复杂配比和观测时的简单后台推进

### 3.3 Fullview 联动发生在哪

Fullview gate、可视化冷却、接受确认等约束，属于：

- `HospitalSupervisor`
- `fullview_mapping`
- `fullview_sync`

不是 `NpcPatientSimulator` 自己负责。

## 4. 当前数据来源

自动病人的资料主要来自：

- `npc_patient/profile.py` 中的固定 profile
- `patient_agent` / runtime 生成器的结构化 case
- runtime console 的全局与科室配置

当前仍存在一个已知数据规范问题：

- `npc_patient/profile.py` 里还有 `General Surgery` 这样的非规范科室显示名

因此调试“脚本病人显示到了哪个科室”时，要同时看 profile、visit、runtime projection，而不是只看页面展示。

## 5. 推进原则

无论来自哪套自动化入口，推进时都应遵守同一套后端真值：

- `PatientStateMachine`
- `VisitStateMachine`
- `EncounterOrchestrationService`
- `disposition`

不要在模拟器里手写一条与主流程分离的“快捷路径”。

## 6. 观测面

### 6.1 正式观测

- `runtime-console`
- `fullview-sync-monitor`

### 6.2 兼容 / 调试观测

- `npc-debug`
- `multi-patient-debug`
- `hospital-runtime-debug`
- `department-runtime-debug`

这些页面仍有用，但不应该替代 `runtime-console` 的正式控制职责。

## 7. 什么时候改哪一层

如果你要改的是：

- 自动病人生成频率、活跃上限、混跑比例：改 `HospitalSupervisor` / `runtime-console`
- 轻量后台自动流：改 `NpcPatientSimulator`
- 脚本病人的画像和预设行为：改 `npc_patient/*`
- Fullview 阻塞或同步：改 `fullview_*` 系列

不要把这几类问题混在一起处理。

## 测试覆盖

新增测试建议与已实现方向：

- 活跃上限不超过配置值。
- 完成后可再生成，且仍不超过上限。
- 队列视图返回并可消费 `patient_name`。

以上可保证“定时生成 + 定时推进 + 最多2个活跃NPC + 队列可见名字”的闭环。
