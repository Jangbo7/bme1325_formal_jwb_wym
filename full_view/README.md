# Full Hospital View

`hospital/full_view` 是 SIM Hospital 的全院可视化与轻量后端模块。仓库发布说明请先阅读上一级 [README.md](../README.md)，department 接入步骤请阅读 [Fullview 接入手册](../docs/fullview-integration-manual.md)。

## 运行

```bash
python dev-server.py 8000
```

打开：

```text
http://localhost:8000/
http://localhost:8000/console.html
```

`dev-server.py` 同时负责静态页面、地图/规则保存 API、医院 snapshot API、事件 API 和 JSON 文件写回。页面也可以用 `python -m http.server 8000` 静态打开，但这种模式不能写回本地 JSON。

## 模块职责

| 模块 | 职责 |
|---|---|
| `index.html` + `main.js` | 全院 Canvas 地图入口，读取 snapshot，播放后端批准的移动动画 |
| `console.html` + `console.js` | Operations Console，查看房间/人员/床位，发送全局移动请求 |
| `dev-server.py` | 轻量 mock 后端，负责状态读取、规则校验、资源更新和事件日志 |
| `hospital-api.js` | 前端访问医院后端 API 的封装 |
| `map-config.json` | 楼层、房间、家具、门、床位布局 |
| `backend-data/*.json` | 患者、医护、房间资源、床位占用、事件历史 |
| `event-rules/*.json` | 后端读取的患者移动规则 |
| `map-admin.js` | 地图编辑器，支持新增/删除房间和调整床位 |
| `rules-admin.js` | 规则编辑器，支持新增/删除/保存移动规则 |

核心边界：**后端负责状态与规则，前端只负责展示、表单提交和动画播放。**

## 数据与规则

地图由 `map-config.json` 驱动：

- `floors[]` 定义楼层。
- `rooms[]` 定义房间。
- `doors[]` 和 `items[]` 使用房间相对坐标，因此房间移动后家具和床位不会跑出房间。
- `protected` 房间不能在编辑器中删除；电梯自动视为保护房间。
- `maxBeds` 可覆盖房间床位上限。

运行状态由 `backend-data/` 驱动：

- `patients.json`：患者身份、当前位置、状态、视觉形态和床位归属。
- `staff.json`：医生、护士、护工等人员。
- `room-state.json`：床位分配、队列、房间资源和转运资源。
- `event-log.json`：accepted/rejected 事件和动画指令。

移动规则由 `event-rules/` 驱动。每条规则应有稳定 `eventId`，并定义 `movement.from`、`movement.to`、`movement.via`、`transport`、`escortRoles`、`equipment`、`finalForm` 和资源策略。

## API

地图页和控制台使用同一套 API：

- `GET /api/hospital/snapshot`
- `GET /api/hospital/rooms`
- `GET /api/hospital/people`
- `GET /api/hospital/events?after=<seq>`
- `POST /api/hospital/patients/admit`
- `POST /api/hospital/events/move`
- `GET /api/event-rules`
- `PUT /api/event-rules/*.json`

请求/响应格式见 [API.md](API.md)。统一数据标准见 [HOSPITAL_CORE_STANDARD.md](HOSPITAL_CORE_STANDARD.md)。

## 开发检查

```bash
python -m py_compile dev-server.py
node --check console.js hospital-api.js main.js
python -m json.tool map-config.json >/dev/null
python -m json.tool backend-data/patients.json >/dev/null
python -m json.tool backend-data/staff.json >/dev/null
python -m json.tool backend-data/room-state.json >/dev/null
```

修改地图、规则或后端接口后，请同时打开地图页和 `console.html` 手动验证一次 accepted 与 rejected 事件。
