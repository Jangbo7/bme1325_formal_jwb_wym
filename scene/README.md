# 医院伪 3D 沙盒原型

当前版本使用原生 `HTML + Canvas` 实现一个第三人称伪 3D 医院箱庭原型，目标是先把空间层次、房间体积感和后续系统扩展的基础搭起来。

## 已实现

- 多房间箱庭式医院布局
- 第三人称伪 3D 轴测渲染
- 主角移动（`WASD` / 方向键）
- 优化后的门洞墙体切分与房门碰撞
- 医院风格自动玻璃门（靠近自动开启，离开自动关闭）
- 简单碰撞体积（墙体、家具、关闭中的门）
- 跟随镜头
- 小地图与房间标签
- 偏霓虹紫调的医院箱庭美术氛围

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
hos_formal/
├── index.html          # 主HTML文件
├── main.js            # 主入口文件，负责初始化游戏
├── constants.js       # 游戏常量和配置
├── gameObjects.js     # 游戏对象定义（玩家、房间、门、道具）
├── utils.js           # 辅助函数
├── collision.js       # 碰撞检测相关函数
├── render.js          # 渲染相关函数
├── gameLogic.js       # 游戏逻辑相关函数
└── styles.css         # 样式文件
```

### 文件说明

- **constants.js**: 包含游戏的常量和配置，如瓦片大小、颜色 palette 等
- **gameObjects.js**: 定义游戏中的各种对象，如玩家、房间、门和道具
- **utils.js**: 提供各种辅助函数，如构建门、墙壁段等
- **collision.js**: 处理碰撞检测相关的逻辑
- **render.js**: 负责游戏的渲染，包括绘制房间、墙壁、门、道具和玩家等
- **gameLogic.js**: 包含游戏的核心逻辑，如更新门的状态、处理玩家移动等
- **main.js**: 主入口文件，负责初始化游戏和启动游戏循环

## 下一步建议

1. 加入护士站、收费、诊室等功能房间的可交互点
2. 加入 NPC、寻路和日程系统
3. 将房间数据抽成配置，转成真正的医院模拟底层
4. 添加更多的游戏功能，如任务系统、物品系统等
5. 优化性能，特别是在处理大量游戏对象时
