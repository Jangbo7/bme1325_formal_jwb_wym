# 前端接线方案：检验仿真模块接入 (Frontend Integration Plan)

## 1. 目标 (Goal)
将后端已实现的「自动分配检查分区 + 生成仿真报告」逻辑，接入到现有的 2D 前端页面中。由于我们目前约定**跳过真实的检验科排队与物理采样流程**，前端接线的核心是**信息展示**与**状态快捷流转**。

## 2. 交互方案设计 (Interaction Design)

为了保持清晰和轻量，采用以下两步交互闭环：

### 流程一：医生开单后的前端感知
- **触发时机**：玩家完成内科问诊，后端状态流转至 `WAITING_AUXILIARY_TEST`（或类似状态）。
- **前端表现**：
  1. `Task Board (任务板)` 更新：当前任务变更为“前往进行辅助检查（影像科/检验科）”。
  2. `Dialogue (对话框)` 提示：内科医生的最后一句对话增加提示：“已为您开具检查单，请直接在任务板确认检查。”

### 流程二：一键获取仿真报告（跳过跑图实测）
- **触发时机**：玩家处于等待检查状态时。
- **前端表现**：
  1. **快捷操作**：在当前任务板 (Task Board) 下方出现一个【模拟完成所有检查】的按钮（或者在导诊台/护士处提供相关的快速交互）。
  2. **系统动作**：玩家点击按钮后，前端向后端发送一个 API 请求，触发后端拉取刚刚生成的仿真报告。
  3. **结果展现**：前端弹窗或在对话框中展示简略的**检查报告结果 (simulated_report)**。
  4. **状态流转**：关闭报告后，Task Board 更新任务为“携带报告返回内科复诊”或“前往缴费”。

## 3. 需修改的核心前端文件 (Files to Modify)

| 文件路径 | 职责范围 | 修改内容 |
|---------|---------|---------|
| `scene/api.private.js` | 网络请求 | 新增拉取当前会话中 `simulated_report` 状态及推进状态的 API 封装。 |
| `scene/ui/task-board.js` | 任务展示列表 | - 监听全局状态变更，若为等待检查状态，渲染“模拟检查”按钮。<br>- 根据从后端轮询到的结果，更新下一步指引任务。 |
| `scene/ui/npc-dialogue.js` (或对应对话组件) | 对话及弹窗反馈 | 医生给出结论时的文案解析（提取`test_category`并高亮展示）。 |
| `scene/gameLogic.js` / `scene/main.js` | 状态机联动 | 增加一个获取报告后的回调方法，推进游戏大循环的状态（修改访客实体状态）。 |

## 4. 前后端数据流简图

1. `End Internal Medicine Consultation` (HTTP POST)  
   -> Backend: 规则校验 -> 生成报告 -> 保存至 visit.data -> 响应200
2. `Frontend Session Polling` (HTTP GET)
   -> 识别到 visit.data 中存在 `simulated_report` && state == 'WAITING_AUXILIARY_TEST'
   -> 刷新 Task Board
3. `User Clicks "Simulate Test"` (UI Event)
   -> 显示报告 UI 弹窗
4. `Report Closed` (UI Event)
   -> Frontend 发起请求将状态变更为 `WAITING_RETURN_CONSULTATION`
   -> 刷新任务板，指引玩家回诊。

---
> **总结**：方案强调通过修改 `task-board.js` 直接暴露出“取报告”的捷径，避免为了一个“跳过的流程”去生硬地做大量地图与寻路逻辑。随时可以开工！