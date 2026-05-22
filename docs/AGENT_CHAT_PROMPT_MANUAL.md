# 分诊 / 医生 Agent 聊天 Prompt 与 RAG 手册

**版本**：v1.0
**日期**：2026-05-22

## 1. 目的

这份手册用于总结当前项目里分诊与医生类 agent 的聊天规则、prompt 结构、RAG 规则，以及这些规则在当前实现中的实际作用方式。

本文侧重于当前已落地的三条链路：

- 分诊 agent (`triage`)
- 门诊内科医生 agent (`internal_medicine`)
- ICU 医生 agent (`icu_doctor`)

## 2. 共用原则

三类 agent 共享以下实现原则：

1. **LLM 不是唯一来源**：所有 agent 都保留规则回退，不把大模型结果当成唯一真相。
2. **RAG 只做证据和约束**：检索到的规则用于补强判断、生成追问、生成初步 plan，不直接取代业务逻辑。
3. **优先结构化输出**：能返回 JSON 的地方，尽量强制 JSON，便于后续校验和持久化。
4. **对话要受控**：
   - 不允许开放式闲聊
   - 不允许随意诊断承诺
   - 不允许重复追问同一信息太多次
5. **失败可退化**：LLM 不可用、返回格式不对、或者内容不合法时，必须退回规则结果或固定模板。

## 3. 分诊 Agent：`triage`

### 3.1 聊天目标

分诊 agent 的目标不是给完整治疗方案，而是：

- 收集主诉、症状、起病时间、体温、疼痛评分、过敏史等关键信息
- 基于现有信息给出分诊等级、优先级、建议科室
- 生成自然、简短、面向患者的追问或结论

### 3.2 Prompt 规则

#### 3.2.1 追问 prompt

当前分诊追问由 `build_follow_up_system_prompt()` 和 `build_follow_up_user_prompt()` 组合生成。

核心约束是：

- 只能围绕缺失字段追问
- 不要给诊断或治疗建议
- 单次最多两句
- 中文为主，可以保留少量英文科室名
- 如果当前建议没有变化，不要重复科室和优先级
- 风险较高时，可以先给一句短提示，再问一个关键问题

#### 3.2.2 初始 / 综合判断 prompt

分诊阶段的综合判断会把以下内容传给模型：

- 病人当前信息
- 短期对话记忆
- 长期病人记忆
- agent 私有记忆
- 检索到的规则

模型需要返回严格 JSON，字段至少包括：

- `triage_level`
- `priority`
- `department`
- `note`

### 3.3 分诊 RAG 规则

分诊 RAG 主要来自 [backend/rag/rule_store.json](../backend/rag/rule_store.json) 和 [backend/app/agents/triage/rules.py](../backend/app/agents/triage/rules.py)。

#### 3.3.1 检索方式

规则检索会根据以下信息打分：

- 关键词命中
- `conditions.symptoms_any`
- 心率、体温、疼痛评分等生命体征

如果没有命中任何高分规则，会回退到默认规则。

#### 3.3.2 规则作用

检索到的规则用于：

- 作为分诊结论的证据
- 辅助推断 `triage_level`
- 辅助推断 `department`
- 辅助生成 `note`

#### 3.3.3 默认行为

如果 LLM 不可用或输出不可解析，系统会使用 `rule_based_triage()` 生成默认分诊结果。

### 3.4 分诊对话行为

- 缺失字段会被优先级排序后逐个追问
- 已经问过的字段会降权
- 同一字段重复追问时会换一种问法
- 多轮后如果仍然无法补齐，系统会收敛到 final recommendation

## 4. 门诊内科 Doctor Agent：`internal_medicine`

### 4.1 聊天目标

门诊内科医生 agent 的目标是：

- 收集和整理症状、起病时间、过敏史等信息
- 基于规则和 LLM 给出初步诊疗建议
- 在需要时生成检查/化验建议
- 在结果足够时输出稳定的 final plan

### 4.2 Prompt 规则

#### 4.2.1 追问 prompt

内科的追问 prompt 位于 [backend/app/agents/internal_medicine/prompts.py](../backend/app/agents/internal_medicine/prompts.py)。

当前追问规则是：

- 中文为主
- 围绕关键信息追问，而不是泛泛聊天
- 对常见缺失字段使用固定模板
- 如果同一字段再次追问，尽量换问法

#### 4.2.2 consultation prompt

`build_consultation_system_prompt()` 要求：

- 以“内科门诊医生助手”身份输出
- 基于患者信息给出安全、可执行的中文建议
- 输出必须是严格 JSON

`build_consultation_user_prompt()` 会输入：

- shared memory
- 最近患者消息
- missing fields
- previous final result
- 额外的历史病历模板

模型需要返回的字段包括：

- `department`
- `priority`
- `diagnosis_level`
- `note`
- `patient_plan`
- `tests_suggested`
- `medication_or_action`
- `red_flags`
- `test_required`
- `test_category`
- `test_items`
- `test_reason`

### 4.3 内科 RAG 规则

内科规则来自 [backend/rag/internal_medicine_rules.json](../backend/rag/internal_medicine_rules.json) 和 [backend/app/agents/internal_medicine/rules.py](../backend/app/agents/internal_medicine/rules.py)。

#### 4.3.1 检索与 fallback

规则检索根据关键词和症状匹配，优先返回最相关的若干规则。

如果没有命中明显规则，会回退到默认内科规则，例如：

- 发热伴呼吸道症状
- 消化系统不适
- 一般内科随访

#### 4.3.2 检查计划推断

内科规则里有一个重要的辅助逻辑：`_infer_test_plan()`。

它会根据：

- `test_category`
- `diagnosis_level`
- 症状文本
- chief complaint

自动补出：

- 是否需要检查
- 检查类别：`medical_imaging` / `medical_laboratory`
- 检查项目
- 检查理由

#### 4.3.3 ICU 升级逻辑

内科规则还保留了更高优先级的升级能力：

- 如果检测到明显危险信号，会把建议提升到急诊/ICU 方向
- 这属于 override，不是普通追问的一部分

### 4.4 内科对话行为

- `create_session` 阶段通常先走规则结果和初始消息，不强制调用 LLM
- 当信息足够时，会尝试调用 LLM 生成 final plan
- 如果已经进入 final 后的补充阶段，则允许更新 final plan，但不应重新回到纯追问模式
- LLM 不可用时，必须退回规则输出

## 5. ICU Doctor Agent：`icu_doctor`

### 5.1 聊天目标

ICU doctor agent 用于高风险或重症场景的会诊判断，目标是：

- 快速判断危重程度
- 生成治疗方案和优先级
- 对缺失的关键病情信息做补问
- 在必要时输出紧急 ICU 级别建议

### 5.2 Prompt 规则

ICU 的 prompt 目前以英文为主，位于 [backend/app/agents/icu_doctor/prompts.py](../backend/app/agents/icu_doctor/prompts.py)。

#### 5.2.1 初始 prompt

`build_initial_prompt()` 会把 triage level 和患者信息传给模型，并要求开始 ICU consultation workflow。

#### 5.2.2 追问 prompt

`build_follow_up_message()` 会根据缺失字段生成英文追问，字段包括：

- chief_complaint
- symptoms
- onset_time
- vitals
- allergies
- chronic_conditions
- treatment_history

#### 5.2.3 治疗方案 prompt

`build_treatment_plan_prompt()` 和 `build_consultation_prompt()` 都要求：

- 以 ICU attending physician 身份输出
- 使用检索到的 ICU protocols 作为支持
- 返回严格 JSON

模型输出字段包括：

- `triage_level`
- `urgency`
- `treatment_plan`
- `note`

### 5.3 ICU RAG 规则

ICU 规则来自 [backend/rag/icu_rules.json](../backend/rag/icu_rules.json) 和 [backend/app/agents/icu_doctor/rules.py](../backend/app/agents/icu_doctor/rules.py)。

#### 5.3.1 检索方式

检索根据以下信号打分：

- 症状关键词
- `symptoms_any`
- `spo2_lte`
- `systolic_bp_lte`
- `temp_c_gte`

#### 5.3.2 规则结果

ICU 规则通常输出：

- `triage_level`
- `urgency`
- `treatment_plan`
- `note`

默认规则是更通用的 ICU observation / semi-stable observation。

### 5.4 ICU 对话行为

- 如果已有 conversation history，会用咨询 prompt
- 如果没有 history，会用初始 prompt
- 如果 LLM 不可用或返回异常，会回退到 ICU rule-based triage
- 结果会继续进入患者状态和就诊状态更新

## 6. 当前实现的实际风格差异

当前代码里，三类 agent 的语言风格并不完全一致：

- `triage`：中文为主，偏短句追问
- `internal_medicine`：中文为主，强调 final plan 和可执行建议
- `icu_doctor`：prompt 主要是英文，偏 ICU 术语和结构化治疗方案

如果后续希望统一风格，建议优先统一：

1. 输出语言
2. JSON 字段命名
3. 追问句式长度
4. fallback 模板的格式

## 7. 读这个手册时要注意的边界

- 这份手册总结的是“当前实现”，不是理想设计稿。
- 一些 agent 已经具备 LLM 接入，但默认配置是否合规，还要看部署环境变量是否覆盖。
- RAG 目前更多是“检索 + 约束 + fallback”，不是把 agent 变成完全自由的生成器。

## 8. 关联文件

- [backend/app/agents/triage/prompts.py](../backend/app/agents/triage/prompts.py)
- [backend/app/agents/triage/rules.py](../backend/app/agents/triage/rules.py)
- [backend/app/agents/internal_medicine/prompts.py](../backend/app/agents/internal_medicine/prompts.py)
- [backend/app/agents/internal_medicine/rules.py](../backend/app/agents/internal_medicine/rules.py)
- [backend/app/agents/icu_doctor/prompts.py](../backend/app/agents/icu_doctor/prompts.py)
- [backend/app/agents/icu_doctor/rules.py](../backend/app/agents/icu_doctor/rules.py)
- [backend/rag/rule_store.json](../backend/rag/rule_store.json)
- [backend/rag/internal_medicine_rules.json](../backend/rag/internal_medicine_rules.json)
- [backend/rag/icu_rules.json](../backend/rag/icu_rules.json)