# Backend Nurse Agent

本目录仅放后端逻辑，前端保持在 scene 目录。

## 功能概述

- 提供护士分诊 Agent 的最小可用后端。
- 接收前端分诊请求后，先将病人状态置为 正在分诊。
- 后台线程异步执行分诊，完成后更新为 等待问诊 并附带分级结果。
- 前端任务栏通过轮询病人状态接口实现实时显示。

## 启动

```powershell
cd backend
python server.py
```

默认地址: http://127.0.0.1:8787

## Key 策略（mock 先跑通）

- 后端优先读取 backend/.env 中的 MOCK_API_KEY。
- 如果未配置，则回退固定值 mock-key-001。
- 前端调用 /api/* 时需要带 X-API-Key 头。

示例 backend/.env:

```env
MOCK_API_KEY=mock-key-001
OPENAI_API_KEY=your-real-openai-key-optional
```

说明:

- OPENAI_API_KEY 可选。
- 若存在 OPENAI_API_KEY，后端会优先尝试模型分诊。
- 若模型调用失败，会自动回退到规则分诊。

## API

### GET /health

返回服务健康状态与当前模式信息（含 key_source）。

### GET /api/statuses

返回病人状态列表（按更新时间倒序）。

请求头:

```http
X-API-Key: mock-key-001
```

### POST /api/triage/request

提交分诊请求，将病人推入分诊队列。

请求头:

```http
Content-Type: application/json
X-API-Key: mock-key-001
```

请求体示例:

```json
{
  "patient_id": "P-self",
  "name": "你(玩家)",
  "symptoms": "头晕、胸闷",
  "vitals": {
    "temp_c": 37.8,
    "heart_rate": 105,
    "systolic_bp": 132,
    "diastolic_bp": 86,
    "pain_score": 5
  },
  "location": "分诊区",
  "floor": 1
}
```

## 当前状态流转

- 待分诊 -> 正在分诊 -> 等待问诊

## 前后端联调要点

- 前端 scene/main.js 已接入:
  - 轮询 GET /api/statuses，任务栏显示实时病人状态。
  - 玩家靠近分诊台后按 E，触发 POST /api/triage/request。
- 若任务栏显示离线，请优先检查:
  - 后端是否启动。
  - 前端 X-API-Key 是否与后端期望值一致。
