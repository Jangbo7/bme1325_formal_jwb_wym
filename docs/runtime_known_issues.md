# Runtime Known Issues

Last updated: 2026-06-20

本文只保留当前仍能在源码中确认、且尚未明确修复的问题。

## 1. `surgery` 的急诊升级结论仍可能继续落到缴费

### Summary

当 `surgery` 在首轮问诊直接得出 urgent / emergency escalation 结论且不进入检查链路时，当前实现仍可能继续触发：

- `finalize_without_tests`
- `request_medical_payment`

这会把 visit 推到：

- `diagnosis_finalized`
- `waiting_payment`

而不是立即进入急诊或 ICU 转运链路。

### Why this matters

这会造成两个后果：

1. 业务上去向不对
2. runtime / Fullview 看到的是缴费链路，而不是升级转运链路

### Confirmed source

- `backend/app/agents/surgery/service.py`
- `backend/app/domain/visit/state_machine.py`
- `backend/app/services/encounter_orchestration.py`

当前代码仍存在 `surgery` 无检查完成后继续请求医疗缴费的路径。

### Expected behavior

如果 `primary_disposition` 已明确是：

- `emergency_escalation`
- `icu_escalation`

则应优先走升级 / 转运，而不是普通缴费。

### Status

- confirmed
- not fixed

## 2. Runtime 里仍可能出现非规范科室名 `General Surgery`

### Summary

当前正式科室目录使用的是 `Surgery`，但脚本病人资料里仍保留：

- `General Surgery`

这会导致 runtime 视图、科室汇总或问题归类出现非规范标签。

### Confirmed source

- 规范科室目录：`backend/app/departments/registry.py`
- 旧脚本画像：`backend/app/agents/npc_patient/profile.py`
- 名称保留链路：`backend/app/services/department_assignment.py`
- runtime 调度保留 visit 上的显示名：`backend/app/services/hospital_supervisor.py`

### Why this matters

问题不只是显示文案不统一，还会影响：

- runtime department bucket 的聚合
- 人工排查时对“哪个科室出问题了”的判断

### Expected behavior

所有 runtime 可见的科室标签都应被规范化到正式目录，例如：

- `Surgery`

而不是把 `General Surgery` 当成一个独立显示类别。

### Status

- confirmed
- not fixed

## 3. 维护约定

如果某个问题已经修复，应直接从本文删除，不要把已完成问题长期留在“known issues”列表里。
- Confirmed UI/runtime inconsistency.
- Root cause of the associated `LLM unavailable` issue is not fully confirmed yet.
