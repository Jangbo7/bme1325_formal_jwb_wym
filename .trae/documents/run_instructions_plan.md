# 运行前后端方式说明

## 运行方式保持不变

根据项目的 README.md 文件，运行前后端的方式与之前完全一致，没有任何变化。

### 后端启动步骤

1. 进入 backend 目录
2. 安装依赖：`python -m pip install -r requirements.txt`
3. 运行服务器：`python server.py`
4. 默认 URL: `http://127.0.0.1:8787`

### 前端启动步骤

1. 进入 scene 目录
2. 启动 HTTP 服务器：`python -m http.server 5500`
3. 访问 URL: `http://127.0.0.1:5500`

## 修改的内容

本次修改主要涉及以下方面，这些修改不会影响项目的启动方式：

1. **前端**：
   - 在 localStorage 中生成唯一的 client_id
   - 使用 `P-${client_id}` 作为 patient_id
   - 移除 session-main 硬编码

2. **后端**：
   - 移除 session-main 兜底，改为生成 UUID
   - 添加环境变量配置：
     - `RESET_ON_SERVER_START=false`
     - `SIMULATOR_ENABLED=false`

## 注意事项

如果需要在不同机器上访问同一后端，还需要：
1. 确保后端监听 `0.0.0.0`
2. 将前端的 `baseUrl` 改为后端机器的局域网 IP

## 验证方法

启动前后端后，可以通过以下方式验证修改是否生效：
1. 打开两个浏览器窗口，检查 localStorage 中的 client_id 是否不同
2. 检查网络请求中的 patient_id 是否为 `P-` 开头的唯一标识符
3. 检查后端日志中的 session_id 是否为 UUID 格式