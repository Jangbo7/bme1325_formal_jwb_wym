# 分诊 / 医生 Agent Prompt 与规则手册

**版本**：v2.0  
**更新日期**：2026-06-20

## 1. 目的

这份文档只描述当前仓库里仍在维护的聊天型 agent 提示词与规则来源，帮助协作者判断：

- 哪些 prompt 仍是主线实现
- 哪些规则文件是当前 source of truth
- 新 agent 应该接入哪套结构
- 调试时优先看哪些入口

本文聚焦以下 agent：

- `triage`
- `internal_medicine`
- `surgery`
- `icu_doctor`

`patient_agent`、`npc_patient` 会消费部分问诊结果，但不属于本文的主说明范围。

## 2. 当前有效规则

### 2.1 LLM 不是唯一决策源

所有主线 agent 都保留规则回退。LLM 负责自然语言理解、追问生成和结构化结果生成，但：

- 不能绕过状态机
- 不能绕过 repository 持久化
- 不能直接定义最终流程去向

### 2.2 结构化结果优先于自由文本

当前实现默认要求模型输出可校验 JSON，常见字段包括：

- `priority`
- `department`
- `test_required` / `needs_second_consultation`
- `primary_disposition`
- `recommended_department`
- `disposition_advice`

自由文本主要用于：

- 给患者的自然语言回复
- 面向调试页的解释性展示

### 2.3 规则分层已经从旧 `docs/*.md` 迁移

当前应优先使用：

- `backend/app/agents/clinical_policy/cards/*.yaml`
- `backend/rag/*.json`
- `backend/app/agents/*/rules.py`

旧的 `docs/*_card.md`、`docs/round_one_two.md` 已不再是主线规则源，不应继续作为新功能依据。

### 2.4 记忆分层仍然有效

当前聊天型 agent 仍按三层信息工作：

- 患者共享事实：患者记录、visit 数据、共享 memory
- agent 私有进度：session memory、追问进度、asked fields、final result
- 检索规则：RAG / clinical policy cards

不要把这三类信息重新混成一份 prompt 文本源。

## 3. 各 agent 的当前来源

### 3.1 `triage`

主要源码：

- `backend/app/agents/triage/service.py`
- `backend/app/agents/triage/prompts.py`
- `backend/app/agents/triage/rules.py`
- `backend/rag/rule_store.json`

当前职责：

- 收集主诉和关键缺失字段
- 产出分诊等级、优先级、目标科室
- 在高风险时直接给出急诊或 ICU 升级路由

当前约束：

- 追问必须围绕缺失字段
- 不给治疗方案
- 输出需兼容后续 `disposition` 和状态机

### 3.2 `internal_medicine`

主要源码：

- `backend/app/agents/internal_medicine/prompts.py`
- `backend/app/agents/internal_medicine/rules.py`
- `backend/app/agents/internal_medicine/service.py`
- `backend/app/agents/clinical_policy/cards/internal_medicine_initial_consultation.yaml`

当前职责：

- 门诊首轮与二轮问诊
- 根据是否需要检查、门诊处置、升级转诊来组织输出
- 和 `encounter_orchestration`、`disposition`、`test_simulator` 联动

当前特点：

- 已经不是单纯“聊天页 demo”
- 输出必须兼容 `needs_tests`、`needs_second_consultation`、`primary_disposition`

### 3.3 `surgery`

主要源码：

- `backend/app/agents/surgery/prompts.py`
- `backend/app/agents/surgery/rules.py`
- `backend/app/agents/surgery/service.py`
- `backend/app/agents/clinical_policy/cards/surgery_initial_consultation.yaml`
- `backend/app/agents/clinical_policy/cards/surgery_round2_result_review.yaml`

当前状态：

- 已接入统一 doctor debug registry
- 与 `internal_medicine` 一样走门诊问诊与 disposition 链路
- 仍有一条已知缺陷：部分 urgent / emergency escalation 结论会在无检查路径上继续落到缴费

### 3.4 `icu_doctor`

主要源码：

- `backend/app/agents/icu_doctor/prompts.py`
- `backend/app/agents/icu_doctor/rules.py`
- `backend/rag/icu_rules.json`

当前定位：

- 保留为 ICU 专项链路
- 与 `doctor-agent-debug` 的主线门诊问诊体系不同
- 仍可运行，但不是目前 runtime console / Fullview 联动的主叙事链

## 4. Prompt 与规则的真实落点

### 4.1 临床规则

当前临床约束主要来自：

- triage: `backend/rag/rule_store.json`
- ICU: `backend/rag/icu_rules.json`
- 门诊医生：`backend/app/agents/clinical_policy/cards/*.yaml` + 各自 `rules.py`

### 4.2 问诊提示词

当前 prompt 应主要从各 agent 自己的 `prompts.py` 维护，不要把规则散写到：

- 根目录临时 markdown
- 旧 `docs/*_card.md`
- 前端页面脚本里

### 4.3 流程语义

聊天结果最终要落到这几层结构：

- `VisitLifecycleState`
- `PatientLifecycleState`
- `StandardOutpatientState`
- `disposition`
- runtime projection

所以 prompt 修改不能只看语言表现，必须同时检查状态流和测试。

## 5. 当前调试入口

### 5.1 正式后台控制面

- `GET /runtime-console`
- `GET /fullview-sync-monitor`

这两个页面用于运行态控制和 Fullview 同步观测，不直接负责单个问诊 prompt 调试。

### 5.2 问诊调试入口

- `GET /triage-agent-debug`
- `GET /doctor-agent-debug`
- `GET /internal-medicine-agent-debug`：兼容别名
- `GET /patient-agent-chat-debug`

其中：

- 新的门诊医生类 agent 应优先复用 `doctor-agent-debug`
- 不应再新增一套平行的独立 doctor debug 页面

## 6. 协作约定

新增或修改 prompt / 规则时，按这个顺序检查：

1. 修改对应 agent 的 `prompts.py`、`rules.py` 或 `clinical_policy/cards`
2. 检查输出字段是否仍兼容 service 校验
3. 检查是否影响 `disposition`、状态机和 runtime projection
4. 补充或更新对应测试
5. 最后再看调试页表现

不要把旧文档里的 prose 规则当成可执行规范。当前规范应始终以后端源码和测试为准。
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
