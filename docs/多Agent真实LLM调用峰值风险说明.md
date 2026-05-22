# 多 Agent 真实 LLM 调用峰值风险说明

## 1. 结论

当前的多 Agent 设计在接入真实 LLM 后，存在短时间内请求数叠加的风险。

这个风险不是由单个模块单独制造的，而是由多个 Agent 各自独立直连 LLM、并且没有统一的全局限流或请求队列共同造成的。只要多个会话或多个患者在相近时间点推进，就可能出现 burst。

## 2. 主要触发点

### 2.1 分诊

分诊链路会先做一次规则评估，再尝试一次 LLM 分诊；如果需要追问，还会再走一次 LLM 追问文案生成。

相关实现见：
- [backend/app/agents/triage/service.py](../backend/app/agents/triage/service.py)

### 2.2 门诊内科

内科链路在会话创建阶段通常不会直接打 LLM，但在继续会话、最终评估和复盘阶段会发起真实请求。遇到复诊或最终再评估时，同一条就诊链路可能再触发一次额外请求。

相关实现见：
- [backend/app/agents/internal_medicine/service.py](../backend/app/agents/internal_medicine/service.py)

### 2.3 ICU

ICU 链路同样是同步阻塞式的真实 HTTP 调用，没有共享的限流层。

相关实现见：
- [backend/app/agents/icu_doctor/service.py](../backend/app/agents/icu_doctor/service.py)

### 2.4 患者 Agent

患者 Agent 除了正常回复外，生成病例卡时还带有重试机制。一次病例生成最坏情况下会发出多次请求，因为生成器默认允许重试。

相关实现见：
- [backend/app/agents/patient_agent/patient_agent.py](../backend/app/agents/patient_agent/patient_agent.py)
- [backend/app/agents/patient_agent/case_generator.py](../backend/app/agents/patient_agent/case_generator.py)

## 3. 哪些因素会放大峰值

1. 多患者并发推进。
2. 分诊、内科、ICU、患者 Agent 同时处于可调用状态。
3. 病例生成或 JSON 解析失败后触发重试。
4. 调试链路与主流程同时运行。
5. 后端是同步阻塞请求，没有统一的排队或背压机制。

## 4. 哪些部分不会直接制造 LLM 峰值

- NPC simulator 本身不直接调用 LLM，它主要负责定时生成和推进模拟病人。
- 排队、病历卡、事件桥、状态机这些模块本身也不直接打模型，它们更多是消费和投影结果。

相关实现见：
- [backend/app/services/npc_simulator.py](../backend/app/services/npc_simulator.py)
- [backend/app/events/bridge.py](../backend/app/events/bridge.py)

## 5. 当前实现里的保护不足

当前代码里没有看到统一的全局限流器、信号量、请求池或 prompt 去重层。

这意味着：
- 单个 Agent 只能靠自己的逻辑控制请求频率。
- 不同 Agent 之间不会自动互相让出配额。
- 多个同步请求可以在很短时间内叠在一起。

## 6. 实际风险判断

如果只是单用户、低并发联调，通常不会立刻出问题。

如果是真实 LLM 且同时开启以下任意几项，风险会明显上升：
- 多患者模拟。
- 多 Agent 并行调试。
- 真实病例生成。
- 连续追问和复盘。

## 7. 建议的缓解方式

### 7.1 先做全局闸门

在后端加一个统一的 LLM 请求闸门，按进程级并发数或按 patient_id / session_id 做限流。

### 7.2 分层预算

把请求预算拆成两层：
- 全局预算，避免总量冲高。
- 单患者预算，避免一个患者链路短时间内连续打爆模型。

### 7.3 给病例生成做缓存

患者病例卡生成如果在同一 seed 下结果可复用，建议缓存一次，不要在调试时反复重建。

### 7.4 把调试流和主流程隔离

interactive debug、multi-patient debug、NPC simulator 这类后台调试流最好单独配额，避免影响真实主流程。

### 7.5 增加观测

至少记录以下指标：
- 每分钟 LLM 请求数。
- 每个 patient_id 的请求数。
- 每个 session_id 的请求数。
- 请求失败率和重试次数。

## 8. 简短结论

所以答案是：会，而且在并发会话、真实病例生成或多个 Agent 同时活跃时，风险会很明显。

当前最稳妥的做法不是先依赖每个 Agent 自己节流，而是先在系统层加统一限流，再让各个 Agent 保持自己的业务逻辑。