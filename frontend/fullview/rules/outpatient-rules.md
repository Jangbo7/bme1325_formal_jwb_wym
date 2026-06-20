# Outpatient Department Event Rules

门诊楼层为 `2F Outpatient`。核心房间包括 `registration_2`、`payment_2`、`triage_2`、`consultation_a_2`、`consultation_b_2`、`internal_2`、`surgery_2`、`pediatrics_2`、`fever_2`、`obgyn_2`、`lab_2`、`pharmacy_2`、`doctor_entry_2`、`outpatient_waiting`、`elevator_2`。

## 门诊登记

- 事件 ID: `OP_REGISTRATION_COMPLETED`
- 所属分类: 门诊登记
- 触发条件: 患者到达门诊并完成挂号或复诊登记。
- 涉及房间: `registration_2`、`outpatient_waiting`
- 涉及人员/Agent: 患者、门诊登记护士。
- 前置检查: 患者身份信息完整；无冲突的未完成就诊。
- 执行动作: 创建或更新门诊 encounter，记录挂号科室。
- 成功后的状态/资源变化: 患者状态变为 `REGISTERED`，进入 `outpatient_waiting` 或 `triage_2`。
- 阻塞或失败提示: 挂号信息缺失时留在 `registration_2` 并提示补全。
- 可视化表现: 患者移动到 `outpatient_waiting`。

## 门诊分诊

- 事件 ID: `OP_TRIAGE_COMPLETED`
- 所属分类: 门诊分诊
- 触发条件: 门诊分诊护士完成基础病情评估。
- 涉及房间: `triage_2`、`outpatient_waiting`、`elevator_2`
- 涉及人员/Agent: 患者、分诊护士、门诊医生。
- 前置检查: 患者状态为 `REGISTERED`；分诊台可用。
- 执行动作: 生成 CTAS 等级和推荐科室。
- 成功后的状态/资源变化: L4/L5 进入门诊候诊；L3 根据规则进入门诊或急诊；L1/L2 触发转急诊或 ICU。
- 阻塞或失败提示: 高危患者如果急诊/ICU 暂不可接收，患者留在 `triage_2` 并触发告警。
- 可视化表现: 普通患者进入 `outpatient_waiting`，高危患者经 `elevator_2` 转运。

## 门诊候诊叫号

- 事件 ID: `OP_WAITING_CALLED`
- 所属分类: 门诊队列
- 触发条件: 目标诊室空闲，候诊队列中有对应科室患者。
- 涉及房间: `outpatient_waiting`、`consultation_a_2`、`consultation_b_2`、`internal_2`、`surgery_2`、`pediatrics_2`、`fever_2`、`obgyn_2`
- 涉及人员/Agent: 患者、门诊医生、叫号系统。
- 前置检查: 目标诊室空闲；患者已 `TRIAGED` 或 `REGISTERED`；队列排序合法。
- 执行动作: 从 waiting room 叫号并移动患者到目标诊室。
- 成功后的状态/资源变化: 患者状态变为 `IN_CONSULTATION`；`outpatient_waiting` 人数 -1；诊室占用。
- 阻塞或失败提示: 若诊室占用，患者继续候诊。
- 可视化表现: 患者从 `outpatient_waiting` 移动到对应诊室。

## 门诊初诊完成

- 事件 ID: `OP_FIRST_CONSULTATION_COMPLETED`
- 所属分类: 门诊诊疗
- 触发条件: 医生完成初诊问诊和基础检查。
- 涉及房间: `consultation_a_2`、`consultation_b_2`、`internal_2`、`surgery_2`、`pediatrics_2`、`fever_2`、`obgyn_2`
- 涉及人员/Agent: 患者、门诊医生。
- 前置检查: 患者正在诊室内，状态为 `IN_CONSULTATION`。
- 执行动作: 医生给出下一步：检查、缴费、药房、治疗、转诊、住院或完成就诊。
- 成功后的状态/资源变化: 诊室释放；患者根据医嘱进入下一节点。
- 阻塞或失败提示: 若诊疗结论缺失，患者留在诊室并提示医生补全。
- 可视化表现: 患者离开诊室，候诊队列可叫下一个患者。

## 门诊检查缴费

- 事件 ID: `OP_EXAM_PAYMENT_COMPLETED`
- 所属分类: 门诊缴费
- 触发条件: 医生开立检查后，患者需要先缴费。
- 涉及房间: `payment_2`
- 涉及人员/Agent: 患者、收费人员。
- 前置检查: 存在未支付检查项目；收费窗口可用或可排队。
- 执行动作: 标记检查项目已支付。
- 成功后的状态/资源变化: 患者可进入 `lab_2`；状态可保持 `IN_EXAM` 的前置排队态。
- 阻塞或失败提示: 未找到检查项目时提示不能缴费。
- 可视化表现: 患者移动到 `payment_2` 后再前往 `lab_2`。

## 门诊检查执行

- 事件 ID: `OP_EXAM_STARTED`
- 所属分类: 门诊检查
- 触发条件: 患者检查项目已支付并到达检查室。
- 涉及房间: `lab_2`
- 涉及人员/Agent: 患者、检验/检查人员。
- 前置检查: 患者身份核验通过；`lab_2` 可服务或可排队；检查项目已支付。
- 执行动作: 执行检验或检查，生成结果等待。
- 成功后的状态/资源变化: 患者状态变为 `IN_EXAM`；检查完成后进入复诊候诊。
- 阻塞或失败提示: 检查室占用时患者排队；身份核验失败时禁止检查。
- 可视化表现: 患者进入 `lab_2`，完成后返回 `outpatient_waiting`。

## 门诊复诊

- 事件 ID: `OP_SECOND_CONSULTATION_STARTED`
- 所属分类: 门诊复诊
- 触发条件: 检查结果已出，患者等待医生复诊。
- 涉及房间: `outpatient_waiting`、原诊室或对应专科诊室。
- 涉及人员/Agent: 患者、门诊医生。
- 前置检查: 检查结果可用；目标诊室空闲；患者在复诊队列中。
- 执行动作: 患者进入诊室，医生解释结果并确定治疗计划。
- 成功后的状态/资源变化: 患者状态变为 `IN_CONSULTATION`；复诊队列 -1。
- 阻塞或失败提示: 检查结果缺失或诊室占用时继续候诊。
- 可视化表现: 患者从 `outpatient_waiting` 回到诊室。

## 门诊取药

- 事件 ID: `OP_PHARMACY_PICKUP`
- 所属分类: 门诊药房
- 触发条件: 医生开立药物处方并完成支付。
- 涉及房间: `pharmacy_2`
- 涉及人员/Agent: 患者、药师。
- 前置检查: 处方存在；药费已支付；药房窗口可用；药品库存可用。
- 执行动作: 药师发药，记录药品已取。
- 成功后的状态/资源变化: 若无其他任务，患者状态变为 `COMPLETED`。
- 阻塞或失败提示: 处方缺失、未支付或药品缺货时患者留在药房队列并提示。
- 可视化表现: 患者进入 `pharmacy_2`，完成后离开地图或进入完成状态。

## 门诊转住院

- 事件 ID: `OP_TO_WARD_ADMISSION_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 门诊医生判断患者需要住院治疗。
- 涉及房间: `doctor_entry_2`、当前诊室、`elevator_2`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: 患者、门诊医生、住院登记护士、BedManager。
- 前置检查: 住院部有匹配床位；入院资料完整；患者适合普通转运。
- 执行动作: 创建入院请求，分配住院床位，患者转往 5F。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED`；住院床位 -1；门诊诊室释放。
- 阻塞或失败提示: 住院无床时进入待入院队列，患者可留在门诊或回家等待。
- 可视化表现: 患者经 `elevator_2` 到 `elevator_5`，再进入 `ward_admission`。

## 门诊转急诊

- 事件 ID: `OP_TO_ED_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 门诊分诊或诊疗发现急危重症。
- 涉及房间: `triage_2`、当前诊室、`elevator_2`、`ed_handoff`、`ed_red_resus`、`ed_observation`
- 涉及人员/Agent: 患者、门诊医生、急诊医生、护士。
- 前置检查: 急诊接收确认；抢救或观察资源可用；转运人员可用。
- 执行动作: 生成急诊交接，患者转入 1F 急诊。
- 成功后的状态/资源变化: 患者状态变为 `TRANSFERRING` 后进入急诊 `IN_TREATMENT`；门诊诊室释放。
- 阻塞或失败提示: 急诊暂不可接收时患者留在原房间并触发告警。
- 可视化表现: 患者经 `elevator_2` 到 1F 急诊。

## 门诊转 ICU

- 事件 ID: `OP_TO_ICU_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 门诊发现极危重患者，需要直接 ICU 或绿色通道。
- 涉及房间: `triage_2`、当前诊室、`elevator_2`、`icu_admission`、ICU 床位房间。
- 涉及人员/Agent: 患者、门诊医生、ICU 医生、ICU 护士、转运人员。
- 前置检查: ICU 有匹配床位；ICU 接收确认；患者适合转运；必要时急诊参与。
- 执行动作: 锁定 ICU 床位，患者直接转往 ICU。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED`；ICU 床位 -1；门诊诊室释放。
- 阻塞或失败提示: ICU 满床时患者留在门诊诊室或转急诊抢救区，提示 ICU 无床。
- 可视化表现: 患者以 stretcher 形式经电梯移动到 ICU。

## 门诊就诊完成

- 事件 ID: `OP_VISIT_COMPLETED`
- 所属分类: 门诊完成
- 触发条件: 患者已完成诊疗、缴费、取药或无需后续处理。
- 涉及房间: 当前诊室、`payment_2`、`pharmacy_2`、`outpatient_waiting`
- 涉及人员/Agent: 患者、门诊医生、药师。
- 前置检查: 无未完成检查、未支付项目、未取药处方或待转诊请求。
- 执行动作: 关闭本次门诊 encounter。
- 成功后的状态/资源变化: 患者状态变为 `COMPLETED`；相关诊室或窗口释放。
- 阻塞或失败提示: 存在未完成事项时提示具体待办。
- 可视化表现: 患者从当前房间离开或隐藏。
