# ICU医生目录 README

## 功能介绍

ICU医生目录 (`icu_doctor`) 实现了重症监护室医生的智能诊疗系统，主要功能包括：

- 重症患者评估和会诊
- 紧急程度分级和风险评估
- 治疗方案制定
- 患者状态管理和追踪
- 重症监护记录的持久化存储

## 目录结构

```
icu_doctor/
├── __init__.py        # 包初始化文件
├── graph.py           # 工作流程图定义
├── prompts.py         # LLM提示词模板
├── rules.py           # ICU诊疗规则
├── schemas.py         # 数据模型定义
├── service.py         # 核心业务逻辑
├── state.py           # 状态管理
└── state_machine.py   # 状态机定义
```

## 核心组件

### 1. ICUDoctorService

核心服务类，提供以下功能：
- `create_session()`: 创建ICU会诊会话
- `continue_session()`: 继续已有的会诊会话
- `get_patient_view()`: 获取患者视图信息
- `prepare_context()`: 准备会诊上下文
- `evaluate()`: 评估患者状况并生成治疗方案
- `persist_result()`: 持久化诊疗结果

### 2. 规则系统

- `retrieve_relevant_icu_rules()`: 获取相关的ICU诊疗规则
- `rule_based_icu_triage()`: 基于规则的ICU分级
- `derive_risk_flags()`: 基于症状和生命体征推导风险标志
- `build_missing_fields()`: 构建缺失的患者信息字段

### 3. LLM集成

- `request_icu_consultation_from_llm()`: 从LLM请求ICU会诊建议
- `build_consultation_prompt()`: 构建会诊提示词
- `build_initial_prompt()`: 构建初始提示词
- `build_treatment_plan_prompt()`: 构建治疗方案提示词

### 4. 状态管理

- `WorkingMemory`: 工作内存，存储会话过程中的临时数据
- 患者状态机：管理患者在ICU的状态变化

## 工作流程

1. **会话创建**：患者进入ICU，创建新的会诊会话
2. **信息收集**：收集患者基本信息、症状、生命体征等
3. **风险评估**：基于症状和体征评估风险等级
4. **规则匹配**：匹配相关的ICU诊疗规则
5. **LLM咨询**：向LLM请求重症诊疗建议
6. **分级与方案**：生成紧急程度分级和治疗方案
7. **结果持久化**：将诊疗结果存储到数据库
8. **状态更新**：更新患者状态和位置信息

## API接口

- `POST /icu-sessions`: 创建新的ICU会诊会话
- `PUT /icu-sessions/{session_id}`: 继续ICU会诊会话
- `GET /icu-sessions/{session_id}`: 获取会话详情

## 示例请求

### 创建ICU会诊会话

```json
POST /icu-sessions
{
  "patient_id": "patient-456",
  "name": "李四",
  "age": 65,
  "sex": "female",
  "symptoms": "胸痛、呼吸困难、意识模糊",
  "vitals": {
    "temperature": 39.2,
    "blood_pressure": "90/60",
    "heart_rate": 110,
    "respiratory_rate": 28
  }
}
```

### 继续ICU会诊会话

```json
PUT /icu-sessions/icu-session-789
{
  "patient_id": "patient-456",
  "message": "患者血氧饱和度下降到85%"
}
```

## 紧急程度分级

- **CRITICAL**: 危急 - 需要立即干预
- **EMERGENT**: 紧急 - 需要在15分钟内干预
- **URGENT**: 急迫 - 需要在30分钟内干预
- **LESS_URGENT**: 较急迫 - 需要在2小时内干预
- **NON_URGENT**: 非紧急 - 需要在4小时内干预

## 依赖

- Python 3.8+
- 重症医学知识库和规则
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
- 重症患者信息需实时监控和备份