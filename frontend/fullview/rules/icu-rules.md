# ICU Event Rules

ICU 楼层为 `3F ICU`。核心房间包括 `icu_admission`、`icu_station`、`icu_beds_a`、`icu_beds_b`、`icu_isolation`、`monitor_center`、`intervention_bay`、`risk_sentinel`、`clinical_summary`、`ward_coordinator`、`icu_support`、`icu_medication`、`icu_equipment`、`icu_transfer`、`elevator_3`。

## ICU 接收入院

- 事件 ID: `ICU_ADMISSION_ACCEPTED`
- 所属分类: ICU 入院
- 触发条件: 急诊、门诊或住院部发出 ICU 接收请求并通过前置检查。
- 涉及房间: `icu_admission`、`icu_beds_a`、`icu_beds_b`、`icu_isolation`、`intervention_bay`
- 涉及人员/Agent: 患者、ICU 医生、ICU 护士、BedManager、转出科室医生。
- 前置检查: 有可用 ICU 床位；床位类型匹配；患者资料和 handoff 完整；接收医生确认。
- 执行动作: 锁定床位，完成 ICU 入院接收，生成初始监测任务。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED`；目标 ICU 床位 -1。
- 阻塞或失败提示: ICU 无床、隔离床不匹配或资料缺失时拒绝接收，患者留原科室。
- 可视化表现: 患者从 `icu_admission` 移动到目标 ICU 床位，显示为 bed。

## ICU 床旁监测

- 事件 ID: `ICU_BEDSIDE_MONITOR_RECORDED`
- 所属分类: ICU 监测
- 触发条件: 监护设备产生生命体征、呼吸机参数或趋势数据。
- 涉及房间: `icu_beds_a`、`icu_beds_b`、`icu_isolation`、`intervention_bay`、`monitor_center`
- 涉及人员/Agent: Bedside Monitor Agent、ICU 护士、患者。
- 前置检查: 患者已 `ADMITTED`；床位存在；监测数据格式有效。
- 执行动作: 写入生命体征事件，更新当前状态和趋势摘要。
- 成功后的状态/资源变化: 患者状态保持 `ADMITTED` 或 `IN_TREATMENT`；监测面板更新。
- 阻塞或失败提示: 数据缺失或床位不匹配时提示监测数据无法归档。
- 可视化表现: `monitor_center` 或床位显示实时监测状态。

## ICU 风险告警

- 事件 ID: `ICU_RISK_ALERT_RAISED`
- 所属分类: ICU 风险
- 触发条件: Risk Sentinel 识别休克、低氧、脓毒症、恶化趋势或危急值。
- 涉及房间: `risk_sentinel`、`monitor_center`、患者所在 ICU 床位。
- 涉及人员/Agent: Risk Sentinel Agent、ICU 医生、ICU 护士、Ward Coordinator Agent。
- 前置检查: 有可用监测数据和患者上下文；风险等级达到 warning 或 critical。
- 执行动作: 生成风险评估和告警，通知医生和护士。
- 成功后的状态/资源变化: 患者仍在原床位；部门 alert level 更新。
- 阻塞或失败提示: 无法定位患者床位时触发 `ERROR` 并要求人工核验。
- 可视化表现: `risk_sentinel` 和患者床位高亮 warning/critical。

## ICU 干预执行

- 事件 ID: `ICU_INTERVENTION_STARTED`
- 所属分类: ICU 干预
- 触发条件: 医生决定进行补液、升压、氧疗、机械通气调整或抢救处置。
- 涉及房间: `intervention_bay`、患者所在 ICU 床位、`icu_equipment`
- 涉及人员/Agent: ICU 医生、ICU 护士、Intervention Tracker Agent、患者。
- 前置检查: 医嘱有效；身份核验通过；设备和护士可用。
- 执行动作: 执行干预，记录开始时间、措施和预期效果。
- 成功后的状态/资源变化: 患者状态保持 `IN_TREATMENT`；干预记录新增。
- 阻塞或失败提示: 设备不足、医嘱缺失或身份核验失败时禁止执行。
- 可视化表现: 患者床位或 `intervention_bay` 显示处置状态。

## ICU 用药

- 事件 ID: `ICU_MEDICATION_ADMINISTERED`
- 所属分类: ICU 用药
- 触发条件: ICU 有有效药物医嘱需要执行。
- 涉及房间: `icu_medication`、患者所在 ICU 床位。
- 涉及人员/Agent: ICU 护士、药师或药物审核 Agent、患者。
- 前置检查: 医嘱有效；药物审核通过；身份核验通过；药品库存可用。
- 执行动作: 发药或给药，记录执行人和时间。
- 成功后的状态/资源变化: 用药执行记录新增；药品库存减少。
- 阻塞或失败提示: 药物过敏、重复用药、库存不足或核验失败时阻塞，并通知医生。
- 可视化表现: `icu_medication` 短暂占用，患者床位显示用药事件。

## ICU 家属沟通

- 事件 ID: `ICU_FAMILY_UPDATE_PREPARED`
- 所属分类: ICU 人文沟通
- 触发条件: 家属请求更新，或系统到达每日沟通时间。
- 涉及房间: `icu_support`、`clinical_summary`
- 涉及人员/Agent: ICU 医生、Compassion Agent、家属。
- 前置检查: 患者最新摘要可用；医生确认沟通内容；不直接向家属暴露未经审核建议。
- 执行动作: 生成家属版病情摘要，经医生确认后沟通。
- 成功后的状态/资源变化: 家属沟通记录新增；患者状态不直接改变。
- 阻塞或失败提示: 医生未确认时不得直接交付给家属。
- 可视化表现: `icu_support` 显示沟通中。

## ICU 查房摘要

- 事件 ID: `ICU_CLINICAL_SUMMARY_GENERATED`
- 所属分类: ICU 查房
- 触发条件: 到达查房时间或医生请求摘要。
- 涉及房间: `clinical_summary`、患者所在 ICU 床位。
- 涉及人员/Agent: Clinical Summary Agent、ICU 医生、ICU 护士。
- 前置检查: 最近生命体征、检查、干预和告警数据可用。
- 执行动作: 生成 6h/24h 趋势摘要和当前问题列表。
- 成功后的状态/资源变化: 患者记录新增查房摘要；状态不直接改变。
- 阻塞或失败提示: 数据不足时提示摘要可信度不足。
- 可视化表现: `clinical_summary` 显示摘要生成。

## ICU 多床协调

- 事件 ID: `ICU_WARD_COORDINATION_UPDATED`
- 所属分类: ICU 调度
- 触发条件: 多个床位同时出现告警或资源冲突。
- 涉及房间: `ward_coordinator`、`risk_sentinel`、ICU 床位房间。
- 涉及人员/Agent: Ward Coordinator Agent、ICU 医生、护士长。
- 前置检查: ICU 全部床位状态、告警等级和人员负荷可用。
- 执行动作: 对告警和任务排序，给出优先处理建议。
- 成功后的状态/资源变化: 部门任务优先级更新；患者状态不直接改变。
- 阻塞或失败提示: 数据不完整时提示需要人工查看床位状态。
- 可视化表现: `ward_coordinator` 显示忙碌或 critical。

## ICU 转普通住院

- 事件 ID: `ICU_TO_WARD_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: ICU 医生评估患者病情稳定，可转普通住院。
- 涉及房间: `icu_transfer`、患者所在 ICU 床位、`elevator_3`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: ICU 医生、ICU 护士、住院部医生、BedManager、患者。
- 前置检查: 住院部有匹配床位；住院部接收确认；患者稳定适合普通转运。
- 执行动作: 锁定住院床，完成转出交接，患者经电梯转运到 5F。
- 成功后的状态/资源变化: 住院床位 -1；ICU 床位 +1；患者状态保持 `ADMITTED`。
- 阻塞或失败提示: 住院无床时患者留 ICU，提示普通病房无床。
- 可视化表现: 患者从 ICU 床位移动到住院目标床位。

## ICU 转 MDT

- 事件 ID: `ICU_TO_MDT_CONSULT_REQUESTED`
- 所属分类: MDT 会诊
- 触发条件: ICU 病例需要多学科评估或术前决策。
- 涉及房间: `icu_transfer`、`clinical_summary`、`mdt_call`、`mdt_meeting`
- 涉及人员/Agent: ICU 医生、MDT 调度员、head doctor、专科医生。
- 前置检查: 病例摘要、检查结果和影像资料完整；MDT 调度可接收。
- 执行动作: 发起 MDT 会诊请求，传递病例而非必须转运患者。
- 成功后的状态/资源变化: 患者仍占用 ICU 床位；MDT 任务 +1。
- 阻塞或失败提示: 资料缺失或 MDT 不可用时提示会诊排队。
- 可视化表现: 病例或医生标记移动到 4F MDT，患者可留 ICU。

## ICU 床位释放

- 事件 ID: `ICU_BED_RELEASED`
- 所属分类: ICU 资源
- 触发条件: 患者转出、出院、死亡或床位取消占用。
- 涉及房间: `icu_beds_a`、`icu_beds_b`、`icu_isolation`、`intervention_bay`
- 涉及人员/Agent: ICU 护士、BedManager、患者。
- 前置检查: 转出或终止事件已完成；床位当前确实由该患者占用。
- 执行动作: 释放床位，清理床位占用映射，触发等待队列重试。
- 成功后的状态/资源变化: ICU 可用床位 +1；若有等待患者，触发重新分配。
- 阻塞或失败提示: 患者床位不匹配时提示床位一致性错误。
- 可视化表现: 床位恢复可用，患者从床位消失或进入新房间。
