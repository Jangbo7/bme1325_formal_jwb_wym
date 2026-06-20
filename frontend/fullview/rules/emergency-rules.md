# Emergency Department Event Rules

急诊楼层为 `1F Emergency`。核心房间包括 `ed_entrance`、`ed_registration`、`ed_triage`、`ed_red_resus`、`ed_trauma`、`ed_major`、`ed_minor`、`ed_diagnostic`、`ed_doctor_room`、`ed_bedside_nurse`、`ed_observation`、`ed_waiting`、`ed_handoff`、`ed_pager`、`elevator_1`。

## 患者到达急诊

- 事件 ID: `ED_ARRIVAL`
- 所属分类: 急诊入口
- 触发条件: 新患者从医院入口进入急诊。
- 涉及房间: `ed_entrance`
- 涉及人员/Agent: 患者、导诊护士或登记护士。
- 前置检查: 检查是否已有同一 `patient_id` 和未完成 `encounter_id`。
- 执行动作: 创建或复用患者档案，记录到达时间。
- 成功后的状态/资源变化: 患者状态变为 `ARRIVED`，患者进入急诊登记或急诊等候。
- 阻塞或失败提示: 若患者 ID 冲突，提示需要人工核验。
- 可视化表现: 患者出现在 `ed_entrance`，随后可移动到 `ed_registration`。

## 急诊登记

- 事件 ID: `ED_REGISTRATION_COMPLETED`
- 所属分类: 急诊登记
- 触发条件: 患者完成急诊基础信息登记。
- 涉及房间: `ed_registration`、`ed_waiting`
- 涉及人员/Agent: 患者、登记护士。
- 前置检查: 患者必须处于 `ARRIVED`；登记窗口未被占用或可排队。
- 执行动作: 补全患者身份、主诉、联系方式、基础风险标记。
- 成功后的状态/资源变化: 患者状态变为 `REGISTERED`，进入 `ed_waiting` 或直接进入 `ed_triage`。
- 阻塞或失败提示: 身份信息缺失时提示登记不完整，患者留在 `ed_registration`。
- 可视化表现: 患者从 `ed_registration` 移动到 `ed_waiting` 或 `ed_triage`。

## 急诊分诊

- 事件 ID: `ED_TRIAGE_COMPLETED`
- 所属分类: 急诊分诊
- 触发条件: 分诊护士完成生命体征、主诉和 CTAS 等级评估。
- 涉及房间: `ed_triage`、`ed_red_resus`、`ed_major`、`ed_minor`、`ed_waiting`
- 涉及人员/Agent: 患者、分诊护士、急诊医生。
- 前置检查: 患者状态为 `REGISTERED` 或 `ARRIVED`；分诊台可用。
- 执行动作: 生成 CTAS 等级和 zone；L1/L2 优先进入抢救或创伤区域，L3 进入急诊诊疗，L4/L5 进入等待。
- 成功后的状态/资源变化: 患者状态变为 `TRIAGED`；目标区域排队或占用更新。
- 阻塞或失败提示: 目标区域满时患者留在 `ed_triage` 或 `ed_waiting`，并提示急诊资源不足。
- 可视化表现: 患者从 `ed_triage` 移动到对应急诊区域。

## 危重患者进入抢救室

- 事件 ID: `ED_RED_RESUS_ADMISSION`
- 所属分类: 急诊抢救
- 触发条件: 患者 CTAS 为 L1/L2，或生命体征提示需要即刻抢救。
- 涉及房间: `ed_triage`、`ed_red_resus`
- 涉及人员/Agent: 患者、急诊医生、床旁护士、抢救团队。
- 前置检查: `ed_red_resus` 至少有 1 张可用抢救床；急诊医生和护士可用。
- 执行动作: 分配抢救床，启动抢救记录，通知急诊医生和床旁护士。
- 成功后的状态/资源变化: 患者状态变为 `IN_TREATMENT`；`ed_red_resus` 可用床位 -1。
- 阻塞或失败提示: 若抢救床满，患者留在 `ed_triage`，触发 `alert.raised`，提示抢救资源不足。
- 可视化表现: 患者移动到 `ed_red_resus` 并显示为 bed/stretcher。

## 创伤患者进入创伤室

- 事件 ID: `ED_TRAUMA_ROOM_ADMISSION`
- 所属分类: 急诊创伤
- 触发条件: 分诊结果提示创伤、骨折、出血或严重外伤。
- 涉及房间: `ed_triage`、`ed_trauma`
- 涉及人员/Agent: 患者、急诊医生、床旁护士。
- 前置检查: `ed_trauma` 床位可用；创伤医生可接诊。
- 执行动作: 分配创伤床，记录创伤评估，启动检查或处置流程。
- 成功后的状态/资源变化: 患者状态变为 `IN_TREATMENT`；`ed_trauma` 可用床位 -1。
- 阻塞或失败提示: 若创伤床满，患者进入 `ed_waiting` 的高优先级队列或 `ed_major`，并提示资源紧张。
- 可视化表现: 患者移动到 `ed_trauma`。

## 普通急诊候诊叫号

- 事件 ID: `ED_WAITING_CALLED`
- 所属分类: 急诊队列
- 触发条件: 急诊诊疗房间空闲，队列中有已分诊患者。
- 涉及房间: `ed_waiting`、`ed_minor`、`ed_major`、`ed_doctor_room`
- 涉及人员/Agent: 患者、急诊医生、护士。
- 前置检查: 目标房间空闲；患者已 `TRIAGED`；按 CTAS 和等待时间排序。
- 执行动作: 将队首患者移动到目标诊疗房间。
- 成功后的状态/资源变化: 患者状态变为 `IN_CONSULTATION` 或 `IN_TREATMENT`；`ed_waiting` 人数 -1，目标诊室占用。
- 阻塞或失败提示: 若目标房间被占用，患者继续留在 `ed_waiting`。
- 可视化表现: 患者从 `ed_waiting` 移动到诊疗房间。

## 急诊观察

- 事件 ID: `ED_OBSERVATION_STARTED`
- 所属分类: 急诊观察
- 触发条件: 医生判断患者需要短期观察，但暂不满足 ICU 或住院条件。
- 涉及房间: `ed_doctor_room`、`ed_observation`
- 涉及人员/Agent: 患者、急诊医生、床旁护士。
- 前置检查: `ed_observation` 有空床；护理人员可接收。
- 执行动作: 分配观察床，设置观察任务和复评时间。
- 成功后的状态/资源变化: 患者状态保持 `IN_TREATMENT`；`ed_observation` 可用床位 -1。
- 阻塞或失败提示: 若观察床满，患者留在原诊疗区域并提示观察区满。
- 可视化表现: 患者移动到 `ed_observation` 并显示为 bed。

## 急诊检查

- 事件 ID: `ED_DIAGNOSTIC_REQUESTED`
- 所属分类: 急诊检查
- 触发条件: 急诊医生开立检验、影像或床旁检查。
- 涉及房间: `ed_doctor_room`、`ed_major`、`ed_red_resus`、`ed_diagnostic`
- 涉及人员/Agent: 患者、急诊医生、检查人员、护士。
- 前置检查: 检查请求有效；患者身份核验通过；`ed_diagnostic` 可服务或可排队。
- 执行动作: 创建检查任务，患者进入检查房或检查队列。
- 成功后的状态/资源变化: 患者状态变为 `IN_EXAM`；检查完成后回到原急诊区域或医生处复评。
- 阻塞或失败提示: 检查房占用时患者保持原位置并进入检查等待队列。
- 可视化表现: 患者移动到 `ed_diagnostic`，完成后返回起点房间。

## 急诊交接

- 事件 ID: `ED_HANDOFF_PREPARED`
- 所属分类: 急诊交接
- 触发条件: 急诊医生决定患者需要转 ICU、住院或 MDT。
- 涉及房间: `ed_handoff`
- 涉及人员/Agent: 急诊医生、接收科室医生、患者、护士。
- 前置检查: 患者已有摘要、生命体征、诊断倾向、待办任务；目标科室存在。
- 执行动作: 生成 handoff ticket 和临床摘要，向接收科室发出请求。
- 成功后的状态/资源变化: 患者状态短暂变为 `TRANSFERRING` 或保留原治疗状态等待接收确认。
- 阻塞或失败提示: 资料缺失时提示补齐检查/病历；目标科室拒收时患者留在急诊。
- 可视化表现: 患者或病例移动到 `ed_handoff`。

## 急诊转 ICU 请求

- 事件 ID: `ED_TO_ICU_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 急诊患者病情危重，需要 ICU 接收。
- 涉及房间: `ed_red_resus`、`ed_observation`、`ed_handoff`、`elevator_1`、`icu_admission`、`icu_beds_a`、`icu_beds_b`、`icu_isolation`、`intervention_bay`
- 涉及人员/Agent: 患者、急诊医生、急诊护士、ICU 医生、ICU 护士、BedManager。
- 前置检查: ICU 有匹配床位；ICU 接收确认；转运人员可用；患者适合转运。
- 执行动作: 锁定 ICU 床位，发布转运事件，患者经 `elevator_1` 到 `elevator_3`，进入 ICU 接收。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED`；ICU 床位 -1；急诊原床位 +1。
- 阻塞或失败提示: ICU 满床或拒收时，患者留在原急诊房间，提示 ICU 无可用床位，触发 `alert.raised`。
- 可视化表现: 患者以 stretcher 形式从急诊移动到 ICU 目标床位。

## 急诊转住院请求

- 事件 ID: `ED_TO_WARD_TRANSFER_REQUESTED`
- 所属分类: 跨部门转运
- 触发条件: 急诊患者病情稳定但需要住院治疗。
- 涉及房间: `ed_observation`、`ed_handoff`、`elevator_1`、`ward_admission`、各 `*_ward`
- 涉及人员/Agent: 患者、急诊医生、住院登记护士、BedManager、责任护士。
- 前置检查: 住院部有匹配专科床位；住院接收确认；转运人员可用。
- 执行动作: 创建住院接收请求，分配住院床，患者经电梯转运到 `ward_admission` 和目标病房。
- 成功后的状态/资源变化: 患者状态变为 `ADMITTED`；住院床位 -1；急诊观察床 +1。
- 阻塞或失败提示: 住院无床时，患者留在急诊观察区，进入待入院队列。
- 可视化表现: 患者从急诊移动到 5F 住院部。
