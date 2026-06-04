# 当前医生 Agent 面诊对话规则整理

## 1. 范围

本文只整理当前已经接入统一 `consultation agent` 框架的医生面诊 agent。

截至目前，真正注册在 consultation registry 里的医生 agent 只有两个：

- `internal_medicine`
- `surgery`

对应注册定义见：

- `backend/app/services/consultation_registry.py`

这意味着下面所有“共性规则”都以这两个 agent 的现状为准，而不是泛指仓库里所有带 doctor 名字的实验/调试 agent。

---

## 2. 当前面诊框架的总体结构

两个医生 agent 都建立在同一个共享 runtime 上：

- 共享 runtime: `backend/app/agents/department_runtime/service.py`
- 共享 prompt scaffold: `backend/app/agents/department_runtime/prompting.py`
- 共享 policy runtime: `backend/app/agents/clinical_policy/runtime.py`
- 共享 policy registry/loader: `backend/app/agents/clinical_policy/registry.py` / `backend/app/agents/clinical_policy/loader.py`

每个专科只在这些位置覆盖差异：

- `config.py`: 把本专科的 prompt/rules/policy 接到共享 runtime
- `service.py`: 决定 visit 状态推进、检查分流、二轮结束后的落库方式
- `rules.py`: 专科 RAG、风险标记、结论规则、转科规则
- `prompts.py`: 面向患者的话术风格、科室标签、最终消息格式
- `policy.py` + policy card YAML: 一轮问诊的临床策略约束

---

## 3. 共同的面诊生命周期

### 3.1 会话入口

医生 agent 统一提供两类入口：

- `create_session(payload)`
- `continue_session(session_id, payload)`

共享 runtime 会根据 `visit` 和 `session` 进入统一 graph，然后调用各专科 service 的：

- `prepare_create_session()`
- `validate_continue_session()`

一轮/二轮不是通过单独路由区分，而是由 `visit.state` 决定：

- `IN_CONSULTATION` -> `consultation_round = 1`
- `IN_SECOND_CONSULTATION` -> `consultation_round = 2`

内科和外科都遵循这套规则：

- `backend/app/agents/internal_medicine/service.py`
- `backend/app/agents/surgery/service.py`

### 3.2 统一评估流程

共享 runtime 的 `evaluate()` 基本流程如下：

1. 读取当前 `shared_memory` / `private_memory` / `turns`
2. 合并本轮 payload 与历史上下文，生成 `merged_payload`
3. 根据 `consultation_round` 和当前进度尝试解析 policy phase
4. 计算缺失字段 `missing_fields`
5. 走专科规则召回，生成 `evidence`
6. 走专科 fallback 规则，生成基础结论
7. 根据当前状态决定：
   - 新建会话时给出首条 follow-up
   - 信息不足时继续追问
   - 信息足够时请求 LLM 生成最终 JSON
   - 已经完成过一次后再次收到补充时，进入 `post_final_reassessment`

### 3.3 一轮结束后的标准决策

当前两个医生 agent 的一轮决策都被约束为四类：

- `urgent_escalation`
- `test_first`
- `treat_and_discharge`
- `recommend_other_clinic`

其中真正会进入二轮面诊的，是：

- `next_step_decision = "test_first"`
- `needs_second_consultation = true`

这在内科和外科里都是同一套模式：

- `backend/app/agents/internal_medicine/rules.py`
- `backend/app/agents/surgery/rules.py`

---

## 4. 记忆体系与交接方式

这是当前框架最关键的部分。

### 4.1 `shared_memory`: 患者级共享记忆

`shared_memory` 是跨 agent、跨 session 的患者共享记忆，至少包含两部分：

- `profile`
- `clinical_memory`

`profile` 当前主要记录：

- `name`
- `age`
- `sex`
- `allergies`
- `allergy_status`
- `chronic_conditions`

`clinical_memory` 当前主要记录：

- `chief_complaint`
- `symptoms`
- `onset_time`
- `vitals`
- `risk_flags`
- `last_department`

这些值在 `prepare_context()` 和 `apply_chat_updates()` 中持续更新。

作用：

- 同一医生多轮追问时复用
- 不同医生切换时可继承基础事实
- 为 policy、RAG、follow-up 生成提供公共上下文

### 4.2 `private_memory`: 当前 agent 当前 session 的私有记忆

`private_memory` 是单个 agent + 单个 session 维度的记忆。当前内科和外科默认都会初始化这些字段：

- `message_type`
- `missing_fields`
- `assistant_message`
- `evidence`
- `latest_extraction`
- `latest_summary`
- `final_result`
- `consultation_round`
- `progress_memory_key` 对应的进度对象

运行过程中还会写入：

- `force_offline_llm`
- `historical_records_template`
- `historical_records_note`
- `latest_policy`
- `latest_payload`

其中最重要的是：

- `final_result`
  当前 session 的最终结构化结论
- `latest_extraction`
  当前轮从患者自然语言里抽出的结构化信息
- `latest_summary`
  当前轮摘要
- `asked_fields_history`
  历史追问过哪些字段
- `last_question_focus`
  上一问聚焦的字段
- `consultation_round`
  明确当前是一轮还是二轮

### 4.3 `turns`: 对话短期记忆

短期对话历史由 `session_repo.list_turns(session_id)` 读取，属于当前 session 的 turn 级记忆。

每次用户消息会以 `role=user` 追加，每次医生回复会以 `role=assistant` 追加。

assistant turn metadata 还会带：

- `agent_type`
- `message_type`
- `department`
- `priority`
- `question_focus`
- `round`
- 某些专科额外字段，如 `diagnosis_level`、`test_category`

### 4.4 `visit.data_json`: 一轮到二轮、跨节点流转的真正交接层

如果说 `shared_memory` 是“患者知识”，`private_memory` 是“会话内记忆”，那么 `visit.data_json` 才是跨流程交接的主载体。

当前会写入这些典型字段：

- round1 session id
- round2 session id
- `diagnostic_session`
- `simulated_report`
- `test_required`
- `test_category`
- `test_category_label`
- `test_items`
- 某些专科的 `*_round1_summary`
- 某些专科的 `*_round2_summary`

具体例子：

- 内科
  - `internal_medicine_session_id`
  - `internal_medicine_round2_session_id`
  - `internal_medicine_round2_summary`
- 外科
  - `surgery_session_id`
  - `surgery_round2_session_id`
  - `surgery_round1_summary`
  - `surgery_round2_summary`

### 4.5 二轮面诊实际能拿到什么

当前共享 runtime 在二轮时，会自动把这些上下文注入 `merged_payload`：

- `consultation_round = 2`
- `simulated_report`
- `diagnostic_session`
- `historical_records_template`
- 如果存在任意 `*_round1_summary`，则注入为 `previous_round_summary`

这部分是最近已经统一到共享 runtime 的：

- `backend/app/agents/department_runtime/service.py`
- `backend/app/agents/department_runtime/prompting.py`

### 4.6 当前记忆交接的核心现状

当前已经具备“二轮面诊共享能力”，但记忆交接还没有完全标准化，主要表现在：

1. 二轮默认会拿到历史病历模板、检查会话和检查报告
2. 二轮只有在 `visit.data_json` 里存在 `*_round1_summary` 时，才会拿到显式的 `previous_round_summary`
3. 典型“进入二轮”的病例，当前并没有稳定写入统一的 `round1_summary`

这意味着：

- 二轮不是完全失忆
- 但它拿到的主要是“检查上下文”和“共享病历上下文”
- 还不是一份标准化的 `round1 -> round2 handoff package`

这是当前框架里最值得继续优化的地方。

---

## 5. 当前医生 agent 的共同 prompt 规则

### 5.1 统一的 system prompt 骨架

两个医生 agent 现在都使用共享的 system prompt scaffold：

- 一轮 prompt 强调：
  - 先做关键安全信息采集
  - 先筛查 red flags
  - 信息足够后再给结构化初步结论
- 二轮 prompt 强调：
  - 优先结合上一轮摘要
  - 优先结合已有检查结果
  - 优先结合本次患者更新
  - 不要重新从头做完整初诊式采集，除非关键安全信息仍缺失

这部分现在已经是统一能力：

- `backend/app/agents/department_runtime/prompting.py`

### 5.2 统一的 user prompt 结构

两个医生 agent 的最终 LLM user prompt 现在都会包含这些共性上下文：

- `consultation_round`
- `shared_memory`
- `previous_round_summary`
- `simulated_report`
- `diagnostic_session`
- `historical_records_template`
- `latest patient message`
- `missing_fields`
- `previous_final_result`
- `policy_prompt_context`

同时响应 schema 采用统一模式：

- 一轮时要求返回更完整的分流/转科/是否二轮字段
- 二轮时要求返回更收敛的最终诊疗结果字段

### 5.3 统一的 follow-up LLM prompt 规则

如果当前信息不足，两个医生 agent 都会优先尝试用 LLM 生成 follow-up question。

统一约束是：

- 只追问一个短问题
- 基于缺失字段
- 不给诊断
- 不给处方
- 不做超出事实的安慰

而且二轮 follow-up 已经和一轮 follow-up 分开：

- 一轮追问：补基础病史缺口
- 二轮追问：结合上一轮和检查结果，只补足完成再评估所需的关键缺口

### 5.4 当前 prompt 的共同限制

当前共性 prompt 还有两个现实限制：

1. policy card 只覆盖一轮，不覆盖二轮
2. 二轮 prompt 虽然有统一骨架，但专门的二轮输出契约还没有被 policy 化

---

## 6. 当前医生 agent 的共同 RAG 规则

### 6.1 RAG 不是向量库，而是“规则检索 + policy card”

当前两个医生 agent 的知识来源都分成两层：

1. 专科规则 JSON
2. 临床 policy card

不是典型 embedding/vector store RAG。

### 6.2 专科规则 JSON 的共性

两个医生 agent 都有自己的 `rag/*.json` 规则库：

- 内科：`rag/internal_medicine_rules.json`
- 外科：`rag/surgery_rules.json`

规则召回方式都是：

- 拼接 `chief_complaint + symptoms`
- 做关键词匹配计分
- 取 top_k

然后把命中的 rule 作为：

- `evidence`
- fallback 结论的基础来源

### 6.3 policy card 的共性

两个医生 agent 都从同一个 clinical policy cards 目录加载 YAML policy card：

- `backend/app/agents/clinical_policy/cards`

一轮 policy card 共性包含：

- `collection_targets`
- `question_policy`
- `red_flags`
- `forbidden_actions`
- `allowed_outputs`
- `outcome_policy`
- `output_contract`
- `prompt_hints`

共享 runtime 会把匹配到的 card 转成：

- `prompt_policy_context`
- output contract
- validator contract
- fallback contract

再用于：

- prompt 注入
- policy snapshot 校验
- fallback 修正

### 6.4 当前 RAG / policy 的共同缺口

当前最大的共同缺口是：

- 两个医生 agent 都只有 `round1_initial_consultation` policy
- 二轮面诊没有单独 policy card

也就是说：

- 一轮的“能问什么、不能说什么、如何分流”有明确策略约束
- 二轮的“如何解释检查结果、如何完成 disposition、如何做最终闭环”还没有被单独策略化

---

## 7. 各医生 agent 的差异

## 7.1 `internal_medicine`

### Prompt 特点

- 患者可见消息是中文
- 一轮强调：
  - 主诉
  - 起病时间
  - 过敏史
  - 症状变化
- 追问模板偏通用内科病史澄清

主要文件：

- `backend/app/agents/internal_medicine/prompts.py`

### RAG / rules 特点

- 规则库偏发热、呼吸道、胃肠道、一般内科问题
- 风险标记偏：
  - 胸痛
  - 呼吸困难
  - 神经系统急症
  - 休克/循环不稳
- 直出白名单偏保守的普通内科低风险问题
- referral target 较广，会转：
  - 皮肤科
  - 口腔科
  - 眼科
  - 耳鼻喉
  - 妇产科
  - 儿科
  - 精神科

主要文件：

- `backend/app/agents/internal_medicine/rules.py`
- `backend/app/agents/clinical_policy/cards/internal_medicine_initial_consultation.yaml`

### 记忆交接特点

- 一轮完成后典型进入检查流程
- 会写：
  - `internal_medicine_session_id`
  - `diagnostic_session`
  - `simulated_report`
  - `test_*`
- 二轮完成后写：
  - `internal_medicine_round2_session_id`
  - `internal_medicine_round2_summary`

当前没有稳定写入显式的 `internal_medicine_round1_summary` 用于典型二轮交接。

---

## 7.2 `surgery`

### Prompt 特点

- 当前患者可见消息是英文
- 一轮强调：
  - 创伤/伤口/术后/腹部问题
  - 起病 trigger
  - 部位与侧别
  - 出血、肿胀、疼痛、功能变化
- 追问模板更手术/创伤导向

主要文件：

- `backend/app/agents/surgery/prompts.py`

### RAG / rules 特点

- 规则库偏：
  - 创伤
  - 伤口
  - 腹部外科问题
  - 术后复查
- 风险标记偏：
  - 出血
  - 骨折/脱位
  - 术后感染/裂开
  - 外科腹痛
  - 血流动力学不稳
- 直出白名单更具体，包含：
  - routine postoperative dressing change
  - superficial minor wound
  - stable minor wound
- referral target 偏外科相关转科：
  - 骨科
  - 泌尿外科
  - 胸外科
  - 妇产科
  - 皮肤科

主要文件：

- `backend/app/agents/surgery/rules.py`
- `backend/app/agents/clinical_policy/cards/surgery_initial_consultation.yaml`

### 记忆交接特点

- 如果一轮判断需要二轮，会写：
  - `surgery_session_id`
  - `diagnostic_session`
  - `simulated_report`
  - `test_*`
- 如果一轮可以直接结束且无需检查，会写：
  - `surgery_round1_summary`
- 二轮完成后写：
  - `surgery_round2_session_id`
  - `surgery_round2_summary`

因此外科在“无检查直接结束”的路径上有显式 round1 summary，但典型进入二轮的 `test_first` 路径，仍然主要依赖检查报告和 visit data，而不是标准化的 round1 handoff。

---

## 8. 当前共同点与不同点总结

### 8.1 共同点

- 都由同一个 consultation runtime 驱动
- 都使用同一个 shared/private memory 模型
- 都使用同一套一轮四分类决策
- 都把 `test_first` 作为进入二轮的核心触发
- 都使用“规则 JSON + policy card”双层知识结构
- 都已经接入统一的二轮 prompt 骨架
- 都会在二轮时默认注入历史病历模板、检查会话、检查报告

### 8.2 不同点

- 内科患者话术当前是中文，外科当前是英文
- 内科风险规则偏系统性内科急症，外科偏创伤/术后/腹部外科急症
- 内科 referral target 更广泛地覆盖非外科门诊
- 外科 direct-treat 场景更细粒度、更程序化
- 内科当前没有显式 `round1_summary` 的典型二轮交接字段
- 外科只有部分路径写 `round1_summary`

---

## 9. 当前最重要的现实结论

如果只用一句话总结当前系统：

**两个医生 agent 已经共享了一套一轮/二轮面诊框架，但“二轮是否能完整继承一轮的医生思路”还没有完全标准化，目前更多依赖共享病历、检查结果和 visit data，而不是统一的 `round1 -> round2` 结构化交接包。**

这也是后续继续优化时，最应该优先补的能力层。

---

## 10. 直接相关代码入口

如果后续继续改这套框架，最关键的入口文件如下：

- `backend/app/services/consultation_registry.py`
- `backend/app/agents/department_runtime/service.py`
- `backend/app/agents/department_runtime/prompting.py`
- `backend/app/agents/internal_medicine/config.py`
- `backend/app/agents/internal_medicine/service.py`
- `backend/app/agents/internal_medicine/rules.py`
- `backend/app/agents/internal_medicine/prompts.py`
- `backend/app/agents/internal_medicine/policy.py`
- `backend/app/agents/surgery/config.py`
- `backend/app/agents/surgery/service.py`
- `backend/app/agents/surgery/rules.py`
- `backend/app/agents/surgery/prompts.py`
- `backend/app/agents/surgery/policy.py`
- `backend/app/agents/clinical_policy/cards/internal_medicine_initial_consultation.yaml`
- `backend/app/agents/clinical_policy/cards/surgery_initial_consultation.yaml`
