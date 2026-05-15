# 前端集成计划：检验科仿真模块接入

## 1. 后端检验科触发机制分析

### 1.1 后端实现架构

* **核心组件**：`TestSimulationAgent` 类（位于 `backend/app/agents/test_simulator/service.py`）

* **主要功能**：

  * `assign_primary_category()`: 根据会诊结果和临床症状分配检查类别（医学影像或医学实验室检验）

  * `build_test_items()`: 构建具体检查项目列表

  * `generate_report()`: 生成完整的仿真检查报告

### 1.2 触发流程

1. **触发时机**：内科医生完成问诊后，后端自动生成仿真报告
2. **数据流转**：

   * 内科医生会话结束时，系统调用 `TestSimulationAgent.generate_report()`

   * 报告生成后存储到 `visit.data` 中的 `simulated_report` 字段

   * 患者状态流转至 `WAITING_AUXILIARY_TEST` 或类似状态

### 1.3 报告内容结构

```json
{
  "simulation": true,
  "simulation_version": "v1",
  "generated_at": "2026-04-24T12:00:00Z",
  "category_code": "medical_laboratory",
  "category_label": "医学实验室检验",
  "window_code": "medical_laboratory_window",
  "window_label": "医学实验室检验窗",
  "test_items": ["血常规", "C反应蛋白", "基础生化"],
  "report_text": "辅助检查模拟报告...",
  "report_summary": {
    "impression": "建议先前往医学实验室检验完成初步检查。",
    "reason": "根据当前临床表现，建议先完成基础检查。",
    "priority": "M",
    "confidence": 0.72,
    "next_step": "return_consultation"
  }
}
```

## 2. 前端集成方案

### 2.1 集成目标

* 在任务板中添加「模拟完成所有检查」按钮

* 实现拉取和展示仿真报告的功能

* 处理检查完成后的状态流转

* **新增**：实现病历卡模块，实时展示分诊、问诊和检查报告结果

### 2.2 需修改的文件

| 文件路径                         | 职责范围   | 修改内容                    | 优先级 |
| ---------------------------- | ------ | ----------------------- | --- |
| `scene/api.private.js`       | 网络请求   | 新增拉取仿真报告和推进状态的API封装     | 高   |
| `scene/agent/client.js`      | API客户端 | 扩展API方法，添加获取报告和完成检查的接口  | 高   |
| `scene/ui/medical-record.js` | 病历卡    | 新增病历卡组件，展示分诊、问诊和检查报告    | 高   |
| `scene/core/bootstrap.js`    | 状态管理   | 增加检查报告处理逻辑，状态流转回调，集成病历卡 | 中   |
| `scene/ui/task-board.js`     | 任务展示   | 添加「模拟检查」按钮，处理检查状态展示     | 中   |
| `scene/ui/npc-dialogue.js`   | 对话反馈   | 处理医生结论中文案的解析和高亮         | 低   |

### 2.3 具体实现步骤

#### 第一阶段：基础准备（可控步骤）

##### 步骤1：创建/更新 API 配置文件

* 复制 `api.private.example.js` 为 `api.private.js`（如果不存在）

* 确保配置正确的后端地址和API密钥

##### 步骤2：扩展 API 客户端

* 在 `scene/agent/client.js` 中添加新的API方法：

  * `getSimulatedReport(visitId)`: 获取仿真报告

  * `completeAuxiliaryTest(visitId)`: 完成辅助检查并推进状态

##### 步骤3：创建病历卡组件

* 新建 `scene/ui/medical-record.js` 文件

* 实现病历卡展示逻辑，包括：

  * 分诊信息展示

  * 问诊记录展示

  * 检查报告展示

  * 实时数据同步

#### 第二阶段：核心功能集成

##### 步骤4：修改任务板组件

* 在 `scene/ui/task-board.js` 中：

  * 增加对 `WAITING_AUXILIARY_TEST` 状态的识别

  * 当处于检查等待状态时，渲染「模拟完成所有检查」按钮

  * 处理按钮点击事件，触发报告获取和状态更新

##### 步骤5：实现报告展示模态框

* 在 `scene/core/bootstrap.js` 中：

  * 创建报告展示模态框的UI结构

  * 实现报告内容的渲染逻辑

  * 添加关闭按钮和状态流转处理

##### 步骤6：处理状态流转

* 在 `scene/core/bootstrap.js` 中：

  * 增加 `handleTestCompletion()` 方法

  * 处理从 `WAITING_AUXILIARY_TEST` 到 `WAITING_RETURN_CONSULTATION` 的状态转换

  * 更新任务板显示相应的后续任务

#### 第三阶段：集成与优化

##### 步骤7：集成病历卡到主界面

* 在 `scene/core/bootstrap.js` 中：

  * 添加病历卡的UI元素和控制逻辑

  * 实现病历卡的显示/隐藏功能

  * 确保病历卡数据与后端同步

##### 步骤8：优化用户体验

* 在医生对话结束时，添加检查提示信息

* 确保任务板和病历卡状态实时更新

* 添加加载状态和错误处理

## 3. 病历卡模块设计

### 3.1 功能需求

* **实时数据**：与后端数据同步，实时显示最新状态

* **分类展示**：分别展示分诊、问诊、检查报告信息

* **历史记录**：保留完整的诊疗历史

* **交互友好**：操作简单，信息清晰

### 3.2 数据结构

```javascript
// 病历卡数据结构
const medicalRecord = {
  patientInfo: {
    id: "P-123",
    name: "患者姓名",
    age: 30,
    gender: "男"
  },
  triageInfo: {
    level: 2,
    department: "内科",
    symptoms: "发热、咳嗽",
    vitalSigns: {
      temperature: 38.5,
      heartRate: 85,
      bloodPressure: "120/80"
    },
    timestamp: "2026-04-24T10:00:00Z"
  },
  consultationInfo: {
    doctor: "张医生",
    diagnosis: "上呼吸道感染",
    prescription: ["抗生素", "退烧药"],
    notes: "建议多休息，多喝水",
    timestamp: "2026-04-24T11:00:00Z"
  },
  testInfo: {
    category: "医学实验室检验",
    items: ["血常规", "C反应蛋白"],
    report: "辅助检查模拟报告...",
    timestamp: "2026-04-24T12:00:00Z"
  }
};
```

## 4. 前后端数据流

1. **内科问诊结束** → 后端生成仿真报告 → 状态变为 `WAITING_AUXILIARY_TEST`
2. **前端轮询** → 识别到检查等待状态 → 任务板显示「模拟检查」按钮
3. **用户点击按钮** → 前端调用 `getSimulatedReport()` → 显示报告模态框
4. **用户关闭报告** → 前端调用 `completeAuxiliaryTest()` → 状态变为 `WAITING_RETURN_CONSULTATION`
5. **前端轮询** → 识别到复诊等待状态 → 任务板更新为「返回内科复诊」
6. **病历卡同步** → 实时更新分诊、问诊、检查报告信息

## 5. 技术要点和注意事项

* **状态管理**：确保前端正确识别和处理检查相关的状态

* **错误处理**：添加API调用失败的处理逻辑

* **用户体验**：保持操作流程的流畅性和直观性

* **代码质量**：遵循现有代码风格和架构模式

* **数据同步**：确保病历卡数据与后端实时同步

## 6. 测试计划

1. **功能测试**：验证整个检查流程的完整性
2. **边界测试**：测试各种状态转换场景
3. **性能测试**：确保API调用和UI更新的响应速度
4. **病历卡测试**：验证病历卡数据的完整性和实时性

## 7. 风险评估

* **低风险**：集成方案基于现有的前端架构，改动范围可控

* **中风险**：需要确保后端状态管理与前端预期一致

* **低风险**：UI修改仅涉及任务板、模态框和病历卡，不影响核心游戏逻辑

## 8. 预期效果

完成集成后，玩家将能够：

1. 在医生开单后看到检查提示
2. 通过任务板一键完成检查并查看报告
3. 无缝过渡到后续的复诊流程
4. 获得清晰的视觉反馈和任务指引
5. **实时查看病历卡**，了解完整的诊疗历史

