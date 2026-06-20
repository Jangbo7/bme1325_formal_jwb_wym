# 门诊后端行为/状态到前端 Rule 与房间映射

> 审核基线：2026-06-18  
> 后端来源：`backend/app/services/encounter_orchestration.py`、`backend/app/services/runtime_projection.py`、`backend/app/services/disposition.py`  
> 前端来源：`frontend/fullview/full_view/event-rules/outpatient.json`、`map-config.json`  
> 目的：给后续前端 rule / 房间映射层提供当前实现下的对齐基线，便于人工审核。

## 1. 对齐前提

当前后端和 Fullview 仍然是两层系统：

- 后端定义业务状态真值
- Fullview rule 负责房间移动、容量约束和动画
- 前端不应自行推断“是否结束门诊”，应消费后端明确状态

本文件中的映射分三类：

- 已可复用：现有 Fullview rule 可直接承接
- 需补充：后端行为已存在，但前端缺规则或能力
- 仅改状态：状态变化不应触发真实房间移动

## 2. 当前 runtime projection 约束

这次后端改动后，前端映射必须先接受以下语义。

### 2.1 不再视为 finished 的状态

以下状态都只是中间态，不可渲染为 finished：

- `waiting_payment`
- `medical_payment_completed`
- `disposition_pending`
- `waiting_pharmacy`
- `disposition_outpatient_treatment`
- `disposition_followup_booking`

### 2.2 display_stage 约束

当前投影层建议按下面理解：

| visit_state | display_stage |
|---|---|
| `diagnosis_finalized` | `payment` |
| `waiting_payment` | `payment` |
| `medical_payment_completed` | `payment` |
| `disposition_pending` | `payment` |
| `waiting_pharmacy` | `pharmacy` |
| `completed` / `disposition_referral` / `admitted` / `transferring` / `in_emergency` / `in_icu_rescue` | `finished` |
| `error` / `cancelled` | `error` |

补充说明：

- `display_stage=finished` 只应出现在真正 finished 的 visit state 上
- `error` / `cancelled` 应进入 error lane，而不是 finished lane

### 2.3 dispatch_state 约束

当前投影层要求：

- `display_stage=error` 时，`dispatch_state=error`
- `error` / `cancelled` 的渲染应走保底异常表现
- 不要把“自动化停止”理解成“已正常结束”

## 3. 后端节点到 Fullview 房间映射

### 3.1 系统节点

| 后端节点 | Fullview 房间 | 说明 |
|---|---|---|
| `triage` | `R-OP-TRIAGE` | 分诊 |
| `payment` | `R-OP-PAYMENT` | 检查费/医疗费共用 |
| `testing` | `R-OP-LAB` | 检查中心 |
| `outpatient_procedure` | `R-OP-SURGERY-PROCEDURE` | 门诊操作室 |
| `pharmacy` | `R-OP-PHARMACY` | 门诊药房 |

### 3.2 科室与诊室

| 后端 department/node | Fullview 房间 |
|---|---|
| `internal` / `internal_consult_room_1` | `R-OP-INTERNAL` |
| `internal_consult_room_2` | `R-OP-INTERNAL-B` |
| `surgery` / `surgery_consult_room_1` | `R-OP-SURGERY` |
| `surgery_consult_room_2` | `R-OP-SURGERY-B` |
| `surgery_outpatient_procedure_room` | `R-OP-SURGERY-PROCEDURE` |
| `pediatrics_consult_room_1` | `R-OP-PEDIATRICS` |
| `fever_consult_room_1` | `R-OP-FEVER` |
| `obgyn_consult_room_1` | `R-OP-OBGYN` |
| `ophthalmology_consult_room_1` | `R-OP-OPHTHALMOLOGY` |
| `ent_consult_room_1` | `R-OP-ENT` |
| `dentistry_consult_room_1` | `R-OP-DENTISTRY` |
| `dermatology_consult_room_1` | `R-OP-DERMATOLOGY` |
| `psychiatry_consult_room_1` | `R-OP-PSYCHIATRY` |
| `rehabilitation_consult_room_1` | `R-OP-REHABILITATION` |
| `pain_consult_room_1` | `R-OP-PAIN` |

### 3.3 科室门口队列

| department | Fullview 队列 |
|---|---|
| `internal` | `R-OP-QUEUE-INTERNAL` |
| `surgery` | `R-OP-QUEUE-SURGERY` |
| `pediatrics` | `R-OP-QUEUE-PEDIATRICS` |
| `fever` | `R-OP-QUEUE-FEVER` |
| `obgyn` | `R-OP-QUEUE-OBGYN` |
| `ophthalmology` | `R-OP-QUEUE-OPHTHALMOLOGY` |
| `ent` | `R-OP-QUEUE-ENT` |
| `dentistry` | `R-OP-QUEUE-DENTISTRY` |
| `dermatology` | `R-OP-QUEUE-DERMATOLOGY` |
| `psychiatry` | `R-OP-QUEUE-PSYCHIATRY` |
| `rehabilitation` | `R-OP-QUEUE-REHABILITATION` |
| `pain` | `R-OP-QUEUE-PAIN` |
| `testing` | `R-OP-QUEUE-DIAGNOSTIC` |

## 4. 后端行为到前端 Rule 的当前映射

### 4.1 主链路映射表

| 后端事件 | 后端状态变化 | 前端 rule | 类型 | 说明 |
|---|---|---|---|---|
| `begin_triage` | `arrived -> in_triage` | 建议新增 `OP_ARRIVAL_TO_TRIAGE` | movement | 进入分诊 |
| `begin_registration` | `triaged -> in_registration` | 建议新增 `OP_TRIAGE_TO_REGISTRATION` | movement | 分诊到挂号 |
| `register_complete` | `in_registration -> registered` | 建议新增 `OP_REGISTRATION_TO_TARGET_QUEUE` | movement | 挂号到目标科室门口队列 |
| `call_patient` | `registered -> waiting_call` | `OP_CURRENT_TO_TARGET_DOOR_QUEUE` | movement | 需要确保人在目标门口队列 |
| `start_initial_consultation` | `waiting_call -> in_initial_consultation` | `OP_TARGET_DOOR_QUEUE_ADVANCE` | movement | 门口队列进入诊室 |
| `request_test_payment` | `test_ordered -> waiting_test_payment` | `OP_CONSULT_TO_PAYMENT` | movement | 需修改为兼容诊室或门诊操作室来源 |
| `pay_test` | `waiting_test_payment -> test_payment_completed` | 无移动 | 状态更新 | 仍在缴费区 |
| `start_exam` | `test_payment_completed -> in_exam` | `OP_PAYMENT_TO_LAB` | movement | 缴费到检查 |
| `finish_exam` | `in_exam -> waiting_test_results` | `OP_LAB_RETURN_TO_WAITING` | movement | 检查后回原科室等待 |
| `order_outpatient_procedure` | `-> waiting_outpatient_procedure` | 建议新增 `OP_CURRENT_TO_PROCEDURE_QUEUE` | movement | 从当前房间进入外科门诊操作室门口队列 |
| `start_outpatient_procedure` | `waiting_outpatient_procedure -> in_outpatient_procedure` | `OP_TARGET_DOOR_QUEUE_ADVANCE` | movement | 从外科队列进入门诊操作室 |
| `finish_outpatient_procedure` | `in_outpatient_procedure -> results_ready`，且无待检查 | 建议新增 `OP_PROCEDURE_RETURN_TO_TARGET_QUEUE` | movement | 操作后回原科室复诊队列 |
| 操作后仍需检查并触发 `request_test_payment` | `test_ordered -> waiting_test_payment` | 更新 `OP_CONSULT_TO_PAYMENT` | movement | 从操作室进入缴费区 |
| `start_second_consultation` | `waiting_second_consultation -> in_second_consultation` | `OP_SECOND_CONSULT_MOVE` 或 `OP_TARGET_DOOR_QUEUE_ADVANCE` | movement | 复诊进入诊室 |
| `request_medical_payment` | `diagnosis_finalized -> waiting_payment` | `OP_CONSULT_TO_PAYMENT` | movement | 普通门诊缴费开始；与检查缴费共用更新后的来源范围 |
| `pay_medical` | `waiting_payment -> medical_payment_completed` | 无移动 | 状态更新 | 不应二次挪房间 |
| `plan_disposition` | `medical_payment_completed -> disposition_pending` 或 `diagnosis_finalized -> disposition_pending` | 无移动 | 状态更新 | 去向计算，不应触发移动 |
| `choose_pharmacy` | `disposition_pending -> waiting_pharmacy` | `OP_CONSULT_TO_PHARMACY` | movement | 现有 rule 只接受诊室来源，需申请兼容 payment 来源 |
| `dispense_medication` | `waiting_pharmacy -> completed` | 无移动 | 状态更新 | 药房完成事件，后端就诊结束 |
| `choose_outpatient_treatment` | `disposition_pending -> disposition_outpatient_treatment` | 通常无移动 | 状态更新 | 若后续需真实治疗房间，则应改走专门 rule |
| `choose_followup_booking` | `disposition_pending -> disposition_followup_booking` | 通常无移动 | 状态更新 | 当前更像结果态，不是物理移动态 |
| `complete_visit` | `disposition_outpatient_treatment/followup_booking -> completed` | `OP_PATIENT_EXIT_HOSPITAL` | discharge | rule 已存在，但需申请启用 outpatient `discharge_request` |
| `choose_referral` | `disposition_pending -> disposition_referral` | 建议新增 `OP_REFERRAL_TO_REGISTRATION` | movement | 专科转诊要求重新挂号 |
| `route_to_emergency` | `-> in_emergency` | `TRANSFER_OP_TO_ED` | transfer | 不能按普通门诊 movement 处理 |
| `route_to_icu_rescue` | `-> in_icu_rescue` | `OP_TO_ICU_MOVE` | transfer | 转 ICU |
| `admit_patient` | `-> admitted` | `OP_TO_WARD_MOVE` | transfer | 转住院 |
| `start_transfer` | `-> transferring` | 按目标服务选择 transfer rule | transfer | 转运中 |
| `cancel` | `-> cancelled` | 无移动 | 状态更新 | 异常/人工收口 |
| `mark_error` | `-> error` | 无移动 | 状态更新 | 异常保底 |

### 4.2 当前最关键的普通门诊闭环

有药病人：

```text
request_medical_payment
-> pay_medical
-> plan_disposition
-> choose_pharmacy
-> dispense_medication
```

无药病人：

```text
plan_disposition
-> choose_outpatient_treatment / choose_followup_booking
-> complete_visit
```

前端映射层必须明确：`finish` 不是在 `plan_disposition` 时发生，而是在 `dispense_medication` 或 `complete_visit` 之后发生。

## 5. 状态到前端房间/表现的推荐映射

该表用于 snapshot 首次加载、刷新修正、错过 movement event 后的兜底定位。

| visit state | 推荐房间 | 推荐表现 |
|---|---|---|
| `arrived` | 门诊入口或 `R-OP-REGISTRATION` | `walking` |
| `in_triage` / `triaged` | `R-OP-TRIAGE` | `waiting` |
| `in_registration` | `R-OP-REGISTRATION` | `waiting` |
| `registered` / `waiting_call` | 对应科室门口队列 | `waiting` |
| `in_initial_consultation` / `in_second_consultation` | 对应诊室 | `consultation` |
| `test_ordered` | 当前诊室 | `consultation` |
| `waiting_test_payment` / `test_payment_completed` | `R-OP-PAYMENT` | `waiting` |
| `in_exam` | `R-OP-LAB` | `consultation` |
| `waiting_test_results` / `results_ready` / `waiting_second_consultation` | 原科室门口队列 | `waiting` |
| `diagnosis_finalized` | 当前诊室 | `consultation` |
| `waiting_payment` / `medical_payment_completed` | `R-OP-PAYMENT` | `waiting` |
| `disposition_pending` | 当前房间，通常仍在 payment 语义下 | `waiting` |
| `waiting_pharmacy` | `R-OP-PHARMACY` | `waiting` |
| `disposition_outpatient_treatment` | 当前房间或后续专门治疗房间 | `waiting` |
| `disposition_followup_booking` | 当前房间 | `waiting` |
| `disposition_referral` | 转诊挂号/目标科室门口队列 | `waiting` |
| `transferring` | 按动画路径 | `walking` / `wheelchair` / `stretcher` |
| `admitted` | ward/bed | `bed` |
| `in_emergency` / `in_icu_rescue` | ED/ICU 接收位置 | `stretcher` / `bed` |
| `completed` | `exit` | `hidden` |
| `cancelled` / `error` | 原位置保留 | `error` fallback |

## 6. Fullview 侧待提交变更

### 6.1 需新增的 rule

根据当前后端状态机与现有 Fullview rule 差异，需要提交新增：

- `OP_ARRIVAL_TO_TRIAGE`
- `OP_TRIAGE_TO_REGISTRATION`
- `OP_REGISTRATION_TO_TARGET_QUEUE`
- `OP_CURRENT_TO_PROCEDURE_QUEUE`
- `OP_PROCEDURE_RETURN_TO_TARGET_QUEUE`
- `OP_REFERRAL_TO_REGISTRATION`

### 6.2 需修改的现有 rule

`OP_CONSULT_TO_PAYMENT` 当前使用 `current_consult_room`。门诊操作完成后若仍需检查缴费，患者来源可能是 `R-OP-SURGERY-PROCEDURE`，因此申请将来源兼容为 `current_room`，并明确允许操作室来源。

`OP_CONSULT_TO_PHARMACY` 当前只接受 `current_consult_room`，但后端标准链路允许患者在 `R-OP-PAYMENT` 完成支付后进入药房。申请将来源放宽为 `current_room`，并明确允许 `R-OP-PAYMENT`。

### 6.3 需启用的 Fullview capability

`OP_PATIENT_EXIT_HOSPITAL` 已存在，但 outpatient 当前未启用 `discharge_request`。申请 Fullview 维护者启用该 request type，并将现有离院 rule 纳入门诊 discharge 许可范围。

### 6.4 若保留旧 rule，需要明确其适用边界

以下规则与当前后端标准门诊顺序并不完全一致，应限制用途：

- `OP_TRIAGE_TO_CONSULT_ROOM`
- `OP_REGISTRATION_TO_TRIAGE_OR_WAITING`

它们更适合作为特例直达或人工调度，不应覆盖标准主链路。

## 7. 推荐的对齐方式

建议后续映射层按下面原则落地：

1. 后端每次正式状态迁移后，发出明确的前端 movement/transfer/discharge 指令
2. 前端不通过“前后状态 diff”猜动作
3. `display_stage` 只作为展示分层，不作为业务真值
4. `error` / `cancelled` 单独走异常 lane
5. `finished` 只接受真正 finished 的 visit state

## 8. 本次改动后需特别审核的点

人工审核建议重点看以下几项：

1. 前端是否仍把 `waiting_payment`、`medical_payment_completed`、`disposition_pending`、`waiting_pharmacy` 当 finished
2. `choose_pharmacy` 是否允许从 payment 区进入 pharmacy
3. `dispense_medication` 后是否正确投影为 completed/finished
4. `choose_followup_booking` 是否仍被错误映射成旧事件
5. `complete_visit` 的 discharge capability 是否已真正打通
6. `error` / `cancelled` 是否被误渲染为正常结束

## 9. 结论

当前后端状态语义已经明确：

- pharmacy 已进入普通病人主流程
- `dispense_medication` 是正确的药房完成事件
- `waiting_payment`、`medical_payment_completed`、`disposition_pending`、`waiting_pharmacy` 都不是 finished
- `error` / `cancelled` 是异常保底态，不是 finished
- 普通门诊最终结束点是 `dispense_medication` 或 `complete_visit`
- 缺失 rule 与 capability 应通过 Fullview 标准变更申请提交，不由门诊后端直接修改前端

因此，前端映射层下一步不是再猜流程，而是把这些已稳定的后端语义精确投影到 rule 和房间系统上。
