# 星露谷门诊看板

这是一个全新的独立前端，只通过 HTTP 调用现有 FastAPI 后端，不修改后端代码，也不依赖后端静态页面。它适合同时做两件事：

- 实时查看病人 NPC 的状态分布、科室分布和趋势变化
- 按门诊流程切换 `triage`、`internal_medicine`、`surgery`、`icu` 等 agent 做对话

## 1. 启动后端

先启动后端服务，默认端口是 `8787`。

```powershell
cd backend
python -m pip install -r requirements.txt
python server.py
```

如果你想先检查后端是否可用，可以打开：

- `http://127.0.0.1:8787/api/v1/health`
- `http://127.0.0.1:8787/api/v1/runtime-console/snapshot`

## 2. 设置大模型 API Key

后端在启动时读取 `backend/.env`。推荐只在这个文件里配置密钥，不要提交到仓库。

如果你使用默认的 `current` provider，可以写成：

```env
ACTIVE_LLM_PROVIDER=current
CURRENT_LLM_ENDPOINT=https://genaiapi.shanghaitech.edu.cn/api/v1/start
CURRENT_LLM_MODEL=deepseek-v3:671b
CURRENT_LLM_API_KEY=你的密钥
```

如果你使用阿里云 DashScope，可以写成：

```env
ACTIVE_LLM_PROVIDER=aliyun_dashscope
ALIYUN_LLM_ENDPOINT=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
ALIYUN_LLM_MODEL=deepseek-v4-flash
DASHSCOPE_API_KEY=你的密钥
```

如果你使用 DeepSeek 官方兼容接口，也可以在 `backend/.env` 里配置：

```env
ACTIVE_LLM_PROVIDER=deepseek_official
DEEPSEEK_LLM_ENDPOINT=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_LLM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=你的密钥
```

## 3. 启动前端

这个前端是纯静态页面，可以直接用 Python 起一个本地静态服务器。

```powershell
cd frontend/stardew-hospital
python -m http.server 8000
```

然后打开：

- `http://127.0.0.1:8000`

页面左上角可以修改后端地址。如果后端不在默认的 `http://127.0.0.1:8787`，直接在页面里改掉即可。

## 4. 你可以做什么

页面分成两部分：

- 左侧是实时总览
- 右侧是就医流程和对话面板

你可以做的事包括：

- 查看病人 `visit_state`、`display_stage`、`dispatch_state` 的实时分布
- 看柱状图、饼图和折线图随着后端状态变化自动更新
- 查看最近的 runtime event 和病人卡片
- 选择一个病人，查看病历摘要、scene 对话、最新检查结果和历史记录
- 在右侧切换 Agent：
  - `门诊分诊`
  - `内科门诊`
  - `外科门诊`
  - `ICU 会诊`
- 按就医流程推进：
  - `创建就诊`
  - `分诊`
  - `挂号`
  - `推进排队`
  - `进入诊室`
  - `结算`
- 给当前 agent 发送消息，并查看对话历史

## 5. 这套前端依赖哪些后端接口

主要会用到这些接口：

- `GET /api/v1/health`
- `GET /api/v1/runtime-console/snapshot`
- `GET /api/v1/runtime-console/events`
- `GET /api/v1/departments`
- `GET /api/v1/patients`
- `GET /api/v1/scene-snapshot`
- `GET /api/v1/medical-records/visit/{visit_id}`
- `POST /api/v1/visits`
- `POST /api/v1/visits/{visit_id}/register`
- `POST /api/v1/visits/{visit_id}/progress`
- `POST /api/v1/visits/{visit_id}/enter-consultation`
- `POST /api/v1/visits/{visit_id}/ready-payment`
- `POST /api/v1/triage-sessions`
- `POST /api/v1/triage-sessions/{session_id}/messages`
- `POST /api/v1/internal-medicine-sessions`
- `POST /api/v1/internal-medicine-sessions/{session_id}/messages`
- `POST /api/v1/surgery-sessions`
- `POST /api/v1/surgery-sessions/{session_id}/messages`
- `POST /api/v1/icu-sessions`
- `POST /api/v1/icu-sessions/{session_id}/messages`

## 6. 目录说明

- `index.html`：页面骨架
- `styles.css`：星露谷风格样式
- `app.js`：页面状态、数据拉取、流程控制、对话逻辑
- `api.js`：后端 API 封装
- `charts.js`：纯 SVG 图表渲染

## 7. 小提示

- 页面默认自动轮询和订阅事件流；如果你想临时暂停实时刷新，可以点 `实时更新：关`
- 如果你换了后端地址，刷新后会从本地缓存恢复
- 如果某个 Agent 需要 visit/挂号状态，先按流程按钮推进，再发送消息，成功率会更高
