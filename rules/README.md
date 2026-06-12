# Hospital Event Rules

本目录用于保存全院整合前的事件规则草案。规则以真实医院流程为基础，并绑定 `hospital/full_view/map-config.json` 中已有的房间 ID，方便后续把事件映射到全院 Canvas 可视化、统一 snapshot、跨部门转运和资源检查逻辑。

这些文档当前只作为设计与联调依据，不直接驱动代码执行。

## 目录

- `emergency-rules.md`: 急诊事件。
- `outpatient-rules.md`: 门诊事件。
- `icu-rules.md`: ICU 事件。
- `ward-rules.md`: 住院部事件。
- `mdt-rules.md`: MDT 会诊事件。
- `transfer-rules.md`: 跨部门转运事件。
- `resource-and-blocking-rules.md`: 统一资源、队列、阻塞和异常规则。

## 通用事件字段

每个事件建议使用以下字段描述：

```md
## 事件名称

- 事件 ID:
- 所属分类:
- 触发条件:
- 涉及房间:
- 涉及人员/Agent:
- 前置检查:
- 执行动作:
- 成功后的状态/资源变化:
- 阻塞或失败提示:
- 可视化表现:
```

## 状态口径

全院对外状态优先使用统一接口契约中的状态：

- `ARRIVED`
- `REGISTERED`
- `TRIAGED`
- `IN_CONSULTATION`
- `IN_EXAM`
- `IN_TREATMENT`
- `ADMITTED`
- `DISCHARGED`
- `COMPLETED`
- `TRANSFERRING`
- `CANCELLED`
- `ERROR`

各部门内部可以保留更细状态，但进入全院事件规则时，需要映射到上述状态。

## 资源检查原则

- 涉及床位的事件必须先检查目标床位容量，再移动患者。
- 涉及诊室的事件必须先检查目标诊室是否空闲，再从 waiting room 叫号。
- 涉及检查、影像、药房、会议室和专家的事件必须先检查排队和占用状态。
- 涉及跨楼层转运的事件必须经过对应电梯房间，例如 `elevator_1` 到 `elevator_3`。
- 资源检查失败时，患者必须留在原房间或进入等待队列，不能直接改变占用状态。

## 阻塞与提示原则

阻塞事件必须明确说明：

- 阻塞原因，例如 ICU 满床、住院无床、诊室占用、检查资料缺失。
- 患者当前保留位置。
- 需要谁处理，例如急诊医生、ICU 护士、BedManager、MDT 调度员。
- 是否需要发布 `alert.raised` 或进入等待队列。

## 可视化原则

- 成功转运：显示患者从起点房间到电梯，再到目标房间的移动路径。
- 资源阻塞：患者不移动，目标房间或部门 snapshot 显示 warning/critical。
- 队列事件：waiting room 人数变化，诊室释放后自动触发下一个候诊患者。
- 床位事件：目标床位占用后患者显示为 bed form，释放后床位计数恢复。

## 后端可复用移动规则标准

当前可执行 JSON 规则位于 `event-rules/`，并由 `hospital/full_view/dev-server.py` 读取。每条患者移动规则必须有稳定的 `eventId` 和结构化 `movement` 字段。

`movement` 建议字段：

```json
{
  "schema": "patient-move",
  "from": "current_ed_room",
  "to": "icu_admission",
  "via": ["ed_handoff", "elevator_1", "elevator_3"],
  "transport": "stretcher",
  "acuity": "critical",
  "patientFormDuringMove": "stretcher",
  "finalForm": "bed",
  "escortRequired": true,
  "escortRoles": ["porter", "ed_nurse"],
  "equipment": ["portable_monitor", "oxygen", "transport_bag"],
  "pathPolicy": {
    "requiresPath": true,
    "useElevator": true,
    "avoidWalls": true,
    "hallwayPreference": "center",
    "stopAtDoorBeforeEntering": true
  },
  "resourcePolicy": {
    "lockBeforeMove": true,
    "releaseSourceOnArrival": true,
    "occupyTargetOnArrival": true,
    "keepSourceReservedUntilArrival": true,
    "retainSourceBed": true,
    "releaseSourceBed": false
  },
  "failurePolicy": {
    "onNoPath": "stay_source",
    "onResourceBlocked": "stay_source",
    "onEscortUnavailable": "stay_source"
  }
}
```

住院部/ICU 床位是长期资源绑定：患者分配床位后，`room-state.json` 使用 `bedAssignments` 按 `patientId` 保留该床位。患者临时去检查或处置时应设置 `retainSourceBed: true`，不能释放原床；患者出院、转 ICU、转住院或转到其他长期床位时才设置 `releaseSourceBed: true`。

住院部和 ICU 患者前往检查/处置默认使用 `stretcher`，并配置 `porter` 以及相应科室护士作为 escort，避免把卧床患者表现成自行步行。

后端处理原则：

- 控制台或科室系统只发送 `eventId + patientId + fromRoomId + toRoomId`。
- 后端根据 `eventId` 查规则，再检查患者当前位置、目标房间、床位、护工/护士资源和跨楼层电梯路径。
- 合法时后端更新 `backend-data/*.json` 和 `event-log.json`，并返回 `animationPlan`。
- 不合法时后端返回 `accepted: false`，前端不移动患者。

## 新增科室、房间或移动规则步骤

1. 在 `hospital/full_view/map-config.json` 增加房间，保证每个房间有唯一 `id`、清晰 `kind`、必要床位 `items` 或 `maxBeds`。
2. 如需首屏出现人员，在 `hospital/full_view/backend-data/patients.json` 或 `staff.json` 增加人员，并使用 `roomId + relX + relY` 放置。
3. 在 `event-rules/*.json` 增加移动规则，填写 `eventId`、`rooms`、`movement.from`、`movement.to`、`movement.via`、`transport`、`escortRoles`、`equipment` 和 `finalForm`。
4. 跨楼层移动必须在 `movement.via` 中写明电梯房间，例如 `elevator_1`、`elevator_3`。
5. 启动 `hospital/full_view/dev-server.py`，打开 `console.html`，用控制台发送 move request 验证。
6. 地图页只消费后端返回的 `animationPlan`，不要在前端新增业务合法性判断。
