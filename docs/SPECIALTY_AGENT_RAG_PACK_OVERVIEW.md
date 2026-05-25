# 新增专科 Agent RAG 资料包说明

## 1. 目的

这份文档用于说明当前项目里为新增专科门诊 agent 构建的 RAG 资料包结构、来源和使用方式，方便后续协作同学继续扩展，而不是把 agent 仅仅做成“演示级话术机器人”。

当前这批新增 agent 主要包括：

- `surgery`
- `pediatrics`
- `ent`

它们的设计目标不是直接做真实临床诊断，而是更贴近：

- 门诊场景下的自然问诊
- 明显危险信号识别
- 科室分流与下一步流程建议
- 面向模拟医院系统的结构化输出

---

## 2. 当前 RAG 结构总览

目前的 RAG 不是单一知识库，而是拆成了两层：

### 2.1 专科规则层

每个专科有自己独立的规则文件，负责：

- 典型主诉和关键词匹配
- 基础分流建议
- 推荐检查
- 基本 action plan
- red flag 提示

当前文件：

- `backend/rag/surgery_rules.json`
- `backend/rag/pediatrics_rules.json`
- `backend/rag/ent_rules.json`

### 2.2 官方流程知识层

单独整理了一份“门诊就医官方资料包”，用于增强 agent 的流程感和真实感，重点不是疾病诊断，而是：

- 国家正式诊疗科目 taxonomy
- 国家门诊质量与预约制度要求
- 三甲医院真实门诊流程/预约/复诊/导诊说明
- 儿童、发热、复诊、检查、结果查询、陪同等真实就诊规则

当前文件：

- `backend/rag/outpatient_official_reference_pack.json`

---

## 3. 相关代码文件

### 3.1 RAG 数据文件

- `backend/rag/surgery_rules.json`
- `backend/rag/pediatrics_rules.json`
- `backend/rag/ent_rules.json`
- `backend/rag/outpatient_official_reference_pack.json`

### 3.2 专科 Agent 逻辑

- `backend/app/agents/specialty_agents/rules.py`
- `backend/app/agents/specialty_agents/official_guidance.py`
- `backend/app/agents/specialty_agents/prompts.py`
- `backend/app/agents/specialty_agents/service.py`
- `backend/app/agents/specialty_agents/departments.py`
- `backend/app/agents/specialty_agents/red_flag_rules.py`
- `backend/app/agents/specialty_agents/department_router.py`
- `backend/app/agents/specialty_agents/schemas.py`

### 3.3 Debug 网页端接入

- `backend/app/agents/interactive_debug/controllers.py`
- `backend/app/agents/interactive_debug/specialty_presets.py`
- `backend/app/api/routes/surgery_agent_debug.py`
- `backend/app/api/routes/pediatrics_agent_debug.py`
- `backend/app/api/routes/ent_agent_debug.py`
- `backend/app/main.py`

---

## 4. 专科规则层设计

每个专科规则文件当前采用统一结构：

```json
{
  "id": "rule-id",
  "title": "Rule title",
  "keywords": ["keyword1", "keyword2"],
  "result": {
    "diagnosis_level": 2,
    "priority": "M",
    "department": "Surgery",
    "note": "Short routing or assessment note",
    "tests_required": true,
    "tests_suggested": ["X-ray imaging"],
    "action_plan": ["Step 1", "Step 2"],
    "red_flags": ["red_flag_1"]
  },
  "source": "Specialty outpatient prototype rules"
}
```

### 当前用途

这层规则主要用于：

- 第一轮 coarse routing
- 给 agent 提供基础安全边界
- 在没有复杂临床知识图谱时，先保证输出“像门诊”

### 当前局限

这层仍然是 prototype 规则，不等于真实临床指南全文。后续可以逐步增强成：

- `common_complaints`
- `must_ask_questions`
- `red_flags`
- `routing_rules`
- `followup_constraints`

---

## 5. 官方流程知识层设计

`backend/rag/outpatient_official_reference_pack.json` 当前采用统一结构：

```json
{
  "id": "policy-or-hospital-item-id",
  "source_type": "national_policy | tertiary_hospital_guide",
  "hospital": "optional hospital name",
  "title": "document title",
  "source_url": "official url",
  "applicable_departments": ["all"],
  "tags": ["appointment", "workflow", "pediatrics"],
  "summary": [
    "fact 1",
    "fact 2",
    "fact 3"
  ]
}
```

### 设计意图

这一层不是为了输出医学诊断，而是为了让 agent 的回答更像真实三甲医院门诊：

- 预约还是现场挂号
- 儿童没有身份证怎么处理
- 体温异常是否优先发热门诊
- 复诊是否需要重新挂号
- 门诊能不能直接处理、是否应先做检查
- 是否有检查预约、结果查询、导航、候诊提醒等流程

---

## 6. 当前使用到的官方来源

### 6.1 国家级政策/规范

1. 国家卫健委《医疗机构诊疗科目名录》
   - 用途：作为门诊科室 taxonomy 的正式依据
   - 已知价值：支持 `pain_medicine` 等科室作为正式合法选项

2. 《医疗机构门诊质量管理暂行规定》
   - 用途：强化“门诊质量、安全、流程边界”的设计思路

3. 《关于进一步完善预约诊疗制度加强智慧医院建设的通知》
   - 用途：为预约、导诊、候诊、结果查询、诊间支付等流程提供政策依据

4. 《关于开展改善就医感受提升患者体验主题活动的通知》
   - 用途：支持 patient-facing 回复更注重流程体验与可执行性

5. 《改善就医感受提升患者体验评估操作手册（2023版）》
   - 用途：支持分时段预约、预就诊、新型门诊、结果推送等真实医院能力

### 6.2 三甲医院官方资料

当前已整理入包的医院包括：

1. 北京协和医院
   - 患者问答 / 就医须知
   - 智能导诊
   - 儿童无身份证办理就医凭证
   - 复诊/挂号限制

2. 瑞金医院
   - 门诊就诊须知
   - 发热门诊分流
   - 诊间预约、社区转诊等路径

3. 华山医院
   - 门诊预约规则
   - 爽约/取消/重复预约规则
   - 门诊智慧服务：预约、支付、检查预约、报告查询、导航、候诊查询

### 6.3 已提炼出的“可直接进 RAG”的正文内容

这一节不再只是列来源，而是把已经整理出来、可以直接服务 agent 的知识摘编写进来。

#### A. 国家层面的门诊流程与能力要求

1. 科室 taxonomy 不是随意起名

- 国家卫健委《医疗机构诊疗科目名录》可以作为项目里门诊科室配置的正式依据。
- 疼痛科在正式诊疗科目体系中是合法存在的，不是临时拼出来的演示科室。
- 这意味着门诊 doctor agent 在输出 `department_key` 时，应该尽量落在正式科室分类上，而不是自由创造“胃病科”“咳嗽科”这种非标准名称。

2. 二级以上医院应普遍建立预约诊疗

- 官方文件要求二级以上医院普遍建立预约诊疗制度，且门诊分时段预约要做细。
- 对 agent 来说，这意味着 patient-facing 回复不应只说“去某科室”，而应能顺带提示：
  - 先预约
  - 分时段就诊
  - 复诊可以走诊间预约
  - 检查和复诊存在前后顺序

3. 智慧医院能力已被国家明确鼓励

- 国家政策明确把智能导医分诊、候诊提醒、移动支付、院内导航、检查检验结果查询等纳入智慧医院能力范围。
- 所以 agent 的“下一步动作”应该天然支持这些流程概念，而不是只停留在医学建议。
- 这对于我们后续设计 `routing_decision.next_node` 很重要，可以扩展出：
  - `appointment_node`
  - `exam_booking_node`
  - `report_query_node`
  - `outpatient_queue`

4. 门诊 doctor agent 更适合“流程安全优先”

- 《门诊质量管理暂行规定》和患者体验提升相关文件，核心导向都不是“AI 直接替代医生做诊断”，而是门诊安全、流程顺畅、患者体验和后续衔接。
- 所以当前这批 agent 维持：
  - 不给最终诊断
  - 不开处方
  - 优先识别 red flags
  - 优先做分流和下一步提示

这条路线是符合国家门诊服务治理方向的。

#### B. 北京协和医院官方就医知识摘编

1. 当患者不知道挂哪个科时，医院本身提供“智能导诊”

- 协和官网患者问答明确有“智能导诊/智能导医”的思路。
- 这直接支持我们把 `general_medicine` 或 `specialty_navigation` 设计成合法兜底入口。
- 也就是说：
  - 症状模糊
  - 跨多个系统
  - 信息不足
  - 患者自己说“不知道该看哪个科”

都不是异常情况，而是现实医院里本来就需要导诊系统承接的场景。

2. 儿科不能默认按成人身份处理

- 协和官网明确提到，儿童没有身份证时，可以通过户口本、出生证明等办理就医凭证。
- 对 pediatrics agent 来说，这很重要，因为儿科 RAG 不应该只关心症状，还要关心：
  - 监护人陪同
  - 身份凭证
  - 年龄限制
  - 儿童流程单独处理

3. 每次就诊通常都需要重新挂号

- 协和患者问答里把“每次就诊是否需要挂号”说得很明确。
- 这说明我们的 agent 在设计 follow-up guidance 时，不能默认“患者回来就自动继续看”，而应该有：
  - 是否需要复诊挂号
  - 诊间预约是否存在
  - 复诊是否受原科室限制

#### C. 瑞金医院官方就医知识摘编

1. 发热/呼吸道症状并不一定直接走普通门诊

- 瑞金门诊就诊须知里明确提示，体温异常或呼吸道症状人群需要关注发热门诊分流。
- 这意味着我们后续如果把 `internal_medicine` 做真一点，不能只把“咳嗽低热”都视作普通内科固定流。
- RAG 可以加入：
  - `fever_clinic_hint`
  - `respiratory_isolation_hint`
  - `precheck_temperature_rule`

2. 预约方式不是单一渠道

- 瑞金公开说明了现场预约、诊间预约、自助机、电话、APP、微信公众号、社区转诊等多种入口。
- 对门诊 agent 来说，这代表 patient-facing guidance 可以更真实，例如：
  - “下次复诊可以走诊间预约”
  - “如果已签约社区家庭医生，可走社区转诊”
  - “当天如果未约满，可能还能现场补挂”

3. 复诊和慢病管理强调连续性

- 瑞金很多资料强调诊间预约、社区转诊、互联网医院续方、专病中心闭环。
- 这对 `pain_medicine`、`rehabilitation`、`pediatrics`、`internal_medicine` 这类需要长期管理的 agent 特别重要。
- 未来这类 agent 的 RAG 应该单独加：
  - `followup_interval`
  - `community_referral_path`
  - `internet_hospital_refill_hint`

#### D. 华山医院官方就医知识摘编

1. 专家号/专科号常常是“全预约管理”

- 华山门诊预约规则明确说明，很多号源实行全预约管理，并有取消、爽约、重复预约限制。
- 这意味着 agent 的回复里可以更像真实医院，例如：
  - “建议先预约，不要默认到院即可加号”
  - “同一专科未完成前，不建议重复占号”
  - “如果不能来，需要提前退号”

2. 一个就诊楼层里本来就有多个专科并行

- 华山门诊楼层说明能看到同楼层并行存在口腔科、眼科、耳鼻喉科、康复科等。
- 这和我们前端“小箱庭里的多专科区”设计其实是匹配的。
- 所以从场景设计上，专科 cluster 不是乱做，而是和三甲医院的现实组织方式相符。

3. 智慧服务不只是挂号

- 华山官方服务能力说明里覆盖了预约、支付、检查预约、报告查询、门诊导航、候诊查询、排班查询等。
- 这意味着我们以后如果做更真的门诊 agent，RAG 不该只围绕“看哪个科”，还应该支持：
  - “如何查报告”
  - “检查约在哪里”
  - “候诊怎么查”
  - “是否需要重新预约”

---

## 6.4 可直接转成 RAG 字段的知识模板

下面这些字段，是从上面的政策和三甲医院资料中反推出来的，可作为后续统一知识包模板。

### 通用字段

- `department_taxonomy`
- `allowed_department_keys`
- `appointment_required`
- `time_slot_required`
- `repeat_registration_rule`
- `smart_service_capabilities`
- `report_query_capabilities`
- `navigation_capabilities`
- `community_referral_available`
- `followup_booking_supported`

### 人群与流程字段

- `pediatric_identity_note`
- `guardian_required`
- `fever_clinic_hint`
- `respiratory_symptom_diversion`
- `exam_companion_required`
- `same_day_registration_limit`
- `specialty_repeat_booking_limit`
- `no_show_penalty_hint`

### 安全与分流字段

- `hard_red_flags`
- `specialty_specific_red_flags`
- `emergency_routing_trigger`
- `general_medicine_fallback_trigger`
- `outpatient_queue_trigger`

---

## 6.5 这批官方资料现在如何影响 agent

目前这批官方资料已经不是“摆设”，而是开始影响新专科 agent 的 retrieval：

1. `specialty_rules`
   - 负责专科主诉、检查、action plan、专科红旗

2. `official_guidance`
   - 负责门诊真实流程、预约、复诊、导诊、儿童/发热/检查等规则

在 debug trace 里可以直接看到两类命中：

- `specialty_rules`
- `official_guidance`

这让同学能明显区分：

- 这条建议是来自专科知识
- 还是来自国家/三甲医院流程知识

---

## 7. 当前 retrieval 方式

### 7.1 专科规则检索

文件：

- `backend/app/agents/specialty_agents/rules.py`

当前策略：

- 对 `chief_complaint + symptoms + message` 做简单关键词匹配
- 命中后按分数排序
- 返回 top-k 专科规则

### 7.2 官方知识检索

文件：

- `backend/app/agents/specialty_agents/official_guidance.py`

当前策略：

- 根据 `applicable_departments`
- 根据 `tags`
- 根据 complaint/symptom 文本与 summary 的弱匹配
- 返回 top-k 官方知识条目

---

## 8. 当前 agent 输出结构

新的专科 agent 不是只返回一段话，而是会返回两类内容：

### 8.1 自然语言输出

面向患者，强调：

- 当前主要担忧
- 是否需要检查
- 下一步建议

### 8.2 结构化 doctor decision

当前结构位于：

- `backend/app/agents/specialty_agents/schemas.py`

核心字段包括：

```json
{
  "reply_to_patient": "...",
  "consultation_state": "routed",
  "suspected_department_key": "surgery",
  "urgency": "routine",
  "red_flags": [],
  "missing_information": [],
  "routing_decision": {
    "next_node": "outpatient_queue",
    "department_key": "surgery",
    "reason": "..."
  },
  "structured_result": {
    "...": "..."
  }
}
```

这使它更接近文档里提出的：

- `reply_to_patient`
- `consultation_state`
- `suspected_department_key`
- `urgency`
- `red_flags`
- `routing_decision`

---

## 9. Debug 页面现在能看到什么

新增的 debug 页面：

- `http://127.0.0.1:8787/surgery-agent-debug`
- `http://127.0.0.1:8787/pediatrics-agent-debug`
- `http://127.0.0.1:8787/ent-agent-debug`

在 debug trace 中，现在可以看到：

- `system_prompt`
- `user_prompt`
- `rag_query`
- `rag_hits`
  - `specialty_rules`
  - `official_guidance`
- `parsed_result`
  - `specialty_result`
  - `doctor_decision`

这意味着同学在网页里就能直接看出：

- 命中了哪些专科知识
- 命中了哪些官方政策/医院流程说明
- 最终为什么会走到某个科室/节点

---

## 10. 当前阶段的真实程度

### 已经不再是“纯儿戏”的部分

- 有正式科室 taxonomy 思路
- 有国家政策支撑
- 有三甲医院官网就医规则支撑
- 有 red flag hard rules
- 有结构化 routing decision
- 有 debug trace 可追踪来源

### 仍然还是 MVP 的部分

- 目前只有 3 个专科 prototype
- 官方资料还是 summary 化，不是全文 chunk 化
- retrieval 还比较轻量，尚未做 embedding / rerank
- 还没接入主门诊状态机与正式生产流程
- 还没有完整 12 科室的 `must_ask_questions` 知识包

---

## 11. 推荐下一步扩展方式

建议后续同学按下面顺序继续完善：

### 11.1 先扩数据，再扩模型

优先为 12 个门诊科室都补：

- 典型主诉
- 必问问题
- 关键 red flags
- 推荐下一步流程
- 检查前准备/复诊限制/特殊人群说明

### 11.2 让官方资料更结构化

建议把医院和政策资料进一步拆成：

- `hospital_rules`
- `appointment_rules`
- `exam_prep_rules`
- `special_population_rules`
- `department_specific_rules`

### 11.3 再考虑更重的 RAG

后续如果要继续升级，可以再加：

- chunk 化
- embedding retrieval
- re-ranker
- hospital-specific prompt injection

---

## 12. 一句话总结

当前这批新增 RAG 的定位是：

> 用“国家政策 + 三甲医院官方就医说明 + 专科 prototype 规则”三层知识，把专科门诊 agent 从演示级话术提升到更像真实门诊分流系统的 MVP。

它还不是完整临床系统，但已经开始具备：

- 正式来源支撑
- 门诊流程感
- 安全边界
- 结构化分流能力
