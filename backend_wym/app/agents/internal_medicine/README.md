# 内科目录 README

## 功能介绍

内科目录 (`internal_medicine`) 负责分诊后的门诊内科问诊与辅助检查接力，主要功能包括：

- 患者内科问诊和追问
- 症状、体征和风险评估
- 基于规则和 LLM 的诊疗建议生成
- 辅助检查仿真与报告落库
- 患者状态和就诊状态更新
- 诊疗结果和会话数据持久化

## 目录结构

```
internal_medicine/
├── __init__.py        # 包初始化文件
├── graph.py           # 工作流程图定义
├── prompts.py         # LLM提示词模板
├── rules.py           # 内科诊疗规则
├── schemas.py         # 数据模型定义
├── service.py         # 核心业务逻辑
├── state.py           # 状态管理
├── state_machine.py   # 状态机定义
└── workflow.py        # 工作流程管理
```

## 核心组件

### 1. InternalMedicineService

核心服务类负责会话评估、结果持久化、visit 记忆更新、状态推进和响应构造。当前实现会在完成时生成 simulated_report，并把诊疗上下文写回 `visit.data_json`。

### 2. 规则系统

- `retrieve_relevant_internal_medicine_rules()`: 获取相关的内科诊疗规则
- `rule_based_internal_medicine()`: 基于规则的内科诊疗
- `derive_risk_flags()`: 基于症状和生命体征推导风险标志
- `build_missing_fields()`: 构建缺失的患者信息字段

### 3. LLM集成

- `request_consultation_from_llm()`: 从LLM请求诊疗建议
- `build_consultation_system_prompt()`: 构建系统提示词
- `build_consultation_user_prompt()`: 构建用户提示词

### 4. 状态管理

- `WorkingMemory`: 工作内存，存储会话过程中的临时数据
- `ConsultationProgress`: 咨询进度跟踪
- `visit.data_json`: 跨步骤载体，保存 `diagnostic_session`、`simulated_report`、`test_category` 和 `test_items`

## 工作流程

1. **会话进入**：患者完成分诊和叫号后进入内科会话
2. **信息收集**：收集患者基本信息、症状、生命体征和缺失字段
3. **风险评估**：基于症状和体征评估风险等级
4. **规则匹配**：匹配相关的内科诊疗规则
5. **LLM 咨询**：如有必要，向 LLM 请求进一步的诊疗建议
6. **诊疗结论**：生成诊疗结论、追问结果和后续计划
7. **辅助检查仿真**：将结果交给 `test_simulator` 生成一级检查分区和 simulated_report
8. **结果持久化**：将诊疗结果存储到数据库并更新患者/就诊状态

## API接口

- `POST /api/v1/internal-medicine-sessions`: 创建新的内科问诊会话
- `POST /api/v1/internal-medicine-sessions/{session_id}/messages`: 继续内科问诊会话
- `GET /api/v1/internal-medicine-sessions/{session_id}`: 获取会话详情

## 示例请求

### 创建内科问诊会话

```json
POST /api/v1/internal-medicine-sessions
{
  "patient_id": "patient-123",
  "visit_id": "visit-123",
  "name": "张三",
  "age": 45,
  "sex": "male",
  "chief_complaint": "头痛、发热、咳嗽"
}
```

### 继续内科问诊会话

```json
POST /api/v1/internal-medicine-sessions/im-session-456/messages
{
  "patient_id": "patient-123",
  "message": "我还有恶心和呕吐的症状"
}
```

## 依赖

- Python 3.8+
- 相关医疗知识库和规则
- LLM API (如OpenAI API)
- 数据库存储

## 配置

需在系统配置中设置以下参数：

- `llm_settings`: LLM API配置，包括endpoint、model和api_key
- 数据库连接信息
- 规则引擎配置

## 错误处理

- 会话不存在：返回404错误
- 患者信息不完整：返回400错误，提示缺少的字段
- LLM请求失败：使用基于规则的回退方案
- 数据库操作失败：返回500错误

## 安全注意事项

- 所有患者数据均需加密存储
- API访问需进行身份验证和授权
- LLM请求需进行内容过滤，确保医疗信息安全
- 遵循医疗数据隐私法规