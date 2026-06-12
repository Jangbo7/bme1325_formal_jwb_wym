# Fullview Department 接入手册

本文档面向门诊、急诊、ICU、住院部、MDT、检验科、药房等 department 开发者，说明如何把本部门系统接入 Fullview 全院核心系统。

Fullview 的职责是维护全院共享状态、资源占用、移动规则、事件日志和可视化动画。Department 的职责是维护本部门内部诊疗逻辑，并在需要跨房间、跨楼层或跨部门移动患者时，向 Fullview 发送标准事件请求。

## 1. 接入原则

1. **Fullview 是全院共享状态权威**：患者当前在哪个房间、床位是否占用、事件是否被批准，由 Fullview 后端判断和记录。
2. **Department 保留内部业务模型**：各组可以继续使用自己的 triage、diagnosis、care-plan、agent 等结构，但对接 Fullview 时必须转换成统一格式。
3. **前端只展示，不判规则**：Canvas 地图和控制台只读取 snapshot、发送请求、播放后端批准的 animation plan。
4. **所有可复用移动都写成规则**：从门诊到检查、急诊转 ICU、ICU 去检查、住院患者出院等，都应该有稳定 `event_id` 和 `movement` 规则。
5. **床位是长期资源**：ICU/住院患者临时离开去检查时，原床位继续属于该患者；出院或转到其他长期床位时才释放。

## 2. 统一 ID 标准

| 对象 | 字段 | 推荐格式 | 示例 |
|---|---|---|---|
| 楼层 | `floor_id` | 1-5 整数 | `3` |
| 科室 | `department_id` | lowercase slug | `icu` |
| 房间 | `room_id` | lowercase semantic slug | `icu_beds_a` |
| 展示房间号 | `display_room_id` | `{floor}F-Room{n}` | `3F-Room3` |
| 床位 | `bed_id` | `{room_id}-bed-{nn}` | `icu_beds_a-bed-01` |
| 患者 | `patient_id` | `P-{dept_code}-{nnn}` | `P-ICU-001` |
| 员工 | `staff_id` | `{role_code}-{dept_code}-{nnn}` | `D-ICU-001` |
| 事件规则 | `event_id` | uppercase action id | `ED_TO_ICU_MOVE` |
| 运行事件 | `event_seq` | 单调递增整数 | `12` |

部门代码建议：

| 代码 | 科室 |
|---|---|
| `ER` | Emergency |
| `OP` | Outpatient |
| `LAB` | Laboratory |
| `PHA` | Pharmacy |
| `ICU` | ICU |
| `WD` | Ward |
| `MDT` | MDT Center |

如果 department 内部已有自己的 ID，不需要全部改掉；只需要在 adapter 层映射到 Fullview ID。

## 3. 核心数据文件

Fullview 当前使用 JSON 文件作为轻量后端数据源：

| 文件 | 作用 |
|---|---|
| `full_view/map-config.json` | 楼层、房间、坐标、门、家具、床位数量 |
| `full_view/backend-data/patients.json` | 患者身份、当前位置、状态、视觉形态 |
| `full_view/backend-data/staff.json` | 医生、护士、护工等人员 |
| `full_view/backend-data/room-state.json` | 床位分配、队列、房间资源、转运资源 |
| `full_view/backend-data/event-log.json` | accepted/rejected 事件历史 |
| `full_view/event-rules/*.json` | 后端读取的可执行移动规则 |

`full_view/HOSPITAL_CORE_STANDARD.md` 是字段标准的权威文件。新增 department 时，优先按照该文件写 snake_case 字段。当前 UI 为兼容旧代码，仍保留部分 camelCase alias。

## 4. 房间维护

### 4.1 新建房间

推荐使用地图页的 `Edit Map`：

1. 启动后端：`python dev-server.py 8000`。
2. 打开 `http://localhost:8000/`。
3. 点击 `Edit Map`。
4. 选择楼层。
5. 输入房间名并添加。
6. 点击 `Save` 写回 `map-config.json`。

系统会自动生成唯一 `room_id`，并给房间分配一个空位。

### 4.2 删除房间

在 `Edit Map` 中点击房间右侧删除按钮后保存。

以下房间不能删除：

- 电梯。
- `protected: true` 的房间。
- 后续被定义为关键路径节点的房间。

删除房间前应检查：

- 是否有患者、医生、护士仍在该房间。
- 是否有 event rule 使用该 `room_id`。
- 是否有患者的 `home_bed.room_id` 指向该房间。

### 4.3 房间记录格式

推荐房间字段：

```json
{
  "room_id": "icu_beds_a",
  "id": "icu_beds_a",
  "floor_id": 3,
  "department_id": "icu",
  "display_name": "ICU Beds1",
  "label": "ICU Beds1",
  "kind": "icu",
  "protected": false,
  "layout": {
    "x": 16,
    "y": 6,
    "w": 12,
    "h": 8
  },
  "capacity": {
    "beds": 4,
    "max_beds": 4
  },
  "items": []
}
```

现阶段 `map-config.json` 仍以 `id`、`label`、`x`、`y`、`w`、`h` 为主，后端 snapshot 会补全标准字段。

## 5. 病床维护

### 5.1 新建或减少床位

推荐使用 `Edit Map` 的床位加减按钮。不同房间类型有默认上限：

| 房间类型 | 默认最大床位 |
|---|---:|
| ICU | 4 |
| Ward | 4 |
| Emergency / Rescue | 2 |

需要特殊上限时，可在房间配置中设置 `maxBeds`。

### 5.2 床位 ID

床位必须有唯一 ID：

```text
{room_id}-bed-{nn}
```

示例：

```text
icu_beds_a-bed-01
resp_ward-bed-04
```

即使床位为空，控制台也应该显示这张床：

```json
{
  "bed_id": "icu_beds_a-bed-01",
  "occupied": false,
  "patient_id": null,
  "patient_away": false
}
```

### 5.3 床位保留规则

ICU 和住院部患者分配床位后：

- 临时去检查或干预：保留原床，设置 `retainSourceBed: true`。
- 从 ICU 转住院或从住院转 ICU：到达目标长期床位后释放原床，设置 `releaseSourceBed: true`。
- 出院：释放所有床位。

这能避免患者暂时离开病房时，原床被其他患者占用。

## 6. 患者与医护数据

### 6.1 患者格式

```json
{
  "patient_id": "P-ICU-001",
  "patientId": "P-ICU-001",
  "type": "patient",
  "name": "Ethan Zhang",
  "gender": "male",
  "department_id": "icu",
  "status": "ADMITTED",
  "current_location": {
    "room_id": "icu_beds_a"
  },
  "home_bed": {
    "room_id": "icu_beds_a",
    "bed_id": "icu_beds_a-bed-01",
    "retained": true
  },
  "clinical": {
    "symptoms": "Postoperative respiratory monitoring",
    "care_phase": "unstable"
  },
  "visual": {
    "form": "bed",
    "rel_x": 0.2,
    "rel_y": 0.4
  }
}
```

### 6.2 医护格式

```json
{
  "staff_id": "D-ICU-001",
  "employee_id": "D-ICU-001",
  "type": "doctor",
  "role": "doctor",
  "name": "Dr. Helen Guo",
  "gender": "female",
  "department_id": "icu",
  "current_location": {
    "room_id": "icu_beds_a"
  },
  "availability": {
    "available": true,
    "current_task_id": null
  },
  "visual": {
    "pose": "monitoring",
    "rel_x": 0.58,
    "rel_y": 0.58
  }
}
```

医生和护士不需要症状字段；症状属于患者 `clinical`。

## 7. 移动规则

规则是后端判断一个患者移动事件是否合法、如何更新资源、前端如何表现动画的结构化配置。

一条移动规则至少需要：

| 字段 | 说明 |
|---|---|
| `event_id` / `eventId` | 稳定事件名，department 调用时使用 |
| `movement.from` | 允许的来源房间或 symbolic source |
| `movement.to` | 允许的目标房间、房间列表或 symbolic target |
| `movement.via` | 中间经过房间，跨楼层时必须包含电梯 |
| `movement.transport` | `walking`、`wheelchair`、`stretcher` |
| `movement.patientFormDuringMove` | 转运途中患者显示形式 |
| `movement.finalForm` | 到达后显示形式 |
| `movement.escortRequired` | 是否需要陪同 |
| `movement.escortRoles` | 护工、护士等陪同角色 |
| `movement.equipment` | 转运设备 |
| `movement.resourcePolicy` | 床位、锁定、释放、占用策略 |

### 7.1 门诊移动示例

```json
{
  "eventId": "OP_TRIAGE_TO_CONSULT_ROOM",
  "movement": {
    "schema": "patient-move",
    "from": "triage_2",
    "to": ["consultation_a_2", "consultation_b_2", "internal_medicine_2"],
    "via": [],
    "transport": "walking",
    "patientFormDuringMove": "walking",
    "finalForm": "consultation",
    "escortRequired": false
  }
}
```

### 7.2 ICU 检查示例

```json
{
  "eventId": "ICU_TO_EXAM_OR_INTERVENTION",
  "movement": {
    "schema": "patient-move",
    "from": "current_icu_bed_room",
    "to": "diagnostic_center",
    "via": ["elevator_3", "elevator_2"],
    "transport": "stretcher",
    "patientFormDuringMove": "stretcher",
    "finalForm": "stretcher",
    "escortRequired": true,
    "escortRoles": ["porter", "icu_nurse"],
    "equipment": ["portable_monitor", "oxygen"],
    "resourcePolicy": {
      "retainSourceBed": true,
      "releaseSourceBed": false
    }
  }
}
```

ICU/住院患者去检查默认不应使用 walking。

## 8. 标准事件 API

### 8.1 发送移动请求

```http
POST /api/hospital/events/move
Content-Type: application/json
```

推荐使用 snake_case：

```json
{
  "request_id": "req-op-001",
  "source": "outpatient",
  "operator_id": "OP-Agent-001",
  "event_id": "OP_TRIAGE_TO_CONSULT_ROOM",
  "patient_id": "P-OP-004",
  "from_room_id": "triage_2",
  "to_room_id": "consultation_a_2",
  "context": {
    "reason": "triage completed"
  }
}
```

当前后端也兼容 camelCase：

```json
{
  "requestId": "req-op-001",
  "operatorId": "OP-Agent-001",
  "eventId": "OP_TRIAGE_TO_CONSULT_ROOM",
  "patientId": "P-OP-004",
  "fromRoomId": "triage_2",
  "toRoomId": "consultation_a_2"
}
```

### 8.2 accepted 响应

```json
{
  "accepted": true,
  "event_seq": 21,
  "event_id": "OP_TRIAGE_TO_CONSULT_ROOM",
  "patient_id": "P-OP-004",
  "status_updates": {
    "patient_status": "IN_CONSULTATION",
    "target_reserved": true
  },
  "animation_plan": {
    "kind": "patient-move",
    "transport": "walking",
    "from_room_id": "triage_2",
    "to_room_id": "consultation_a_2",
    "via_room_ids": [],
    "final_form": "consultation"
  }
}
```

### 8.3 rejected 响应

```json
{
  "accepted": false,
  "event_seq": 22,
  "event_id": "OP_TRIAGE_TO_CONSULT_ROOM",
  "patient_id": "P-OP-004",
  "reason_code": "PATIENT_LOCATION_MISMATCH",
  "message": "Patient is not in from_room_id."
}
```

常见失败原因：

| `reason_code` | 含义 |
|---|---|
| `RULE_NOT_FOUND` | 找不到对应事件规则 |
| `PATIENT_NOT_FOUND` | 患者不存在 |
| `PATIENT_LOCATION_MISMATCH` | 患者当前位置与请求来源不一致 |
| `TARGET_ROOM_NOT_FOUND` | 目标房间不存在 |
| `TARGET_NOT_ALLOWED` | 目标房间不符合规则 |
| `NO_AVAILABLE_BED` | 目标房间没有空床 |
| `ESCORT_UNAVAILABLE` | 需要陪同但资源不可用 |

## 9. Department 接入步骤

### 步骤 1：确认房间

在 `map-config.json` 或地图编辑器中确认本部门需要的所有房间都存在，并记录 `room_id`。

### 步骤 2：确认人员和患者

如需在 Fullview 初始页面显示人员，把患者写入 `patients.json`，医生护士写入 `staff.json`。

### 步骤 3：定义移动规则

把本部门会触发的可复用移动写入 `event-rules/*.json`：

- 门诊：挂号、分诊、诊室、缴费、检验、药房、住院/ICU/出院。
- 急诊：入口、登记、分诊、抢救、检查、ICU、住院、出院。
- ICU：入床、检查/干预、返回床位、转住院、转急诊、出院。
- 住院部：入床、检查、返回病房、转 ICU、出院。
- MDT：会诊相关移动或状态触发。

### 步骤 4：通过 API 发送事件

Department 不直接移动前端人物，只发送 `POST /api/hospital/events/move`。

### 步骤 5：读取结果

- `accepted: true`：Fullview 会写入事件日志，地图页自动动画。
- `accepted: false`：读取 `reason_code`，让 department 决定排队、等待资源或提示人工处理。

### 步骤 6：用控制台验证

打开 `console.html`：

1. 选择患者。
2. 选择该患者当前位置合法的 event rule。
3. 选择目标楼层和目标房间。
4. 发送请求。
5. 查看 Event Log 和地图动画。

## 10. 新增内容 Checklist

新增一个房间：

- [ ] `map-config.json` 中有唯一 `room_id`。
- [ ] 房间有正确 `floor_id`、`department_id`、`kind`。
- [ ] 如为电梯或关键节点，设置保护。
- [ ] 相关规则中的 `movement.from/to/via` 使用正确 ID。

新增一张床：

- [ ] 房间 `items` 或 capacity 中增加床位。
- [ ] 控制台能看到空床 `bed_id`。
- [ ] 目标移动规则能检查并分配床位。

新增一条移动规则：

- [ ] 有稳定 `event_id`。
- [ ] 明确 `from`、`to`、`via`。
- [ ] 跨楼层经过电梯。
- [ ] ICU/住院检查使用 `stretcher`。
- [ ] 床位临时离开设置 `retainSourceBed: true`。
- [ ] 出院或转长期床位设置 `releaseSourceBed: true`。
- [ ] 在控制台发送 accepted 和 rejected 两类测试。

新增一个 department 接入：

- [ ] 建立 department 内部 ID 到 Fullview ID 的映射。
- [ ] 只通过 Fullview API 改全院状态。
- [ ] 不在地图前端写业务规则。
- [ ] 失败原因能在 department UI 或日志中显示。

## 11. 推荐阅读顺序

1. `README.md`：了解系统功能和启动方式。
2. `full_view/HOSPITAL_CORE_STANDARD.md`：了解统一数据格式。
3. `full_view/API.md`：了解接口字段。
4. `rules/README.md`：了解规则设计原则。
5. 本手册：按步骤接入 department。
