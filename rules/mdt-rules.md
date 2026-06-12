# MDT Event Rules

MDT 楼层为 `4F MDT`。核心房间包括 `mdt_call`、`head_doctor`、`mdt_meeting`、`imaging_review`、`final_plan`、`anesthesia_room`、`cardiology_room`、`hbp_room`、`neurosurgery_room`、`orthopaedics_room`、`mdt_records`、`mdt_lounge`、`mdt_memory`、`mdt_kb`、`elevator_4`。

## 发起 MDT 会诊

- 事件 ID: `MDT_CONSULT_REQUESTED`
- 所属分类: MDT 入口
- 触发条件: 急诊、门诊、ICU 或住院医生发起多学科会诊请求。
- 涉及房间: `mdt_call`、发起科室房间。
- 涉及人员/Agent: 发起医生、MDT_Call Agent、患者或病例。
- 前置检查: 病例摘要、主诉、诊断倾向、检查结果和会诊目的完整。
- 执行动作: 创建 MDT 会诊任务，进入 MDT 调度队列。
- 成功后的状态/资源变化: MDT 任务 +1；患者通常保留原科室床位或诊室。
- 阻塞或失败提示: 资料缺失时提示补齐病历和检查结果。
- 可视化表现: 病例标记进入 `mdt_call`，患者可不物理移动。

## MDT 专科分派

- 事件 ID: `MDT_SPECIALTIES_ASSIGNED`
- 所属分类: MDT 调度
- 触发条件: MDT_Call 完成首轮分诊，确定需要参与的专科。
- 涉及房间: `mdt_call`、`anesthesia_room`、`cardiology_room`、`hbp_room`、`neurosurgery_room`、`orthopaedics_room`
- 涉及人员/Agent: MDT_Call Agent、麻醉科、心内科、肝胆胰外科、神经外科、骨科 Agent。
- 前置检查: 至少一个专科被选中；所需专科 Agent 可用。
- 执行动作: 向对应专科发送病例任务。
- 成功后的状态/资源变化: 专科任务队列增加；MDT 主任务进入进行中。
- 阻塞或失败提示: 专科不可用时任务进入等待，并提示缺少对应专家。
- 可视化表现: 对应专科房间高亮。

## MDT 影像复核

- 事件 ID: `MDT_IMAGING_REVIEW_STARTED`
- 所属分类: MDT 资料复核
- 触发条件: 会诊需要影像资料或专科提出影像复核需求。
- 涉及房间: `imaging_review`
- 涉及人员/Agent: 影像医生、head doctor、相关专科医生。
- 前置检查: 影像资料存在；影像复核室可用；患者或病例关联正确。
- 执行动作: 复核影像并形成影像意见。
- 成功后的状态/资源变化: 影像复核意见写入 MDT 任务。
- 阻塞或失败提示: 影像缺失时提示资料不完整，暂停最终方案生成。
- 可视化表现: `imaging_review` 显示检查资料复核中。

## MDT 会议召开

- 事件 ID: `MDT_MEETING_STARTED`
- 所属分类: MDT 会议
- 触发条件: 首轮专科意见已返回，或需要多学科同步讨论。
- 涉及房间: `mdt_meeting`
- 涉及人员/Agent: head doctor、各专科医生、发起科室医生。
- 前置检查: 会议室可用；核心专家到齐或可异步参与；关键资料完整。
- 执行动作: 进行多学科讨论，识别冲突意见和待澄清问题。
- 成功后的状态/资源变化: MDT 任务进入汇总阶段。
- 阻塞或失败提示: 会议室或关键专家不可用时进入 `mdt_lounge` 等待。
- 可视化表现: 多名医生或病例标记聚集到 `mdt_meeting`。

## Head Doctor 汇总

- 事件 ID: `MDT_HEAD_DOCTOR_REVIEWED`
- 所属分类: MDT 汇总
- 触发条件: 专科意见、影像复核和补充问题返回。
- 涉及房间: `head_doctor`
- 涉及人员/Agent: head_doctor Agent、MDT_Call Agent、各专科 Agent。
- 前置检查: 至少有一个专科意见；未解决问题清单已生成。
- 执行动作: 汇总各专科意见，识别风险优先级和冲突点。
- 成功后的状态/资源变化: 生成综合建议草案。
- 阻塞或失败提示: 专科意见不足或冲突未处理时要求二次追问。
- 可视化表现: `head_doctor` 高亮处理。

## MDT 二次追问

- 事件 ID: `MDT_FOLLOWUP_REQUESTED`
- 所属分类: MDT 多轮
- 触发条件: Head Doctor 发现关键资料缺失、风险不明确或专科意见冲突。
- 涉及房间: `mdt_call`、相关专科房间、`mdt_records`
- 涉及人员/Agent: MDT_Call Agent、相关专科医生、发起科室医生。
- 前置检查: 明确待澄清问题；能够定位负责专科或发起科室。
- 执行动作: 生成补充问题并派发给对应专科或原科室。
- 成功后的状态/资源变化: MDT 任务保持进行中，等待补充信息。
- 阻塞或失败提示: 无法获取补充资料时记录 unresolved issues。
- 可视化表现: `mdt_call` 和相关专科房间再次高亮。

## 生成最终方案

- 事件 ID: `MDT_FINAL_PLAN_GENERATED`
- 所属分类: MDT 方案
- 触发条件: Head Doctor 完成综合判断。
- 涉及房间: `final_plan`
- 涉及人员/Agent: head_doctor Agent、Final Surgical Plan Memory Agent、发起医生。
- 前置检查: 风险、建议、下一步计划和安全边界已明确。
- 执行动作: 生成结构化最终方案，包括 `case_summary`、`final_plan`、`key_risks`、`next_steps`。
- 成功后的状态/资源变化: MDT 任务完成；方案返回发起科室。
- 阻塞或失败提示: 缺少安全边界或关键风险时不得标记完成。
- 可视化表现: `final_plan` 高亮，发起科室收到方案。

## MDT 方案记忆更新

- 事件 ID: `MDT_PLAN_MEMORY_UPDATED`
- 所属分类: MDT 多轮方案
- 触发条件: 用户或医生在最终方案后继续补充病情信息。
- 涉及房间: `mdt_memory`、`mdt_kb`
- 涉及人员/Agent: Final Surgical Plan Memory Agent、head doctor。
- 前置检查: 已存在上一轮 MDT 结果；补充信息与同一患者或病例匹配。
- 执行动作: 在既有 MDT 结果基础上更新终局方案。
- 成功后的状态/资源变化: 方案版本更新；原科室收到修订意见。
- 阻塞或失败提示: 无历史方案或病例不匹配时提示无法更新。
- 可视化表现: `mdt_memory` 高亮。

## MDT 返回原科室

- 事件 ID: `MDT_RESULT_RETURNED`
- 所属分类: MDT 返回
- 触发条件: MDT 方案生成或会诊终止。
- 涉及房间: `mdt_call`、`final_plan`、发起科室房间。
- 涉及人员/Agent: MDT 调度员、发起医生、患者或病例。
- 前置检查: 方案状态为完成或明确终止；发起科室可接收结果。
- 执行动作: 将最终方案、风险和建议返回原科室。
- 成功后的状态/资源变化: 患者状态通常不变；原科室根据方案决定治疗、手术、转 ICU 或住院。
- 阻塞或失败提示: 发起科室无法接收时记录待确认。
- 可视化表现: 病例标记从 MDT 返回原科室。
