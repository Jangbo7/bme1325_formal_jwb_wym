# 门诊状态模型说明

> 本文以当前源码为准，重点解释五层语义：
> `VisitLifecycleState`、`PatientLifecycleState`、`StandardOutpatientState`、`disposition`、`runtime projection`。

## 1. 先分清五层语义

### 1.1 `VisitLifecycleState`

定义文件：

- `backend/app/schemas/common.py`
- `backend/app/domain/visit/state_machine.py`

它表示 visit 当前处在哪个流程阶段，例如：

- `triaging`
- `waiting_consultation`
- `waiting_test`
- `diagnosis_finalized`
- `waiting_payment`
- `disposition_pending`

### 1.2 `PatientLifecycleState`

定义文件：

- `backend/app/schemas/common.py`
- `backend/app/domain/patient/state_machine.py`

它更偏“病人在整个流程里当前处于什么运行态”，例如：

- `triaging`
- `queued`
- `called`
- `in_consultation`
- `in_test`
- `completed`

### 1.3 `StandardOutpatientState`

定义文件：

- `backend/app/schemas/orchestration.py`
- `backend/app/services/encounter_orchestration.py`

这是 encounter 级标准门诊状态机，用来把内部 visit 状态映射成更稳定的门诊业务语义，例如：

- `IN_TRIAGE`
- `WAITING_CALL`
- `IN_INITIAL_CONSULTATION`
- `WAITING_MEDICAL_PAYMENT`
- `DISPOSITION_PENDING`
- `TRANSFERRING`

### 1.4 `disposition`

定义文件：

- `backend/app/services/disposition.py`

它表示医生或系统给出的结构化去向建议，例如：

- `outpatient_treatment`
- `followup_booking`
- `specialty_referral`
- `emergency_escalation`
- `icu_rescue`
- `inpatient_admission`

### 1.5 `runtime projection`

定义文件：

- `backend/app/services/runtime_projection.py`

它不是业务真值，而是给前端 / 控制台消费的显示投影，例如：

- `triage`
- `waiting_call`
- `consultation`
- `testing`
- `procedure`
- `payment`
- `pharmacy`
- `finished`

## 2. 当前门诊主链路

### 2.1 分诊阶段

主线起点是：

- `arrived`
- `registration_pending`

当前实际主路径会进入：

- `triaging`
- `waiting_followup`
- `triaged`

说明：

- `waiting_triage`、`in_triage` 仍保留在枚举里，但不是当前 `VISIT_TRANSITIONS` 主表的主要入口
- 兼容值可以保留，但新逻辑不应优先围绕它们建模

### 2.2 首轮门诊

分诊完成后，主线进入：

- `registered`
- `waiting_consultation`
- `in_consultation`

在 `in_consultation` 之后，当前主要有三条分支：

1. 需要检查
2. 需要门诊处置
3. 无检查直接完成问诊

### 2.3 检查分支

检查相关状态：

- `waiting_test`
- `waiting_test_payment`
- `test_payment_completed`
- `in_test`
- `waiting_return_consultation`
- `results_ready`
- `waiting_second_consultation`
- `in_second_consultation`

### 2.4 门诊处置分支

门诊处置相关状态：

- `waiting_outpatient_procedure`
- `in_outpatient_procedure`

处置完成后会回到：

- `results_ready`
- 或重新进入检查链路

### 2.5 结算与处置分支

当前后端把问诊完成后的结算 / 去向拆成：

- `diagnosis_finalized`
- `waiting_payment`
- `medical_payment_completed`
- `disposition_pending`
- `waiting_pharmacy`
- `disposition_outpatient_treatment`
- `disposition_followup_booking`
- `disposition_referral`
- `admitted`
- `transferring`
- `completed`

## 3. 哪些状态不算门诊结束

这部分容易被前端误判。

当前不应视为门诊完成的 visit 状态包括：

- `diagnosis_finalized`
- `waiting_payment`
- `medical_payment_completed`
- `disposition_pending`
- `waiting_pharmacy`

这些状态已经离开“问诊中”，但还没真正完成门诊去向落地。

对应地，`runtime_projection` 会把其中一部分投影成：

- `payment`
- `pharmacy`

但这不等于患者已经完成整个门诊旅程。

## 4. 哪些状态算门诊流程已完成

当前 `disposition.py` 中真正被视为 `outpatient_flow_finished` 的 visit 状态主要是：

- `in_emergency`
- `in_icu_rescue`
- `disposition_referral`
- `admitted`
- `transferring`
- `completed`

此外：

- `cancelled`
- `error`

会停止自动流程，但不算正常完成。

## 5. 为什么不能只看 `finished`

### 5.1 `finished` 是投影词，不是唯一真值

在 runtime / debug / 前端里，`finished` 更接近：

- 当前门诊流程已经走到终点或转出点

而不是：

- 患者的整个医疗旅程完全结束

### 5.2 `outpatient_flow_finished` 仍需和 visit 状态一起看

`disposition.py` 允许 `visit_data.outpatient_flow_finished` 参与判断，但只有在状态匹配时才应成立。

因此排查问题时不要只看：

- `finished=true`

还要一起看：

- `visit_state`
- `disposition.category`
- `target_department`

## 6. UI 投影应该怎么理解

当前 `runtime_projection.py` 的显示阶段大致是：

- `triage`
- `pending_registration`
- `waiting_call`
- `called`
- `consultation`
- `testing`
- `procedure`
- `payment`
- `pharmacy`
- `finished`
- `error`

这层职责是“让 UI 好渲染”，不是重新定义业务流程。

## 7. 当前建模约定

新增门诊能力时，优先遵守：

1. `visit_state` 只描述流程阶段
2. `disposition` 描述结构化去向
3. `runtime projection` 只做展示映射
4. 不要为每种临床建议继续增加新的顶层 visit 状态

例如，不推荐再新增：

- `recommended_surgery`
- `recommended_icu`
- `recommended_admission`

因为这些语义应落到 `disposition`，而不是让 visit 状态爆炸。

## 8. 当前最重要的排查顺序

看一个患者“为什么显示不对”时，按这个顺序查：

1. `VisitLifecycleState`
2. `PatientLifecycleState`
3. `disposition`
4. `runtime projection`
5. Fullview 映射 / 前端渲染

顺序不要反过来。
- `in_outpatient_procedure`
- `waiting_return_consultation`
- `results_ready`
- `waiting_second_consultation`
- `in_second_consultation`
- `diagnosis_finalized`
- `waiting_payment`
- `medical_payment_completed`

这些状态负责表达普通门诊过程，不负责表达最终建议去向。

## 4. 建议保留并强化的“非普通门诊”状态

以下状态本身就有明确跨模块语义，建议保留并作为正式接口状态使用：

- `in_emergency`
- `in_icu_rescue`
- `disposition_pending`
- `disposition_outpatient_treatment`
- `disposition_followup_booking`
- `disposition_referral`
- `admitted`

其中：

- `in_emergency`
  - 表示病人已从普通门诊视角转入急诊去向
- `in_icu_rescue`
  - 表示病人已从普通门诊视角转入 ICU rescue 去向
- `disposition_pending`
  - 表示门诊诊断已形成，等待系统把建议去向落地为明确流程状态
- `disposition_outpatient_treatment`
  - 表示后续按普通门诊治疗闭环，例如药房、开药、离院指导
- `disposition_followup_booking`
  - 表示后续重点是复诊预约/随访安排
- `disposition_referral`
  - 表示转诊到其他专科/机构
- `admitted`
  - 表示已经进入住院建议或住院接收状态

## 5. disposition 模型

推荐为每个 visit 增加或统一一个结构化 `disposition` 对象，而不是让前端从 `assistant_message` 或 `patient_plan` 猜。

建议字段：

```json
{
  "category": "inpatient_admission",
  "target_service": "surgery",
  "target_department": "Surgery",
  "urgency": "expedited",
  "reason": "Second-round review suggests inpatient surgical management.",
  "source_phase": "doctor_round2",
  "handoff_status": "planned",
  "outpatient_flow_finished": true
}
```

### 5.1 推荐的 `category` 枚举

- `outpatient_treatment`
- `followup_booking`
- `specialty_referral`
- `emergency_escalation`
- `icu_rescue`
- `inpatient_admission`

### 5.2 推荐的 `handoff_status` 枚举

- `none`
- `planned`
- `accepted`
- `transferred`
- `closed`

语义说明：

- `planned`
  - 门诊系统已经给出建议去向，但下游尚未接收
- `accepted`
  - 下游模块或人工流程已经确认接收
- `transferred`
  - 病人已正式转入目标流程
- `closed`
  - 该 disposition 已完成闭环

## 6. 推荐的状态映射规则

### 6.1 triage 直接升级

当 triage 结果已经明确不是普通门诊时，不应再走普通门诊 finished 语义。

推荐映射：

- triage -> Emergency
  - `visit_state = in_emergency`
  - `disposition.category = emergency_escalation`
  - `outpatient_flow_finished = true`
- triage -> ICU
  - `visit_state = in_icu_rescue`
  - `disposition.category = icu_rescue`
  - `outpatient_flow_finished = true`

这里的重点是：

- 门诊流程结束
- 但病人 journey 没结束

### 6.2 医生二轮问诊后的 disposition

当内科/外科在二轮给出最终建议后，建议先统一进入：

- `visit_state = disposition_pending`

然后再根据 `primary_disposition` / `admission_recommendation` / `procedure_recommendation` 落到具体状态。

推荐映射：

- `primary_disposition = outpatient_management`
  - `visit_state = disposition_outpatient_treatment`
- `primary_disposition = observe_then_revisit`
  - `visit_state = disposition_followup_booking`
- `primary_disposition = specialty_referral`
  - `visit_state = disposition_referral`
- `primary_disposition = emergency_escalation`
  - `visit_state = in_emergency`
- `icu_escalation = true`
  - `visit_state = in_icu_rescue`
- `primary_disposition = inpatient_admission_recommended`
  - `visit_state = admitted`

## 7. 关于“建议手术”的建模建议

不建议把“建议手术”本身做成顶层 `visit_state`。

原因：

- “住院”是流程阶段
- “手术建议”更像结构化临床结论

推荐做法：

- `visit_state = admitted` 或 `visit_state = disposition_referral`
- 同时在 `disposition` 或 `final_result` 中保留：
  - `procedure_recommendation.surgery_evaluation_recommended`
  - `procedure_recommendation.urgency`
  - `target_service = surgery`

也就是说：

- 是否需要进一步外科/手术评估：放在结构化 disposition
- 当前流程处于什么阶段：放在 visit_state

这样比新增：

- `surgery_recommended`
- `waiting_surgery_admission`

之类状态更干净。

## 8. 推荐的最小落地版本

如果第一版想尽量少改已有状态机，建议按下面的最小方案推进：

1. 保留现有 `VisitLifecycleState` 枚举，不大改主干流程
2. 新增或统一 `disposition` 结构
3. 在 debug / snapshot / UI 中显式增加：
   - `outpatient_flow_finished`
   - `journey_closed`
4. triage 到急诊/ICU 时，直接写入：
   - `in_emergency`
   - `in_icu_rescue`
5. 二轮最终结论后，先进入：
   - `disposition_pending`
6. 再按 disposition 结果推进到：
   - `disposition_outpatient_treatment`
   - `disposition_followup_booking`
   - `disposition_referral`
   - `admitted`
   - `in_emergency`
   - `in_icu_rescue`

## 9. 前端渲染建议

前端不要再仅依赖文案判断去向。

建议渲染优先读：

1. `visit_state`
2. `disposition.category`
3. `disposition.target_service`
4. `disposition.urgency`
5. `disposition.handoff_status`
6. `outpatient_flow_finished`

前端可以据此稳定区分：

- 普通门诊仍在进行
- 普通门诊已结束，但后续需要复诊
- 普通门诊已结束，但建议住院
- 普通门诊已结束，但转急诊/ICU
- 普通门诊已结束，但转其他专科

## 10. 当前文档的最终口径

本项目后续应采用以下统一口径：

- `completed / finished` 不再默认代表病人全流程结束
- 它们只代表普通门诊阶段结束，或历史兼容字段
- “去向”由 `disposition` 结构表达
- “病人当前流程位置”由 `visit_state` 表达
- triage 直转急诊 / ICU，应直接进入目标状态
- 门诊二轮建议住院 / 手术评估，应进入 disposition / admitted 语义，而不是直接被当成普通门诊 completed
