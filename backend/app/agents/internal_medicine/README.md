# 内科目录 README

## 功能介绍

内科目录 (`internal_medicine`) 实现了内科医生的智能诊疗系统，主要功能包括：

- 患者内科问诊和咨询
- 症状分析和诊断建议
- 基于规则和LLM的智能决策
- 患者状态管理和追踪
- 医疗记录的持久化存储

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

核心服务类，提供以下功能：
- `create_session()`: 创建内科问诊会话
- `continue_session()`: 继续已有的问诊会话
- `get_patient_view()`: 获取患者视图信息
- `prepare_context()`: 准备问诊上下文
- `evaluate()`: 评估患者症状并生成诊断
- `persist_result()`: 持久化诊疗结果

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

## 工作流程

1. **会话创建**：患者进入内科，创建新的问诊会话
2. **信息收集**：收集患者基本信息、症状、生命体征等
3. **风险评估**：基于症状和体征评估风险等级
4. **规则匹配**：匹配相关的内科诊疗规则
5. **LLM咨询**：如有必要，向LLM请求进一步的诊疗建议
6. **诊断生成**：生成诊断结果和治疗建议
7. **结果持久化**：将诊疗结果存储到数据库
8. **状态更新**：更新患者和访问状态

## API接口

- `POST /internal-medicine-sessions`: 创建新的内科问诊会话
- `PUT /internal-medicine-sessions/{session_id}`: 继续内科问诊会话
- `GET /internal-medicine-sessions/{session_id}`: 获取会话详情

## 示例请求

### 创建内科问诊会话

```json
POST /internal-medicine-sessions
{
  "patient_id": "patient-123",
  "name": "张三",
  "age": 45,
  "sex": "male",
  "symptoms": "头痛、发热、咳嗽",
  "vitals": {
    "temperature": 38.5,
    "blood_pressure": "120/80",
    "heart_rate": 85
  }
}
```

### 继续内科问诊会话

```json
PUT /internal-medicine-sessions/im-session-456
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