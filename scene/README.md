# 医院门诊前端

当前版本使用原生 `HTML + Canvas` + ES modules 实现医院门诊前端，目标是把分诊、排队、病历、NPC 和后端状态展示拆成独立模块。

## 已实现

- 模块化的前端装配入口
- 分诊表单与分诊对话
- 队列、叫号和就诊状态展示
- 固定 NPC 对话与随机 NPC 流动
- 病历卡展示 triage、internal medicine 和 simulated_report
- 私有 API 配置隔离
- 前端只负责呈现状态，业务逻辑仍在后端

## 启动方式

直接用浏览器打开 `index.html` 即可。

如果你本地有 Python，也可以在目录下启动一个静态服务：

```bash
python -m http.server 8000
```

然后访问 `http://localhost:8000`。

## 前端私有 API 配置

为避免将 API key 直接提交到仓库，前端改为从独立私有文件读取：

1. 复制 `scene/api.private.example.js` 为 `scene/api.private.js`
2. 在 `scene/api.private.js` 中填写本地配置

```js
window.HOS_PRIVATE_API = {
	baseUrl: "http://127.0.0.1:8787",
	apiKey: "mock-key-001",
};
```

说明：
- `scene/api.private.js` 已在仓库根目录 `.gitignore` 中忽略，不会被 push。
- `scene/index.html` 会先加载 `api.private.js`，再加载 `main.js`。

## 项目结构

```
scene/
├── main.js
├── core/
│   └── bootstrap.js
├── agent/
│   ├── client.js
│   ├── store.js
│   ├── triage-dialogue.js
│   └── triage-form.js
├── queue/
│   └── runtime.js
├── npc/
│   ├── runtime.js
│   └── fixed-runtime.js
├── ui/
│   ├── task-board.js
│   └── medical-record.js
├── img/
│   ├── process-assets.py
│   └── process-assets.js
├── api.private.example.js
└── api.private.js
```

### 文件说明

- **main.js**: 浏览器入口，负责启动前端运行时
- **core/bootstrap.js**: 组合后端客户端、分诊、队列、NPC 和 UI 模块
- **agent/client.js**: 后端 API 封装
- **agent/store.js**: 对话和会话状态存储
- **queue/runtime.js**: 排队与叫号展示
- **npc/runtime.js**: 随机 NPC 的移动逻辑
- **npc/fixed-runtime.js**: 固定 NPC 对话和交互逻辑
- **ui/task-board.js**: 当前患者、会话、agent 状态看板
- **ui/medical-record.js**: 病历卡渲染
- **img/**: 素材处理脚本与生成的头像资源

## 下一步建议

1. 新增 UI 时优先放进 `agent/` 或 `ui/`，不要把逻辑继续堆回单文件。
2. 如果要接新的 agent，先补后端契约，再补前端展示。
3. 若要替换头像或素材，优先调整 `img/` 里的处理脚本和生成产物。
