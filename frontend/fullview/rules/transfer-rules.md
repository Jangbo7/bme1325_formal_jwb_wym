# Cross-Department Transfer Rules

本文件定义跨部门转运事件。所有转运都必须先锁定目标资源，再移动患者。目标资源不可用时，患者必须留在原房间，原资源不得释放。

## 急诊转 ICU

- 事件 ID: `TRANSFER_ED_TO_ICU`
- 所属分类: 跨部门转运
- 触发条件: 急诊医生判断患者需要 ICU 监护或抢救。
- 涉及房间: `ed_red_resus`、`ed_observation`、`ed_handoff`、`elevator_1`、`elevator_3`、`icu_admission`、`icu_beds_a`、`icu_beds_b`、`icu_isolation`、`intervention_bay`
- 涉及人员/Agent: 急诊医生、急诊护士、ICU 医生、ICU 护士、BedManager、患者。
- 前置检查: ICU 有匹配空床；ICU 接收确认；患者转运风险可接受；转运人员可用。
- 执行动作: 锁定 ICU 床位，生成 handoff，患者经电梯转入 ICU。
- 成功后的状态/资源变化: 患者状态由 `TRANSFERRING` 进入 `ADMITTED` 或 `IN_TREATMENT`；ICU 床位 -1；急诊原床位 +1。
- 阻塞或失败提示: ICU 满床、拒收或转运人员不足时，患者留在急诊原房间，发布 `alert.raised`。
- 可视化表现: 患者以 stretcher 形式从 1F 移动到 3F。

## ICU 转住院

- 事件 ID: `TRANSFER_ICU_TO_WARD`
- 所属分类: 跨部门转运
- 触发条件: ICU 医生评估患者稳定，可转普通病区。
- 涉及房间: ICU 原床位、`icu_transfer`、`elevator_3`、`elevator_5`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: ICU 医生、ICU 护士、住院医生、BedManager、责任护士、患者。
- 前置检查: 住院部有匹配专科床位；住院接收确认；患者稳定；转运人员可用。
- 执行动作: 锁定住院床位，完成 ICU 转出和住院接收。
- 成功后的状态/资源变化: ICU 床位 +1；住院床位 -1；患者继续为 `ADMITTED`。
- 阻塞或失败提示: 住院无床时患者留在 ICU 原床位，提示普通病房无床。
- 可视化表现: 患者从 3F ICU 移动到 5F 目标病房。

## 住院转 ICU

- 事件 ID: `TRANSFER_WARD_TO_ICU`
- 所属分类: 跨部门转运
- 触发条件: 住院患者病情恶化，需要 ICU。
- 涉及房间: 原 `*_ward`、`nurse_station`、`elevator_5`、`elevator_3`、`icu_admission`、ICU 床位房间。
- 涉及人员/Agent: 住院医生、责任护士、ICU 医生、ICU 护士、BedManager、患者。
- 前置检查: ICU 有空床；ICU 接收确认；原科医生完成病情摘要；患者可安全转运。
- 执行动作: 锁定 ICU 床位，患者经电梯转入 ICU。
- 成功后的状态/资源变化: ICU 床位 -1；住院原床位 +1；患者状态进入 `IN_TREATMENT` 或保持 `ADMITTED`。
- 阻塞或失败提示: ICU 满床时患者留原住院床，触发 critical alert 和床旁抢救。
- 可视化表现: 患者以 stretcher 形式从 5F 移动到 3F。

## 门诊转住院

- 事件 ID: `TRANSFER_OP_TO_WARD`
- 所属分类: 跨部门转运
- 触发条件: 门诊医生判断患者需要入院。
- 涉及房间: 当前门诊诊室、`doctor_entry_2`、`elevator_2`、`elevator_5`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: 门诊医生、AdmissionNurse、BedManager、患者。
- 前置检查: 入院资料完整；住院部有匹配床位；患者可普通转运。
- 执行动作: 创建住院接收请求，锁定床位，患者转入住院部。
- 成功后的状态/资源变化: 门诊诊室释放；住院床位 -1；患者状态变为 `ADMITTED`。
- 阻塞或失败提示: 住院无床时患者进入待入院队列，门诊诊室释放但不转运。
- 可视化表现: 患者从 2F 移动到 5F。

## 门诊转急诊

- 事件 ID: `TRANSFER_OP_TO_ED`
- 所属分类: 跨部门转运
- 触发条件: 门诊分诊或诊室中发现急危重风险。
- 涉及房间: `triage_2`、当前门诊诊室、`elevator_2`、`elevator_1`、`ed_handoff`、`ed_red_resus`、`ed_observation`
- 涉及人员/Agent: 门诊医生、分诊护士、急诊医生、急诊护士、患者。
- 前置检查: 急诊接收确认；抢救床或观察床可用；转运人员可用。
- 执行动作: 生成急诊交接，患者转入急诊目标房间。
- 成功后的状态/资源变化: 门诊诊室释放；患者进入急诊 `IN_TREATMENT`。
- 阻塞或失败提示: 急诊资源满时患者留在门诊原房间并触发告警。
- 可视化表现: 患者从 2F 移动到 1F。

## 门诊转 ICU

- 事件 ID: `TRANSFER_OP_TO_ICU`
- 所属分类: 跨部门转运
- 触发条件: 门诊发现极危重病情，需要 ICU 直接接收。
- 涉及房间: 当前门诊诊室、`triage_2`、`elevator_2`、`elevator_3`、`icu_admission`、ICU 床位房间。
- 涉及人员/Agent: 门诊医生、ICU 医生、ICU 护士、转运人员、患者。
- 前置检查: ICU 有匹配空床；ICU 接收确认；必要时急诊参与护送。
- 执行动作: 锁定 ICU 床位，患者经电梯转入 ICU。
- 成功后的状态/资源变化: 门诊诊室释放；ICU 床位 -1；患者状态变为 `ADMITTED`。
- 阻塞或失败提示: ICU 满床时患者转急诊抢救或留原房间等待，发布告警。
- 可视化表现: 患者以 stretcher 形式从 2F 移动到 3F。

## 急诊转住院

- 事件 ID: `TRANSFER_ED_TO_WARD`
- 所属分类: 跨部门转运
- 触发条件: 急诊患者稳定但需住院治疗。
- 涉及房间: `ed_observation`、`ed_handoff`、`elevator_1`、`elevator_5`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: 急诊医生、AdmissionNurse、BedManager、责任护士、患者。
- 前置检查: 住院部有匹配床位；急诊摘要完整；患者稳定。
- 执行动作: 锁定住院床，患者转入住院部。
- 成功后的状态/资源变化: 急诊观察床 +1；住院床位 -1；患者状态变为 `ADMITTED`。
- 阻塞或失败提示: 住院无床时患者留在 `ed_observation` 或进入急诊待入院队列。
- 可视化表现: 患者从 1F 移动到 5F。

## 各科转 MDT

- 事件 ID: `TRANSFER_CASE_TO_MDT`
- 所属分类: MDT 会诊
- 触发条件: 急诊、门诊、ICU 或住院医生发起 MDT。
- 涉及房间: 发起科室房间、`mdt_call`、`mdt_meeting`、`head_doctor`
- 涉及人员/Agent: 发起医生、MDT_Call Agent、head_doctor、专科医生。
- 前置检查: 病例资料完整；MDT 可接收；需要的专科可用或可排队。
- 执行动作: 移交病例资料到 MDT 流程。
- 成功后的状态/资源变化: 患者通常保留原床位或诊室；MDT 任务 +1。
- 阻塞或失败提示: 资料缺失、MDT 满负荷或专家不可用时会诊排队。
- 可视化表现: 病例标记移动到 4F，患者实体可保持原位置。

## MDT 方案返回原科室

- 事件 ID: `TRANSFER_MDT_RESULT_TO_SOURCE`
- 所属分类: MDT 返回
- 触发条件: MDT 最终方案生成。
- 涉及房间: `final_plan`、`mdt_call`、发起科室房间。
- 涉及人员/Agent: head_doctor、发起医生、患者或病例。
- 前置检查: 方案已完成；发起科室可接收。
- 执行动作: 将 MDT 方案返回原科室，并触发下一步治疗、手术、住院或 ICU 决策。
- 成功后的状态/资源变化: 患者状态不一定改变；原科室记录新增 MDT 方案。
- 阻塞或失败提示: 发起科室不可用时方案进入待确认队列。
- 可视化表现: 病例标记从 4F 返回发起楼层。
