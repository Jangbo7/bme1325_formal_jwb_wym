# scene_stardew 使用说明

## 1. 运行后端
在仓库根目录执行：

```powershell
cd backend
python server.py
```

如果提示端口被占用（`[WinError 10048]`），说明 8787 已有后端在跑，不用重复启动。

## 2. 运行前端（stardew 场景）
在仓库根目录执行：

```powershell
cd scene_stardew
python -m http.server 5500
```

浏览器打开：
- `http://127.0.0.1:5500`

## 3. 连接后端配置
当前默认连接：
- `http://127.0.0.1:8787/api/v1`
- API Key: `mock-key-001`

如需覆盖默认值，可在页面加载前注入：

```html
<script>
  window.HOS_STARDEW_API = {
    baseUrl: "http://127.0.0.1:8787/api/v1",
    apiKey: "mock-key-001",
  };
</script>
<script type="module" src="./game.js"></script>
```

## 4. 操作方式
- 移动：`WASD` / 方向键
- 与 NPC 对话：靠近后按 `E`
- 离开房间出口：按 `Q`
- 关闭对话：`Esc`
- 右上角可点击“API设置”更新 API Key

## 5. 常见问题
- 画面能玩但提示离线：
  - 检查后端是否在 `127.0.0.1:8787`
  - 检查浏览器控制台是否有 `API错误: 401/404`
- `python -m http.server 5500` 启动失败：
  - 5500 端口被占用，改成 5501 后访问 `http://127.0.0.1:5501`
- `python server.py` 启动失败：
  - 多数是 8787 被占用；如果后端日志已有请求 200，就直接使用即可
