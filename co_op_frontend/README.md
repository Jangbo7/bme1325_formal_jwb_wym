# Hospital Co-op Frontend

这个目录现在是一个**从原始 `scene/` 场景前端拆出来的合作包**。

这次的目标不是重做一个轻量版，而是：

- 保留原先已经很好用的前端场景能力
  - 墙体实体阻挡
  - 原始草坪背景
  - HUD / board / main gate
  - 每个门按 `E` 切换箱庭
- 只尽量剥离或弱化强耦合后端 agent 的部分
- 给协作者补上可复用素材、配置入口和扩展位

## 现在保留了什么

这份合作包保留了原始场景前端的这些能力：

- `core/bootstrap.js`
  原始校园场景、碰撞、门、箱庭、HUD、board、main gate、NPC 绘制逻辑
- `npc/`
  原始固定 NPC、流动 NPC 和 runtime NPC 渲染结构
- `queue/`
  原始队列显示
- `ui/`
  原始任务板、NPC 对话等
- `img/`
  原始前端资源

也就是说，这不是一个“重画版”的前端，而是**原 scene 的可合作拆分版**。

## 新增了什么

### 1. 可复用素材

在 `assets/` 里新增了可供协作者直接复用的素材：

- `assets/sprites/patient-*.svg`
  不同颜色小人
- `assets/sprites/doctor-redcross.svg`
  白大褂红十字医生
- `assets/textures/grass-tile.svg`
  草坪贴图参考
- `assets/textures/wall-tile.svg`
  墙体贴图参考
- `assets/textures/desk.svg`
  桌子贴图参考
- `assets/textures/clinic-floor-checker.svg`
  白瓷砖 / 浅蓝色瓷砖交替地面

注意：
- 当前主场景背景仍然保留原来的草坪渲染逻辑
- 格子瓷砖主要用于室内箱庭地面

### 2. 扩展配置入口

- [config/scene.coop.js](/E:/shanghaitech/hospital_new/co_op_frontend/config/scene.coop.js)
  用于不改核心文件时补一些扩展配置
- [config/agents.config.js](/E:/shanghaitech/hospital_new/co_op_frontend/config/agents.config.js)
  作为 agent API 范式参考
- [config/rooms.config.js](/E:/shanghaitech/hospital_new/co_op_frontend/config/rooms.config.js)
  作为房间扩展示例参考
- [extensions/agents/example-custom-agent.js](/E:/shanghaitech/hospital_new/co_op_frontend/extensions/agents/example-custom-agent.js)
  自定义 agent 示例

### 3. 启动脚本

- [run_frontend.bat](/E:/shanghaitech/hospital_new/co_op_frontend/run_frontend.bat)
- [run_frontend.ps1](/E:/shanghaitech/hospital_new/co_op_frontend/run_frontend.ps1)

## 怎么运行

### 最简单

双击：

- [run_frontend.bat](/E:/shanghaitech/hospital_new/co_op_frontend/run_frontend.bat)

或者 PowerShell：

- [run_frontend.ps1](/E:/shanghaitech/hospital_new/co_op_frontend/run_frontend.ps1)

### 手动运行

```powershell
cd co_op_frontend
python -m http.server 8000
```

然后打开：

[http://127.0.0.1:8000](http://127.0.0.1:8000)

## API 怎么接

默认配置文件：

[api.private.js](/E:/shanghaitech/hospital_new/co_op_frontend/api.private.js)

内容默认是：

```js
window.HOS_PRIVATE_API = {
  baseUrl: "http://127.0.0.1:8787",
  apiKey: "mock-key-001",
};
```

如果后端端口不一样，只要改这里。

说明：

- 顶部 `Stats HTML` 按钮会跳到后端提供的独立统计页
- 前端本身不生成那一页
- 所以**只有后端也在运行时**，这个入口才会真正显示统计内容

如果你不想直接改默认文件，也可以参考：

[api.private.example.js](/E:/shanghaitech/hospital_new/co_op_frontend/api.private.example.js)

## 给协作者的推荐改法

### 尽量只改这些

- `api.private.js`
- `config/scene.coop.js`
- `extensions/agents/*.js`
- 新增素材文件

### 尽量不要先改这些

- `core/bootstrap.js`
- `npc/runtime.js`
- `queue/runtime.js`
- `styles.css`

## 房间和 label

当前这版里已经整理过的标签包括：

- `Consultation Room`
- `Doctor Entry Hall`
- `Pharmacy Pickup`
- `Laboratory`
- `ICU Room`
- `Admin Office`
- `Main Hall`
- `Specialty Clinic`

并且保留了：

- `main gate`
- 任务板 / debug 板 / 其他患者面板
- 原场景的墙体碰撞
- 原草坪背景

## 箱庭说明

当前每个门进入后，都已经会切到一个箱庭场景。

现在先统一复用已有的过渡室内模板，方便协作者后续替换：

- 到时候他们只要保留房间 kind / 交互点
- 再把内部模板替换成自己的精细场景

就不需要重写整套门切换逻辑

## Agent 范式

虽然当前运行主链仍然保留原场景的既有调用方式，但合作包里已经放了一个**推荐 agent API 范式**，供后续协作者照着接新医生：

- [config/agents.config.js](/E:/shanghaitech/hospital_new/co_op_frontend/config/agents.config.js)
- [extensions/agents/example-custom-agent.js](/E:/shanghaitech/hospital_new/co_op_frontend/extensions/agents/example-custom-agent.js)

推荐模式是：

1. `createSession`
2. `sendMessage`
3. `parseCreatedSession`
4. `parseReply`

这样后面接不同的 doctor agent / specialty agent 时，结构会统一。

## 这份包目前最适合的用途

适合：

- 给前端协作者直接拿去跑
- 在不破坏原 scene 交互感的前提下继续接新房间 / 新 agent
- 当成“原场景前端 SDK 基底”

暂时不建议把它当：

- 完全脱离原 scene 的极简演示版
- 完整独立业务重构版

因为这版的重点是**保留原先成熟的前端体验**。
