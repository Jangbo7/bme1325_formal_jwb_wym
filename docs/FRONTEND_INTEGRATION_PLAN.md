# 前端接线方案：检验仿真模块接入（历史归档）

## 1. 文档定位
本文件记录的是早期“在前端增加一个模拟完成检查按钮”的方案。当前实现已经转向由后端写入 `simulated_report`、`diagnostic_session` 和 `internal_medicine_round2_summary`，前端只负责读取结果并引导回诊，因此本文应当视为历史归档，不是当前实施依据。

## 2. 当前实现现状
- 内科完成后，后端会把一级辅助检查相关结果落到 `visit.data_json` 中，核心字段是 `simulated_report`、`diagnostic_session` 和 `internal_medicine_round2_summary`。
- 前端通过 `scene/agent/client.js` 里的 `getSimulatedReport`、任务板、病历卡和现有轮询消费这些数据。
- `scene/agent/client.js` 里的 `completeAuxiliaryTest` 仍然只是历史占位封装，当前后端没有对应的业务路由。
- 没有单独成型的检验科跑图页，也没有真实的检查排队与采样流程。

## 3. 如果继续优化前端展示，建议沿用的真实接线
- 任务板只做结果提示和回诊引导。
- 病历卡展示 `simulated_report`。
- `scene/core/bootstrap.js` 继续作为 orchestration layer，负责把轮询到的结果分发给 UI。
- 如果未来补齐真实检查流程，再考虑增加独立的检验科交互页。

## 4. 与旧方案的差异
1. 旧方案假设存在 `WAITING_AUXILIARY_TEST` 和一键完成检查按钮。
2. 现实现并没有该独立业务状态对外暴露。
3. 当前更准确的描述是“内科完成后生成仿真报告，前端读取报告并引导后续流程”。