# 模拟医院门诊医生 Agent 的 MVP 实现思路说明

> 建议文件名：`docs/OUTPATIENT_DOCTOR_AGENT_MVP_IDEA.md`  
> 更新时间：2026-05-22  
> 项目场景：Simulated Hospital Triage and Outpatient Flow / 模拟医院分诊与门诊流程系统

---

## 1. 背景与目标

我们当前正在开发一个 **Simulated Hospital Triage and Outpatient Flow / 模拟医院分诊与门诊流程系统**。系统目标不是构建真实医疗诊断工具，而是模拟患者从：

```text
registration / 挂号
  → triage / 分诊
  → queue / 排队
  → consultation / 问诊
  → next node / 后续节点
```

这一整套门诊就诊过程。

现阶段，我们希望先实现一个轻量、可运行、容易展示的 **doctor agent / 医生智能体**。它能够与 **simulated patient / 模拟病人** 进行自然对话，根据患者主诉和补充信息，进行初步问询、识别明显危险信号，并把患者导向合适的门诊科室或 `emergency_node`。

这个设计更接近真实世界中的 **digital triage / 数字分诊** 思路。例如 NHS 111 online 的目标是让用户根据症状回答问题，并被导向合适的 care pathway，而不是获得确定诊断。

---

## 2. 核心设计判断

我们的核心判断是：

> 第一阶段不应把医生 agent 做成严格医学诊断系统，而应做成 **simulation-oriented outpatient consultation agent / 面向仿真的门诊问诊智能体**。

也就是说，当前目标不是：

```text
症状 → 精确疾病诊断 → 治疗方案
```

而是：

```text
症状 → 追问关键信息 → 检查 red flags → 推荐科室 / 排队节点 / 急诊节点
```

这样做的原因是：

1. 我们的项目主要用于模拟医院流程，不是用于真实临床诊疗。
2. 医生 agent 的重点是让流程“像医院”、交互“自然”、分流“大致合理”。
3. 如果一开始追求完整医学 RAG / clinical guideline / 疾病诊断，会显著增加开发复杂度。
4. 医疗 AI 存在 hallucination / 幻觉、过度自信、自动化偏差等风险。
5. 因此，第一版医生 agent 应该是 **prompt-first / 以场景提示为主**，而不是一开始构建复杂医学知识系统。

---

## 3. 科室范围：先做 12 个高频门诊科室

门诊科室配置可以参考国家卫健委《医疗机构诊疗科目名录》。该名录用于医疗机构诊疗科目的标准化登记和管理，因此适合作为本项目的 **department taxonomy / 科室分类基准**。

我们第一阶段选取 12 个适合 MVP 的高频 outpatient departments：

```json
[
  {"code": "02", "name": "全科医疗科", "key": "general_medicine"},
  {"code": "03", "name": "内科", "key": "internal_medicine"},
  {"code": "04", "name": "外科", "key": "surgery"},
  {"code": "05", "name": "妇产科", "key": "ob_gyn"},
  {"code": "07", "name": "儿科", "key": "pediatrics"},
  {"code": "10", "name": "眼科", "key": "ophthalmology"},
  {"code": "11", "name": "耳鼻咽喉科", "key": "ent"},
  {"code": "12", "name": "口腔科", "key": "dentistry"},
  {"code": "13", "name": "皮肤科", "key": "dermatology"},
  {"code": "15", "name": "精神科", "key": "psychiatry"},
  {"code": "21", "name": "康复医学科", "key": "rehabilitation"},
  {"code": "27", "name": "疼痛科", "key": "pain_medicine"}
]
```

其中 **general_medicine / 全科医疗科** 作为系统兜底科室。当患者症状模糊、跨多个系统、或医生 agent 信心不足时，默认推荐全科医疗科。

---

## 4. 医生 Agent 的定位

医生 agent 的角色不是 **diagnosis agent / 诊断智能体**，而是：

> **Outpatient Consultation and Routing Agent / 门诊问诊与分流智能体**

它负责：

| 能力 | 是否允许 | 说明 |
|---|---:|---|
| 询问主诉 chief complaint | 允许 | 例如“哪里不舒服”“持续多久” |
| 追问症状细节 | 允许 | duration、severity、associated symptoms |
| 识别明显 red flags | 必须 | 例如胸痛伴呼吸困难、意识模糊、严重外伤、自伤风险 |
| 推荐门诊科室 | 允许 | 只能从 12 个 configured departments 中选择 |
| 输出正式诊断 | 不建议 | 可以说“需要进一步评估”，不能说“你就是某病” |
| 开药或治疗方案 | 不允许 | 第一版不做 medication / prescription |
| 决定系统节点 | 允许 | `ask_more`、`outpatient_queue`、`emergency_node` 等 |

---

## 5. 最简技术路线

第一阶段采用：

```text
Prompt-first + Rule-light + RAG-later
```

### 5.1 Prompt-first

先通过 **scenario prompt / 场景提示** 控制医生 agent 的行为，让 LLM 利用自身通用医学常识完成自然问诊。

重点是让它知道：

```text
这是模拟医院系统；
目标不是诊断；
目标是自然问诊和科室分流；
不能自由创造科室；
不能开药；
不能输出正式诊断。
```

### 5.2 Rule-light

在 LLM 外部加一层简单的 **hard rules / 硬规则**，用于处理明显危险情况。

例如：

```yaml
emergency_red_flags:
  - chest pain with shortness of breath
  - loss of consciousness
  - severe bleeding
  - severe trauma
  - sudden weakness or speech difficulty
  - suicidal intent
  - severe allergic reaction
  - severe abdominal pain with persistent vomiting
```

这些规则不追求覆盖所有医学情况，只用于保证 simulation 中最明显的危险情况不会被普通门诊流程吞掉。

### 5.3 RAG-later

**RAG / Retrieval-Augmented Generation** 可以作为第二阶段扩展。

第一阶段不需要为每个科室准备完整 clinical guideline。后续可以逐步为每个科室补充：

```text
common_complaints
must_ask_questions
red_flags
routing_rules
example_cases
```

---

## 6. 推荐系统结构

建议将医生 agent 拆成两个层次：

```text
Doctor Dialogue Layer
负责生成自然语言问诊回复。

Triage Decision Layer
负责生成结构化 routing decision。
```

整体流程：

```text
patient message
   ↓
doctor agent prompt
   ↓
natural reply + structured decision JSON
   ↓
red flag rule checker
   ↓
department router
   ↓
queue / emergency / ask_more
```

这样可以同时保留 LLM 的灵活性和系统状态机的可控性。

---

## 7. 医生 Agent 的输出格式

每轮医生 agent 输出建议固定为 JSON，方便后端接入 `queue system`、`EventBus` 和 `patient lifecycle state machine`。

### 7.1 继续问诊时

```json
{
  "reply_to_patient": "我先了解一下，你这个咳嗽大概持续多久了？有没有发热、胸痛或者呼吸困难？",
  "consultation_state": "asking_more",
  "suspected_department_key": "internal_medicine",
  "urgency": "routine",
  "red_flags": [],
  "missing_information": ["duration", "fever", "chest_pain", "breathing_difficulty"],
  "routing_decision": {
    "next_node": "ask_more",
    "department_key": null,
    "reason": "当前信息不足，需要继续询问症状持续时间和危险信号"
  }
}
```

### 7.2 最终分流时

```json
{
  "reply_to_patient": "根据你目前的描述，更适合先到内科门诊进一步评估。我会帮你进入内科排队。",
  "consultation_state": "routed",
  "suspected_department_key": "internal_medicine",
  "urgency": "routine",
  "red_flags": [],
  "missing_information": [],
  "routing_decision": {
    "next_node": "outpatient_queue",
    "department_key": "internal_medicine",
    "reason": "患者主诉为咳嗽、低热、乏力，无明显急诊危险信号，符合普通内科门诊场景"
  }
}
```

---

## 8. 医生 Agent 的 System Prompt 草稿

```text
You are a doctor agent in a simulated outpatient hospital system.

This is a simulation, not real medical care.
Your goal is not to make a final diagnosis.
Your goal is to conduct a realistic but simple outpatient consultation.

You should:
1. Understand the patient's chief complaint.
2. Ask concise follow-up questions.
3. Check for obvious red flags.
4. Decide whether the patient should go to emergency care or one of the configured outpatient departments.
5. Recommend only one primary department unless more information is needed.

Configured outpatient departments:
- general_medicine: 全科医疗科
- internal_medicine: 内科
- surgery: 外科
- ob_gyn: 妇产科
- pediatrics: 儿科
- ophthalmology: 眼科
- ent: 耳鼻咽喉科
- dentistry: 口腔科
- dermatology: 皮肤科
- psychiatry: 精神科
- rehabilitation: 康复医学科
- pain_medicine: 疼痛科

Rules:
- Do not provide a definitive diagnosis.
- Do not prescribe medication.
- Do not say the patient is definitely safe.
- If symptoms are unclear or span multiple systems, route to general_medicine.
- If red flags are present, route to emergency_node.
- For children, consider pediatrics unless another emergency or specialty is clearly more appropriate.
- For possible pregnancy-related symptoms, ask pregnancy status before routing.
- For mental health complaints, always ask about self-harm or harm-to-others risk.
- Keep the conversation natural and short.
```

---

## 9. MVP 模块拆分建议

建议新增以下模块：

```text
backend/app/triage/
  departments.py
  schemas.py
  doctor_agent_prompt.py
  doctor_agent_service.py
  department_router.py
  red_flag_rules.py
  tests/
    test_department_routing.py
    test_red_flags.py
    test_doctor_agent_output.py
```

### 9.1 departments.py

保存 12 个门诊科室配置。

### 9.2 schemas.py

定义结构化输出，例如：

```text
DoctorAgentDecision
RoutingDecision
UrgencyLevel
ConsultationState
```

### 9.3 doctor_agent_prompt.py

保存医生 agent 的 system prompt 和输出格式约束。

### 9.4 doctor_agent_service.py

负责调用 LLM，生成自然回复和结构化 decision JSON。

### 9.5 red_flag_rules.py

在 LLM 输出后进行 deterministic check，覆盖明显急诊情况。

### 9.6 department_router.py

根据 LLM 判断、hard rules 和 fallback 规则，决定最终节点。

---

## 10. 第一阶段验收目标

第一阶段的目标不是医学正确率，而是流程合理性。

建议验收标准：

```text
1. 患者输入一个常见轻症主诉后，医生 agent 能自然追问 2-4 个问题。
2. 医生 agent 不输出正式诊断、不直接开药。
3. 医生 agent 最终能从 12 个科室中选择一个合理科室。
4. 症状模糊时可以分到 general_medicine。
5. 明显 red flags 会进入 emergency_node。
6. 输出 JSON 能被后端 queue / state machine 消费。
7. 至少覆盖 12 个科室各 2-3 个 simulated patient cases。
```

示例测试用例：

| 患者主诉 | 期望科室 / 节点 |
|---|---|
| 皮疹、瘙痒 | dermatology |
| 牙痛、牙龈肿 | dentistry |
| 红眼、视力模糊 | ophthalmology |
| 儿童发热、咳嗽 | pediatrics |
| 焦虑、失眠 | psychiatry |
| 腰痛三个月 | pain_medicine |
| 术后活动受限 | rehabilitation |
| 咳嗽低热 | internal_medicine |
| 伤口出血 | surgery |
| 月经异常 | ob_gyn |
| 症状模糊、全身不适 | general_medicine |
| 咽痛、鼻塞 | ent |
| 胸痛伴呼吸困难 | emergency_node |
| 明确自伤想法 | emergency_node / mental health crisis handling |

---

## 11. 为什么这是合理的第一步

这个方案的优势是：

1. **实现成本低**：主要依赖 prompt 和 structured output，不需要一开始构建完整医学知识库。
2. **展示效果好**：医生 agent 能自然对话，适合 demo。
3. **系统可控**：通过 12 个科室配置、red flag rules 和 JSON schema 控制输出。
4. **可扩展**：后续可以逐步加入 RAG、OpenEMR、FHIR、症状库和科室知识包。
5. **安全边界清楚**：系统明确不是现实医疗工具，不做正式诊断和处方。

---

## 12. 后续扩展方向

后续可以逐步增强：

```text
Phase 1:
Prompt-first doctor agent + hard-coded red flags + 12 departments.

Phase 2:
为每个科室增加 RAG pack：
common_complaints / must_ask / red_flags / routing_rules。

Phase 3:
引入 simulated patient profiles：
年龄、性别、病史、主诉、隐藏症状、期望科室。

Phase 4:
接入 OpenEMR：
把 encounter、department、consultation note、patient record 写入 EMR。

Phase 5:
引入更标准化的数据结构：
FHIR Questionnaire、FHIR Encounter、FHIR Condition、SNOMED / ICD mapping。
```

---

## 13. 给开发者的简短实现说明

```text
Build a prompt-first simulated outpatient doctor agent.

The goal is not clinical diagnosis.
The goal is realistic outpatient consultation and department routing for a hospital simulation.

Requirements:
1. Use the existing 12 outpatient departments as the only allowed department options.
2. The doctor agent should ask natural follow-up questions based on the patient's chief complaint.
3. The agent should never provide a definitive diagnosis or prescription.
4. The agent should output both:
   - a natural language reply to the patient
   - a structured JSON decision object
5. Add a simple red flag rule checker outside the LLM.
6. If red flags are detected, route to emergency_node.
7. If symptoms are vague or confidence is low, route to general_medicine.
8. Keep the implementation simple and modular.
9. Do not build full RAG yet; leave interfaces for future RAG context injection.

Create:
- departments.py
- schemas.py
- doctor_agent_prompt.py
- doctor_agent_service.py
- red_flag_rules.py
- department_router.py
- tests for example patient complaints
```

---

## 14. 总结

我们的当前想法是：

> 先用大模型本身的知识能力和场景 prompt，快速实现一个轻量、自然、可控的门诊医生 agent。

它不追求真实临床诊断，而是服务于模拟医院系统中的流程推进：

```text
问诊 → 分诊 → 识别明显危险信号 → 推荐科室 → 进入排队或急诊节点
```

第一版重点是：

```text
能跑通流程 > 自然对话 > 科室分流合理 > 可结构化接入系统状态机
```

而不是：

```text
医学诊断准确率 > 完整 guideline > 复杂 RAG > 真实临床决策
```

这条路线更适合作为我们的 MVP，也更符合当前模拟医院项目的开发阶段。

---

## 参考资料

1. NHS 111 online：  
   https://111.nhs.uk/

2. NHS: When to use 111 online or call 111：  
   https://www.nhs.uk/nhs-services/urgent-and-emergency-care-services/when-to-use-111/

3. NHS Digital: NHS 111 online service description：  
   https://digital.nhs.uk/services/nhs-111-online

4. 国家卫生健康委员会：《医疗机构诊疗科目名录》：  
   https://www.nhc.gov.cn/fzs/c100048/201808/afa9a6d10b9c4ed3ac36358fc20243ff.shtml

5. WHO: Ethics and governance of artificial intelligence for health: Guidance on large multi-modal models：  
   https://www.who.int/publications/i/item/9789240084759

6. FDA: Clinical Decision Support Software Guidance：  
   https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
