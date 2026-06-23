# Fullview 门诊多患者并发修复

本次修改只涉及门诊后端与 Fullview 的同步边界。共享 Fullview 公共事件契约和
`frontend/fullview/full_view/main.js` 未修改；前端仍只保留门诊地图可达性修复。

## 状态机

- HTTP 接受命令后，outbox 进入 `accepted_unobserved`。
- `FullviewEventListener` 从现有 `/api/v1/events?after_seq=` 持久化追踪事件。
- 只有匹配 `event_seq + patient_id` 的事件被监听到后，命令才进入 `observed`。
- 动画冷却从 `observed_at` 开始，而不是从 HTTP 响应时间开始。
- 30 秒内未观察到事件时进入 `observe_timeout`，该患者停止推进并等待手工重试。

## 并发约束

- `patient_upsert` 使用全局 admission gate；一次只准入一个新患者。
- upsert 被观察后保留 4 秒首次渲染窗口。
- 同一 encounter 严格按 sequence 和视觉冷却推进。
- 不同患者的后续 movement 不使用全局锁，可交错发送和监听。
- mapping 不再发送独立 `encounter_open`；首个 movement 由 Fullview 自动建立 encounter。

## 安全清理

- 不再在 `discharge_request` 不受支持时立即 DELETE。
- 患者先进入 `cleanup_pending`。
- 仅在没有发送中、未观察或超时命令，没有活跃视觉冷却，且最近 3 秒没有全局
  movement 时执行 DELETE。
- DELETE 通过同一调度器串行执行，并在删除期间设置发送屏障。
- runtime reset/stop 同样先经清理调度器，再清空本地运行数据。

## 配置

```text
FULLVIEW_EVENT_LISTENER_INTERVAL_SECONDS=0.5
FULLVIEW_EVENT_OBSERVE_TIMEOUT_SECONDS=30
FULLVIEW_ADMISSION_GAP_SECONDS=4
FULLVIEW_CLEANUP_IDLE_SECONDS=3
```

## 自动验证

```powershell
$env:PYTHONPATH='backend'
python -m pytest backend/tests/test_fullview_sync.py `
  backend/tests/test_fullview_event_listener.py `
  backend/tests/test_runtime_console.py -q
```

覆盖监听分页、幂等、游标恢复、事件早于 HTTP 响应的竞态、admission 串行、
跨患者 movement、观察超时、手工重试和安全清理。
