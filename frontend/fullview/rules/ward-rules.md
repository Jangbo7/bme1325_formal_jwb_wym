# Ward Event Rules

住院部楼层为 `5F Ward`。核心房间包括 `ward_admission`、`nurse_station`、`resp_ward`、`card_ward`、`gastro_ward`、`neuro_ward`、`endo_ward`、`gensurg_ward`、`ortho_ward`、`obgyn_ward`、`peds_ward`、`doctor_office`、`diagnostic_center`、`discharge_desk`、`elevator_5`。

## 住院登记

- 事件 ID: `WARD_ADMISSION_REGISTERED`
- 所属分类: 住院入院
- 触发条件: 急诊、门诊、ICU 或外部病例发起住院请求。
- 涉及房间: `ward_admission`
- 涉及人员/Agent: 患者、AdmissionNurse、BedManager、转出科室医生。
- 前置检查: 入院资料完整；患者有有效 `patient_id` 和 `encounter_id`；目标专科存在。
- 执行动作: 完成入院登记和轻量入院评估。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED` 或进入待分床；入院队列更新。
- 阻塞或失败提示: 资料缺失时留在 `ward_admission`，提示补齐入院信息。
- 可视化表现: 患者出现在 `ward_admission`。

## 住院分床

- 事件 ID: `WARD_BED_ASSIGNED`
- 所属分类: 住院床位
- 触发条件: 患者完成入院登记，需要分配普通病区床位。
- 涉及房间: `resp_ward`、`card_ward`、`gastro_ward`、`neuro_ward`、`endo_ward`、`gensurg_ward`、`ortho_ward`、`obgyn_ward`、`peds_ward`
- 涉及人员/Agent: BedManager、AdmissionNurse、ChargeNurseAgent、患者。
- 前置检查: 目标病区有空床；专科、年龄、性别、隔离等约束满足。
- 执行动作: 锁定床位，生成 bed assignment，通知护士长。
- 成功后的状态/资源变化: 目标住院床位 -1；患者绑定床位。
- 阻塞或失败提示: 无床或约束不匹配时患者进入待入院队列，不能移动到病房。
- 可视化表现: 患者从 `ward_admission` 移动到目标病房床位。

## 入科护理接收

- 事件 ID: `WARD_NURSING_RECEPTION_COMPLETED`
- 所属分类: 住院护理
- 触发条件: 患者到达病房床位。
- 涉及房间: `nurse_station`、患者所在 `*_ward`
- 涉及人员/Agent: ChargeNurseAgent、责任护士、患者。
- 前置检查: 患者已分床；责任护士可接收；身份核验通过。
- 执行动作: 完成首次护理评估，生成护理任务和风险标记。
- 成功后的状态/资源变化: 患者正式进入病区护理；护理任务新增。
- 阻塞或失败提示: 未分床或身份核验失败时禁止护理接收。
- 可视化表现: 护士从 `nurse_station` 到患者病房，病房显示护理接收。

## 住院医生查房

- 事件 ID: `WARD_DOCTOR_ROUND_COMPLETED`
- 所属分类: 住院查房
- 触发条件: 到达查房时间，或病情变化需要医生复评。
- 涉及房间: `doctor_office`、患者所在 `*_ward`
- 涉及人员/Agent: ResidentDoctorAgent、患者、责任护士。
- 前置检查: 患者已 `ADMITTED`；医生负责该患者；患者记录可读。
- 执行动作: 医生查房，更新问题列表，开立医嘱、检查或出院评估。
- 成功后的状态/资源变化: 患者状态保持 `ADMITTED` 或 `IN_TREATMENT`；医嘱/检查/出院评估新增。
- 阻塞或失败提示: 患者记录缺失时提示无法查房并触发人工核验。
- 可视化表现: 医生从 `doctor_office` 移动到病房。

## 住院辅助检查

- 事件 ID: `WARD_DIAGNOSTIC_REQUESTED`
- 所属分类: 住院检查
- 触发条件: 医生开立检验、影像或会诊类检查。
- 涉及房间: 患者所在 `*_ward`、`diagnostic_center`
- 涉及人员/Agent: ResidentDoctorAgent、责任护士、DiagnosticCenterAgent、患者。
- 前置检查: 检查医嘱有效；身份核验通过；`diagnostic_center` 可服务或可排队；患者可转运。
- 执行动作: 护士协调检查，检查中心生成报告并回写患者记录。
- 成功后的状态/资源变化: 患者状态短暂变为 `IN_EXAM`，完成后回到 `ADMITTED` 或 `IN_TREATMENT`。
- 阻塞或失败提示: 检查中心忙、患者不稳定或身份核验失败时检查阻塞。
- 可视化表现: 患者从病房移动到 `diagnostic_center`，完成后返回病房。

## 住院护理或给药

- 事件 ID: `WARD_NURSING_TASK_EXECUTED`
- 所属分类: 住院护理
- 触发条件: 有待执行护理任务、给药任务或医生医嘱。
- 涉及房间: `nurse_station`、患者所在 `*_ward`
- 涉及人员/Agent: 责任护士、患者、必要时药师或医生。
- 前置检查: 任务有效；医嘱有效；身份核验通过；高风险操作需要复核。
- 执行动作: 执行护理或给药，记录执行状态。
- 成功后的状态/资源变化: 护理任务变为 DONE；医嘱执行记录新增。
- 阻塞或失败提示: 医嘱缺失、身份核验失败或高风险操作未复核时阻塞。
- 可视化表现: 护士移动到患者病房，病房显示护理/给药。

## 住院病情恶化转 ICU

- 事件 ID: `WARD_TO_ICU_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 患者病情恶化，住院医生判断需要 ICU。
- 涉及房间: 患者所在 `*_ward`、`nurse_station`、`elevator_5`、`icu_admission`、ICU 床位房间。
- 涉及人员/Agent: ResidentDoctorAgent、责任护士、ICU 医生、ICU 护士、BedManager、患者。
- 前置检查: ICU 有匹配床位；ICU 接收确认；患者适合转运；转运人员可用。
- 执行动作: 锁定 ICU 床位，完成交接，患者经电梯转往 ICU。
- 成功后的状态/资源变化: ICU 床位 -1；原住院床位 +1；患者状态保持 `ADMITTED` 或 `IN_TREATMENT`。
- 阻塞或失败提示: ICU 满床时患者留原病房，触发 critical alert，要求床旁抢救或等待 ICU。
- 可视化表现: 患者以 stretcher 形式从 5F 转到 3F ICU。

## 住院转 MDT 会诊

- 事件 ID: `WARD_TO_MDT_CONSULT_REQUESTED`
- 所属分类: MDT 会诊
- 触发条件: 住院医生判断病例需要多学科会诊。
- 涉及房间: `doctor_office`、患者所在 `*_ward`、`mdt_call`、`mdt_meeting`
- 涉及人员/Agent: ResidentDoctorAgent、head doctor、专科医生、患者。
- 前置检查: 病例摘要、检查结果、影像资料完整；MDT 可接收。
- 执行动作: 发起 MDT 请求，传递病例资料。
- 成功后的状态/资源变化: 患者保留原住院床位；MDT 任务 +1。
- 阻塞或失败提示: 资料不完整或 MDT 无空档时进入会诊等待。
- 可视化表现: 病例标记或医生移动到 4F MDT，患者可留病房。

## 住院转床

- 事件 ID: `WARD_BED_TRANSFER_COMPLETED`
- 所属分类: 住院床位
- 触发条件: 患者需要从一个病房或床位转到另一个病房或床位。
- 涉及房间: 任意两个 `*_ward`
- 涉及人员/Agent: BedManager、ChargeNurseAgent、责任护士、患者。
- 前置检查: 新床可用；转床原因有效；护士长确认；原床当前由该患者占用。
- 执行动作: 锁定新床，转移患者，释放原床。
- 成功后的状态/资源变化: 新床位 -1；原床位 +1；患者床位记录更新。
- 阻塞或失败提示: 新床不可用时不得释放原床，提示转床失败。
- 可视化表现: 患者从原病房移动到新病房。

## 住院出院

- 事件 ID: `WARD_DISCHARGE_COMPLETED`
- 所属分类: 住院出院
- 触发条件: 医生出院评估通过并下达出院医嘱。
- 涉及房间: 患者所在 `*_ward`、`discharge_desk`
- 涉及人员/Agent: ResidentDoctorAgent、AdmissionNurse、责任护士、患者。
- 前置检查: 出院医嘱有效；护理宣教完成；费用或文书已处理；身份核验通过。
- 执行动作: 办理出院，关闭住院流程，释放床位。
- 成功后的状态/资源变化: 患者状态变为 `DISCHARGED`，随后可进入 `COMPLETED`；住院床位 +1。
- 阻塞或失败提示: 未完成医嘱、检查、费用或宣教时禁止出院。
- 可视化表现: 患者从病房移动到 `discharge_desk` 后离开。
