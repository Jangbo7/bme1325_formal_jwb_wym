# 门诊流程状态节点文档

> 本文档描述当前后端已完善的普通门诊（非急诊/非ICU/非住院）流程中，病人可能到达的所有状态节点。每个状态由三层状态机共同描述：**PatientLifecycleState**（患者生命周期）、**VisitLifecycleState**（就诊生命周期）、**DialogueState**（对话状态机）。

---

## 一、门诊主流程状态图

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐
│ UNTRIAGED│───▶│ TRIAGING │───▶│  TRIAGED │───▶│ REGISTERED│───▶│WAITING_CONSULTAT.│
│          │    │(多轮对话) │    │          │    │          │    │                  │
│  ARRIVED │    │ TRIAGING │    │  TRIAGED │    │REGISTERED│    │WAITING_CONSULTAT.│
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └────────┬─────────┘
                                                                         │
                                                                         ▼
                                                                  ┌──────────────┐
                                                                  │    CALLED     │  ← 叫号
                                                                  │WAITING_CONS.  │
                                                                  └──────┬───────┘
                                                                         │
                                                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            IN_CONSULTATION (Round 1)                                 │
│                      内科/外科问诊 · 多轮对话                                         │
│          Dialogue: COLLECTING_INFO → EVALUATING →                                    │
│                NEEDS_FOLLOWUP ⇄ AWAITING_PATIENT_REPLY                               │
│                            → DIAGNOSIS_COMPLETE                                       │
└──────────────────────────────────────┬────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │ (内科路径)        │                  │ (外科路径)
                    ▼                  │                  ▼
             ┌──────────┐              │    ┌───────────────────────────┐
             │ IN_TEST  │              │    │WAITING_OUTPATIENT_PROCEDURE│ ← 门诊手术等待
             │          │              │    └─────────────┬─────────────┘
             └────┬─────┘              │                  │
                  │                    │                  ▼
                  │                    │    ┌──────────────────────────┐
                  │                    │    │IN_OUTPATIENT_PROCEDURE   │ ← 门诊手术中
                  │                    │    │  (手术室/操作室)          │
                  │                    │    └─────────────┬────────────┘
                  │                    │                  │
                  ▼                    │    ┌─────────────┼─────────────┐
           ┌──────────────┐           │    │             │             │
           │RESULTS_READY │           │    ▼             ▼             ▼
           │WAITING_RETURN│           │  ┌──────────┐ ┌──────────┐
           │_CONSULTATION │           │  │ IN_TEST  │ │RESULTS_  │ ← 手术+检查可以并行
           └──────┬───────┘           │  │          │ │READY     │     或先后执行
                  │                   │  └────┬─────┘ └────┬─────┘
                  │                   │       │            │
                  └───────────────────┼───────┘            │
                                      │                    │
                                      ▼                    ▼
                              ┌──────────────────────────────────┐
                              │     IN_SECOND_CONSULTATION        │
                              │        (Round 2) 复诊 · 出方案    │
                              │  Dialogue: ... → COMPLETED        │
                              └────────────────┬─────────────────┘
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │DIAGNOSIS_FINAL. │
                                      └────────┬────────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │WAITING_PAYMENT│
                                        └──────┬───────┘
                                               │
                                               ▼
                                   ┌───────────────────┐
                                   │MEDICAL_PAYMENT_   │
                                   │COMPLETED           │
                                   └────────┬──────────┘
                                            │
                                            ▼
                             ┌──────────────────────────────┐
                             │       DISPOSITION_PENDING     │
                             └──────────────┬───────────────┘
                                            │
                        ┌───────────────────┼───────────────────┐
                        ▼                   ▼                   ▼
             ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
             │DISPOSITION_      │ │DISPOSITION_      │ │DISPOSITION_      │
             │OUTPATIENT_       │ │FOLLOWUP_BOOKING  │ │REFERRAL          │
             │TREATMENT         │ │                  │ │                  │
             └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
                      │                    │                    │
                      ▼                    ▼                    ▼
                ┌──────────┐        ┌──────────┐        ┌──────────┐
                │ COMPLETED│        │ COMPLETED│        │ COMPLETED│
                └──────────┘        └──────────┘        └──────────┘
```

---

## 二、PatientLifecycleState（患者生命周期）

定义文件：[backend/app/schemas/common.py](backend/app/schemas/common.py)

| # | 状态值 | 含义 | 触发事件 | 前端表现 |
|---|--------|------|----------|----------|
| 1 | `untriaged` | 未分诊 | 患者首次创建 | 显示"开始分诊"入口 |
| 2 | `triaging` | 分诊中 | `begin_triage` | 分诊对话界面 |
| 3 | `waiting_followup` | 等待患者回复 | `followup_requested` | 显示追问问题，等待用户输入 |
| 4 | `triaged` | 已分诊 | `triage_completed` | 显示分诊结果卡片 + 挂号按钮 |
| 5 | `queued` | 排队中 | `queue_created` | 显示排队号 + 倒计时 |
| 6 | `called` | 已叫号 | `ticket_called` | 高亮提示"请进入诊室" |
| 7 | `in_consultation` | 问诊中 | `start_consultation` | 医生对话界面 |
| 8 | `in_test` | 检查/手术中 | `internal_medicine_completed` 或 `surgery_completed`（R1完成） | 显示检查进行中 / 手术进行中 / 报告 |
| 9 | `completed` | 就诊完成 | `finish`（R2完成） | 显示完成总结 |

---

## 三、VisitLifecycleState（就诊生命周期）

定义文件：[backend/app/schemas/common.py](backend/app/schemas/common.py)

> 比 PatientLifecycleState 更细粒度，驱动 `current_node`、`current_department`、`ui_flags`。

### 3.1 门诊核心路径（含手术岔路）

| # | 状态值 | 含义 | current_department | 对应ui_flags | 所属路径 |
|---|--------|------|-------------------|-------------|----------|
| 1 | `arrived` | 已到达 | Lobby | `can_submit_triage = true` | 共有 |
| 2 | `triaging` | 分诊对话中 | Triage | `can_continue_triage = true` | 共有 |
| 3 | `waiting_followup` | 等待分诊追问回复 | Triage | `can_continue_triage = true` | 共有 |
| 4 | `triaged` | 分诊完成 | Registration | `can_register = true` | 共有 |
| 5 | `registered` | 已挂号 | 分配科室 | `can_progress_visit = true` | 共有 |
| 6 | `waiting_consultation` | 等待叫号问诊 | 分配科室 | `ready_for_consultation = true` | 共有 |
| 7 | `in_consultation` | Round 1 问诊中 | Consultation Room | `can_start_consultation = true` | 共有 |
| 8 | `waiting_outpatient_procedure` | 等待门诊手术 | Outpatient Procedure | — | **外科** |
| 9 | `in_outpatient_procedure` | 门诊手术/操作中 | Outpatient Procedure | — | **外科** |
| 10 | `waiting_test` | 等待化验/检查 | Auxiliary Diagnostic Center | — | 共有 |
| 11 | `in_test` | 化验/检查中 | Auxiliary Diagnostic Center | `can_view_test_report = true` | 共有 |
| 12 | `results_ready` | 检查/手术结果已出 | 分配科室 | `can_view_test_report = true` | 共有 |
| 13 | `waiting_return_consultation` | 等待复诊 | 分配科室 | — | 共有 |
| 14 | `waiting_second_consultation` | 等待第二轮叫号 | 分配科室 | — | 共有 |
| 15 | `in_second_consultation` | Round 2 复诊中 | Consultation Room | `can_start_consultation = true` | 共有 |
| 16 | `diagnosis_finalized` | 诊断已确定 | Consultation | `can_ready_payment = true` | 共有 |
| 17 | `waiting_payment` | 等待缴费 | Payment | — | 共有 |
| 18 | `medical_payment_completed` | 缴费完成 | Payment | — | 共有 |
| 19 | `completed` | 就诊结束 | — | — | 共有 |

### 3.2 Round1 之后的三条岔路

Round1 问诊完成后，根据医生的判断，进入以下三条路径之一（可组合）：

```
                         Round1 完成
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
    │  纯检查路径   │ │  纯手术路径   │ │  检查 + 手术 并行     │
    │  (内科常见)   │ │  (外科: 清创等)│ │  (外科: 复杂病例)     │
    │              │ │              │ │                      │
    │ IN_TEST      │ │ WAITING_OP   │ │ IN_TEST ⇄ WAITING_OP │
    │     ↓        │ │     ↓        │ │     ↓        ↓       │
    │ RESULTS_READY│ │ IN_OP        │ │ RESULTS    IN_OP     │
    │     ↓        │ │     ↓        │ │  READY       ↓       │
    │    (复诊)    │ │ RESULTS_READY│ │     ↓     RESULTS    │
    │              │ │     ↓        │ │    (都完成后复诊)     │
    │              │ │    (复诊)    │ │                      │
    └──────────────┘ └──────────────┘ └──────────────────────┘
```

- **纯检查**：`OutpatientProcedureService.mark_tests_completed()` 判断 `outpatient_procedure_required=false` → 直接 `results_ready`
- **纯手术**：`OutpatientProcedureService.finish_outpatient_procedure()` 判断 `tests_required=false` → 直接 `results_ready`
- **检查+手术**：两者都完成后才进入 `results_ready`，由 `OutpatientProcedureService.requirements_ready()` 判断

### 3.3 disposition（处置）状态（R2完成后）

| # | 状态值 | 含义 | 说明 |
|---|--------|------|------|
| — | `disposition_pending` | 待定处置方案 | R2结束后默认进入 |
| — | `disposition_outpatient_treatment` | 门诊治疗 | 开药/治疗，去药房 |
| — | `disposition_followup_booking` | 预约复诊 | 定期复查 |
| — | `disposition_referral` | 转诊 | 转上级医院/其他科室 |
| — | `waiting_pharmacy` | 等待取药 | 关联disposition_outpatient_treatment |

---

## 四、DialogueState（对话状态机）

### 4.1 分诊对话 TriageDialogueState

定义文件：[backend/app/schemas/common.py](backend/app/schemas/common.py)

```
IDLE → COLLECTING_INITIAL_INFO → EVALUATING
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            NEEDS_FOLLOWUP     TRIAGED          FAILED
                    │          (完成)
                    ▼
          AWAITING_PATIENT_REPLY
                    │
                    ▼
              RE_EVALUATING ──→ (循环最多3轮)
```

| 状态值 | 含义 |
|--------|------|
| `idle` | 初始 |
| `collecting_initial_info` | 收集初始信息 |
| `evaluating` | LLM评估中 |
| `needs_followup` | 需要追问 |
| `awaiting_patient_reply` | 等待患者回复 |
| `re_evaluating` | 重新评估 |
| `triaged` | 分诊完成 |
| `failed` | 失败 |

### 4.2 内科问诊对话 InternalMedicineDialogueState

定义文件：[backend/app/schemas/common.py](backend/app/schemas/common.py)

```
IDLE → COLLECTING_INFO → EVALUATING
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      NEEDS_FOLLOWUP    DIAGNOSIS_COMPLETE   FAILED
              │          (Round1 完成)
              ▼
    AWAITING_PATIENT_REPLY
              │
              ▼
        RE_EVALUATING ──→ (循环)

Round 2 (复诊):
IDLE → COLLECTING_INFO → ... → TREATMENT_PLANNING → COMPLETED
```

| 状态值 | 含义 |
|--------|------|
| `idle` | 初始 |
| `collecting_info` | 收集病史信息 |
| `evaluating` | LLM诊断评估中 |
| `needs_followup` | 需要追问 |
| `awaiting_patient_reply` | 等待患者回复 |
| `re_evaluating` | 重新评估 |
| `diagnosis_complete` | 初步诊断完成（R1结束） |
| `treatment_planning` | 制定治疗方案（R2） |
| `completed` | 问诊完成 |
| `failed` | 失败 |

### 4.3 外科问诊对话 SurgeryDialogueState

> 外科同样使用 `InternalMedicineDialogueState` 的状态值（共用同一套对话状态机），但 Round1 完成后多了一条 **门诊手术** 的判断分支。

区别在于 R1 的 `final_result` 多了三个字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| `needs_outpatient_procedure` | bool | 是否需要门诊手术 |
| `outpatient_procedure_category` | str | 手术类别（如 wound_care） |
| `outpatient_procedure_reason` | str | 手术原因 |

当 `needs_outpatient_procedure=true` 时，`SurgeryService` 调用 `OutpatientProcedureService.route_after_round1()` 进入门诊手术流程。

---

## 五、DepartmentFlowStatus（科室流程状态）

定义文件：[backend/app/schemas/common.py](backend/app/schemas/common.py)

用于 hospital-runtime 和 department-runtime 的投影视图。

| # | 状态值 | 对应visit_state |
|---|--------|----------------|
| 1 | `assigned_pending_registration` | triaged（已分诊未挂号） |
| 2 | `waiting_queue_round1` | registered（排队中） |
| 3 | `called_round1` | waiting_consultation（已叫号） |
| 4 | `in_consultation_round1` | in_consultation（Round1问诊） |
| 5 | `in_test` | in_test / waiting_test 等 |
| 6 | `in_outpatient_procedure` | waiting_outpatient_procedure / in_outpatient_procedure |
| 7 | `waiting_queue_round2` | waiting_second_consultation |
| 8 | `called_round2` | (被叫号) |
| 9 | `in_consultation_round2` | in_second_consultation（Round2问诊） |
| 10 | `finished` | 所有终态（waiting_payment 及之后） |

---

## 六、当前完善的完整路径汇总

### 路径A：内科门诊（无手术）
```
arrived → triaging → triaged → registered → waiting_consultation
→ in_consultation(R1) → in_test → results_ready
→ in_second_consultation(R2) → diagnosis_finalized
→ waiting_payment → medical_payment_completed → completed
```

### 路径B：外科门诊 — 纯手术（无检查）
```
arrived → triaging → triaged → registered → waiting_consultation
→ in_consultation(R1,surgery)
→ waiting_outpatient_procedure → in_outpatient_procedure
→ results_ready
→ in_second_consultation(R2,surgery) → diagnosis_finalized
→ waiting_payment → medical_payment_completed → completed
```

### 路径C：外科门诊 — 检查 + 手术（并行或先后）
```
arrived → triaging → triaged → registered → waiting_consultation
→ in_consultation(R1,surgery)
→ waiting_outpatient_procedure → in_outpatient_procedure
        ↘                          ↙
         （可与 in_test 交叉或同时）
              ↓
         results_ready
              ↓
→ in_second_consultation(R2,surgery) → diagnosis_finalized
→ waiting_payment → medical_payment_completed → completed
```

### 分诊子流程（多轮追问）
```
untriaged → triaging [COLLECTING → EVALUATING → NEEDS_FOLLOWUP ⇄ AWAITING_REPLY] → triaged
```
最多3轮 `NEEDS_FOLLOWUP → AWAITING_REPLY → RE_EVALUATING` 循环。

### 问诊Round1子流程（内科/外科共用）
```
in_consultation [COLLECTING_INFO → EVALUATING → NEEDS_FOLLOWUP ⇄ AWAITING_REPLY → DIAGNOSIS_COMPLETE]
```
医生收集病史 → 开检查单/手术单 → 患者去做检查/手术。

### 门诊手术子流程
```
waiting_outpatient_procedure → in_outpatient_procedure → (完成)
     ↑                              ↑
  route_after_round1()       start_outpatient_procedure()
  mark_tests_completed()      finish_outpatient_procedure()
```
由 `OutpatientProcedureService` 驱动（[outpatient_procedure_service.py](backend/app/services/outpatient_procedure_service.py)），通过 `SurgeryService.after_persist_result()` 触发。

### 问诊Round2子流程
```
in_second_consultation [COLLECTING_INFO → ... → TREATMENT_PLANNING → COMPLETED]
```
医生看报告 → 下诊断 → 开处方/治疗方案 → 出处置意见。

---

## 七、各状态对应的前端场景

| 患者所在阶段 | 前端主界面 | 关键数据 |
|-------------|-----------|---------|
| Lobby（未分诊） | 分诊表单 (`can_submit_triage`) | 输入主诉、症状、生命体征 |
| Triage（分诊对话） | 分诊聊天 (`can_continue_triage`) | dialogue.turns, dialogue.assistant_message |
| Triage完成 | 分诊结果 + 挂号入口 (`can_register`) | patient.triage, triage_evidence |
| 排队中 | 排队号 + 倒计时 (`can_progress_visit`) | queue_ticket, timers |
| 已叫号 | 进入诊室按钮 (`can_enter_consultation`) | queue_ticket.status="called" |
| Round1 问诊（内科） | 内科医生聊天 | dialogue.turns, dialogue.final_result(R1) |
| Round1 问诊（外科） | 外科医生聊天 | dialogue.turns, dialogue.final_result(R1): 含 needs_outpatient_procedure |
| 化验/检查中 | 检查进行中 / 化验报告卡片 (`can_view_test_report`) | latest_test_report, diagnostic_session |
| 门诊手术等待 | 手术安排通知 | visit.data.outpatient_procedure_plan |
| 门诊手术中 | 手术进行中界面 | visit.data.outpatient_procedure_summary |
| Round2 问诊 | 医生聊天 + 报告/手术结果参考 | dialogue.final_result(R2): 诊断、处方、处置 |
| 缴费 | 缴费按钮 (`can_ready_payment`) | — |
| 完成 | 就诊总结 | medical_record_summary |
